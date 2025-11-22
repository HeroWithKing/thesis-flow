#!/usr/bin/env python3
# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Test script for research planner integration."""

import asyncio
import json
from src.prompt_enhancer.graph import build_graph


async def test_research_planner():
    """Test the research planner functionality."""
    
    # Build the graph
    graph = build_graph()
    
    # Test research plan generation
    test_input = {
        "prompt": "人工智能在医疗诊断中的应用研究",
        "report_style": "research_plan",
        "locale": "zh-CN",
        "context": "这是为计算机科学研究生设计的文献调研项目"
    }
    
    print("=== Testing Research Planner ===")
    print(f"Input: {test_input['prompt']}")
    
    try:
        # Execute the graph
        result = await graph.ainvoke(test_input)
        
        print("✓ Research plan generated successfully!")
        print("\n=== Generated Research Plan ===")
        
        if "research_plan" in result:
            plan = result["research_plan"]
            print(f"Research Topic: {plan.get('research_topic', 'N/A')}")
            print(f"Key Questions: {plan.get('key_research_questions', [])}")
            print(f"Innovation Points: {plan.get('innovation_generation', {}).get('proposed_innovations', [])}")
            
        if "output" in result:
            print("\n=== Raw Output ===")
            print(result["output"])
            
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_research_planner())