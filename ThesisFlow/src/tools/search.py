# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Union

import requests
from langchain_community.tools.arxiv import ArxivQueryRun
from langchain_community.utilities import ArxivAPIWrapper
from langchain_core.tools import BaseTool
from langchain_tavily._utilities import TAVILY_API_URL

from src.tools.decorators import create_logged_tool
from src.tools.query_optimizer import QueryOptimizer
from src.tools.result_filter import ResultFilter

logger = logging.getLogger(__name__)

# Initialize optimization tools
_query_optimizer = QueryOptimizer()
_result_filter = ResultFilter(quality_threshold=0.3)

# Create logged version of arxiv search tool
LoggedArxivSearch = create_logged_tool(ArxivQueryRun)


def _load_search_config() -> Dict[str, Any]:
    """Load search configuration from conf.yaml."""
    from src.config import load_yaml_config
    config = load_yaml_config("conf.yaml")
    return config.get("SEARCH_ENGINE", {})


def _is_chinese_text(text: str) -> bool:
    """检测文本是否包含中文字符（CJK 统一表意文字）"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False


async def _translate_query_to_english(query: str) -> str:
    """使用 LLM 将查询翻译成英文（仅在检测到中文时调用）"""
    try:
        from src.config import load_yaml_config
        from langchain_openai import ChatOpenAI
        
        config = load_yaml_config("conf.yaml")
        basic_model = config.get("BASIC_MODEL", {})
        
        # 初始化 LLM
        llm = ChatOpenAI(
            base_url=basic_model.get("base_url"),
            model_name=basic_model.get("model"),
            api_key=basic_model.get("api_key"),
            temperature=0,
        )
        
        prompt = (
            f"Translate this academic research query to English for arXiv search. "
            f"Keep technical terms and acronyms unchanged. "
            f"Return ONLY the translated query, no explanation.\n\n"
            f"Query: {query}"
        )
        
        response = await asyncio.to_thread(llm.invoke, prompt)
        translated = response.content.strip()
        
        logger.info(f"Successfully translated: '{query}' → '{translated}'")
        return translated
    
    except Exception as e:
        logger.warning(f"Translation failed, falling back to original query: {e}", exc_info=True)
        return query



def _parse_arxiv_results(results: Any) -> List[Dict]:
    """Convert ArXiv results to standard format.
    
    ArXiv tool returns formatted string with paper content.
    Convert it to standardized dict format for consistent handling.
    """
    # Handle string responses (ArxivQueryRun returns formatted strings with results)
    if isinstance(results, str):
        if not results or results.strip() == "":
            logger.debug("ArXiv returned empty string")
            return []
        # Non-empty string means ArXiv found papers and formatted them
        # Wrap the entire formatted result as a single content block
        logger.info(f"ArXiv returned formatted string with {len(results)} characters")
        return [{
            "title": "ArXiv Search Results",
            "content": results,
            "source": "arxiv"
        }]
    
    # Handle None
    if results is None:
        logger.debug("ArXiv returned None")
        return []
    
    # Handle list of results
    if isinstance(results, list):
        if len(results) == 0:
            logger.debug("ArXiv returned empty list")
            return []
        
        logger.debug(f"ArXiv returned list with {len(results)} items")
        # Convert any list format to standard dict format
        formatted = []
        for item in results:
            if isinstance(item, dict):
                formatted.append(item)
            elif isinstance(item, str):
                formatted.append({"title": "Result", "content": item, "source": "arxiv"})
            else:
                formatted.append({"title": "Result", "content": str(item), "source": "arxiv"})
        return formatted
    
    # Unknown return type - treat as potential content
    logger.debug(f"ArXiv returned unexpected type: {type(results)}, converting to string")
    content_str = str(results)
    if content_str.strip():
        return [{"title": "ArXiv Result", "content": content_str, "source": "arxiv"}]
    return []


def _call_tavily_search(query: str, max_results: int, config: Dict) -> List[Dict]:
    """Call Tavily Search API directly and return results."""
    tavily_config = config.get("tavily", {})
    api_key = config.get("tavily_api_key", "")
    
    if not api_key:
        logger.warning("Tavily API key not configured, skipping fallback search")
        return []
    
    logger.debug(f"Calling Tavily search with query: {query}, max_results: {max_results}")
    
    try:
        params = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": tavily_config.get("search_depth", "advanced"),
            "include_raw_content": tavily_config.get("include_raw_content", True),
            "include_images": tavily_config.get("include_images", True),
            "include_image_descriptions": tavily_config.get("include_image_descriptions", True),
            "include_answer": tavily_config.get("include_answer", False),
            "include_domains": tavily_config.get("include_domains", []),
            "exclude_domains": tavily_config.get("exclude_domains", []),
        }
        
        response = requests.post(
            f"{TAVILY_API_URL}/search",
            json=params,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        # Extract and format results
        results = []
        for item in result.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score", 0),
                "source": "tavily"
            })
        
        logger.info(f"Tavily API returned {len(results)} results for query: {query}")
        return results
    
    except Exception as e:
        logger.error(f"Tavily search failed: {e}", exc_info=True)
        return []


def _deduplicate_results(arxiv_results: List[Dict], tavily_results: List[Dict]) -> List[Dict]:
    """Remove duplicate results between ArXiv and Tavily based on URL/title."""
    if not arxiv_results:
        return tavily_results
    
    arxiv_urls = {r.get("url", "").lower() for r in arxiv_results if r.get("url")}
    arxiv_titles = {r.get("title", "").lower() for r in arxiv_results if r.get("title")}
    
    unique_tavily = []
    for result in tavily_results:
        url = result.get("url", "").lower()
        title = result.get("title", "").lower()
        
        # Skip if URL or title already exists in ArXiv results
        if url and url in arxiv_urls:
            continue
        if title and title in arxiv_titles:
            continue
        
        unique_tavily.append(result)
    
    return unique_tavily


class FallbackSearchTool(BaseTool):
    """Search tool that uses ArXiv primarily, falls back to Tavily if needed."""
    
    name: str = "web_search"
    description: str = "Search for academic papers and technical information with fallback to web search"
    max_results: int = 10
    fallback_threshold: int = 3
    
    def _run(self, query: str) -> str:
        """Execute the search with fallback strategy."""
        logger.info(f"Starting search for: {query}")
        
        # Step 0: 检测并翻译中文查询到英文
        english_query = query
        original_query = query
        
        if _is_chinese_text(query):
            logger.info(f"Chinese query detected, translating to English")
            try:
                # 在同步上下文中运行异步翻译
                english_query = asyncio.run(_translate_query_to_english(query))
                logger.info(f"Query translated: '{original_query}' → '{english_query}'")
            except Exception as e:
                logger.warning(f"Translation error, using original query: {e}")
                english_query = query
        
        # Step 1: Try ArXiv search using English query
        arxiv_tool = LoggedArxivSearch(
            name="web_search_arxiv",
            api_wrapper=ArxivAPIWrapper(
                top_k_results=self.max_results,
                load_max_docs=self.max_results,
                load_all_available_meta=True,
            ),
        )
        
        arxiv_results = []
        try:
            raw_result = arxiv_tool.invoke(english_query)
            logger.debug(f"Raw ArXiv result type: {type(raw_result)}, value sample: {str(raw_result)[:100]}")
            
            arxiv_results = _parse_arxiv_results(raw_result)
            arxiv_count = len(arxiv_results)
            logger.info(f"ArXiv search parsed to {arxiv_count} valid results")
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}", exc_info=True)
            arxiv_results = []
        
        # Step 1.5: If ArXiv results are insufficient, try optimized queries
        arxiv_count = len(arxiv_results)
        if arxiv_count < self.fallback_threshold:
            logger.info(f"ArXiv returned {arxiv_count} results (< threshold {self.fallback_threshold}), optimizing query...")
            
            try:
                optimized_queries = _query_optimizer.optimize_description(english_query)
                # Limit to 3 optimized queries
                optimized_queries = optimized_queries[:3]
                
                for opt_query in optimized_queries:
                    try:
                        logger.debug(f"Searching ArXiv with optimized query: {opt_query}")
                        extra_raw = arxiv_tool.invoke(opt_query)
                        extra_results = _parse_arxiv_results(extra_raw)
                        
                        if extra_results:
                            arxiv_results.extend(extra_results)
                            logger.debug(f"Optimized query '{opt_query}' added {len(extra_results)} results")
                    except Exception as e:
                        logger.debug(f"Optimized ArXiv query failed for '{opt_query}': {e}")
                        continue
                
                arxiv_count = len(arxiv_results)
                logger.info(f"After optimization: ArXiv now has {arxiv_count} results")
            except Exception as e:
                logger.warning(f"Query optimization failed: {e}", exc_info=True)
        
        # Step 2: Check if fallback is needed
        arxiv_count = len(arxiv_results)
        if arxiv_count < self.fallback_threshold:
            logger.info(
                f"ArXiv returned {arxiv_count} results (< threshold {self.fallback_threshold}), "
                "triggering Tavily fallback"
            )
            
            config = _load_search_config()
            # Use original query for Tavily (supports Chinese)
            tavily_results = _call_tavily_search(
                original_query, 
                self.max_results - arxiv_count,
                config
            )
            tavily_count = len(tavily_results)
            logger.info(f"Tavily fallback returned {tavily_count} results")
            
            # Deduplicate and combine results
            unique_tavily = _deduplicate_results(arxiv_results, tavily_results)
            unique_count = len(unique_tavily)
            logger.info(f"After deduplication: {unique_count} unique Tavily results added")
            
            final_results = arxiv_results + unique_tavily
        else:
            logger.info(f"ArXiv returned {arxiv_count} results (>= threshold {self.fallback_threshold}), "
                       "no fallback needed")
            final_results = arxiv_results
        
        # Step 3: Apply intelligent ranking and filtering (DISABLED)
        # Disabled to diagnose search quality issues - ResultFilter was over-filtering results
        # if final_results:
        #     try:
        #         query_keywords = english_query.split()
        #         final_results = _result_filter.filter_and_rank(final_results, query_keywords)
        #         logger.debug(f"After ResultFilter: {len(final_results)} results remain")
        #     except Exception as e:
        #         logger.warning(f"Result filtering failed: {e}, using unfiltered results", exc_info=True)
        
        # Step 4: Format results for return
        if not final_results:
            logger.info("No search results found, returning empty message")
            return "No search results found."
        
        # Convert to readable format matching original behavior
        formatted = []
        for item in final_results:
            if isinstance(item, dict):
                title = item.get("title", "Untitled")
                content = item.get("content", "No content available")
                formatted.append(f"## {title}\n\n{content}")
            else:
                formatted.append(str(item))
        
        result_str = "\n\n".join(formatted)
        logger.info(f"Returning {len(final_results)} total search results (formatted)")
        return result_str


def get_web_search_tool(max_search_results: int) -> BaseTool:
    """Get the web search tool with fallback support."""
    config = _load_search_config()
    fallback_threshold = config.get("fallback_threshold", 3)
    
    logger.info(
        f"Initializing web search tool with max_results={max_search_results}, "
        f"fallback_threshold={fallback_threshold}"
    )
    
    return FallbackSearchTool(
        max_results=max_search_results,
        fallback_threshold=fallback_threshold,
    )
