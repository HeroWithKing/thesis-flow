# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Test fallback search logic."""

import pytest
from unittest.mock import patch, MagicMock

from src.tools.search import (
    _parse_arxiv_results,
    _deduplicate_results,
    _load_search_config,
    _is_chinese_text,
    FallbackSearchTool,
    get_web_search_tool,
)


class TestParseArxivResults:
    """Test ArXiv result parsing."""
    
    def test_parse_list_of_dicts(self):
        """Test parsing list of dictionaries."""
        results = [
            {"title": "Paper 1", "content": "Content 1"},
            {"title": "Paper 2", "content": "Content 2"},
        ]
        parsed = _parse_arxiv_results(results)
        assert len(parsed) == 2
        assert parsed[0]["title"] == "Paper 1"
    
    def test_parse_empty_list(self):
        """Test parsing empty list."""
        parsed = _parse_arxiv_results([])
        assert parsed == []
    
    def test_parse_non_dict_results(self):
        """Test parsing non-dict results."""
        results = ["Some string result"]
        parsed = _parse_arxiv_results(results)
        assert len(parsed) > 0


class TestChineseDetection:
    """Test Chinese text detection."""
    
    def test_detect_chinese(self):
        """Test detecting Chinese text."""
        assert _is_chinese_text("AI4S在生命科学领域的技术") is True
        assert _is_chinese_text("机器学习") is True
        assert _is_chinese_text("深度学习") is True
    
    def test_detect_english(self):
        """Test detecting English text."""
        assert _is_chinese_text("AI for Science") is False
        assert _is_chinese_text("machine learning") is False
        assert _is_chinese_text("deep learning") is False
    
    def test_detect_mixed(self):
        """Test detecting mixed text."""
        assert _is_chinese_text("AI4S在生命科学") is True
        assert _is_chinese_text("machine learning 机器学习") is True


class TestDeduplicateResults:
    """Test result deduplication."""
    
    def test_deduplicate_by_url(self):
        """Test deduplication by URL."""
        arxiv_results = [
            {"title": "Paper 1", "url": "https://arxiv.org/abs/1234.5678"},
        ]
        tavily_results = [
            {"title": "Same Paper", "url": "https://arxiv.org/abs/1234.5678"},
            {"title": "New Paper", "url": "https://example.com"},
        ]
        
        unique = _deduplicate_results(arxiv_results, tavily_results)
        assert len(unique) == 1
        assert unique[0]["title"] == "New Paper"
    
    def test_deduplicate_by_title(self):
        """Test deduplication by title."""
        arxiv_results = [
            {"title": "Important Paper", "url": "https://arxiv.org/abs/1234"},
        ]
        tavily_results = [
            {"title": "Important Paper", "url": "https://other.com"},
            {"title": "Different Paper", "url": "https://example.com"},
        ]
        
        unique = _deduplicate_results(arxiv_results, tavily_results)
        assert len(unique) == 1
        assert unique[0]["title"] == "Different Paper"
    
    def test_empty_arxiv_results(self):
        """Test when ArXiv results are empty."""
        tavily_results = [
            {"title": "Paper 1", "url": "https://example.com"},
        ]
        
        unique = _deduplicate_results([], tavily_results)
        assert len(unique) == 1


class TestLoadSearchConfig:
    """Test configuration loading."""
    
    @patch('src.tools.search.load_yaml_config')
    def test_load_config(self, mock_load):
        """Test loading search configuration."""
        mock_load.return_value = {
            "SEARCH_ENGINE": {
                "fallback_threshold": 3,
                "tavily_api_key": "test-key",
            }
        }
        
        config = _load_search_config()
        assert config["fallback_threshold"] == 3
        assert config["tavily_api_key"] == "test-key"


class TestFallbackSearchTool:
    """Test FallbackSearchTool class."""
    
    def test_tool_initialization(self):
        """Test tool initialization."""
        tool = FallbackSearchTool(max_results=5, fallback_threshold=2)
        assert tool.name == "web_search"
        assert tool.max_results == 5
        assert tool.fallback_threshold == 2
    
    def test_tool_description(self):
        """Test tool has description."""
        tool = FallbackSearchTool()
        assert tool.description is not None
        assert len(tool.description) > 0


class TestGetWebSearchTool:
    """Test get_web_search_tool factory function."""
    
    @patch('src.tools.search._load_search_config')
    def test_get_tool_default_threshold(self, mock_config):
        """Test getting tool with default threshold."""
        mock_config.return_value = {"fallback_threshold": 3}
        
        tool = get_web_search_tool(10)
        assert tool.name == "web_search"
        assert tool.max_results == 10
        assert tool.fallback_threshold == 3
    
    @patch('src.tools.search._load_search_config')
    def test_get_tool_custom_threshold(self, mock_config):
        """Test getting tool with custom threshold."""
        mock_config.return_value = {"fallback_threshold": 5}
        
        tool = get_web_search_tool(15)
        assert tool.max_results == 15
        assert tool.fallback_threshold == 5

