# src/tools/search_postprocessor.py
import base64
import logging
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SearchResultPostProcessor:
    """Search result post-processor"""

    base64_pattern = r"data:image/[^;]+;base64,[a-zA-Z0-9+/=]+"

    def __init__(self, min_score_threshold: float, max_content_length_per_page: int):
        """
        Initialize the post-processor

        Args:
            min_score_threshold: Minimum relevance score threshold
            max_content_length_per_page: Maximum content length
        """
        self.min_score_threshold = min_score_threshold
        self.max_content_length_per_page = max_content_length_per_page

    def process_results(self, results: List[Dict]) -> List[Dict]:
        """
        Process search results

        Args:
            results: Original search result list

        Returns:
            Processed result list
        """
        # Input validation: ensure results is a list and not None
        if not results:
            logger.debug("No results to process or results is None/empty")
            return []
        
        if not isinstance(results, list):
            logger.warning(f"Results is not a list, received: {type(results)}. Converting to empty list.")
            return []

        # Combined processing in a single loop for efficiency
        cleaned_results = []
        seen_urls = set()

        for idx, result in enumerate(results):
            try:
                # Skip invalid results
                if not isinstance(result, dict):
                    logger.debug(f"Skipping result {idx} - not a dict: {type(result)}")
                    continue
                
                # 1. Remove duplicates
                cleaned_result = self._remove_duplicates(result, seen_urls)
                if not cleaned_result:
                    continue

                # 2. Filter low quality results
                if (
                    "page" == cleaned_result.get("type")
                    and self.min_score_threshold
                    and self.min_score_threshold > 0
                    and cleaned_result.get("score", 0) < self.min_score_threshold
                ):
                    continue

                # 3. Clean base64 images from content
                cleaned_result = self._remove_base64_images(cleaned_result)
                if not cleaned_result:
                    continue

                # 4. When max_content_length_per_page is set, truncate long content
                if (
                    self.max_content_length_per_page
                    and self.max_content_length_per_page > 0
                ):
                    cleaned_result = self._truncate_long_content(cleaned_result)

                if cleaned_result:
                    cleaned_results.append(cleaned_result)
                    
            except Exception as e:
                logger.warning(f"Error processing result at index {idx}: {str(e)}. Skipping this result.")
                continue

        # 5. Sort (by score descending)
        try:
            sorted_results = sorted(
                cleaned_results, key=lambda x: x.get("score", 0), reverse=True
            )
        except Exception as sort_error:
            logger.warning(f"Error sorting results: {str(sort_error)}. Returning unsorted results.")
            sorted_results = cleaned_results

        logger.info(
            f"Search result post-processing: {len(results)} -> {len(sorted_results)}"
        )
        return sorted_results

    def _remove_base64_images(self, result: Dict) -> Dict:
        """Remove base64 encoded images from content"""
        try:
            if not isinstance(result, dict):
                logger.warning(f"Result is not a dict in _remove_base64_images: {type(result)}")
                return {}
            
            if "page" == result.get("type"):
                cleaned_result = self.processPage(result)
            elif "image" == result.get("type"):
                cleaned_result = self.processImage(result)
            else:
                # For other types, keep as is
                cleaned_result = result.copy()

            return cleaned_result
        except Exception as e:
            logger.warning(f"Error in _remove_base64_images: {str(e)}")
            return result.copy() if isinstance(result, dict) else {}

    def processPage(self, result: Dict) -> Dict:
        """Process page type result"""
        try:
            # Clean base64 images from content
            cleaned_result = result.copy()

            if "content" in result and result["content"]:
                original_content = result["content"]
                cleaned_content = re.sub(self.base64_pattern, " ", original_content)
                cleaned_result["content"] = cleaned_content

                # Log if significant content was removed
                if len(cleaned_content) < len(original_content) * 0.8:
                    logger.debug(
                        f"Removed base64 images from search content: {result.get('url', 'unknown')}"
                    )

            # Clean base64 images from raw content
            if "raw_content" in cleaned_result and cleaned_result["raw_content"]:
                original_raw_content = cleaned_result["raw_content"]
                cleaned_raw_content = re.sub(self.base64_pattern, " ", original_raw_content)
                cleaned_result["raw_content"] = cleaned_raw_content

                # Log if significant content was removed
                if len(cleaned_raw_content) < len(original_raw_content) * 0.8:
                    logger.debug(
                        f"Removed base64 images from search raw content: {result.get('url', 'unknown')}"
                    )

            return cleaned_result
        except Exception as e:
            logger.warning(f"Error in processPage: {str(e)}")
            return result.copy()

    def processImage(self, result: Dict) -> Dict:
        """Process image type result - clean up base64 data and long fields"""
        try:
            cleaned_result = result.copy()

            # Remove base64 encoded data from image_url if present
            if "image_url" in cleaned_result and isinstance(
                cleaned_result["image_url"], str
            ):
                # Check if image_url contains base64 data
                if "data:image" in cleaned_result["image_url"]:
                    original_image_url = cleaned_result["image_url"]
                    cleaned_image_url = re.sub(self.base64_pattern, " ", original_image_url)
                    if len(cleaned_image_url) == 0 or not cleaned_image_url.startswith(
                        "http"
                    ):
                        logger.debug(
                            f"Removed base64 data from image_url and the cleaned_image_url is empty or not start with http, origin image_url: {result.get('image_url', 'unknown')}"
                        )
                        return {}
                    cleaned_result["image_url"] = cleaned_image_url
                    logger.debug(
                        f"Removed base64 data from image_url: {result.get('image_url', 'unknown')}"
                    )

            # Truncate very long image descriptions
            if "image_description" in cleaned_result and isinstance(
                cleaned_result["image_description"], str
            ):
                if (
                    self.max_content_length_per_page
                    and len(cleaned_result["image_description"])
                    > self.max_content_length_per_page
                ):
                    cleaned_result["image_description"] = (
                        cleaned_result["image_description"][
                            : self.max_content_length_per_page
                        ]
                        + "..."
                    )
                    logger.info(
                        f"Truncated long image description from search result: {result.get('image_url', 'unknown')}"
                    )

            return cleaned_result
        except Exception as e:
            logger.warning(f"Error in processImage: {str(e)}")
            return result.copy()

    def _truncate_long_content(self, result: Dict) -> Dict:
        """Truncate long content"""
        try:
            truncated_result = result.copy()

            # Truncate content length
            if "content" in truncated_result and truncated_result["content"]:
                content = truncated_result["content"]
                if len(content) > self.max_content_length_per_page:
                    truncated_result["content"] = (
                        content[: self.max_content_length_per_page] + "..."
                    )
                    logger.info(
                        f"Truncated long content from search result: {result.get('url', 'unknown')}"
                    )

            # Truncate raw content length (can be slightly longer)
            if "raw_content" in truncated_result and truncated_result["raw_content"]:
                raw_content = truncated_result["raw_content"]
                if len(raw_content) > self.max_content_length_per_page * 2:
                    truncated_result["raw_content"] = (
                        raw_content[: self.max_content_length_per_page * 2] + "..."
                    )
                    logger.info(
                        f"Truncated long raw content from search result: {result.get('url', 'unknown')}"
                    )

            return truncated_result
        except Exception as e:
            logger.warning(f"Error in _truncate_long_content: {str(e)}")
            return result.copy()

    def _remove_duplicates(self, result: Dict, seen_urls: set) -> Dict:
        """Remove duplicate results"""
        try:
            url = result.get("url")
            if not url:
                image_url_val = result.get("image_url", "")
                if isinstance(image_url_val, dict):
                    url = image_url_val.get("url", "")
                else:
                    url = image_url_val

            if url and url not in seen_urls:
                seen_urls.add(url)
                return result.copy()  # Return a copy to avoid modifying original
            elif not url:
                # Keep results with empty URLs
                return result.copy()  # Return a copy to avoid modifying original

            return {}  # Return empty dict for duplicates
        except Exception as e:
            logger.warning(f"Error in _remove_duplicates: {str(e)}")
            return result.copy() if isinstance(result, dict) else {}
