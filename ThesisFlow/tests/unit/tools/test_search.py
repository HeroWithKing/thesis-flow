# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import pytest

from src.tools.search import get_web_search_tool


class TestGetWebSearchTool:
    def test_get_web_search_tool_arxiv(self):
        """Test arxiv search tool initialization."""
        tool = get_web_search_tool(max_search_results=2)
        assert tool.name == "web_search"
        assert tool.api_wrapper.top_k_results == 2
        assert tool.api_wrapper.load_max_docs == 2
        assert tool.api_wrapper.load_all_available_meta is True

    def test_get_web_search_tool_arxiv_with_different_results(self):
        """Test arxiv search tool with different max_results."""
        tool = get_web_search_tool(max_search_results=10)
        assert tool.name == "web_search"
        assert tool.api_wrapper.top_k_results == 10
        assert tool.api_wrapper.load_max_docs == 10
