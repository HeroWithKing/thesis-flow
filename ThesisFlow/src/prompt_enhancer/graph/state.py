# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import Optional, TypedDict, Dict, Any, List

from src.config.report_style import ReportStyle


class ResearchPlan(TypedDict):
    """Research plan structure for academic research."""
    research_topic: str
    background_analysis: str
    key_research_questions: List[str]
    literature_review_plan: Dict[str, Any]
    innovation_generation: Dict[str, Any]
    report_structure: Dict[str, Any]
    literature_references: List[Dict[str, Any]]  # 新增文献引用字段


class PromptEnhancerState(TypedDict):
    """State for the prompt enhancer workflow."""

    prompt: str  # Original prompt to enhance
    context: Optional[str]  # Additional context
    report_style: Optional[ReportStyle]  # Report style preference
    output: Optional[str]  # Enhanced prompt result
    research_plan: Optional[ResearchPlan]  # 新增：结构化研究计划
    locale: Optional[str]  # 语言设置