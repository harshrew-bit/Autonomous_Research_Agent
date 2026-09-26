"""
Tool definitions and interface contracts for web search, page fetching, and report generation.
"""

from app.tools.web_search import search_web
from app.tools.page_fetcher import fetch_page_content
from app.tools.report_writer import export_report

__all__ = [
    "search_web",
    "fetch_page_content",
    "export_report",
]
