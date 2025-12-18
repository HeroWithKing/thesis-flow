# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging

from langchain_community.tools.arxiv import ArxivQueryRun
from langchain_community.utilities import ArxivAPIWrapper

from src.tools.decorators import create_logged_tool

logger = logging.getLogger(__name__)

# Create logged version of arxiv search tool
LoggedArxivSearch = create_logged_tool(ArxivQueryRun)


# Get the arxiv search tool
def get_web_search_tool(max_search_results: int):
    logger.info(f"Using Arxiv search with max_results={max_search_results}")
    
    return LoggedArxivSearch(
        name="web_search",
        api_wrapper=ArxivAPIWrapper(
            top_k_results=max_search_results,
            load_max_docs=max_search_results,
            load_all_available_meta=True,
        ),
    )
