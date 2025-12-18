# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Query Validator - Validates and sanitizes search queries before execution
to prevent malformed queries from breaking the search pipeline.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class QueryValidator:
    """Validates and sanitizes search queries to prevent common issues."""
    
    # Common problematic patterns that cause search failures
    PROBLEMATIC_PATTERNS = [
        (r'[,;]\s*$', 'trailing_comma_or_semicolon'),  # Trailing commas/semicolons
        (r'\s+(AND|OR|NOT)\s*$', 'trailing_boolean_operator'),  # Trailing operators
        (r'AND\s*AND', 'double_and'),  # Double AND
        (r'OR\s*OR', 'double_or'),  # Double OR
        (r'\(\s*\)', 'empty_parentheses'),  # Empty parentheses
        (r'"\s*"', 'empty_quotes'),  # Empty quoted strings
        (r'\s{2,}', 'excessive_whitespace'),  # Multiple spaces
    ]
    
    # Boolean operators that should be properly spaced
    BOOLEAN_OPERATORS = ['AND', 'OR', 'NOT']
    
    @staticmethod
    def validate_query(query: str) -> Tuple[bool, str, Optional[str]]:
        """
        Validate a search query for common issues.
        
        Args:
            query: The search query to validate
            
        Returns:
            Tuple of (is_valid, cleaned_query, error_message)
            - is_valid: True if query is valid
            - cleaned_query: The cleaned query string
            - error_message: Error message if invalid (None if valid)
        """
        if not query:
            return False, "", "Query is empty"
        
        if not isinstance(query, str):
            return False, "", f"Query must be string, got {type(query)}"
        
        query = query.strip()
        
        if len(query) < 2:
            return False, "", "Query is too short (minimum 2 characters)"
        
        # Clean and validate
        cleaned_query, issues = QueryValidator._clean_query(query)
        
        if issues:
            logger.warning(f"Query validation found issues: {', '.join(issues)}")
        
        # Check if cleaned query is empty
        if not cleaned_query or not cleaned_query.strip():
            return False, "", "Query became empty after cleaning"
        
        return True, cleaned_query, None if not issues else f"Cleaned issues: {', '.join(issues)}"
    
    @staticmethod
    def _clean_query(query: str) -> Tuple[str, List[str]]:
        """
        Clean a query by fixing common issues.
        
        Args:
            query: The query to clean
            
        Returns:
            Tuple of (cleaned_query, list_of_issues_fixed)
        """
        issues_fixed = []
        
        # Start with the original query
        cleaned = query.strip()
        
        # Fix trailing commas and semicolons
        if re.search(r'[,;]\s*$', cleaned):
            cleaned = re.sub(r'[,;]\s*$', '', cleaned)
            issues_fixed.append('removed_trailing_comma_or_semicolon')
        
        # Fix trailing Boolean operators
        if re.search(r'\s+(AND|OR|NOT)\s*$', cleaned):
            cleaned = re.sub(r'\s+(AND|OR|NOT)\s*$', '', cleaned)
            issues_fixed.append('removed_trailing_boolean_operator')
        
        # Fix double Boolean operators (AND AND -> AND, etc.)
        if re.search(r'AND\s+AND', cleaned):
            cleaned = re.sub(r'AND\s+AND', 'AND', cleaned)
            issues_fixed.append('fixed_double_and')
        
        if re.search(r'OR\s+OR', cleaned):
            cleaned = re.sub(r'OR\s+OR', 'OR', cleaned)
            issues_fixed.append('fixed_double_or')
        
        # Fix empty parentheses
        if re.search(r'\(\s*\)', cleaned):
            cleaned = re.sub(r'\(\s*\)', '', cleaned)
            issues_fixed.append('removed_empty_parentheses')
        
        # Fix empty quotes
        if re.search(r'"\s*"', cleaned):
            cleaned = re.sub(r'"\s*"', '', cleaned)
            issues_fixed.append('removed_empty_quotes')
        
        # Fix excessive whitespace
        if re.search(r'\s{2,}', cleaned):
            cleaned = re.sub(r'\s{2,}', ' ', cleaned)
            issues_fixed.append('normalized_whitespace')
        
        # Remove orphaned Boolean operators (AND/OR/NOT at beginning)
        if re.match(r'^(AND|OR|NOT)\s+', cleaned):
            cleaned = re.sub(r'^(AND|OR|NOT)\s+', '', cleaned)
            issues_fixed.append('removed_leading_boolean_operator')
        
        # Clean up whitespace around parentheses
        cleaned = re.sub(r'\s*\(\s*', '(', cleaned)
        cleaned = re.sub(r'\s*\)\s*', ')', cleaned)
        
        # Final cleanup
        cleaned = cleaned.strip()
        
        return cleaned, issues_fixed
    
    @staticmethod
    def validate_query_list(queries: List[str]) -> Dict[str, any]:
        """
        Validate a list of queries.
        
        Args:
            queries: List of queries to validate
            
        Returns:
            Dictionary with validation results
        """
        if not queries:
            return {
                'valid_queries': [],
                'invalid_queries': [],
                'all_valid': False,
                'summary': 'No queries provided'
            }
        
        valid_queries = []
        invalid_queries = []
        
        for query in queries:
            is_valid, cleaned_query, error_msg = QueryValidator.validate_query(query)
            
            if is_valid:
                valid_queries.append({
                    'original': query,
                    'cleaned': cleaned_query,
                    'status': 'valid'
                })
            else:
                invalid_queries.append({
                    'original': query,
                    'error': error_msg,
                    'status': 'invalid'
                })
        
        return {
            'valid_queries': valid_queries,
            'invalid_queries': invalid_queries,
            'all_valid': len(invalid_queries) == 0,
            'valid_count': len(valid_queries),
            'invalid_count': len(invalid_queries),
            'total_count': len(queries),
            'summary': f"{len(valid_queries)}/{len(queries)} queries are valid"
        }


def validate_and_clean_query(query: str) -> str:
    """
    Convenience function to validate and clean a single query.
    
    Args:
        query: The query to validate and clean
        
    Returns:
        The cleaned query, or empty string if invalid
        
    Raises:
        ValueError: If query is invalid
    """
    is_valid, cleaned_query, error_msg = QueryValidator.validate_query(query)
    
    if not is_valid:
        logger.error(f"Invalid query: {error_msg}")
        raise ValueError(f"Invalid search query: {error_msg}")
    
    if error_msg:  # Has warnings but still valid
        logger.warning(f"Query cleaned: {error_msg}")
    
    return cleaned_query


def validate_and_clean_query_safe(query: str, fallback: str = "") -> str:
    """
    Safe version that returns cleaned query or fallback without raising.
    
    Args:
        query: The query to validate and clean
        fallback: Fallback query if validation fails
        
    Returns:
        The cleaned query, or fallback if invalid
    """
    try:
        is_valid, cleaned_query, error_msg = QueryValidator.validate_query(query)
        
        if not is_valid:
            logger.warning(f"Query validation failed: {error_msg}. Using fallback: {fallback}")
            return fallback
        
        return cleaned_query
        
    except Exception as e:
        logger.error(f"Error validating query: {e}. Using fallback.")
        return fallback
