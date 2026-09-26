# Autonomous Research Agent

> A production-ready, autonomous research agent built with **LangGraph**, **Pydantic**, and Python 3.12 for the Agentic AI Engineer Intern technical assessment.

## Overview

The **Autonomous Research Agent** accepts high-level user research queries, extracts structured goal parameters, autonomously formulates dynamic execution plans, and executes reliable research tools with comprehensive error handling and visible tracing.

---

## Architectural Principles

1. **LLM Provider Abstraction (`app/agent/llm.py`)**: Provider-agnostic interface (`LLMProvider`) supporting Google Gemini (`GeminiProvider`) and deterministic mock backends (`MockLLMProvider`) for offline testing without API keys.
2. **Goal Analysis (`app/agent/planner.py`)**: High-level goal breakdown extracting objective, domain topic, scope constraints, time boundaries, output requirements, and success criteria.
3. **Dynamic Decomposition & Planning**: The LLM dynamically constructs tailored task sequences with sub-objectives, tool recommendations, and dependencies based on user intent.
4. **Deterministic External Tools (Phase 3)**:
   - **Web Search Tool (`app/tools/web_search.py`)**: Provider-abstracted search (`TavilySearchProvider` & `MockSearchProvider`) returning typed `SearchResponse` containers with error resilience for timeouts, rate limits, and network errors.
   - **Page Fetcher Tool (`app/tools/page_fetcher.py`)**: Robust HTML content extraction with active SSRF protection, response size limits (2MB), text truncation (50k chars), whitespace normalization, and SHA-256 deduplication hashing.
5. **Structured Validation & Recovery**: Uses Pydantic schema validation for LLM outputs and tool responses with bounded retry recovery.
6. **Visible Planning Trace (`app/utils/logging.py`)**: Renders clean, user-facing goal breakdowns, step execution tables, and tool operational logs using `Rich`.

---

## Execution Workflow

```
[Phase 2]
                      +-------------------+
                      |   User Query      |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   analyze_goal    |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   generate_plan   |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      | Visible Trace CLI |
                      +-------------------+

[Phase 3 Tools Available for Orchestration in Phase 4]
             +-----------------------+     +-----------------------+
             |   web_search Tool     |     |   page_fetcher Tool   |
             | (Tavily/Mock Provider)|     | (SSRF Guarded / HTML) |
             +-----------------------+     +-----------------------+
```

*Note: Autonomous tool orchestration (connecting planner to tool execution loops, observations, and replanning) will be connected in Phase 4.*

---

## Security Considerations (Page Fetcher)

- **SSRF Protection**: `validate_url_ssrf_safe()` blocks requests to private IPv4/IPv6 ranges (RFC 1918), loopback (`127.0.0.1`, `localhost`), link-local (`169.254.0.0/16`), cloud metadata endpoints (`metadata.google.internal`), and non-HTTP schemes.
- **Resource Limiting**: Response size is capped at 2MB via streaming download to guard against zip bombs and memory exhaustion. Body text is truncated to 50,000 characters.
- **Content Filtering**: Strips `<script>`, `<style>`, `<nav>`, `<footer>`, `<header>`, and `<noscript>` elements before extracting clean plain text.

---

## Installation & Setup

### 1. Virtual Environment & Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and set your credentials:

```bash
cp .env.example .env
```

Key environment options:
```env
# LLM Provider
LLM_PROVIDER=gemini        # Options: gemini, mock
GEMINI_API_KEY=your_key    # Required if LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash

# Search Tool Provider
SEARCH_PROVIDER=tavily     # Options: tavily, mock
TAVILY_API_KEY=your_key    # Required if SEARCH_PROVIDER=tavily
```

---

## Manual Tool Testing

You can manually invoke and test the tools from the command line:

### 1. Web Search
```bash
# Using live Tavily API (requires TAVILY_API_KEY in .env):
python -m app.tools.web_search "latest developments in Agentic AI"

# Using Mock Provider (no API key needed):
SEARCH_PROVIDER=mock python -m app.tools.web_search "latest developments in Agentic AI"
```

### 2. Page Fetcher
```bash
# Fetch and extract readable text from a public web page:
python -m app.tools.page_fetcher "https://example.com"

# Verify SSRF protection on forbidden internal hosts:
python -m app.tools.page_fetcher "http://127.0.0.1:8080"
```

---

## Running the Planner (CLI)

```bash
python app/main.py "Research the latest developments in Agentic AI" --provider mock
```

---

## Running Tests

Run the full pytest suite (no API keys required; 100% mocked offline):

```bash
pytest
```
