# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
ArXiv Metadata Enhancer for enriching search results with additional metadata.
Fetches publication venue, citation counts, and other metadata from external APIs.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import requests

logger = logging.getLogger(__name__)


class VenueResolver:
    """Resolve paper publication venues using Semantic Scholar and Crossref APIs."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the VenueResolver.

        Args:
            cache_dir: Directory to store venue cache. Defaults to .cache/venue_cache
        """
        self.semantic_scholar_url = "http://api.semanticscholar.org/graph/v1/paper/search"
        self.crossref_url = "https://api.crossref.org/works"
        
        if cache_dir is None:
            cache_dir = Path(".cache")
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "venue_cache.json"
        self.cache = self._load_cache()
        self.citation_cache = {}

    def _load_cache(self) -> Dict[str, Dict]:
        """Load venue cache from file."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Error loading venue cache: {str(e)}")
        return {}

    def _save_cache(self):
        """Save venue cache to file."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Error saving venue cache: {str(e)}")

    def _fetch_semantic_scholar(self, title: str) -> Optional[str]:
        """Fetch venue from Semantic Scholar API."""
        try:
            params = {"query": title, "fields": "venue,title", "limit": 1}
            response = requests.get(self.semantic_scholar_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("data") and len(data["data"]) > 0:
                    venue = data["data"][0].get("venue", "")
                    return venue if venue else None
        except Exception as e:
            logger.debug(f"Semantic Scholar API error for '{title}': {str(e)}")
        return None

    def _fetch_crossref(self, title: str) -> Optional[str]:
        """Fetch venue from Crossref API."""
        try:
            params = {
                "query.title": title,
                "select": "container-title",
                "rows": 1,
            }
            headers = {"User-Agent": "ThesisFlow/1.0"}
            response = requests.get(
                self.crossref_url, params=params, headers=headers, timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("message", {}).get("items"):
                    venue = data["message"]["items"][0].get("container-title", [""])[0]
                    return venue if venue else None
        except Exception as e:
            logger.debug(f"Crossref API error for '{title}': {str(e)}")
        return None

    def _fetch_citations(self, title: str) -> int:
        """Fetch citation count from Semantic Scholar API."""
        if title in self.citation_cache:
            return self.citation_cache[title]

        try:
            params = {
                "query": title,
                "fields": "citationCount",
                "limit": 1,
            }
            response = requests.get(
                self.semantic_scholar_url, params=params, timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    citations = data["data"][0].get("citationCount", 0)
                    self.citation_cache[title] = citations
                    return citations
        except Exception as e:
            logger.debug(f"Error fetching citations for '{title}': {str(e)}")
        return 0

    async def resolve_venue(self, title: str) -> Dict[str, Any]:
        """
        Resolve paper venue asynchronously with caching.

        Args:
            title: Paper title

        Returns:
            Dictionary with venue info:
            {
                'venue': str,
                'source': 'Semantic Scholar' | 'Crossref' | 'arXiv',
                'timestamp': ISO timestamp,
                'citations': int (optional)
            }
        """
        if title in self.cache:
            logger.debug(f"Using cached venue for: {title}")
            return self.cache[title]

        venue_info = {
            "venue": "",
            "source": "",
            "timestamp": datetime.now().isoformat(),
            "citations": 0,
        }

        # Try Semantic Scholar first
        venue = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_semantic_scholar, title
        )
        await asyncio.sleep(0.5)  # Rate limiting

        if venue:
            venue_info["venue"] = venue
            venue_info["source"] = "Semantic Scholar"
        else:
            # Try Crossref
            venue = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_crossref, title
            )
            await asyncio.sleep(0.5)

            if venue:
                venue_info["venue"] = venue
                venue_info["source"] = "Crossref"
            else:
                venue_info["venue"] = "arXiv"
                venue_info["source"] = "Default"

        # Fetch citations
        citations = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_citations, title
        )
        venue_info["citations"] = citations
        await asyncio.sleep(0.5)

        self.cache[title] = venue_info
        self._save_cache()

        return venue_info


class ArXivEnhancer:
    """Enhance ArXiv search results with metadata from external sources."""

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the ArXiv Enhancer.

        Args:
            cache_dir: Directory for caching. Defaults to .cache
        """
        self.venue_resolver = VenueResolver(cache_dir)

    async def enhance_result(self, arxiv_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance a single ArXiv search result.

        Args:
            arxiv_result: ArXiv search result dictionary with keys:
                - title: str
                - authors: List[str]
                - published: datetime
                - summary: str
                - entry_id: str

        Returns:
            Enhanced result with additional metadata:
                - venue: Publication venue
                - venue_source: Source of venue info
                - citations: Citation count
                - timestamp: When metadata was fetched
        """
        try:
            title = arxiv_result.get("title", "")
            if not title:
                logger.warning("ArXiv result missing title")
                return arxiv_result

            logger.debug(f"Enhancing ArXiv result: {title[:50]}...")

            # Resolve venue
            venue_info = await self.venue_resolver.resolve_venue(title)

            # Add enhanced metadata
            enhanced_result = {
                **arxiv_result,
                "venue": venue_info["venue"],
                "venue_source": venue_info["source"],
                "citations": venue_info["citations"],
                "metadata_timestamp": venue_info["timestamp"],
            }

            logger.debug(
                f"Enhancement complete for '{title[:50]}': "
                f"venue={venue_info['venue']}, "
                f"citations={venue_info['citations']}"
            )

            return enhanced_result

        except Exception as e:
            logger.error(f"Error enhancing ArXiv result: {str(e)}")
            # Return original result on error
            return arxiv_result

    async def enhance_results(
        self, arxiv_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enhance multiple ArXiv search results.

        Args:
            arxiv_results: List of ArXiv search results

        Returns:
            List of enhanced results
        """
        if not arxiv_results:
            return []

        logger.info(f"Enhancing {len(arxiv_results)} ArXiv results")

        # Enhance results sequentially to avoid rate limiting
        enhanced = []
        for result in arxiv_results:
            enhanced_result = await self.enhance_result(result)
            enhanced.append(enhanced_result)
            await asyncio.sleep(1)  # Rate limiting between API calls

        logger.info(f"Enhancement complete for {len(enhanced)} results")
        return enhanced

    def get_quality_score(self, enhanced_result: Dict[str, Any]) -> float:
        """
        Calculate quality score for a paper based on metadata.

        Considers:
        - Publication venue quality
        - Citation count
        - Publication year (more recent is better)

        Args:
            enhanced_result: Enhanced ArXiv result

        Returns:
            Quality score between 0 and 1
        """
        score = 0.0

        # Venue score
        venue = enhanced_result.get("venue", "")
        if venue and venue != "arXiv":
            score += 0.4  # Paper published in peer-reviewed venue
        else:
            score += 0.1

        # Citation score (normalized)
        citations = enhanced_result.get("citations", 0)
        citation_score = min(citations / 100, 0.3)  # Cap at 0.3
        score += citation_score

        # Recency score
        try:
            year = enhanced_result.get("year")
            if year:
                current_year = datetime.now().year
                recency_score = max(0, min((year - 2015) / 10, 0.3))
                score += recency_score
        except Exception as e:
            logger.debug(f"Error calculating recency score: {str(e)}")

        return min(score, 1.0)
