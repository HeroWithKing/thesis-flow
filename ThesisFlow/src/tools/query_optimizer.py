# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import json
import logging
import re
from typing import List, Optional
from langchain_core.tools import tool
from .query_validator import QueryValidator
from .chinese_query_handler import handle_user_query, ChineseQueryHandler

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """
    Optimizes verbose search descriptions into multiple specific, focused search queries.
    Converts natural language descriptions into Boolean search queries suitable for academic databases.
    """

    def __init__(self):
        self.keyword_extractors = {
            "domain_terms": r"\b(?:AI|artificial intelligence|deep learning|machine learning|computer vision|NLP|" +
                           r"augmented reality|AR|mixed reality|MR|virtual reality|VR|neural network|transformer|" +
                           r"blockchain|quantum|IoT|cloud|edge computing|5G|6G)\b",
            "time_keywords": r"\b(?:2024|2025|2023|2022|2021|recent|latest|current|historical|timeline|evolution)\b",
            "application_keywords": r"\b(?:medical|healthcare|education|business|retail|entertainment|gaming|" +
                                  r"manufacturing|transportation|agriculture|finance|security)\b",
            "technical_keywords": r"\b(?:algorithm|architecture|framework|model|method|approach|technique|" +
                                 r"implementation|design|protocol|standard|optimization)\b"
        }
        # Stop words for query filtering
        self.stop_words = {
            'search', 'collect', 'gather', 'information', 'find', 'about', 'the', 'and',
            'or', 'not', 'with', 'for', 'of', 'to', 'in', 'is', 'be', 'a', 'an', 'at',
            'by', 'from', 'on', 'it', 'this', 'that', 'as', 'are', 'was', 'were'
        }

    def optimize_description(self, description: str) -> List[str]:
        """
        Convert a verbose description into multiple focused search queries.

        Args:
            description: Original verbose search description

        Returns:
            List of optimized search queries
        """
        if not description or len(description.strip()) < 2:
            return []

        # Check if description is primarily non-English (Chinese, Japanese, etc.)
        # by counting non-ASCII characters
        non_ascii_count = sum(1 for c in description if ord(c) > 127)
        total_chars = len(description.strip())
        is_non_english = (non_ascii_count / total_chars) > 0.5 if total_chars > 0 else False
        
        # For non-English (especially Chinese), treat the whole phrase as a single query
        if is_non_english:
            logger.info(f"Detected non-English input (Chinese/similar). Input: {description[:50]}")
            # Simply return the description as-is, without decomposition
            cleaned = description.strip()
            if len(cleaned) > 2:
                return [cleaned]
            return []

        # Check if description already contains structured queries
        if self._is_already_structured(description):
            return self._extract_existing_queries(description)

        # For English: generate optimized queries
        return self._generate_queries_from_description(description)

    def _is_already_structured(self, description: str) -> bool:
        """Check if description already has numbered queries or Boolean operators."""
        has_numbered = bool(re.search(r"\d+\.\s*['\"]?(?:search|query|find)", description, re.IGNORECASE))
        has_boolean = bool(re.search(r"\b(?:AND|OR|NOT)\b", description))
        return has_numbered or has_boolean

    def _extract_existing_queries(self, description: str) -> List[str]:
        """Extract structured queries from description."""
        queries = []

        # Try to extract numbered queries
        numbered_queries = re.findall(
            r'\d+\.\s*["\']?([^"\'\n]+?)["\']?(?:(?=\d+\.)|$)',
            description,
            re.MULTILINE | re.IGNORECASE
        )

        if numbered_queries:
            queries = [q.strip() for q in numbered_queries if q.strip() and len(q.strip()) > 5]

        # If no numbered queries, try to split by common delimiters
        if not queries:
            for delimiter in [';', '|', '\n\n']:
                parts = description.split(delimiter)
                if len(parts) > 1:
                    queries = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]
                    break

        return queries[:5]  # Limit to 5 queries

    def _generate_queries_from_description(self, description: str) -> List[str]:
        """Generate optimized queries from verbose description."""
        queries = []

        # Extract key domain terms
        domain_terms = self._extract_terms(description, "domain_terms")
        tech_terms = self._extract_terms(description, "technical_keywords")
        app_terms = self._extract_terms(description, "application_keywords")
        time_terms = self._extract_terms(description, "time_keywords")

        # Generate Query 1: Core concept (domain terms + technical approach)
        if domain_terms or tech_terms:
            q1 = self._build_query(
                required_terms=domain_terms[:2],
                optional_terms=tech_terms[:2],
                exclude_terms=[]
            )
            if q1:
                queries.append(q1)

        # Generate Query 2: Application-focused (domain + application + time)
        if domain_terms and app_terms:
            q2 = self._build_query(
                required_terms=domain_terms[:1],
                optional_terms=app_terms[:2],
                time_filter=time_terms[0] if time_terms else None
            )
            if q2:
                queries.append(q2)

        # Generate Query 3: Technical depth (technical terms + methodology)
        if tech_terms:
            q3 = self._build_query(
                required_terms=tech_terms[:2],
                optional_terms=domain_terms[:1],
                exclude_terms=[]
            )
            if q3:
                queries.append(q3)

        # Generate Query 4: Specific focus if multiple domain/app terms exist
        if len(domain_terms) > 1 or len(app_terms) > 1:
            remaining_domain = domain_terms[1:] if len(domain_terms) > 1 else []
            remaining_app = app_terms[1:] if len(app_terms) > 1 else []

            q4 = self._build_query(
                required_terms=remaining_domain or remaining_app,
                optional_terms=[],
                time_filter=time_terms[0] if time_terms else None
            )
            if q4:
                queries.append(q4)

        # If no queries generated, create a simple fallback using primary terms only
        if not queries:
            # Extract any substantial noun phrases (4+ characters)
            words = description.split()
            
            # Filter for meaningful words (not stop words, not too short)
            important_words = [
                w.lower() for w in words 
                if len(w) > 3 and w.lower() not in self.stop_words and not w.startswith('_')
            ]
            
            if important_words:
                # Use the first 2-3 important words with simple space (not AND)
                q_fallback = " ".join(important_words[:3])
                if q_fallback.strip():
                    queries.append(q_fallback)

        # Limit to 5 queries maximum and remove duplicates
        queries = list(dict.fromkeys(queries))  # Remove duplicates while preserving order
        
        # Final validation: ensure all queries are clean
        queries = [q.strip() for q in queries if q and q.strip()]
        
        return queries[:5]

    def _extract_terms(self, text: str, term_type: str, limit: int = 5) -> List[str]:
        """Extract specific types of terms from text."""
        if term_type not in self.keyword_extractors:
            return []

        pattern = self.keyword_extractors[term_type]
        matches = re.findall(pattern, text, re.IGNORECASE)
        # Normalize and deduplicate
        terms = list(dict.fromkeys([m.lower() for m in matches]))
        return terms[:limit]

    def _build_query(self, required_terms: List[str], optional_terms: List[str] = None,
                     exclude_terms: List[str] = None, time_filter: str = None) -> str:
        """
        Build a Boolean search query from terms.

        Args:
            required_terms: Terms that MUST be in results (joined with AND)
            optional_terms: Terms that MAY be in results (joined with OR)
            exclude_terms: Terms to exclude
            time_filter: Optional time range filter

        Returns:
            Formatted Boolean search query
        """
        if not required_terms:
            return ""

        # Build required part - filter out empty strings
        clean_required_terms = [t.strip() for t in required_terms if t and t.strip()]
        if not clean_required_terms:
            return ""
            
        required_part = " AND ".join(f'"{term}"' if " " in term else term
                                    for term in clean_required_terms)

        # Build optional part
        optional_part = ""
        if optional_terms:
            # Filter out empty strings from optional terms
            clean_optional_terms = [t.strip() for t in optional_terms if t and t.strip()]
            if clean_optional_terms:
                optional_str = " OR ".join(f'"{term}"' if " " in term else term
                                          for term in clean_optional_terms)
                optional_part = f" OR ({optional_str})"

        # Build exclusion part
        exclude_part = ""
        if exclude_terms:
            # Filter out empty strings from exclude terms
            clean_exclude_terms = [t.strip() for t in exclude_terms if t and t.strip()]
            if clean_exclude_terms:
                exclude_str = " NOT ".join(clean_exclude_terms)
                exclude_part = f" NOT ({exclude_str})"

        # Combine parts - use proper Boolean operators
        parts = [p for p in [required_part, optional_part, exclude_part] if p]
        if not parts:
            return ""
            
        query = " ".join(parts)

        # Add time filter if provided
        if time_filter:
            # Only add year ranges, not subjective terms like "recent"
            if re.search(r"\d{4}", time_filter):
                year_match = re.search(r"(\d{4})[-–]?(\d{4})?", time_filter)
                if year_match:
                    query += f" {year_match.group(0)}"

        # Final cleanup: remove any trailing commas, AND, OR, NOT operators
        query = re.sub(r'\s*[,;]\s*$', '', query)  # Remove trailing commas/semicolons
        query = re.sub(r'\s+(AND|OR|NOT)\s*$', '', query)  # Remove trailing Boolean operators
        query = re.sub(r'\s+', ' ', query)  # Normalize whitespace
        
        return query.strip()


# Create global optimizer instance
_optimizer = QueryOptimizer()


@tool
def optimize_search_queries(description: str) -> str:
    """
    Convert verbose search descriptions into multiple specific search queries.
    
    Handles both English and non-English (especially Chinese) queries correctly.
    For Chinese queries, preserves them as complete phrases rather than decomposing.

    This tool analyzes a lengthy description of what to search for and converts it into
    2-5 concise, Boolean-formatted queries suitable for academic search engines like arXiv.

    Args:
        description: The verbose description of what to search for (can be English or Chinese)

    Returns:
        JSON string containing:
        - queries: List of optimized search queries
        - explanation: Brief explanation of the query strategy

    Example (English):
        Input: "Search academic databases for information related to AI glasses"
        Output: {
            "queries": ["AI glasses", "augmented reality glasses"],
            "explanation": "Query 1 focuses on core concept. Query 2 explores related terms."
        }
        
    Example (Chinese):
        Input: "液体神经网络的历史发展和应用"
        Output: {
            "queries": ["液体神经网络的历史发展和应用"],
            "explanation": "Chinese query preserved as complete phrase"
        }
    """
    try:
        if not description or len(description.strip()) < 2:
            return json.dumps({
                "queries": [],
                "explanation": "Description is too short",
                "error": "Minimum 2 characters required"
            })
        
        description = description.strip()
        
        # Check if this is a non-English (especially Chinese) query
        is_non_english, language = ChineseQueryHandler.is_non_english(description)
        
        if is_non_english and language == "chinese":
            logger.info(f"Processing Chinese query: {description}")
            # For Chinese, handle specially to preserve meaning
            optimized_queries = handle_user_query(description)
        else:
            # For English queries, use the standard optimization
            optimized_queries = _optimizer.optimize_description(description)

        if not optimized_queries:
            return json.dumps({
                "queries": [],
                "explanation": "Unable to extract meaningful search queries from the provided description.",
                "error": "No valid queries could be generated"
            })

        # Validate and clean each query
        validated_queries = []
        validation_issues = []
        
        for query in optimized_queries:
            is_valid, cleaned_query, error_msg = QueryValidator.validate_query(query)
            
            if is_valid:
                validated_queries.append(cleaned_query)
                if error_msg:
                    validation_issues.append(f"Query cleaned: {error_msg}")
            else:
                validation_issues.append(f"Query invalid: {error_msg}")
                logger.warning(f"Query validation failed: {error_msg}. Original: {query}")
        
        # If no valid queries after validation, try the original ones
        if not validated_queries:
            validated_queries = optimized_queries
            logger.warning("No queries passed validation, using original queries")
        
        # Create explanation
        explanations = []
        if len(validated_queries) > 0:
            if is_non_english and language == "chinese":
                explanations.append("Chinese phrase preserved as single query for semantic integrity")
            else:
                explanations.append("Query 1: Core concept with primary technical focus")
        if len(validated_queries) > 1:
            explanations.append("Query 2: Application-domain specific search")
        if len(validated_queries) > 2:
            explanations.append("Query 3: Technical depth and methodology focus")
        if len(validated_queries) > 3:
            explanations.append("Query 4: Extended coverage of related domains")
        if len(validated_queries) > 4:
            explanations.append("Query 5: Additional refinement or alternative perspectives")

        result = {
            "queries": validated_queries,
            "explanation": " | ".join(explanations),
            "count": len(validated_queries)
        }
        
        if validation_issues:
            result["validation_notes"] = validation_issues
        
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"Error optimizing search queries: {str(e)}")
        return json.dumps({
            "queries": [],
            "explanation": f"Error during query optimization: {str(e)}",
            "error": str(e)
        })


if __name__ == "__main__":
    # Test examples
    test_descriptions = [
        "Search academic databases (arXiv, IEEE Xplore, ACM Digital Library) for information related to AI glasses. Gather historical data such as timeline of development, early pioneers, and foundational work. Also collect current data including latest technological advances, market situation, and recent product launches.",
        "Find information about machine learning approaches in medical imaging, including deep learning techniques, convolutional neural networks, and their applications in diagnosis and treatment planning.",
        "Research quantum computing and its applications in cryptography, including quantum algorithms, post-quantum cryptography, and security implications.",
    ]

    optimizer = QueryOptimizer()
    for desc in test_descriptions:
        print(f"\nOriginal: {desc[:80]}...")
        queries = optimizer.optimize_description(desc)
        print(f"Optimized Queries:")
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")
