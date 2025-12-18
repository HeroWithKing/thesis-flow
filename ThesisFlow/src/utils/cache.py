# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""
Caching utilities for performance optimization.

This module provides centralized caching strategies for expensive operations:
- Template caching: Avoid repeated template file I/O
- LLM instance caching: Reuse LLM instances across calls
- Configuration caching: Cache frequently accessed configuration
"""

from typing import Any, Callable, Dict, Optional

__all__ = ["TemplateCache", "get_cache_stats"]


class TemplateCache:
    """
    Singleton cache manager for prompt templates.
    Prevents repeated file I/O for the same template+locale combinations.
    """
    
    _instance: Optional["TemplateCache"] = None
    _cache: Dict[tuple[str, str], str] = {}
    _stats: Dict[str, int] = {"hits": 0, "misses": 0}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get(self, prompt_name: str, locale: str, fetcher: Callable[[str, str], str]) -> str:
        """
        Get or fetch a template from cache.
        
        Args:
            prompt_name: Name of the prompt template
            locale: Language locale (e.g., en-US, zh-CN)
            fetcher: Callable that loads the template if not in cache
        
        Returns:
            The template string
        """
        cache_key = (prompt_name, locale)
        
        if cache_key in self._cache:
            self._stats["hits"] += 1
            return self._cache[cache_key]
        
        # Cache miss - fetch template
        self._stats["misses"] += 1
        template = fetcher(prompt_name, locale)
        self._cache[cache_key] = template
        return template
    
    def clear(self):
        """Clear all cached templates."""
        self._cache.clear()
        self._stats = {"hits": 0, "misses": 0}
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "total": total,
            "hit_rate": f"{hit_rate:.1f}%",
            "cached_templates": len(self._cache)
        }


def get_cache_stats() -> Dict[str, Any]:
    """
    Get performance statistics for all caches.
    
    Returns:
        Dictionary with cache statistics
    """
    cache = TemplateCache()
    return {
        "template_cache": cache.stats()
    }
