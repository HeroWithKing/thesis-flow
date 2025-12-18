# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT


from dataclasses import field

from langgraph.graph import MessagesState

from src.prompts.planner_model import Plan
from src.rag import Resource


class State(MessagesState):
    """State for the agent system, extends MessagesState with next field."""

    # ========================================================================
    # MODULE 1: Basic Configuration (基础配置)
    # ========================================================================
    locale: str = "en-US"
    auto_accepted_plan: bool = False
    enable_background_investigation: bool = True
    background_investigation_results: str = None

    # ========================================================================
    # MODULE 2: Research Workflow (研究工作流)
    # ========================================================================
    research_topic: str = ""
    clarified_research_topic: str = (
        ""  # Complete/final clarified topic with all clarification rounds
    )
    current_plan: Plan | str = None
    plan_iterations: int = 0
    observations: list[str] = []
    resources: list[Resource] = []
    final_report: str = ""

    # ========================================================================
    # MODULE 3: Clarification System (澄清系统 - 可选功能)
    # ========================================================================
    enable_clarification: bool = (
        False  # Enable/disable clarification feature (default: False)
    )
    clarification_rounds: int = 0
    clarification_history: list[str] = field(default_factory=list)
    is_clarification_complete: bool = False
    max_clarification_rounds: int = (
        3  # Default: 3 rounds (only used when enable_clarification=True)
    )

    # ========================================================================
    # MODULE 4: Citation Management (引用管理)
    # ========================================================================
    citations: list[dict] = field(default_factory=list)  # Track all citations
    next_citation_id: int = 1  # Next citation ID to assign

    # ========================================================================
    # MODULE 5: Routing Control (路由控制 - 内部使用)
    # ========================================================================
    goto: str = "planner"  # Default next node
