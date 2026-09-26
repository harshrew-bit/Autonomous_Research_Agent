"""
Tool definitions and interface contracts for web search, page fetching, and report generation.
"""

from app.tools.web_search import (
    web_search,
    search_web,
    SearchProvider,
    TavilySearchProvider,
    MockSearchProvider,
    get_search_provider,
)
from app.tools.page_fetcher import (
    fetch_page,
    fetch_page_content,
    validate_url_ssrf_safe,
    extract_clean_text,
)
from app.tools.report_writer import export_report

__all__ = [
    "web_search",
    "search_web",
    "SearchProvider",
    "TavilySearchProvider",
    "MockSearchProvider",
    "get_search_provider",
    "fetch_page",
    "fetch_page_content",
    "validate_url_ssrf_safe",
    "extract_clean_text",
    "export_report",
]
