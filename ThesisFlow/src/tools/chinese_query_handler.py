# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Chinese Query Handler - Special handling for Chinese and non-English queries
to prevent incorrect decomposition and semantic loss.
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)


class ChineseQueryHandler:
    """Handle Chinese and non-English queries specially to preserve meaning."""
    
    @staticmethod
    def is_non_english(text: str) -> Tuple[bool, str]:
        """
        Detect if text is primarily non-English (Chinese, Japanese, Korean, etc.).
        
        Args:
            text: The text to check
            
        Returns:
            Tuple of (is_non_english, language_hint)
        """
        if not text:
            return False, "empty"
        
        # Count non-ASCII characters (ord > 127)
        non_ascii_count = sum(1 for c in text if ord(c) > 127)
        total_chars = len(text)
        
        if total_chars == 0:
            return False, "empty"
        
        ratio = non_ascii_count / total_chars
        
        # Detect specific languages/scripts first
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)  # CJK Unified Ideographs
        has_japanese = any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text)
        has_korean = any('\uac00' <= c <= '\ud7af' for c in text)
        has_arabic = any('\u0600' <= c <= '\u06ff' for c in text)
        
        # Determine language based on detected scripts
        if has_chinese:
            return True, "chinese"
        elif has_japanese:
            return True, "japanese"
        elif has_korean:
            return True, "korean"
        elif has_arabic:
            return True, "arabic"
        elif ratio > 0.3:
            # More than 30% non-ASCII but unknown language
            return True, "other_non_english"
        else:
            # ASCII-dominant text = English (or similar)
            return False, "english"
    
    @staticmethod
    def handle_chinese_query(query: str) -> List[str]:
        """
        Handle Chinese queries specially - keep them intact.
        
        Args:
            query: The Chinese query string
            
        Returns:
            List containing the query (usually just one item)
        """
        if not query or len(query.strip()) < 2:
            return []
        
        # Simply clean and return the query as-is
        # Don't decompose Chinese phrases into individual words
        cleaned = query.strip()
        
        logger.info(f"Handling Chinese query: {cleaned}")
        
        return [cleaned]
    
    @staticmethod
    def generate_english_variants(query: str) -> List[str]:
        """
        If the query contains both English and Chinese, generate variants.
        
        Example: "液体神经网络 liquid neural networks" 
        → ["液体神经网络", "liquid neural networks"]
        
        Args:
            query: The mixed query
            
        Returns:
            List of variant queries
        """
        variants = []
        
        # Split by common delimiters
        parts = re.split(r'[,;/\\|\s]{1,}(?=[A-Za-z]|[\u4e00-\u9fff])', query)
        
        for part in parts:
            part = part.strip()
            if len(part) >= 2:
                variants.append(part)
        
        # If only one part, just return the original
        if len(variants) <= 1:
            return [query.strip()]
        
        logger.info(f"Generated {len(variants)} variants from mixed query: {variants}")
        
        return variants
    
    @staticmethod
    def is_search_term_chinese(term: str) -> bool:
        """Check if a term is primarily Chinese."""
        if not term:
            return False
        
        chinese_count = sum(1 for c in term if '\u4e00' <= c <= '\u9fff')
        return chinese_count / len(term) > 0.5 if len(term) > 0 else False
    
    @staticmethod
    def handle_mixed_language_query(query: str) -> List[str]:
        """
        Handle queries with mixed English and Chinese content.
        
        Args:
            query: The mixed language query
            
        Returns:
            List of queries, one for each language component
        """
        queries = []
        
        # Extract English parts
        english_parts = re.findall(r'[a-zA-Z][a-zA-Z\s]*', query)
        english_query = ' '.join(english_parts).strip()
        
        # Extract Chinese parts
        chinese_parts = re.findall(r'[\u4e00-\u9fff]+', query)
        chinese_query = ''.join(chinese_parts)
        
        # Add non-empty parts to queries
        if chinese_query:
            queries.append(chinese_query)
            logger.debug(f"Chinese component: {chinese_query}")
        
        if english_query and english_query not in ['a', 'the', 'and']:
            queries.append(english_query)
            logger.debug(f"English component: {english_query}")
        
        # If no good splits, return original
        if not queries:
            queries.append(query.strip())
        
        return queries


def handle_user_query(query: str) -> List[str]:
    """
    Main entry point for handling any user query (English, Chinese, mixed).
    
    Args:
        query: The user's search query
        
    Returns:
        List of processed queries ready for search
    """
    if not query or len(query.strip()) < 2:
        return []
    
    query = query.strip()
    
    # Detect language
    is_non_english, language = ChineseQueryHandler.is_non_english(query)
    
    logger.info(f"Query language detection: is_non_english={is_non_english}, language={language}")
    logger.info(f"Original query: {query}")
    
    # Handle based on language
    if language == "chinese":
        return ChineseQueryHandler.handle_chinese_query(query)
    elif is_non_english and language != "unknown":
        # For other non-English languages, treat similarly to Chinese
        return ChineseQueryHandler.handle_chinese_query(query)
    elif ' ' in query and any('\u4e00' <= c <= '\u9fff' for c in query):
        # Mixed language
        return ChineseQueryHandler.handle_mixed_language_query(query)
    else:
        # English or already broken down, return as-is
        return [query]
