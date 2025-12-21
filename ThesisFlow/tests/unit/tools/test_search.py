# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import pytest

from src.tools.search import get_web_search_tool, FallbackSearchTool


class TestGetWebSearchTool:
    def test_get_web_search_tool_initialization(self):
        """Test web search tool initialization."""
        tool = get_web_search_tool(max_search_results=2)
        assert tool.name == "web_search"
        assert isinstance(tool, FallbackSearchTool)
        assert tool.max_results == 2
        assert tool.fallback_threshold == 3

    def test_get_web_search_tool_with_different_results(self):
        """Test web search tool with different max_results."""
        tool = get_web_search_tool(max_search_results=10)
        assert tool.name == "web_search"
        assert tool.max_results == 10
        assert isinstance(tool, FallbackSearchTool)

    def test_fallback_search_tool_properties(self):
        """Test FallbackSearchTool properties."""
        tool = FallbackSearchTool(max_results=5, fallback_threshold=3)
        assert tool.name == "web_search"
        assert tool.max_results == 5
        assert tool.fallback_threshold == 3
        assert tool.description is not None
