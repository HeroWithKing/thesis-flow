#!/usr/bin/env python3
# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Example usage of ArXiv Enhancer in research workflow.
This script demonstrates how to use the ArXivEnhancer to improve search results.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

from src.tools.arxiv_enhancer import ArXivEnhancer, VenueResolver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def example_basic_enhancement():
    """Example 1: Basic enhancement of ArXiv results."""
    logger.info("=" * 60)
    logger.info("Example 1: Basic Enhancement")
    logger.info("=" * 60)

    # Sample ArXiv search results
    sample_results = [
        {
            "title": "Attention is All You Need",
            "authors": ["Ashish Vaswani", "Noam Shazeer", "Parmar Noam"],
            "year": 2017,
            "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks in an encoder-decoder configuration. The best performing models also connect the encoder and decoder through an attention mechanism.",
            "url": "http://arxiv.org/abs/1706.03762",
        },
        {
            "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
            "authors": ["Jacob Devlin", "Ming-Wei Chang", "Kenton Lee", "Kristina Toutanova"],
            "year": 2018,
            "abstract": "We introduce a new language representation model called BERT, which stands for Bidirectional Encoder Representations from Transformers.",
            "url": "http://arxiv.org/abs/1810.04805",
        },
    ]

    # Initialize enhancer
    enhancer = ArXivEnhancer(cache_dir=Path(".cache"))

    # Enhance results
    logger.info(f"Enhancing {len(sample_results)} results...")
    enhanced_results = await enhancer.enhance_results(sample_results)

    # Display results
    for i, result in enumerate(enhanced_results, 1):
        logger.info(f"\nResult {i}:")
        logger.info(f"  Title: {result['title']}")
        logger.info(f"  Year: {result['year']}")
        logger.info(f"  Venue: {result.get('venue', 'N/A')}")
        logger.info(f"  Venue Source: {result.get('venue_source', 'N/A')}")
        logger.info(f"  Citations: {result.get('citations', 0)}")
        logger.info(f"  Quality Score: {enhancer.get_quality_score(result):.3f}")


async def example_quality_scoring():
    """Example 2: Quality scoring for paper selection."""
    logger.info("\n" + "=" * 60)
    logger.info("Example 2: Quality Scoring")
    logger.info("=" * 60)

    enhancer = ArXivEnhancer(cache_dir=Path(".cache"))

    # Different quality papers
    papers = [
        {
            "title": "Top-tier conference paper",
            "venue": "ICML",
            "citations": 100,
            "year": 2024,
        },
        {
            "title": "ArXiv preprint",
            "venue": "arXiv",
            "citations": 5,
            "year": 2024,
        },
        {
            "title": "Well-cited older paper",
            "venue": "NeurIPS",
            "citations": 500,
            "year": 2018,
        },
    ]

    logger.info("\nScoring papers:")
    scored_papers = []
    for paper in papers:
        score = enhancer.get_quality_score(paper)
        scored_papers.append((paper, score))
        logger.info(f"  {paper['title']}: {score:.3f}")

    # Rank by quality
    ranked = sorted(scored_papers, key=lambda x: x[1], reverse=True)
    logger.info("\nRanked by quality:")
    for i, (paper, score) in enumerate(ranked, 1):
        logger.info(f"  {i}. {paper['title']} ({score:.3f})")


async def example_filter_papers():
    """Example 3: Filter papers by quality threshold."""
    logger.info("\n" + "=" * 60)
    logger.info("Example 3: Quality Filtering")
    logger.info("=" * 60)

    # Simulated enhanced search results
    papers = [
        {
            "title": "Paper A",
            "venue": "ICML",
            "citations": 150,
            "year": 2024,
        },
        {
            "title": "Paper B",
            "venue": "arXiv",
            "citations": 2,
            "year": 2024,
        },
        {
            "title": "Paper C",
            "venue": "ACL",
            "citations": 80,
            "year": 2023,
        },
        {
            "title": "Paper D",
            "venue": "arXiv",
            "citations": 0,
            "year": 2025,
        },
    ]

    enhancer = ArXivEnhancer(cache_dir=Path(".cache"))

    # Filter by quality threshold
    threshold = 0.6
    high_quality = []

    logger.info(f"\nFiltering papers (threshold: {threshold}):")
    for paper in papers:
        score = enhancer.get_quality_score(paper)
        logger.info(
            f"  {paper['title']}: {score:.3f} "
            f"{'✓ PASS' if score >= threshold else '✗ FAIL'}"
        )
        if score >= threshold:
            high_quality.append((paper, score))

    logger.info(f"\nSelected {len(high_quality)}/{len(papers)} papers")
    for paper, score in high_quality:
        logger.info(f"  - {paper['title']} (score: {score:.3f})")


async def example_cache_usage():
    """Example 4: Demonstrate cache usage."""
    logger.info("\n" + "=" * 60)
    logger.info("Example 4: Cache Usage")
    logger.info("=" * 60)

    resolver = VenueResolver(cache_dir=Path(".cache"))

    # Same title twice - second should use cache
    title = "Attention is All You Need"

    logger.info(f"\nResolving venue for: {title}")

    logger.info("First call (will query API)...")
    start_time = asyncio.get_event_loop().time()
    result1 = await resolver.resolve_venue(title)
    time1 = asyncio.get_event_loop().time() - start_time

    logger.info("Second call (will use cache)...")
    start_time = asyncio.get_event_loop().time()
    result2 = await resolver.resolve_venue(title)
    time2 = asyncio.get_event_loop().time() - start_time

    logger.info(f"\nFirst call: {time1:.3f}s - {result1['source']}")
    logger.info(f"Second call: {time2:.3f}s - {result2['source']}")
    logger.info(f"Cache speedup: {time1/max(time2, 0.001):.1f}x faster")

    # Show cache contents
    logger.info(f"\nCache size: {len(resolver.cache)} entries")
    if resolver.cache:
        logger.info("Cache entries:")
        for cached_title, info in list(resolver.cache.items())[:3]:
            logger.info(
                f"  - {cached_title}: {info['venue']} "
                f"({info['source']}, {info['citations']} citations)"
            )


async def example_batch_processing():
    """Example 5: Batch processing large result sets."""
    logger.info("\n" + "=" * 60)
    logger.info("Example 5: Batch Processing")
    logger.info("=" * 60)

    # Simulate large number of results
    large_result_set = []
    for i in range(5):  # Use 5 for demo, could be 100+
        large_result_set.append(
            {
                "title": f"Research Paper {i+1}",
                "authors": [f"Author {i+1}"],
                "year": 2024 - (i % 3),
                "abstract": "Sample abstract",
                "url": f"http://arxiv.org/abs/240{i:02d}.{i+1:05d}",
            }
        )

    enhancer = ArXivEnhancer(cache_dir=Path(".cache"))

    logger.info(f"Processing {len(large_result_set)} papers...")

    # Enhance all
    enhanced = await enhancer.enhance_results(large_result_set)

    # Summarize results
    logger.info(f"\nProcessed {len(enhanced)} papers")

    venues = {}
    for paper in enhanced:
        venue = paper.get("venue", "Unknown")
        venues[venue] = venues.get(venue, 0) + 1

    logger.info("Venue distribution:")
    for venue, count in sorted(venues.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  - {venue}: {count} papers")

    # Calculate average quality
    avg_quality = sum(
        enhancer.get_quality_score(p) for p in enhanced
    ) / len(enhanced)
    logger.info(f"Average quality score: {avg_quality:.3f}")


async def main():
    """Run all examples."""
    try:
        await example_basic_enhancement()
        await example_quality_scoring()
        await example_filter_papers()
        await example_cache_usage()
        await example_batch_processing()

        logger.info("\n" + "=" * 60)
        logger.info("All examples completed successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error running examples: {str(e)}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
