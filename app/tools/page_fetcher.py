"""
Page fetcher tool module providing robust HTML content extraction, SSRF security validation,
size-limiting, whitespace normalization, and comprehensive error handling.
"""

import asyncio
import ipaddress
import re
import socket
import sys
from urllib.parse import urlparse
from typing import Optional
from bs4 import BeautifulSoup
import httpx

from app.models.schemas import FetchedPage
from app.utils.deduplication import compute_content_hash
from app.utils.logging import get_logger, TraceLogger, console

logger = get_logger("page_fetcher")

# Restricted internal hostname patterns
BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "metadata.azure.com",
    "instance-data",
}

BLOCKED_TLDS = (".local", ".internal", ".localhost", ".corp", ".lan", ".home", ".test")


def validate_url_ssrf_safe(url: str) -> None:
    """
    Validates that a URL is safe to fetch and protects against SSRF (Server-Side Request Forgery).

    Checks:
      1. Scheme must be HTTP or HTTPS.
      2. Hostname must be present and not in blocked local/cloud-metadata domains.
      3. Resolved IP must not be private, loopback, link-local, multicast, or reserved.

    Raises:
        ValueError: If the URL fails any security check.
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise ValueError(f"Malformed URL: {e}")

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme '{scheme}'. Only 'http' and 'https' are permitted.")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL must include a valid hostname.")

    if hostname in BLOCKED_HOSTNAMES:
        raise ValueError(f"SSRF Protection: Access to restricted host '{hostname}' is forbidden.")

    if any(hostname.endswith(tld) for tld in BLOCKED_TLDS) or "." not in hostname:
        raise ValueError(f"SSRF Protection: Access to internal/local domain '{hostname}' is forbidden.")

    # Resolve hostname to verify IP address ranges
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for host '{hostname}': {e}")

    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                f"SSRF Protection: Host '{hostname}' resolves to restricted IP address '{ip_str}'."
            )


def extract_clean_text(html_content: str, max_text_chars: int = 50_000) -> tuple[Optional[str], str]:
    """
    Parses HTML content, strips non-content elements, extracts title and normalized text.

    Args:
        html_content: Raw HTML string.
        max_text_chars: Maximum character limit for extracted body text.

    Returns:
        Tuple of (title, cleaned_text).
    """
    soup = BeautifulSoup(html_content, "html.parser")

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Decompose non-content / boilerplate elements
    for element in soup(
        ["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "iframe", "form", "button", "menu"]
    ):
        element.decompose()

    raw_text = soup.get_text(separator=" ", strip=True)
    # Normalize excessive whitespace/newlines
    cleaned_text = re.sub(r"\s+", " ", raw_text).strip()

    if len(cleaned_text) > max_text_chars:
        cleaned_text = cleaned_text[:max_text_chars] + "... [Content Truncated]"

    return title, cleaned_text


async def fetch_page(
    url: str,
    timeout_seconds: float = 10.0,
    max_size_bytes: int = 2_000_000,
    max_text_chars: int = 50_000,
) -> FetchedPage:
    """
    Safely fetches a web page, validates SSRF security, extracts clean text, and returns structured data.

    Args:
        url: The web URL to fetch.
        timeout_seconds: Network request timeout.
        max_size_bytes: Maximum allowed byte size of HTTP response payload.
        max_text_chars: Maximum character length for extracted body text.

    Returns:
        Structured FetchedPage instance.
    """
    TraceLogger.print_tool_start("page_fetcher", url)

    # 1. SSRF and URL validation
    try:
        validate_url_ssrf_safe(url)
    except ValueError as e:
        err = str(e)
        logger.warning(f"URL validation failed for {url}: {err}")
        TraceLogger.print_tool_error("page_fetcher", url, err, "Verify the URL is valid, public, and uses HTTP/HTTPS.")
        return FetchedPage(
            url=url,
            success=False,
            error=err,
        )

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; AutonomousResearchAgent/0.1; +https://github.com/harshrew-bit/Autonomous_Research_Agent)",
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
    }

    # 2. HTTP Request with streaming size check and redirect limits
    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            async with client.stream("GET", url, headers=headers) as response:
                status_code = response.status_code
                final_url = str(response.url)
                content_type = response.headers.get("content-type", "")

                # Check HTTP status code
                if status_code != 200:
                    err = f"HTTP {status_code}: {response.reason_phrase or 'Request Failed'}"
                    logger.warning(f"Failed to fetch {url}: {err}")
                    TraceLogger.print_tool_error("page_fetcher", url, err, "Check if page is publicly accessible or try an alternative URL.")
                    return FetchedPage(
                        url=url,
                        final_url=final_url,
                        status_code=status_code,
                        content_type=content_type,
                        success=False,
                        error=err,
                    )

                # Check Content-Type (must be HTML or plain text)
                lower_ct = content_type.lower()
                if not any(t in lower_ct for t in ("text/html", "application/xhtml+xml", "text/plain")):
                    err = f"Unsupported Content-Type: '{content_type}'. Only HTML and text documents are allowed."
                    logger.warning(f"Skipping {url}: {err}")
                    TraceLogger.print_tool_error("page_fetcher", url, err, "Target resource is not an HTML or plain text document.")
                    return FetchedPage(
                        url=url,
                        final_url=final_url,
                        status_code=status_code,
                        content_type=content_type,
                        success=False,
                        error=err,
                    )

                # Content-Length header limit check
                cl_header = response.headers.get("content-length")
                if cl_header and cl_header.isdigit() and int(cl_header) > max_size_bytes:
                    err = f"Response size ({cl_header} bytes) exceeds maximum limit of {max_size_bytes} bytes."
                    logger.warning(f"Skipping {url}: {err}")
                    TraceLogger.print_tool_error("page_fetcher", url, err, "Page is too large to process safely.")
                    return FetchedPage(
                        url=url,
                        final_url=final_url,
                        status_code=status_code,
                        content_type=content_type,
                        success=False,
                        error=err,
                    )

                # Stream response body with strict byte counter
                body_chunks = []
                total_bytes = 0
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > max_size_bytes:
                        err = f"Downloaded content exceeded limit of {max_size_bytes} bytes."
                        logger.warning(f"Aborting {url}: {err}")
                        TraceLogger.print_tool_error("page_fetcher", url, err, "Response stream exceeded maximum byte limit.")
                        return FetchedPage(
                            url=url,
                            final_url=final_url,
                            status_code=status_code,
                            content_type=content_type,
                            success=False,
                            error=err,
                        )
                    body_chunks.append(chunk)

                raw_bytes = b"".join(body_chunks)
                html_text = raw_bytes.decode(response.encoding or "utf-8", errors="replace")

    except httpx.TimeoutException as e:
        err = f"Request to {url} timed out after {timeout_seconds}s."
        logger.warning(err)
        TraceLogger.print_tool_error("page_fetcher", url, err, "The target server was slow to respond. Consider retrying.")
        return FetchedPage(url=url, success=False, error=err)
    except httpx.RequestError as e:
        err = f"Network connection failed: {type(e).__name__} - {str(e)}"
        logger.warning(err)
        TraceLogger.print_tool_error("page_fetcher", url, err, "Network/DNS failure reaching host.")
        return FetchedPage(url=url, success=False, error=err)
    except Exception as e:
        err = f"Unexpected fetch error: {type(e).__name__} - {str(e)}"
        logger.error(err)
        TraceLogger.print_tool_error("page_fetcher", url, err)
        return FetchedPage(url=url, success=False, error=err)

    # 3. HTML parsing and text extraction
    title, cleaned_text = extract_clean_text(html_text, max_text_chars=max_text_chars)
    content_hash = compute_content_hash(cleaned_text) if cleaned_text else ""

    TraceLogger.print_tool_success("page_fetcher", f"Extracted {len(cleaned_text)} chars (title='{title or 'Untitled'}')")

    return FetchedPage(
        url=url,
        final_url=final_url,
        title=title,
        content=cleaned_text,
        content_hash=content_hash,
        text_length=len(cleaned_text),
        status_code=status_code,
        content_type=content_type,
        success=True,
        error=None,
    )


# Backwards compatibility alias
fetch_page_content = fetch_page


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    console.print(f"[bold green]Running Manual Page Fetcher Test:[/bold green] '{test_url}'")
    page = asyncio.run(fetch_page(test_url))
    console.print(f"Success: {page.success} | Status: {page.status_code} | Title: {page.title}")
    console.print(f"Content length: {page.text_length} chars | Hash: {page.content_hash[:16]}...")
    if page.error:
        console.print(f"[bold red]Error:[/bold red] {page.error}")
    else:
        preview = page.content[:300] + ("..." if len(page.content) > 300 else "")
        console.print(f"Preview:\n[italic]{preview}[/italic]")
