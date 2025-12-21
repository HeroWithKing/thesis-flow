# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import os
import re
from functools import partial
from typing import Annotated, Literal

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.types import Command, interrupt

from src.agents import create_agent
from src.config.agents import AGENT_LLM_MAP
from src.config.configuration import Configuration
from src.llms.llm import get_llm_by_type, get_llm_token_limit_by_type
from src.prompts.planner_model import Plan
from src.prompts.template import apply_prompt_template
from src.tools import (
    crawl_tool,
    get_retriever_tool,
    get_web_search_tool,
    python_repl_tool,
)
from src.tools.academic_analysis import (
    paper_metadata_extraction,
    citation_analysis,
    technical_breakdown,
    innovation_graph,
    paper_anonymize,
)
from src.utils.context_manager import ContextManager, validate_message_content
from src.utils.json_utils import repair_json_output, sanitize_tool_response

from .types import State
from .utils import (
    build_clarified_topic_from_history,
    get_message_content,
    is_user_message,
    reconstruct_clarification_history,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Citation Processing Utilities
# ============================================================================
class CitationProcessor:
    """Handle citation extraction and renumbering with robust error handling."""
    
    # Patterns for citation processing
    CITATIONS_SECTION_PATTERN = r'(## Key Citations\s*\n(?:- \[\d+\].*?\(.*?\)\s*\n?)+)'
    CITATION_PATTERN = r'- \[(\d+)\]\s*(.*?)\((.*?)\)'
    INLINE_CITATION_PATTERN = r'(?<!\w)\[(\d+)\](?!\w)'
    
    @staticmethod
    def extract_citations_section(content: str) -> tuple[str, int, str]:
        """Extract citations section from content.
        
        Returns:
            (main_content, section_start_index, citations_section)
        """
        lines = content.split('\n')
        section_start = -1
        
        for i, line in enumerate(lines):
            if 'Key Citations' in line or 'References' in line or '## Citations' in line:
                section_start = i
                break
        
        if section_start == -1:
            return content, -1, ""
        
        return '\n'.join(lines[:section_start]), section_start, '\n'.join(lines[section_start:])
    
    @staticmethod
    def parse_citations(citations_section: str) -> list[tuple[int, str, str]]:
        """Parse citations from citations section.
        
        Returns:
            List of (id, title, url) tuples
        """
        if not citations_section:
            return []
        
        try:
            pattern = CitationProcessor.CITATION_PATTERN
            matches = re.findall(pattern, citations_section, re.DOTALL)
            return [(int(cid), title.strip(), url.strip()) for cid, title, url in matches]
        except Exception as e:
            logger.error(f"Failed to parse citations: {e}")
            return []
    
    @staticmethod
    def renumber_citations(content: str, citations: list[dict]) -> str:
        """Renumber citations in content from old IDs to new sequential IDs.
        
        Args:
            content: Content with citations
            citations: List of citation dicts with 'id', 'title', 'url'
        
        Returns:
            Content with renumbered citations
        """
        if not citations:
            return content
        
        # Create mapping from old to new IDs
        id_mapping = {old_cit['id']: idx + 1 for idx, old_cit in enumerate(citations)}
        
        # Replace citation numbers
        updated_content = content
        for old_id, new_id in sorted(id_mapping.items(), reverse=True):
            try:
                # Replace inline citations [old_id] with [new_id]
                pattern = r'(?<!\w)\[' + re.escape(str(old_id)) + r'\](?!\w)'
                updated_content = re.sub(pattern, f'[{new_id}]', updated_content)
            except Exception as e:
                logger.error(f"Failed to renumber citation {old_id}: {e}")
        
        return updated_content
    
    @staticmethod
    def extract_citations_from_text(content: str) -> list[dict]:
        """Extract citations from text with inline format.
        
        Returns:
            List of citation dicts extracted from references section
        """
        main_content, section_start, citations_section = CitationProcessor.extract_citations_section(content)
        
        if section_start == -1:
            return []
        
        parsed = CitationProcessor.parse_citations(citations_section)
        return [
            {'id': cid, 'title': title, 'url': url}
            for cid, title, url in parsed
        ]


@tool
def handoff_to_planner(
    research_topic: Annotated[str, "The topic of the research task to be handed off."],
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
):
    """Handoff to planner agent to do plan."""
    # This tool is not returning anything: we're just using it
    # as a way for LLM to signal that it needs to hand off to planner agent
    return


@tool
def handoff_after_clarification(
    locale: Annotated[str, "The user's detected language locale (e.g., en-US, zh-CN)."],
    research_topic: Annotated[
        str, "The clarified research topic based on all clarification rounds."
    ],
):
    """Handoff to planner after clarification rounds are complete. Pass all clarification history to planner for analysis."""
    return


def needs_clarification(state: dict) -> bool:
    """
    Check if clarification is needed based on current state.
    Centralized logic for determining when to continue clarification.
    """
    if not state.get("enable_clarification", False):
        return False

    clarification_rounds = state.get("clarification_rounds", 0)
    is_clarification_complete = state.get("is_clarification_complete", False)
    max_clarification_rounds = state.get("max_clarification_rounds", 3)

    # Need clarification if: enabled + has rounds + not complete + not exceeded max
    # Use <= because after asking the Nth question, we still need to wait for the Nth answer
    return (
        clarification_rounds > 0
        and not is_clarification_complete
        and clarification_rounds <= max_clarification_rounds
    )


def preserve_state_meta_fields(state: State) -> dict:
    """
    Extract meta/config fields that should be preserved across state transitions.
    
    These fields are critical for workflow continuity and should be explicitly
    included in all Command.update dicts to prevent them from reverting to defaults.
    
    Args:
        state: Current state object
        
    Returns:
        Dict of meta fields to preserve
    """
    return {
        "locale": state.get("locale", "en-US"),
        "research_topic": state.get("research_topic", ""),
        "clarified_research_topic": state.get("clarified_research_topic", ""),
        "clarification_history": state.get("clarification_history", []),
        "enable_clarification": state.get("enable_clarification", False),
        "max_clarification_rounds": state.get("max_clarification_rounds", 3),
        "clarification_rounds": state.get("clarification_rounds", 0),
        "resources": state.get("resources", []),
    }


def validate_and_fix_plan(plan: dict, enforce_web_search: bool = False) -> dict:
    """
    Validate and fix a plan to ensure it meets requirements.

    Args:
        plan: The plan dict to validate
        enforce_web_search: If True, ensure at least one step has need_search=true

    Returns:
        The validated/fixed plan dict
    """
    if not isinstance(plan, dict):
        return plan

    steps = plan.get("steps", [])

    # ============================================================
    # SECTION 1: Repair missing step_type fields (Issue #650 fix)
    # ============================================================
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        
        # Check if step_type is missing or empty
        if "step_type" not in step or not step.get("step_type"):
            # Infer step_type based on need_search value
            inferred_type = "research" if step.get("need_search", False) else "processing"
            step["step_type"] = inferred_type
            logger.info(
                f"Repaired missing step_type for step {idx} ({step.get('title', 'Untitled')}): "
                f"inferred as '{inferred_type}' based on need_search={step.get('need_search', False)}"
            )

    # ============================================================
    # SECTION 2: Enforce web search requirements
    # ============================================================
    if enforce_web_search:
        # Check if any step has need_search=true
        has_search_step = any(step.get("need_search", False) for step in steps)

        if not has_search_step and steps:
            # Ensure first research step has web search enabled
            for idx, step in enumerate(steps):
                if step.get("step_type") == "research":
                    step["need_search"] = True
                    logger.info(f"Enforced web search on research step at index {idx}")
                    break
            else:
                # Fallback: If no research step exists, convert the first step to a research step with web search enabled.
                # This ensures that at least one step will perform a web search as required.
                steps[0]["step_type"] = "research"
                steps[0]["need_search"] = True
                logger.info(
                    "Converted first step to research with web search enforcement"
                )
        elif not has_search_step and not steps:
            # Add a default research step if no steps exist
            logger.warning("Plan has no steps. Adding default research step.")
            plan["steps"] = [
                {
                    "need_search": True,
                    "title": "Initial Research",
                    "description": "Gather information about the topic",
                    "step_type": "research",
                }
            ]

    return plan


def background_investigation_node(state: State, config: RunnableConfig):
    logger.info("background investigation node is running.")
    configurable = Configuration.from_runnable_config(config)
    query = state.get("clarified_research_topic") or state.get("research_topic")
    background_investigation_results = []
    
    # Use ArXiv search tool (only search engine)
    searched_content = get_web_search_tool(
        configurable.max_search_results
    ).invoke(query)
    
    # Handle response from ArXiv search
    if isinstance(searched_content, str):
        background_investigation_results = searched_content
    elif isinstance(searched_content, list):
        background_investigation_results = "\n\n".join(
            [f"## {item.get('title', 'Untitled')}\n\n{item.get('content', 'No content')}" 
             if isinstance(item, dict) else str(item) for item in searched_content]
        )
    else:
        background_investigation_results = str(searched_content)
    
    # Ensure consistent return format
    if isinstance(background_investigation_results, str):
        return {
            "background_investigation_results": background_investigation_results
        }
    else:
        return {
            "background_investigation_results": json.dumps(
                background_investigation_results, ensure_ascii=False
            )
        }


def planner_node(
    state: State, config: RunnableConfig
) -> Command[Literal["human_feedback", "reporter"]]:
    """Planner node that generate the full plan."""
    logger.info("Planner generating full plan with locale: %s", state.get("locale", "en-US"))
    configurable = Configuration.from_runnable_config(config)
    plan_iterations = state.get("plan_iterations", 0) or 0

    # For clarification feature: use the clarified research topic (complete history)
    if state.get("enable_clarification", False) and state.get(
        "clarified_research_topic"
    ):
        # Modify state to use clarified research topic instead of full conversation
        modified_state = state.copy()
        clarified_topic = state.get("clarified_research_topic", "")
        modified_state["messages"] = [
            {"role": "user", "content": clarified_topic}
        ]
        modified_state["research_topic"] = clarified_topic
        messages = apply_prompt_template("planner", modified_state, configurable, state.get("locale", "en-US"))

        logger.info(
            f"Clarification mode: Using clarified research topic: {clarified_topic}"
        )
    else:
        # Normal mode: use full conversation history
        messages = apply_prompt_template("planner", state, configurable, state.get("locale", "en-US"))

    if state.get("enable_background_investigation") and state.get(
        "background_investigation_results"
    ):
        background_results = state.get("background_investigation_results", "")
        messages += [
            {
                "role": "user",
                "content": (
                    "background investigation results of user query:\n"
                    + background_results
                    + "\n"
                ),
            }
        ]

    if configurable.enable_deep_thinking:
        llm = get_llm_by_type("reasoning")
    elif AGENT_LLM_MAP["planner"] == "basic":
        llm = get_llm_by_type("basic").with_structured_output(
            Plan,
            method="json_mode",
        )
    else:
        llm = get_llm_by_type(AGENT_LLM_MAP["planner"])

    # if the plan iterations is greater than the max plan iterations, return the reporter node
    if plan_iterations >= configurable.max_plan_iterations:
        return Command(
            update=preserve_state_meta_fields(state),
            goto="reporter"
        )

    full_response = ""
    if AGENT_LLM_MAP["planner"] == "basic" and not configurable.enable_deep_thinking:
        response = llm.invoke(messages)
        full_response = response.model_dump_json(indent=4, exclude_none=True)
    else:
        response = llm.stream(messages)
        for chunk in response:
            full_response += chunk.content
    logger.debug(f"Current state messages: {state['messages']}")
    logger.info(f"Planner response: {full_response}")

    try:
        curr_plan = json.loads(repair_json_output(full_response))
    except json.JSONDecodeError:
        logger.warning("Planner response is not a valid JSON")
        if plan_iterations > 0:
            return Command(
                update=preserve_state_meta_fields(state),
                goto="reporter"
            )
        else:
            return Command(
                update=preserve_state_meta_fields(state),
                goto="__end__"
            )

    # Validate and fix plan to ensure web search requirements are met
    if isinstance(curr_plan, dict):
        curr_plan = validate_and_fix_plan(curr_plan, configurable.enforce_web_search)

    if isinstance(curr_plan, dict) and curr_plan.get("has_enough_context"):
        logger.info("Planner response has enough context.")
        new_plan = Plan.model_validate(curr_plan)
        return Command(
            update={
                "messages": [AIMessage(content=full_response, name="planner")],
                "current_plan": new_plan,
                **preserve_state_meta_fields(state),
            },
            goto="reporter",
        )
    return Command(
        update={
            "messages": [AIMessage(content=full_response, name="planner")],
            "current_plan": full_response,
            **preserve_state_meta_fields(state),
        },
        goto="human_feedback",
    )


def human_feedback_node(
    state: State, config: RunnableConfig
) -> Command[Literal["planner", "research_team", "reporter", "__end__"]]:
    current_plan = state.get("current_plan", "")
    # check if the plan is auto accepted
    auto_accepted_plan = state.get("auto_accepted_plan", False)
    if not auto_accepted_plan:
        feedback = interrupt("Please Review the Plan.")

        # Handle None or empty feedback
        if not feedback:
            logger.warning(f"Received empty or None feedback: {feedback}. Returning to planner for new plan.")
            return Command(
                update=preserve_state_meta_fields(state),
                goto="planner"
            )

        # Normalize feedback string
        feedback_normalized = str(feedback).strip().upper()

        # if the feedback is not accepted, return the planner node
        if feedback_normalized.startswith("[EDIT_PLAN]"):
            logger.info(f"Plan edit requested by user: {feedback}")
            return Command(
                update={
                    "messages": [
                        HumanMessage(content=feedback, name="feedback"),
                    ],
                    **preserve_state_meta_fields(state),
                },
                goto="planner",
            )
        elif feedback_normalized.startswith("[ACCEPTED]"):
            logger.info("Plan is accepted by user.")
        else:
            logger.warning(f"Unsupported feedback format: {feedback}. Please use '[ACCEPTED]' to accept or '[EDIT_PLAN]' to edit.")
            return Command(
                update=preserve_state_meta_fields(state),
                goto="planner"
            )

    # if the plan is accepted, run the following node
    plan_iterations = state.get("plan_iterations", 0) or 0
    goto = "research_team"
    try:
        current_plan = repair_json_output(current_plan)
        # increment the plan iterations
        plan_iterations += 1
        # parse the plan
        new_plan = json.loads(current_plan)
        # Validate and fix plan to ensure web search requirements are met
        configurable = Configuration.from_runnable_config(config)
        new_plan = validate_and_fix_plan(new_plan, configurable.enforce_web_search)
    except json.JSONDecodeError:
        logger.warning("Planner response is not a valid JSON")
        if plan_iterations > 1:  # the plan_iterations is increased before this check
            return Command(
                update=preserve_state_meta_fields(state),
                goto="reporter"
            )
        else:
            return Command(
                update=preserve_state_meta_fields(state),
                goto="__end__"
            )

    # Build update dict with safe locale handling
    update_dict = {
        "current_plan": Plan.model_validate(new_plan),
        "plan_iterations": plan_iterations,
        **preserve_state_meta_fields(state),
    }
    
    # Only override locale if new_plan provides a valid value, otherwise use preserved locale
    if new_plan.get("locale"):
        update_dict["locale"] = new_plan["locale"]
    
    return Command(
        update=update_dict,
        goto=goto,
    )


def _process_clarification_mode(
    state: State, config: RunnableConfig, response, max_clarification_rounds: int
) -> tuple[str, str, str, int, list, str]:
    """
    Process clarification mode branch for coordinator node.
    
    Handles:
    - Preparing clarification context
    - Managing conversation history
    - Determining when to continue vs. handoff
    - Keeping indentation depth minimal
    
    Returns: 
        (goto, locale, research_topic, clarification_rounds, clarification_history, clarified_topic)
        where goto can be: "coordinator" (continue), "planner" (handoff), or "__end__" (error)
    """
    configurable = Configuration.from_runnable_config(config)
    clarification_rounds = state.get("clarification_rounds", 0)
    clarification_history = list(state.get("clarification_history", []) or [])
    clarification_history = [item for item in clarification_history if item]
    
    state_messages = list(state.get("messages", []))
    initial_topic = state.get("research_topic", "")
    
    # Rebuild clarification history from message thread
    clarification_history = reconstruct_clarification_history(
        state_messages, clarification_history, initial_topic
    )
    clarified_topic, clarification_history = build_clarified_topic_from_history(
        clarification_history
    )
    
    if clarification_history:
        initial_topic = clarification_history[0]
        latest_user_content = clarification_history[-1]
    else:
        latest_user_content = ""
    
    # Initialize return values
    goto = "__end__"
    locale = state.get("locale", "en-US")
    research_topic = (
        clarification_history[0]
        if clarification_history
        else state.get("research_topic", "")
    )
    if not clarified_topic:
        clarified_topic = research_topic
    
    # Handle response without tool calls - LLM is asking a clarifying question
    if not response.tool_calls and response.content:
        # Check if max rounds reached
        if clarification_rounds >= max_clarification_rounds:
            logger.warning(
                f"Max clarification rounds ({max_clarification_rounds}) reached. "
                "LLM continued asking instead of calling handoff tool. Forcing handoff to planner."
            )
            goto = "planner"
        else:
            # LLM asked a clarifying question - need to continue clarification
            clarification_rounds += 1
            logger.info(
                f"Clarification response: {clarification_rounds}/{max_clarification_rounds}: {response.content}"
            )
            # Signal to coordinator_node that we need to interrupt and wait for user response
            goto = "coordinator"
    
    return goto, locale, research_topic, clarification_rounds, clarification_history, clarified_topic


def coordinator_node(
    state: State, config: RunnableConfig
) -> Command[Literal["planner", "background_investigator", "coordinator", "__end__"]]:
    """Coordinator node that communicate with customers and handle clarification."""
    logger.info("Coordinator talking.")
    configurable = Configuration.from_runnable_config(config)

    # Check if clarification is enabled
    enable_clarification = state.get("enable_clarification", False)
    initial_topic = state.get("research_topic", "")
    clarified_topic = initial_topic
    # ============================================================
    # BRANCH 1: Clarification DISABLED (Legacy Mode)
    # ============================================================
    if not enable_clarification:
        # Use normal prompt with explicit instruction to skip clarification
        messages = apply_prompt_template("coordinator", state, locale=state.get("locale", "en-US"))
        messages.append(
            {
                "role": "system",
                "content": "CRITICAL: Clarification is DISABLED. You MUST immediately call handoff_to_planner tool with the user's query as-is. Do NOT ask questions or mention needing more information.",
            }
        )

        # Only bind handoff_to_planner tool
        tools = [handoff_to_planner]
        response = (
            get_llm_by_type(AGENT_LLM_MAP["coordinator"])
            .bind_tools(tools)
            .invoke(messages)
        )

        goto = "__end__"
        locale = state.get("locale", "en-US")
        logger.info(f"Coordinator locale: {locale}")
        research_topic = state.get("research_topic", "")

        # Process tool calls for legacy mode
        if response.tool_calls:
            try:
                for tool_call in response.tool_calls:
                    tool_name = tool_call.get("name", "")
                    tool_args = tool_call.get("args", {})

                    if tool_name == "handoff_to_planner":
                        logger.info("Handing off to planner")
                        goto = "planner"

                        # Extract research_topic if provided
                        if tool_args.get("research_topic"):
                            research_topic = tool_args.get("research_topic")
                        break

            except Exception as e:
                logger.error(f"Error processing tool calls: {e}")
                goto = "planner"

    # ============================================================
    # BRANCH 2: Clarification ENABLED (New Feature) - Delegated to helper
    # ============================================================
    else:
        # Load clarification state
        clarification_rounds = state.get("clarification_rounds", 0)
        clarification_history = list(state.get("clarification_history", []) or [])
        max_clarification_rounds = state.get("max_clarification_rounds", 3)
        
        # Prepare the messages for the coordinator
        state_messages = list(state.get("messages", []))
        messages = apply_prompt_template("coordinator", state, locale=state.get("locale", "en-US"))

        # Rebuild clarification history from message thread
        clarification_history = reconstruct_clarification_history(
            state_messages, clarification_history, initial_topic
        )
        clarified_topic, clarification_history = build_clarified_topic_from_history(
            clarification_history
        )
        logger.debug("Clarification history rebuilt: %s", clarification_history)

        if clarification_history:
            initial_topic = clarification_history[0]
            latest_user_content = clarification_history[-1]
        else:
            latest_user_content = ""

        # Add clarification status for first round
        if clarification_rounds == 0:
            messages.append(
                {
                    "role": "system",
                    "content": "Clarification mode is ENABLED. Follow the 'Clarification Process' guidelines in your instructions.",
                }
            )

        current_response = latest_user_content or "No response"
        logger.info(
            "Clarification round %s/%s | topic: %s | current user response: %s",
            clarification_rounds,
            max_clarification_rounds,
            clarified_topic or initial_topic,
            current_response,
        )

        clarification_context = f"""Continuing clarification (round {clarification_rounds}/{max_clarification_rounds}):
            User's latest response: {current_response}
            Ask for remaining missing dimensions. Do NOT repeat questions or start new topics."""

        messages.append({"role": "system", "content": clarification_context})

        # Bind both clarification tools - let LLM choose the appropriate one
        tools = [handoff_to_planner, handoff_after_clarification]

        # Check if we've already reached max rounds
        if clarification_rounds >= max_clarification_rounds:
            # Max rounds reached - force handoff by adding system instruction
            logger.warning(
                f"Max clarification rounds ({max_clarification_rounds}) reached. Forcing handoff to planner."
            )
            # Add system instruction to force handoff
            messages.append(
                {
                    "role": "system",
                    "content": f"MAX ROUNDS REACHED. You MUST call handoff_after_clarification with the research_topic and locale. Do not ask any more questions.",
                }
            )

        response = (
            get_llm_by_type(AGENT_LLM_MAP["coordinator"])
            .bind_tools(tools)
            .invoke(messages)
        )
        logger.debug(f"Current state messages: {state['messages']}")

        # Initialize response processing variables
        goto = "__end__"
        locale = state.get("locale", "en-US")
        research_topic = initial_topic or state.get("research_topic", "")
        clarified_topic = clarified_topic or research_topic

        # Use helper function to process clarification response and reduce nesting
        goto, locale, research_topic, clarification_rounds, clarification_history, clarified_topic = (
            _process_clarification_mode(state, config, response, max_clarification_rounds)
        )
        
        # Check if we should return early (clarification continues)
        if goto == "coordinator" and response.content:
            messages = list(state.get("messages", []) or [])
            updated_messages = list(messages)
            updated_messages.append(
                HumanMessage(content=response.content, name="coordinator")
            )

            return Command(
                update={
                    "messages": updated_messages,
                    "locale": locale,
                    "research_topic": research_topic,
                    "resources": configurable.resources,
                    "clarification_rounds": clarification_rounds,
                    "clarification_history": clarification_history,
                    "clarified_research_topic": clarified_topic,
                    "is_clarification_complete": False,
                    "goto": goto,
                    "__interrupt__": [("coordinator", response.content)],
                },
                goto=goto,
            )

    # ============================================================
    # Final: Build and return Command
    # ============================================================
    messages = list(state.get("messages", []) or [])
    if response.content:
        messages.append(HumanMessage(content=response.content, name="coordinator"))

    # Process tool calls for BOTH branches (legacy and clarification)
    if response.tool_calls:
        try:
            for tool_call in response.tool_calls:
                tool_name = tool_call.get("name", "")
                tool_args = tool_call.get("args", {})

                if tool_name in ["handoff_to_planner", "handoff_after_clarification"]:
                    logger.info("Handing off to planner")
                    goto = "planner"

                    if not enable_clarification and tool_args.get("research_topic"):
                        research_topic = tool_args["research_topic"]

                    if enable_clarification:
                        logger.info(
                            "Using prepared clarified topic: %s",
                            clarified_topic or research_topic,
                        )
                    else:
                        logger.info(
                            "Using research topic for handoff: %s", research_topic
                        )
                    break

        except Exception as e:
            logger.error(f"Error processing tool calls: {e}")
            goto = "planner"
    else:
        # No tool calls detected - fallback to planner instead of ending
        logger.warning(
            "LLM didn't call any tools. This may indicate tool calling issues with the model. "
            "Falling back to planner to ensure research proceeds."
        )
        # Log full response for debugging
        logger.debug(f"Coordinator response content: {response.content}")
        logger.debug(f"Coordinator response object: {response}")
        # Fallback to planner to ensure workflow continues
        goto = "planner"

    # Apply background_investigation routing if enabled (unified logic)
    if goto == "planner" and state.get("enable_background_investigation"):
        goto = "background_investigator"

    # Set default values for state variables (in case they're not defined in legacy mode)
    if not enable_clarification:
        clarification_rounds = 0
        clarification_history = []

    clarified_research_topic_value = clarified_topic or research_topic

    # clarified_research_topic: Complete clarified topic with all clarification rounds
    return Command(
        update={
            "messages": messages,
            "locale": locale,
            "research_topic": research_topic,
            "clarified_research_topic": clarified_research_topic_value,
            "resources": configurable.resources,
            "clarification_rounds": clarification_rounds,
            "clarification_history": clarification_history,
            "is_clarification_complete": goto != "coordinator",
            "goto": goto,
        },
        goto=goto,
    )


def reporter_node(state: State, config: RunnableConfig):
    """Reporter node that write a final report."""
    logger.info("Reporter write final report")
    configurable = Configuration.from_runnable_config(config)
    current_plan = state.get("current_plan")
    
    # Handle missing or invalid plan
    if not current_plan:
        logger.warning("No current plan found in state. Cannot generate report.")
        return {"final_report": "Error: No plan provided for report generation.", "citations": []}
    
    plan_title = getattr(current_plan, 'title', 'Unknown Task')
    plan_thought = getattr(current_plan, 'thought', 'No description available')
    
    input_ = {
        "messages": [
            HumanMessage(
                f"# Research Requirements\n\n## Task\n\n{plan_title}\n\n## Description\n\n{plan_thought}"
            )
        ],
        "locale": state.get("locale", "en-US"),
    }
    invoke_messages = apply_prompt_template("reporter", input_, configurable, input_.get("locale", "en-US"))
    observations = state.get("observations", [])

    # Get the citations from state to include in the prompt
    citations = state.get("citations", [])
    
    # Ensure citations are numbered sequentially before passing to reporter
    # Sort citations by their current ID to maintain order (with safe key access)
    citations.sort(key=lambda x: x.get('id', 0) if isinstance(x, dict) else 0)
    
    # Renumber citations sequentially starting from 1
    renumbered_citations = []
    for idx, citation in enumerate(citations):
        if isinstance(citation, dict):
            renumbered_citation = {
                'id': idx + 1,
                'title': citation.get('title', ''),
                'url': citation.get('url', '')
            }
            renumbered_citations.append(renumbered_citation)
    
    # Update the citations in state with renumbered ones
    citations = renumbered_citations
    
    # Format citations for the message
    formatted_citations = []
    for citation in citations:
        if isinstance(citation, dict):
            cid = citation.get('id', '?')
            title = citation.get('title', '')
            url = citation.get('url', '')
            formatted_citations.append(f"- [{cid}] {title} ({url})")
    
    citations_text = "\n".join(formatted_citations)
    if citations_text:
        citations_text = f"\n\nAvailable Citations:\n{citations_text}\n\n"

    # Add a reminder about the new report format, citation style, and table usage
    invoke_messages.append(
        HumanMessage(
            content=f"IMPORTANT: Structure your report according to the format in the prompt. Remember to include:\n\n1. Key Points - A bulleted list of the most important findings\n2. Overview - A brief introduction to the topic\n3. Detailed Analysis - Organized into logical sections\n4. Survey Note (optional) - For more comprehensive reports\n5. Key Citations - List all references at the end{citations_text}\nFor citations, you must use inline citations in the text where appropriate using numbered brackets (e.g., [1], [2], [3], [4], etc.) that correspond exactly to the references listed in the 'Key Citations' section. Each numbered citation in the text must have a matching entry in the reference list, and vice versa. You MUST incorporate every available citation into the appropriate sections of your report content, ensuring that no citations are left unused. Use the format: `- [1] Source Title (URL)` in the Key Citations section. Include an empty line between each citation for better readability.\n\nPRIORITIZE USING MARKDOWN TABLES for data presentation and comparison. Use tables whenever presenting comparative data, statistics, features, or options. Structure tables with clear headers and aligned columns. Example table format:\n\n| Feature | Description | Pros | Cons |\n|---------|-------------|------|------|\n| Feature 1 | Description 1 | Pros 1 | Cons 1 |\n| Feature 2 | Description 2 | Pros 2 | Cons 2 |",
            name="system",
        )
    )

    observation_messages = []
    for observation in observations:
        observation_messages.append(
            HumanMessage(
                content=f"Below are some observations for the research task:\n\n{observation}",
                name="observation",
            )
        )

    # Context compression
    llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP["reporter"])
    compressed_state = ContextManager(llm_token_limit).compress_messages(
        {"messages": observation_messages}
    )
    invoke_messages += compressed_state.get("messages", [])

    logger.debug(f"Current invoke messages: {invoke_messages}")
    response = get_llm_by_type(AGENT_LLM_MAP["reporter"]).invoke(invoke_messages)
    response_content = response.content
    logger.info(f"reporter response: {response_content}")

    # Process the response to ensure citation numbers in the text match the final citation list
    # Use CitationProcessor utility class for safe regex handling
    updated_response_content = response_content
    
    try:
        # Extract citations section using utility class - returns (main_content, section_start, citations_section)
        main_content, section_start, citations_section = CitationProcessor.extract_citations_section(response_content)
        
        if section_start >= 0 and citations_section:  # Check if citations section was found
            # Parse citations from the extracted section - returns list of (id, title, url) tuples
            found_citations_tuples = CitationProcessor.parse_citations(citations_section)
            
            if found_citations_tuples:
                # Convert tuples to dicts for renumber_citations function
                found_citations_dicts = [
                    {'id': int(cid), 'title': title, 'url': url}
                    for cid, title, url in found_citations_tuples
                ]
                # Renumber citations and update response content
                updated_response_content = CitationProcessor.renumber_citations(
                    response_content, 
                    found_citations_dicts
                )
                logger.debug(f"Successfully processed {len(found_citations_dicts)} citations")
    except Exception as e:
        logger.warning(f"Error processing citations in reporter_node: {e}. Using original response.")
        updated_response_content = response_content
    
    # Update the state with the final report and renumbered citations
    return {"final_report": updated_response_content, "citations": citations}


def research_team_node(state: State) -> State:
    """Research team node that acts as a coordinator/router for research and coder agents."""
    logger.info("Research team is collaborating on tasks.")
    logger.debug("Entering research_team_node - coordinating research and coder agents")
    # This node just passes through the state - actual routing is handled by conditional edges
    return state


async def _execute_agent_step(
    state: State, agent, agent_name: str
) -> Command[Literal["research_team"]]:
    """Helper function to execute a step using the specified agent."""
    logger.debug(f"[_execute_agent_step] Starting execution for agent: {agent_name}")
    
    current_plan = state.get("current_plan")
    if not current_plan:
        logger.error(f"[_execute_agent_step] No current plan found for agent: {agent_name}")
        return Command(
            update=preserve_state_meta_fields(state),
            goto="research_team"
        )
    
    plan_title = current_plan.title
    observations = state.get("observations", [])
    logger.debug(f"[_execute_agent_step] Plan title: {plan_title}, observations count: {len(observations)}")

    # Find the first unexecuted step
    current_step = None
    completed_steps = []
    for idx, step in enumerate(current_plan.steps):
        if not step.execution_res:
            current_step = step
            logger.debug(f"[_execute_agent_step] Found unexecuted step at index {idx}: {step.title}")
            break
        else:
            completed_steps.append(step)

    if not current_step:
        logger.warning(f"[_execute_agent_step] No unexecuted step found in {len(current_plan.steps)} total steps")
        return Command(
            update=preserve_state_meta_fields(state),
            goto="research_team"
        )

    logger.info(f"[_execute_agent_step] Executing step: {current_step.title}, agent: {agent_name}")
    logger.debug(f"[_execute_agent_step] Completed steps so far: {len(completed_steps)}")

    # Format completed steps information
    completed_steps_info = ""
    if completed_steps:
        completed_steps_info = "# Completed Research Steps\n\n"
        for i, step in enumerate(completed_steps):
            completed_steps_info += f"## Completed Step {i + 1}: {step.title}\n\n"
            completed_steps_info += f"<finding>\n{step.execution_res}\n</finding>\n\n"

    # Prepare the input for the agent with completed steps info
    agent_input = {
        "messages": [
            HumanMessage(
                content=f"# Research Topic\n\n{plan_title}\n\n{completed_steps_info}# Current Step\n\n## Title\n\n{current_step.title}\n\n## Description\n\n{current_step.description}\n\n## Locale\n\n{state.get('locale', 'en-US')}"
            )
        ]
    }

    # Add citation reminder for researcher agent
    if agent_name == "researcher":
        if state.get("resources"):
            resources_info = "**The user mentioned the following resource files:**\n\n"
            for resource in state.get("resources"):
                resources_info += f"- {resource.title} ({resource.description})\n"

            agent_input["messages"].append(
                HumanMessage(
                    content=resources_info
                    + "\n\n"
                    + "You MUST use the **local_search_tool** to retrieve the information from the resource files.",
                )
            )

        # Create a system message that uses the state's citation management
        next_citation_id = state.get("next_citation_id", 1)
        citations = state.get("citations", [])
        
        # Format existing citations for the message
        formatted_citations = []
        for citation in citations:
            formatted_citations.append(f"- [{citation['id']}] {citation['title']} ({citation['url']})")
        
        citation_format = "\n\n".join(formatted_citations)
        if citation_format:
            citation_format = "\n\nCurrent citations:\n" + citation_format
        
        agent_input["messages"].append(
            HumanMessage(
                content=f"IMPORTANT: You may include inline citations in the text where appropriate using numbered brackets (e.g., [{next_citation_id}], [{next_citation_id+1}], [{next_citation_id+2}], etc.) AND/OR track all sources and include a References section at the end using numbered reference format. Include an empty line between each citation for better readability. Use this format for each reference:\n- [{next_citation_id}] Source Title (URL)\n\n- [{next_citation_id+1}] Another Source (URL){citation_format}",
                name="system",
            )
        )

    # Invoke the agent
    default_recursion_limit = 25
    try:
        env_value_str = os.getenv("AGENT_RECURSION_LIMIT", str(default_recursion_limit))
        parsed_limit = int(env_value_str)

        if parsed_limit > 0:
            recursion_limit = parsed_limit
            logger.info(f"Recursion limit set to: {recursion_limit}")
        else:
            logger.warning(
                f"AGENT_RECURSION_LIMIT value '{env_value_str}' (parsed as {parsed_limit}) is not positive. "
                f"Using default value {default_recursion_limit}."
            )
            recursion_limit = default_recursion_limit
    except ValueError:
        raw_env_value = os.getenv("AGENT_RECURSION_LIMIT")
        logger.warning(
            f"Invalid AGENT_RECURSION_LIMIT value: '{raw_env_value}'. "
            f"Using default value {default_recursion_limit}."
        )
        recursion_limit = default_recursion_limit

    logger.info(f"Agent input: {agent_input}")
    
    # Validate message content before invoking agent
    try:
        validated_messages = validate_message_content(agent_input["messages"])
        agent_input["messages"] = validated_messages
    except Exception as validation_error:
        logger.error(f"Error validating agent input messages: {validation_error}")
    
    try:
        result = await agent.ainvoke(
            input=agent_input, config={"recursion_limit": recursion_limit}
        )
    except Exception as e:
        import traceback

        error_traceback = traceback.format_exc()
        error_message = f"Error executing {agent_name} agent for step '{current_step.title}': {str(e)}"
        logger.exception(error_message)
        logger.error(f"Full traceback:\n{error_traceback}")
        
        # Enhanced error diagnostics for content-related errors
        if "Field required" in str(e) and "content" in str(e):
            logger.error(f"Message content validation error detected")
            for i, msg in enumerate(agent_input.get('messages', [])):
                logger.error(f"Message {i}: type={type(msg).__name__}, "
                            f"has_content={hasattr(msg, 'content')}, "
                            f"content_type={type(msg.content).__name__ if hasattr(msg, 'content') else 'N/A'}, "
                            f"content_len={len(str(msg.content)) if hasattr(msg, 'content') and msg.content else 0}")

        detailed_error = f"[ERROR] {agent_name.capitalize()} Agent Error\n\nStep: {current_step.title}\n\nError Details:\n{str(e)}\n\nPlease check the logs for more information."
        current_step.execution_res = detailed_error

        return Command(
            update={
                "messages": [
                    HumanMessage(
                        content=detailed_error,
                        name=agent_name,
                    )
                ],
                "observations": observations + [detailed_error],
                **preserve_state_meta_fields(state),
            },
            goto="research_team",
        )

    # Process the result
    response_content = result["messages"][-1].content
    
    # Sanitize response to remove extra tokens and truncate if needed
    response_content = sanitize_tool_response(str(response_content))
    
    logger.debug(f"{agent_name.capitalize()} full response: {response_content}")

    # Parse citations from the response content using CitationProcessor utility class
    current_citations = state.get("citations", [])
    next_citation_id = state.get("next_citation_id", 1)
    new_citations_added = []
    
    try:
        # Extract all citations from the response using CitationProcessor
        # Returns list of dicts with 'id', 'title', 'url' keys
        response_citations = CitationProcessor.extract_citations_from_text(response_content)
        
        # Update citations based on found references
        for citation_dict in response_citations:
            ref_id = int(citation_dict.get('id', 0))
            title = citation_dict.get('title', '')
            url = citation_dict.get('url', '')
            
            # Check if this citation already exists
            exists = False
            for citation in current_citations:
                if citation['id'] == ref_id:
                    exists = True
                    break
            if not exists and ref_id > 0:
                new_citation = {
                    'id': ref_id,
                    'title': title.strip() if title else '',
                    'url': url.strip() if url else ''
                }
                current_citations.append(new_citation)
                new_citations_added.append(new_citation)
                # Update next_citation_id if needed
                if ref_id >= next_citation_id:
                    next_citation_id = ref_id + 1
    except Exception as e:
        logger.warning(f"Error extracting citations from {agent_name} response: {e}")

    # Renumber all citations to ensure they are sequential and update the response content accordingly
    # Sort all citations by their original ID
    current_citations.sort(key=lambda x: x['id'])
    
    # Create a mapping from old IDs to new sequential IDs
    id_mapping = {}
    for idx, citation in enumerate(current_citations):
        old_id = citation['id']
        new_id = idx + 1
        id_mapping[old_id] = new_id
        citation['id'] = new_id  # Update the citation's ID to be sequential
    
    # Update next_citation_id to be one more than the highest citation ID
    next_citation_id = len(current_citations) + 1
    
    # Use CitationProcessor to renumber citations in the response content
    try:
        # Build proper dict format for renumber_citations function
        citations_for_renumber = [
            {'id': old_id, 'title': '', 'url': ''}
            for old_id in id_mapping.keys()
        ]
        response_content = CitationProcessor.renumber_citations(
            response_content,
            citations_for_renumber
        )
        logger.debug(f"Successfully renumbered {len(id_mapping)} citations")
    except Exception as e:
        logger.warning(f"Error renumbering citations: {e}. Using original response.")

    # Update the step with the execution result
    current_step.execution_res = response_content
    logger.info(f"Step '{current_step.title}' execution completed by {agent_name}")

    return Command(
        update={
            "messages": [
                HumanMessage(
                    content=response_content,
                    name=agent_name,
                )
            ],
            "observations": observations + [response_content],
            "citations": current_citations,
            "next_citation_id": next_citation_id,
            **preserve_state_meta_fields(state),
        },
        goto="research_team",
    )


async def _setup_and_execute_agent_step(
    state: State,
    config: RunnableConfig,
    agent_type: str,
    default_tools: list,
) -> Command[Literal["research_team"]]:
    """Helper function to set up an agent with appropriate tools and execute a step.

    This function handles the common logic for both researcher_node and coder_node:
    1. Configures MCP servers and tools based on agent type
    2. Creates an agent with the appropriate tools or uses the default agent
    3. Executes the agent on the current step

    Args:
        state: The current state
        config: The runnable config
        agent_type: The type of agent ("researcher" or "coder")
        default_tools: The default tools to add to the agent

    Returns:
        Command to update state and go to research_team
    """
    configurable = Configuration.from_runnable_config(config)
    
    # Try to load MCP tools, but continue without them if not available
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        mcp_servers = {}
        enabled_tools = {}

        # Extract MCP server configuration for this agent type
        if configurable.mcp_settings:
            for server_name, server_config in configurable.mcp_settings["servers"].items():
                if (
                    server_config["enabled_tools"]
                    and agent_type in server_config["add_to_agents"]
                ):
                    mcp_servers[server_name] = {
                        k: v
                        for k, v in server_config.items()
                        if k in ("transport", "command", "args", "url", "env", "headers")
                    }
                    for tool_name in server_config["enabled_tools"]:
                        enabled_tools[tool_name] = server_name

        # Create and execute agent with MCP tools if available
        if mcp_servers:
            client = MultiServerMCPClient(mcp_servers)
            loaded_tools = default_tools[:]
            all_tools = await client.get_tools()
            for tool in all_tools:
                if tool.name in enabled_tools:
                    tool.description = (
                        f"Powered by '{enabled_tools[tool.name]}'.\n{tool.description}"
                    )
                    loaded_tools.append(tool)

            llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP[agent_type])
            pre_model_hook = partial(ContextManager(llm_token_limit, 3).compress_messages)
            agent = create_agent(
                agent_type,
                agent_type,
                loaded_tools,
                agent_type,
                pre_model_hook,
                interrupt_before_tools=configurable.interrupt_before_tools,
            )
            return await _execute_agent_step(state, agent, agent_type)
        else:
            # Use default tools if no MCP servers are configured
            llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP[agent_type])
            pre_model_hook = partial(ContextManager(llm_token_limit, 3).compress_messages)
            agent = create_agent(
                agent_type,
                agent_type,
                default_tools,
                agent_type,
                pre_model_hook,
                interrupt_before_tools=configurable.interrupt_before_tools,
            )
            return await _execute_agent_step(state, agent, agent_type)
    except ImportError:
        logger.warning("langchain_mcp_adapters not installed, skipping MCP tool loading")
        # Fallback to default tools without MCP
        llm_token_limit = get_llm_token_limit_by_type(AGENT_LLM_MAP[agent_type])
        pre_model_hook = partial(ContextManager(llm_token_limit, 3).compress_messages)
        agent = create_agent(
            agent_type,
            agent_type,
            default_tools,
            agent_type,
            pre_model_hook,
            interrupt_before_tools=configurable.interrupt_before_tools,
        )
        return await _execute_agent_step(state, agent, agent_type)


async def researcher_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Researcher node that do research with support for traditional and deep-mining analysis modes"""
    logger.info("Researcher node is researching.")
    logger.debug(f"[researcher_node] Starting researcher agent")
    
    configurable = Configuration.from_runnable_config(config)
    logger.debug(f"[researcher_node] Max search results: {configurable.max_search_results}")
    
    # Get the current step to determine analysis type
    current_plan = state.get("current_plan")
    current_step = None
    analysis_type = None
    
    if current_plan and hasattr(current_plan, 'steps'):
        for step in current_plan.steps:
            if not step.execution_res:
                current_step = step
                if hasattr(step, 'analysis_type') and step.analysis_type:
                    analysis_type = step.analysis_type
                break
    
    logger.debug(f"[researcher_node] Current analysis_type: {analysis_type}")
    
    # Build tools based on analysis type
    tools = []
    
    # Always include standard research tools
    tools.append(get_web_search_tool(configurable.max_search_results))
    tools.append(crawl_tool)
    
    # Add specialized academic analysis tools if needed
    if analysis_type:
        logger.info(f"[researcher_node] Adding specialized tools for analysis_type: {analysis_type}")
        
        if analysis_type == "paper_analysis":
            logger.debug("[researcher_node] Adding paper metadata extraction tool")
            tools.append(paper_metadata_extraction)
        elif analysis_type == "citation_network":
            logger.debug("[researcher_node] Adding citation analysis tool")
            tools.append(citation_analysis)
        elif analysis_type == "technical_breakdown":
            logger.debug("[researcher_node] Adding technical breakdown tool")
            tools.append(technical_breakdown)
            tools.append(innovation_graph)
    
    # Add general-purpose tools
    tools.append(innovation_graph)
    tools.append(paper_anonymize)
    
    # Add retriever tool if resources are available
    retriever_tool = get_retriever_tool(state.get("resources", []))
    if retriever_tool:
        logger.debug(f"[researcher_node] Adding retriever tool to tools list")
        tools.insert(0, retriever_tool)
    
    logger.info(f"[researcher_node] Researcher tools count: {len(tools)}")
    logger.debug(f"[researcher_node] Researcher tools: {[tool.name if hasattr(tool, 'name') else str(tool) for tool in tools]}")
    
    return await _setup_and_execute_agent_step(
        state,
        config,
        "researcher",
        tools,
    )


async def coder_node(
    state: State, config: RunnableConfig
) -> Command[Literal["research_team"]]:
    """Coder node that do code analysis."""
    logger.info("Coder node is coding.")
    logger.debug(f"[coder_node] Starting coder agent with python_repl_tool")
    
    return await _setup_and_execute_agent_step(
        state,
        config,
        "coder",
        [python_repl_tool],
    )
