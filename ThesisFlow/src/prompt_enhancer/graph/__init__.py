# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from langgraph.graph import StateGraph

from src.prompt_enhancer.graph.enhancer_node import prompt_enhancer_node
from src.prompt_enhancer.graph.research_planner_node import research_planner_node
from src.prompt_enhancer.graph.state import PromptEnhancerState


def build_graph():
    """Build and return the prompt enhancer workflow graph."""
    # Build state graph
    builder = StateGraph(PromptEnhancerState)

    # Add both nodes
    builder.add_node("enhancer", prompt_enhancer_node)
    builder.add_node("research_planner", research_planner_node)

    # Define conditional routing
    def route_based_on_style(state: PromptEnhancerState) -> str:
        if state.get("report_style") == "research_plan":
            return "research_planner"
        else:
            return "enhancer"

    # Set entry point with conditional routing
    builder.set_conditional_entry_point(
        route_based_on_style,
        {
            "research_planner": "research_planner",
            "enhancer": "enhancer"
        }
    )

    # Set finish points
    builder.set_finish_point("enhancer")
    builder.set_finish_point("research_planner")

    # Compile and return the graph
    return builder.compile()