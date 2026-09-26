# Autonomous Research Agent

> A production-ready, autonomous research agent built with **LangGraph**, **Pydantic**, and Python 3.12 for the Agentic AI Engineer Intern technical assessment.

## Overview

The **Autonomous Research Agent** accepts high-level user research queries, extracts structured goal parameters, autonomously formulates dynamic multi-step execution plans, dispatches authorized research tools, observes results, and dynamically adapts, retries, or replans based on feedback.

---

## Architecture (Phase 4)

```
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
                +------------> execute_step
                |                   |
                |                   v
                |             evaluate_step
                |                   |
 (continue / retry)                 +---------------+---------------+
                +-------------------|               |               |
                |                   v (replan)      v (complete)    v (fail)
                |           replan_research        END             END
                +-------------------+
```

---

## Key Modules & Responsibilities

1. **LLM Provider Abstraction (`app/agent/llm.py`)**: Provider-agnostic interface (`LLMProvider`) supporting Google Gemini (`GeminiProvider`) and deterministic mock backends (`MockLLMProvider`) for offline testing without API keys.
2. **Goal Analysis (`app/agent/planner.py`)**: High-level goal breakdown extracting objective, domain topic, scope constraints, time boundaries, output requirements, and success criteria.
3. **Dynamic Decomposition & Replanning (`app/agent/planner.py`)**: The LLM dynamically constructs tailored task sequences with sub-objectives, tool recommendations, and dependencies. If a strategy fails, `replan_research` autonomously pivots to alternative sources.
4. **Tool Registry & Safe Dispatcher (`app/tools/registry.py`)**:
   - `TOOL_REGISTRY` enforces strict whitelisting and validates tool inputs using Pydantic schemas (`WebSearchInput`, `PageFetcherInput`).
   - Prevents arbitrary code execution and rejects unauthorized tool names.
5. **Execution Node (`app/agent/executor.py`)**:
   - Resolves tool calls dynamically (e.g. derives search queries from task objectives, passes unvisited URLs to page fetcher).
   - Records structured `Observation` containers and updates state memory.
6. **Evaluator Node (`app/agent/evaluator.py`)**:
   - Evaluates step observations and determines next actions: `CONTINUE`, `RETRY`, `REPLAN`, `COMPLETE`, or `FAIL`.
   - Distinguishes between transient errors (timeouts -> bounded retries) and structural issues (empty search results -> replanning).
   - Enforces configurable `--max-steps` guards to prevent infinite runaway loops.
7. **External Tools**:
   - **Web Search Tool (`app/tools/web_search.py`)**: Tavily and Mock providers with timeout, empty result, and rate-limit resilience.
   - **Page Fetcher Tool (`app/tools/page_fetcher.py`)**: Robust HTML content extraction with active SSRF protection, response size limits (2MB), text truncation (50k chars), whitespace normalization, and SHA-256 deduplication hashing.

*Note: Final structured report synthesis, content deduplication, and export (Markdown/PDF) will be implemented in Phase 5.*

---

## Security Safeguards

- **SSRF Protection**: `validate_url_ssrf_safe()` blocks requests to private IPv4/IPv6 ranges (RFC 1918), loopback (`127.0.0.1`, `localhost`), link-local (`169.254.0.0/16`), cloud metadata endpoints (`metadata.google.internal`), and non-HTTP schemes.
- **Resource Limiting**: Response size is capped at 2MB via streaming download to guard against zip bombs and memory exhaustion. Body text is truncated to 50,000 characters.
- **Tool Sandbox**: The agent cannot invoke arbitrary Python methods; only explicitly registered tools in `TOOL_REGISTRY` can be called.

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

## Running the Agent (CLI)

### 1. Offline Execution (Mock Mode)
Run the full planning, tool execution, and evaluation cycle without API keys:
```bash
python app/main.py "Research the latest developments in Agentic AI" --provider mock --search-provider mock
```

### 2. Live Execution (Gemini + Tavily)
Requires `GEMINI_API_KEY` and `TAVILY_API_KEY` set in `.env`:
```bash
python app/main.py "Research recent advances in vision language models"
```

### 3. Deliberately Induced Failure Demo
Simulate a transient network timeout to demonstrate retry recovery:
```bash
python app/main.py "Research agentic workflows" --provider mock --search-provider mock --simulate-failure timeout
```

Simulate an empty search result to demonstrate autonomous replanning:
```bash
python app/main.py "Research agentic workflows" --provider mock --search-provider mock --simulate-failure empty
```

---

## Running Tests

Run the full pytest suite (no API keys required; 100% mocked offline):

```bash
pytest
```
