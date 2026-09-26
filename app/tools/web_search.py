"""
Web search tool module providing provider abstraction, Tavily integration, mock provider,
and robust error handling.
"""

from abc import ABC, abstractmethod
import asyncio
import os
import sys
from typing import Optional, List
import httpx

from app.models.schemas import SearchResponse, SearchResultItem
from app.utils.logging import get_logger, TraceLogger, console

logger = get_logger("web_search")


class SearchProvider(ABC):
    """Abstract base class for external search providers."""

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        """Execute a search query and return a structured SearchResponse."""
        pass


class TavilySearchProvider(SearchProvider):
    """Production search provider integrating with the Tavily Search API."""

    API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: Optional[str] = None, timeout_seconds: float = 15.0):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.timeout_seconds = timeout_seconds

    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        if not query or not query.strip():
            logger.warning("Empty search query provided.")
            return SearchResponse(
                query=query,
                results=[],
                provider="tavily",
                success=False,
                error="Search query cannot be empty.",
            )

        if not self.api_key:
            err = "TAVILY_API_KEY environment variable is not configured."
            logger.warning(err)
            return SearchResponse(
                query=query,
                results=[],
                provider="tavily",
                success=False,
                error=err,
            )

        payload = {
            "query": query.strip(),
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.API_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            raw_results = data.get("results", [])
            items: List[SearchResultItem] = []
            for r in raw_results:
                items.append(
                    SearchResultItem(
                        title=r.get("title", "Untitled"),
                        url=r.get("url", ""),
                        snippet=r.get("content", ""),
                        source=r.get("source"),
                        published_at=r.get("published_date"),
                        relevance_score=r.get("score"),
                    )
                )

            return SearchResponse(
                query=query,
                results=items,
                provider="tavily",
                success=True,
                error=None,
            )

        except httpx.TimeoutException as e:
            err = f"Search provider timed out after {self.timeout_seconds}s."
            logger.error(err)
            return SearchResponse(query=query, results=[], provider="tavily", success=False, error=err)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                err = "Search provider authentication failed (HTTP 401 Unauthorized)."
            elif status == 429:
                err = "Search provider rate limit exceeded (HTTP 429 Too Many Requests)."
            else:
                err = f"Search provider HTTP error: {status} - {e.response.text[:150]}"
            logger.error(err)
            return SearchResponse(query=query, results=[], provider="tavily", success=False, error=err)
        except Exception as e:
            err = f"Search request failed: {type(e).__name__} - {str(e)}"
            logger.error(err)
            return SearchResponse(query=query, results=[], provider="tavily", success=False, error=err)


class MockSearchProvider(SearchProvider):
    """Deterministic mock search provider for testing without external network calls."""

    _simulated_timeouts_count = 0

    def __init__(
        self,
        predefined_results: Optional[List[SearchResultItem]] = None,
        simulate_failure: Optional[str] = None,
    ):
        self.predefined_results = predefined_results
        self.simulate_failure = simulate_failure

    async def search(self, query: str, max_results: int = 5) -> SearchResponse:
        sim_mode = (self.simulate_failure or os.getenv("SIMULATE_FAILURE", "")).lower()

        # Simulate transient timeout on first occurrence, then succeed on retry!
        if sim_mode == "timeout" and MockSearchProvider._simulated_timeouts_count == 0:
            MockSearchProvider._simulated_timeouts_count += 1
            logger.info("[MockSearchProvider] Simulating induced transient timeout failure.")
            return SearchResponse(
                query=query,
                results=[],
                provider="mock",
                success=False,
                error="Request timed out after 15.0s (Simulated Failure for Assessment Demo).",
            )
        elif sim_mode == "empty":
            logger.info("[MockSearchProvider] Simulating induced empty search results.")
            return SearchResponse(
                query=query,
                results=[],
                provider="mock",
                success=True,
            )

        if not query or not query.strip():
            return SearchResponse(
                query=query,
                results=[],
                provider="mock",
                success=False,
                error="Search query cannot be empty.",
            )

        if self.predefined_results is not None:
            return SearchResponse(
                query=query,
                results=self.predefined_results[:max_results],
                provider="mock",
                success=True,
            )

        # Default generated mock items
        items = [
            SearchResultItem(
                title=f"Analysis of {query} - Overview",
                url="https://example.com",
                snippet=f"Detailed overview and key findings regarding {query}, highlighting practical implications.",
                source="example.com",
                published_at="2026-09-01",
                relevance_score=round(0.95 - (i * 0.05), 2),
            )
            for i in range(min(max_results, 3))
        ]
        return SearchResponse(query=query, results=items, provider="mock", success=True)


def get_search_provider(provider_type: Optional[str] = None) -> SearchProvider:
    """Factory function returning configured SearchProvider instance."""
    provider = (provider_type or os.getenv("SEARCH_PROVIDER", "tavily")).lower()
    if provider == "tavily":
        return TavilySearchProvider()
    elif provider == "mock":
        return MockSearchProvider()
    else:
        raise ValueError(f"Unsupported SEARCH_PROVIDER: '{provider}'. Supported: 'tavily', 'mock'.")


async def web_search(
    query: str,
    max_results: int = 5,
    provider: Optional[SearchProvider] = None,
) -> SearchResponse:
    """
    Executes a web search query via configured search provider and logs visible trace.

    Args:
        query: Search query string.
        max_results: Maximum results to retrieve.
        provider: Optional SearchProvider instance.

    Returns:
        Structured SearchResponse containing items or failure metadata.
    """
    active_provider = provider or get_search_provider()
    provider_name = type(active_provider).__name__

    TraceLogger.print_tool_start("web_search", f"Query='{query}' (provider={provider_name})")

    response = await active_provider.search(query=query, max_results=max_results)

    if response.success:
        TraceLogger.print_tool_success("web_search", f"Retrieved {len(response.results)} results")
    else:
        TraceLogger.print_tool_error(
            "web_search",
            target=query,
            error=response.error or "Unknown failure",
            recovery_hint="Check SEARCH_PROVIDER / TAVILY_API_KEY credentials or refine search terms.",
        )

    return response


# Backwards compatibility alias
search_web = web_search


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_query = sys.argv[1] if len(sys.argv) > 1 else "Agentic AI developments"
    console.print(f"[bold green]Running Manual Web Search Test:[/bold green] '{test_query}'")
    result = asyncio.run(web_search(test_query))
    console.print(f"Success: {result.success} | Results: {len(result.results)} | Error: {result.error}")
    for idx, r in enumerate(result.results, 1):
        console.print(f"  {idx}. [bold]{r.title}[/bold] ({r.url})")
        console.print(f"     [dim]{r.snippet}[/dim]")
