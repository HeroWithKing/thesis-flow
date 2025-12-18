# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Unit tests for ArXiv enhancer and integration tools.
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.tools.arxiv_enhancer import ArXivEnhancer, VenueResolver
from src.tools.arxiv_enhancement_tool import enhance_arxiv_results, get_paper_quality_metrics


class TestVenueResolver:
    """Test VenueResolver functionality."""

    def test_cache_initialization(self):
        """Test that cache is properly initialized."""
        resolver = VenueResolver(cache_dir=Path(".test_cache"))
        assert resolver.cache_file.parent == Path(".test_cache")

    @patch("src.tools.arxiv_enhancer.requests.get")
    async def test_resolve_venue_with_cache(self, mock_get):
        """Test that venue resolution uses cache on second call."""
        resolver = VenueResolver(cache_dir=Path(".test_cache"))
        
        # Clear cache for fresh test
        resolver.cache.clear()
        
        title = "Test Paper Title"
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"venue": "ICML", "title": title}]
        }
        mock_get.return_value = mock_response
        
        # First call should hit API
        result1 = await resolver.resolve_venue(title)
        assert result1["source"] == "Semantic Scholar"
        
        # Second call should use cache
        result2 = await resolver.resolve_venue(title)
        assert result2 == result1
        assert title in resolver.cache

    def test_get_quality_score(self):
        """Test quality score calculation."""
        enhancer = ArXivEnhancer(cache_dir=Path(".test_cache"))
        
        # Test high quality paper
        high_quality_result = {
            "title": "High Quality Paper",
            "venue": "ICML",
            "citations": 100,
            "year": 2024,
        }
        score1 = enhancer.get_quality_score(high_quality_result)
        assert 0.8 <= score1 <= 1.0
        
        # Test low quality paper
        low_quality_result = {
            "title": "Low Quality Paper",
            "venue": "arXiv",
            "citations": 0,
            "year": 2015,
        }
        score2 = enhancer.get_quality_score(low_quality_result)
        assert 0 <= score2 <= 0.3


class TestArXivEnhancer:
    """Test ArXiv Enhancer functionality."""

    @pytest.mark.asyncio
    @patch("src.tools.arxiv_enhancer.requests.get")
    async def test_enhance_single_result(self, mock_get):
        """Test enhancing a single ArXiv result."""
        enhancer = ArXivEnhancer(cache_dir=Path(".test_cache"))
        
        # Mock API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"venue": "ICML", "citationCount": 42}]
        }
        mock_get.return_value = mock_response
        
        arxiv_result = {
            "title": "Test Paper",
            "authors": ["Author 1", "Author 2"],
            "year": 2024,
            "abstract": "Test abstract",
            "url": "http://arxiv.org/abs/2401.00001",
        }
        
        enhanced = await enhancer.enhance_result(arxiv_result)
        
        assert "venue" in enhanced
        assert "venue_source" in enhanced
        assert enhanced["year"] == 2024

    @pytest.mark.asyncio
    async def test_enhance_results_empty_list(self):
        """Test enhancing empty results list."""
        enhancer = ArXivEnhancer(cache_dir=Path(".test_cache"))
        
        enhanced = await enhancer.enhance_results([])
        assert enhanced == []

    def test_quality_score_boundaries(self):
        """Test that quality scores stay within bounds."""
        enhancer = ArXivEnhancer(cache_dir=Path(".test_cache"))
        
        test_cases = [
            {"venue": "", "citations": 0, "year": 2000},
            {"venue": "ICML", "citations": 1000, "year": 2024},
            {"venue": "arXiv", "citations": 500, "year": 2020},
        ]
        
        for test_case in test_cases:
            test_case["title"] = "Test"
            score = enhancer.get_quality_score(test_case)
            assert 0 <= score <= 1.0, f"Score {score} out of bounds for {test_case}"


class TestArXivEnhancementTool:
    """Test LangChain tool integration."""

    @pytest.mark.asyncio
    async def test_enhance_arxiv_results_valid_input(self):
        """Test enhance_arxiv_results with valid JSON input."""
        search_results = json.dumps([
            {
                "title": "Test Paper",
                "authors": ["Author"],
                "year": 2024,
                "url": "http://arxiv.org/abs/2401.00001",
            }
        ])
        
        with patch("src.tools.arxiv_enhancement_tool.get_arxiv_enhancer") as mock_get:
            mock_enhancer = MagicMock()
            mock_enhancer.enhance_result = MagicMock(
                return_value={
                    "title": "Test Paper",
                    "venue": "arXiv",
                    "citations": 0,
                    "year": 2024,
                }
            )
            mock_enhancer.get_quality_score = MagicMock(return_value=0.5)
            mock_get.return_value = mock_enhancer
            
            # Note: We need to handle async properly
            result = await enhance_arxiv_results(search_results, scoring=False)
            result_dict = json.loads(result)
            
            assert result_dict["status"] == "success"
            assert result_dict["count"] >= 1

    @pytest.mark.asyncio
    async def test_enhance_arxiv_results_invalid_json(self):
        """Test enhance_arxiv_results with invalid JSON."""
        invalid_json = "not valid json"
        
        result = await enhance_arxiv_results(invalid_json, scoring=False)
        result_dict = json.loads(result)
        
        assert result_dict["status"] == "error"
        assert "Invalid JSON" in result_dict.get("error", "")

    def test_get_paper_quality_metrics(self):
        """Test quality metrics calculation."""
        result = get_paper_quality_metrics(
            title="Test Paper",
            venue="ICML",
            citations=50,
            year=2024,
        )
        
        result_dict = json.loads(result)
        assert result_dict["status"] == "success"
        assert "quality_score" in result_dict
        assert "breakdown" in result_dict
        assert 0 <= result_dict["quality_score"] <= 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
