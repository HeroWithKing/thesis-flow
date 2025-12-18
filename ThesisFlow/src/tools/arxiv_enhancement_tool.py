# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
ArXiv Enhancement Tool - LangChain integration for ArXiv result enrichment.
Provides tools for enhancing ArXiv search results with metadata and quality scoring.
"""

import asyncio
import json
import logging
from typing import Annotated, Any, Dict, List

from langchain_core.tools import tool

from .arxiv_enhancer import ArXivEnhancer

logger = logging.getLogger(__name__)

# Global enhancer instance
_arxiv_enhancer = None


def get_arxiv_enhancer() -> ArXivEnhancer:
    """Get or create the ArXiv enhancer instance."""
    global _arxiv_enhancer
    if _arxiv_enhancer is None:
        _arxiv_enhancer = ArXivEnhancer()
    return _arxiv_enhancer


@tool
async def enhance_arxiv_results(
    search_results: Annotated[
        str,
        "JSON string containing list of ArXiv search results with fields: title, authors, year, abstract, url",
    ],
    scoring: Annotated[
        bool,
        "Whether to calculate quality scores for each paper",
    ] = True,
) -> str:
    """
    Enhance ArXiv search results with metadata from external sources.

    This tool enriches ArXiv search results by fetching:
    - Publication venue (from Semantic Scholar or Crossref)
    - Citation counts
    - Quality scoring based on venue, citations, and recency

    Args:
        search_results: JSON string of ArXiv search results
        scoring: Whether to include quality scores

    Returns:
        JSON string with enhanced results including venue, citations, and optional quality scores

    Example:
        Input: [{"title": "Example Paper", "authors": [...], "year": 2024, "url": "..."}]
        Output: [{"title": "Example Paper", ..., "venue": "ICML", "citations": 42, "quality_score": 0.85}]
    """
    try:
        # Parse input
        results = json.loads(search_results)
        if not isinstance(results, list):
            results = [results]

        logger.info(f"Enhancing {len(results)} ArXiv search results")

        # Enhance results
        enhancer = get_arxiv_enhancer()
        enhanced_results = []

        for result in results:
            enhanced = await enhancer.enhance_result(result)

            # Add quality score if requested
            if scoring:
                enhanced["quality_score"] = enhancer.get_quality_score(enhanced)

            enhanced_results.append(enhanced)
            await asyncio.sleep(0.5)  # Rate limiting

        logger.info(f"Successfully enhanced {len(enhanced_results)} results")

        return json.dumps(
            {
                "status": "success",
                "count": len(enhanced_results),
                "results": enhanced_results,
            },
            indent=2,
            ensure_ascii=False,
        )

    except json.JSONDecodeError as e:
        logger.error(f"Error parsing search results JSON: {str(e)}")
        return json.dumps(
            {
                "status": "error",
                "error": f"Invalid JSON format: {str(e)}",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"Error enhancing ArXiv results: {str(e)}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
            ensure_ascii=False,
        )


@tool
def get_paper_quality_metrics(
    title: Annotated[str, "Paper title"],
    venue: Annotated[str, "Publication venue (optional)", ""] = "",
    citations: Annotated[int, "Citation count (optional)", 0] = 0,
    year: Annotated[int, "Publication year (optional)", 2024] = 2024,
) -> str:
    """
    Calculate quality metrics for a paper based on publication metadata.

    Scoring considers:
    - Publication venue (peer-reviewed vs preprint)
    - Citation count (impact factor)
    - Publication recency (within last 10 years preferred)

    Args:
        title: Paper title
        venue: Publication venue (e.g., "ICML", "arXiv")
        citations: Number of citations
        year: Publication year

    Returns:
        JSON with quality score (0-1) and scoring breakdown

    Example:
        Input: title="Example", venue="ICML", citations=50, year=2024
        Output: {"quality_score": 0.85, "breakdown": {...}}
    """
    try:
        result_dict = {
            "title": title,
            "venue": venue,
            "citations": citations,
            "year": year,
        }

        enhancer = get_arxiv_enhancer()
        quality_score = enhancer.get_quality_score(result_dict)

        # Calculate breakdown
        venue_score = 0.4 if venue and venue != "arXiv" else 0.1
        citation_score = min(citations / 100, 0.3)
        current_year = 2025
        recency_score = max(0, min((year - 2015) / 10, 0.3))

        return json.dumps(
            {
                "status": "success",
                "quality_score": round(quality_score, 3),
                "breakdown": {
                    "venue_score": round(venue_score, 3),
                    "citation_score": round(citation_score, 3),
                    "recency_score": round(recency_score, 3),
                },
                "metadata": {
                    "title": title,
                    "venue": venue,
                    "citations": citations,
                    "year": year,
                },
            },
            indent=2,
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"Error calculating quality metrics: {str(e)}")
        return json.dumps(
            {
                "status": "error",
                "error": str(e),
            },
            ensure_ascii=False,
        )
