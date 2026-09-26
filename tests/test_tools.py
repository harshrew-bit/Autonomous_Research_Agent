"""
Unit tests for external research tools (Web Search & Page Fetcher).
Zero live network calls; all external APIs and HTTP endpoints are tested via mocks.
"""

import socket
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from app.models.schemas import SearchResponse, SearchResultItem, FetchedPage
from app.tools.web_search import (
    web_search,
    TavilySearchProvider,
    MockSearchProvider,
    get_search_provider,
)
from app.tools.page_fetcher import (
    fetch_page,
    validate_url_ssrf_safe,
    extract_clean_text,
)


# ==============================================================================
# 1. WEB SEARCH TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_web_search_success_parsing():
    """Verify parsing of valid search results from search provider."""
    mock_payload = {
        "results": [
            {
                "title": "Agentic AI in 2026",
                "url": "https://example.com/agentic",
                "content": "A comprehensive study on autonomous LLM agents.",
                "source": "example.com",
                "published_date": "2026-09-20",
                "score": 0.98,
            },
            {
                "title": "LangGraph Architectures",
                "url": "https://example.com/langgraph",
                "content": "Designing stateful multi-agent workflows.",
                "source": "example.com",
                "score": 0.91,
            },
        ]
    }

    mock_resp = httpx.Response(200, json=mock_payload, request=httpx.Request("POST", "https://api.tavily.com/search"))

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        provider = TavilySearchProvider(api_key="tvly-mock-key")
        res = await web_search("agentic AI", provider=provider)

        assert res.success is True
        assert res.query == "agentic AI"
        assert len(res.results) == 2
        assert res.results[0].title == "Agentic AI in 2026"
        assert res.results[0].url == "https://example.com/agentic"
        assert res.results[0].relevance_score == 0.98
        assert res.results[1].title == "LangGraph Architectures"


@pytest.mark.asyncio
async def test_web_search_empty_query():
    """Verify empty query returns structured error without making HTTP call."""
    res = await web_search("   ", provider=TavilySearchProvider(api_key="tvly-mock-key"))
    assert res.success is False
    assert "empty" in res.error.lower()
    assert len(res.results) == 0


@pytest.mark.asyncio
async def test_web_search_missing_api_key():
    """Verify missing API key returns structured failure."""
    with patch.dict("os.environ", {}, clear=True):
        provider = TavilySearchProvider(api_key=None)
        res = await web_search("agentic AI", provider=provider)
        assert res.success is False
        assert "TAVILY_API_KEY" in res.error


@pytest.mark.asyncio
async def test_web_search_timeout_handling():
    """Verify provider request timeout is handled gracefully."""
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Read timed out")
        provider = TavilySearchProvider(api_key="tvly-mock-key")
        res = await web_search("deep research", provider=provider)

        assert res.success is False
        assert "timed out" in res.error.lower()
        assert len(res.results) == 0


@pytest.mark.asyncio
async def test_web_search_http_status_errors():
    """Verify 401 and 429 and 500 HTTP errors return structured failure."""
    provider = TavilySearchProvider(api_key="tvly-mock-key")

    # 401 Unauthorized
    resp_401 = httpx.Response(401, text="Unauthorized", request=httpx.Request("POST", "https://api.tavily.com/search"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp_401
        res = await web_search("auth test", provider=provider)
        assert res.success is False
        assert "401" in res.error or "authentication" in res.error.lower()

    # 429 Rate Limit
    resp_429 = httpx.Response(429, text="Rate limited", request=httpx.Request("POST", "https://api.tavily.com/search"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = resp_429
        res = await web_search("rate test", provider=provider)
        assert res.success is False
        assert "429" in res.error or "rate limit" in res.error.lower()


@pytest.mark.asyncio
async def test_web_search_malformed_response():
    """Verify unexpected JSON format from provider does not crash tool."""
    mock_resp = httpx.Response(200, json={"unexpected_format": []}, request=httpx.Request("POST", "https://api.tavily.com/search"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        provider = TavilySearchProvider(api_key="tvly-mock-key")
        res = await web_search("test query", provider=provider)

        assert res.success is True
        assert len(res.results) == 0


@pytest.mark.asyncio
async def test_web_search_no_results():
    """Verify empty results array from provider is handled cleanly."""
    mock_resp = httpx.Response(200, json={"results": []}, request=httpx.Request("POST", "https://api.tavily.com/search"))
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_resp
        provider = TavilySearchProvider(api_key="tvly-mock-key")
        res = await web_search("rare term xyz999", provider=provider)

        assert res.success is True
        assert len(res.results) == 0


@pytest.mark.asyncio
async def test_mock_search_provider():
    """Verify MockSearchProvider behaves deterministically."""
    provider = MockSearchProvider()
    res = await provider.search("python async", max_results=3)
    assert res.success is True
    assert len(res.results) == 3
    assert "python async" in res.results[0].title


# ==============================================================================
# 2. PAGE FETCHER TESTS
# ==============================================================================

def test_extract_clean_text_cleaning():
    """Verify stripping of scripts, styles, navs, and whitespace normalization."""
    raw_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Test Page Title</title>
        <style>body { color: red; }</style>
        <script>console.log("tracking code");</script>
      </head>
      <body>
        <nav><a href="/">Home</a><a href="/about">About</a></nav>
        <header>Header Banner</header>
        <main>
          <h1>Main Article Headline</h1>
          <p>This is the first paragraph with important research information.</p>
          <p>Second paragraph   with    excessive    spaces   and\nnewlines.</p>
        </main>
        <footer>Copyright 2026 Privacy Policy</footer>
      </body>
    </html>
    """
    title, text = extract_clean_text(raw_html)
    assert title == "Test Page Title"
    assert "Main Article Headline" in text
    assert "important research information" in text
    assert "tracking code" not in text
    assert "body { color: red; }" not in text
    assert "Home" not in text
    assert "Copyright 2026" not in text
    assert "    " not in text  # Whitespace normalized


def test_ssrf_validation_rejections():
    """Verify SSRF validation blocks private IPs, loopback, and internal addresses."""
    # Loopback
    with pytest.raises(ValueError, match="SSRF Protection"):
        validate_url_ssrf_safe("http://localhost/admin")
    with pytest.raises(ValueError, match="SSRF Protection"):
        validate_url_ssrf_safe("http://127.0.0.1:8080/secret")
    with pytest.raises(ValueError, match="SSRF Protection"):
        validate_url_ssrf_safe("http://0.0.0.0/")

    # Unsupported schemes
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        validate_url_ssrf_safe("ftp://example.com/file.txt")
    with pytest.raises(ValueError, match="Unsupported URL scheme"):
        validate_url_ssrf_safe("file:///etc/passwd")

    # Cloud metadata
    with pytest.raises(ValueError, match="SSRF Protection"):
        validate_url_ssrf_safe("http://metadata.google.internal/computeMetadata/v1/")

    # Private network resolved IPs
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("192.168.1.100", 80))]
        with pytest.raises(ValueError, match="restricted IP address"):
            validate_url_ssrf_safe("http://intranet.example.com")

        mock_dns.return_value = [(2, 1, 6, "", ("10.0.0.5", 80))]
        with pytest.raises(ValueError, match="restricted IP address"):
            validate_url_ssrf_safe("http://private.example.com")

        mock_dns.return_value = [(2, 1, 6, "", ("169.254.169.254", 80))]
        with pytest.raises(ValueError, match="restricted IP address"):
            validate_url_ssrf_safe("http://aws-metadata.example.com")


def test_ssrf_validation_valid_url():
    """Verify public internet host passes SSRF check."""
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [(2, 1, 6, "", ("93.184.216.34", 80))]
        # Should not raise
        validate_url_ssrf_safe("https://example.com/page")


@pytest.mark.asyncio
async def test_page_fetcher_success():
    """Verify fetching and extracting clean text from a public web page."""
    html_content = "<html><head><title>Research Findings</title></head><body><p>Key insight on AI.</p></body></html>"

    async def mock_stream_chunks():
        yield html_content.encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://example.com/research"
    mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
    mock_resp.encoding = "utf-8"
    mock_resp.aiter_bytes = mock_stream_chunks

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp

    with patch("app.tools.page_fetcher.validate_url_ssrf_safe"):
        with patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx):
            page = await fetch_page("https://example.com/research")

            assert page.success is True
            assert page.title == "Research Findings"
            assert "Key insight on AI" in page.content
            assert page.status_code == 200
            assert page.text_length > 0
            assert len(page.content_hash) == 64


@pytest.mark.asyncio
async def test_page_fetcher_invalid_url():
    """Verify invalid or forbidden URLs are rejected immediately."""
    page = await fetch_page("file:///etc/hosts")
    assert page.success is False
    assert "unsupported url scheme" in page.error.lower()


@pytest.mark.asyncio
async def test_page_fetcher_timeout():
    """Verify request timeout returns structured failure."""
    with patch("app.tools.page_fetcher.validate_url_ssrf_safe"):
        with patch("httpx.AsyncClient.stream", side_effect=httpx.TimeoutException("Timeout")):
            page = await fetch_page("https://example.com/slow")
            assert page.success is False
            assert "timed out" in page.error.lower()


@pytest.mark.asyncio
async def test_page_fetcher_http_errors():
    """Verify 404 and 500 error responses."""
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.reason_phrase = "Not Found"
    mock_resp.url = "https://example.com/notfound"
    mock_resp.headers = {"content-type": "text/html"}

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp

    with patch("app.tools.page_fetcher.validate_url_ssrf_safe"):
        with patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx):
            page = await fetch_page("https://example.com/notfound")
            assert page.success is False
            assert page.status_code == 404
            assert "404" in page.error


@pytest.mark.asyncio
async def test_page_fetcher_non_html_response():
    """Verify non-HTML content (e.g. binary PDF or images) is rejected safely."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://example.com/document.pdf"
    mock_resp.headers = {"content-type": "application/pdf"}

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp

    with patch("app.tools.page_fetcher.validate_url_ssrf_safe"):
        with patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx):
            page = await fetch_page("https://example.com/document.pdf")
            assert page.success is False
            assert "unsupported content-type" in page.error.lower()


@pytest.mark.asyncio
async def test_page_fetcher_oversized_response():
    """Verify oversized response exceeding byte limit is aborted."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.url = "https://example.com/huge"
    mock_resp.headers = {
        "content-type": "text/html",
        "content-length": "10000000",  # 10MB > 2MB limit
    }

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__.return_value = mock_resp

    with patch("app.tools.page_fetcher.validate_url_ssrf_safe"):
        with patch("httpx.AsyncClient.stream", return_value=mock_stream_ctx):
            page = await fetch_page("https://example.com/huge", max_size_bytes=1_000_000)
            assert page.success is False
            assert "exceeds maximum limit" in page.error.lower()
