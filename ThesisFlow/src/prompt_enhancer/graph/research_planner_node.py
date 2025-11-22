# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import json
import re
from typing import Dict, Any

from langchain.schema import HumanMessage

from src.config.agents import AGENT_LLM_MAP
from src.llms.llm import get_llm_by_type
from src.prompt_enhancer.graph.state import PromptEnhancerState, ResearchPlan
from src.prompts.template import apply_prompt_template

logger = logging.getLogger(__name__)


def research_planner_node(state: PromptEnhancerState) -> Dict[str, Any]:
    """Node that generates detailed research plans for academic research."""
    logger.info("Generating research plan for academic topic...")

    model = get_llm_by_type(AGENT_LLM_MAP["research_planner"])

    try:
        # Create research context message
        context_info = ""
        if state.get("context"):
            context_info = f"\n\nResearch Context: {state['context']}"

        research_topic_message = HumanMessage(
            content=f"Please create a comprehensive research plan for:{context_info}\n\nResearch Topic: {state['prompt']}"
        )

        # Apply research planner template
        messages = apply_prompt_template(
            "research_planner/research_planner",
            {
                "messages": [research_topic_message],
                "report_style": state.get("report_style"),
                "research_topic": state["prompt"]
            },
            locale=state.get("locale", "en-US"),
        )

        # Get the response from the model
        response = model.invoke(messages)
        response_content = response.content.strip()
        logger.debug(f"Research planner response: {response_content}")

        # Extract JSON from response
        research_plan = extract_research_plan_from_response(response_content)
        
        # Validate research plan structure
        if validate_research_plan(research_plan):
            logger.info("Research plan generation completed successfully")
            return {
                "output": json.dumps(research_plan, ensure_ascii=False, indent=2),
                "research_plan": research_plan
            }
        else:
            logger.warning("Research plan validation failed, using fallback")
            return generate_fallback_plan(state["prompt"])

    except Exception as e:
        logger.error(f"Error in research plan generation: {str(e)}")
        return generate_fallback_plan(state["prompt"])


def extract_research_plan_from_response(response_content: str) -> Dict[str, Any]:
    """Extract and parse research plan from model response."""
    try:
        # Try to extract JSON from code blocks first
        json_match = re.search(r'```json\s*(.*?)\s*```', response_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            return json.loads(json_str)
        
        # Try to find JSON directly
        json_match = re.search(r'\{.*\}', response_content, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            return json.loads(json_str)
        
        # Fallback: return as text
        return {"raw_response": response_content}
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return {"error": "Failed to parse research plan", "raw_response": response_content}


def validate_research_plan(plan: Dict[str, Any]) -> bool:
    """Validate the structure of the research plan."""
    required_fields = [
        "research_topic", 
        "background_analysis", 
        "key_research_questions",
        "literature_review_plan",
        "innovation_generation"
    ]
    
    return all(field in plan for field in required_fields)


def generate_fallback_plan(topic: str) -> Dict[str, Any]:
    """Generate a fallback research plan when generation fails."""
    return {
        "output": f"Research plan generation failed for topic: {topic}",
        "research_plan": {
            "research_topic": topic,
            "background_analysis": "Automatic generation failed, manual review required.",
            "key_research_questions": ["Please specify research questions manually"],
            "literature_review_plan": {
                "classic_papers": {"time_range": "Past 5-10 years"},
                "cutting_edge_papers": {"time_range": "Past 1-2 years"}
            },
            "innovation_generation": {
                "gap_analysis": "Manual analysis required",
                "proposed_innovations": []
            }
        }
    }