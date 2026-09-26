"""
Tool module for performing live web search.
"""

from typing import List, Dict, Any
from app.models.schemas import SearchResultItem


async def search_web(query: str, max_results: int = 5) -> List[SearchResultItem]:
    """
    Executes a web search query via external search API (e.g. Tavily / Serper).

    Args:
        query: The search query string.
        max_results: Maximum number of search results to return.

    Returns:
        List of SearchResultItem instances containing title, url, and snippet.
    """
    raise NotImplementedError("web_search tool implementation pending Phase 2.")
