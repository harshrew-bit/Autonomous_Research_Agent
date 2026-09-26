# Autonomous Research Agent

The Autonomous Research Agent is an autonomous system that accepts a high-level research goal, decomposes it into structured tasks, uses external tools to retrieve web information, evaluates intermediate findings, recovers from failures via retries or dynamic replanning, filters and deduplicates gathered evidence, and synthesizes a structured Markdown research report. The system is designed as a CLI-first Agentic AI prototype, pairing large language model reasoning with deterministic, stateful execution orchestration.

---

## Why This Is Agentic

Traditional search scripts and data pipelines execute fixed, linear sequences of pre-programmed steps without inspecting runtime feedback or adapting to intermediate findings. In contrast, this system exhibits agentic characteristics across the full research lifecycle:

* **LLM-Driven Goal Analysis:** Rather than executing raw keyword searches, the system breaks user objectives into explicit topic domains, scope constraints, output requirements, and completion criteria.
* **Dynamic Task Planning:** The agent formulates a directed plan of targeted search and retrieval tasks specific to the goal, determining which tools to invoke and with what parameters.
* **Deterministic Execution Control:** The language model does not execute arbitrary code or communicate unchecked with external systems. Instead, deterministic application code dispatches permitted tools through an authorized registry with strict schema validation.
* **Observation and Evaluation Loop:** Every tool execution produces an observation that is systematically evaluated against task objectives by a rule-based decision engine.
* **Multi-Branch Decision Routing:** Execution transitions conditionally between `CONTINUE`, `RETRY`, `REPLAN`, `COMPLETE`, and `FAIL` based on runtime evidence and error signatures.
* **Dynamic Replanning:** When an unrecoverable failure occurs (such as an HTTP 404 or exhausted data source), the agent feeds the failure context back to the LLM to formulate an alternate investigative strategy.
* **Bounded Autonomy:** Hard execution ceilings prevent infinite looping, excessive API consumption, or runaway processes.

---

## Architecture

The system executes over a cyclic state graph built with LangGraph:

```text
User Goal
   │
   ▼
Goal Analysis (app/agent/planner.py)
   │
   ▼
Dynamic Plan Generation (app/agent/planner.py)
   │
   ▼
LangGraph Execution Loop (app/agent/graph.py)
   │
   ├──► Tool Registry (app/tools/registry.py)
   │       └──► External Tools (web_search, page_fetcher)
   │
   ├──► Evaluator Node (app/agent/evaluator.py)
   │       ├── [CONTINUE] ──► Next Plan Step
   │       ├── [RETRY]    ──► Re-execute Tool (Transient Error)
   │       ├── [REPLAN]   ──► Dynamic Replanning via LLM
   │       └── [COMPLETE] ──► Proceed to Evidence Processing
   │
   ▼
Evidence Pipeline (app/agent/evidence.py, app/utils/deduplication.py)
   │
   ▼
Report Synthesis (app/agent/synthesizer.py)
   │
   ▼
Markdown Report Export (app/agent/report_writer.py)
```

A complete visual architecture diagram and technical specifications are available in [Autonomous_Research_Agent_Architecture.pdf](Autonomous_Research_Agent_Architecture.pdf).

---

## Core Components

| Component | Implementation | Purpose |
| :--- | :--- | :--- |
| **GeminiProvider** | `app/agent/llm.py` | Interfaces with Google Gemini Developer API using `gemini-3.5-flash-lite` for structured Pydantic schema generation. |
| **LangGraph Engine** | `app/agent/graph.py` | Manages cyclic state transitions, execution boundaries, routing conditions, and research memory channels (`ResearchAgentState`). |
| **ToolRegistry** | `app/tools/registry.py` | Enforces tool authorization whitelisting, prevents arbitrary tool execution, and validates tool parameters against strict Pydantic schemas. |
| **TavilySearchProvider** | `app/tools/web_search.py` | Performs targeted external web searches via the Tavily Search API with structured result parsing. |
| **page_fetcher** | `app/tools/page_fetcher.py` | Safely fetches web pages over HTTP/HTTPS with custom SSRF IP filtering, streaming size caps, and HTML-to-text normalization. |
| **Evaluator** | `app/agent/evaluator.py` | Inspects step observations against task goals to emit deterministic decisions: `CONTINUE`, `RETRY`, `REPLAN`, `COMPLETE`, or `FAIL`. |
| **Evidence Pipeline** | `app/agent/evidence.py`<br>`app/utils/deduplication.py` | Extracts paragraph chunks, filters candidate text by keyword density, and deduplicates content via SHA-256 and token Jaccard similarity. |
| **Report Synthesizer** | `app/agent/synthesizer.py` | Prompts Gemini to synthesize verified evidence items into a structured research report with citations, findings, and takeaways. |
| **Mock Providers** | `app/agent/llm.py`<br>`app/tools/web_search.py` | Deterministic offline providers (`MockLLMProvider`, `MockSearchProvider`) enabling complete test suite execution with fault injection. |

---

## Autonomous Recovery

The agent does not assume external tool calls will succeed. The `Evaluator` inspects every step's `Observation` and dispatches execution according to a 5-state decision model:

* **CONTINUE:** The tool executed successfully and yielded informative evidence. The agent advances to the next task in the plan.
* **RETRY:** A transient failure occurred (such as a network timeout, socket disconnect, or rate limit) and the task has not exceeded its retry budget (`retry_count < 2`). The agent preserves state and re-executes the tool.
* **REPLAN:** A persistent or structural failure occurred (such as an HTTP 404, invalid domain, or empty search result), or retries were exhausted. The agent prompts the LLM with the failure context and prior steps to generate a revised plan with new investigative directions.
* **COMPLETE:** All tasks in the active plan are finished, or the gathered evidence meets research sufficiency criteria. The agent transitions to evidence processing.
* **FAIL:** Circuit breaker triggered when the global execution budget is exceeded (`step_count >= 10`), preventing infinite execution loops.

### Real Recovery Scenarios Validated

1. **Deliberate Timeout Recovery:**
   During automated failure simulation (`--simulate-failure timeout`), the initial search tool call simulated a 15-second timeout. The Evaluator intercepted the failure, issued a `RETRY` decision, and successfully re-executed the task on attempt 2 without user intervention.
2. **Live HTTP 404 Replanning:**
   During live testing against real web endpoints, a candidate URL returned an unrecoverable `HTTP 404: Not Found`. The Evaluator identified the non-transient failure and triggered `REPLAN`. Gemini analyzed the dead link and generated four revised search queries covering alternative academic literature, allowing the agent to complete research successfully.

---

## Tools

### Tavily Web Search
* File: `app/tools/web_search.py`
* Executes external web search queries using Tavily's search API.
* Returns structured `SearchResponse` objects containing title, URL, snippet, published date, and relevance score for each result.

### Page Fetcher
* File: `app/tools/page_fetcher.py`
* Retrieves remote web documents over HTTP/HTTPS, normalizes HTML structure via BeautifulSoup, and extracts clean plaintext.
* Features defense-in-depth protections:
  * **SSRF Firewall:** Resolves hostnames at the socket level prior to HTTP connection. Rejects loopback addresses (`127.0.0.0/8`, `::1`), private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local blocks (`169.254.0.0/16`), and cloud metadata IP ranges.
  * **Payload Limiting:** Streams downloads and halts transfers exceeding 2 MB to prevent memory exhaustion and zip bomb attacks.
  * **Text Truncation:** Caps extracted text at 50,000 characters per document.

### Tool Registry
* File: `app/tools/registry.py`
* Enforces explicit tool whitelisting (`TOOL_REGISTRY`). Tools cannot be dynamically introduced or invoked without registration.
* Validates runtime argument payloads against typed Pydantic models (`WebSearchInput`, `PageFetcherInput`) prior to execution.

---

## Evidence Processing

The evidence pipeline (`app/agent/evidence.py`, `app/utils/deduplication.py`) processes raw web text into verified, grounded research items through four sequential stages:

1. **Candidate Extraction:** Splits raw page text and search snippets into discrete paragraph-level chunks (100–1,500 characters), discarding boilerplate, navigation fragments, and script remnants.
2. **Relevance Filtering:** Evaluates candidate chunks against query terms. A chunk must meet or exceed a keyword density threshold of **0.30** to be retained as relevant evidence.
3. **Multi-Signal Deduplication:** Prevents redundant source information from saturating the synthesis context:
   * **Exact Hash Matching:** Chunks with identical SHA-256 hashes are discarded.
   * **Lexical Similarity:** Candidate chunks are tokenized and compared via Jaccard similarity. Chunks with a similarity coefficient of **0.75 or higher** are treated as duplicate information and pruned.
4. **Source Traceability & Synthesis Grounding:** Each verified evidence item maintains strict metadata linkage (source URL, title, ingest timestamp). The synthesizer uses these items to back every claim with bibliographic citations.

---

## LLM / Planning Design

The agent uses **Gemini 3.5 Flash-Lite** (`gemini-3.5-flash-lite`) via the Google GenAI SDK (`google-genai`).

### Closed Planning Schema vs. Runtime Plan
The Gemini Developer API enforces strict OpenAPI validation rules for structured generation and rejects schemas containing open-ended dictionary types or unsupported `additionalProperties`.

To ensure complete API compatibility, the planning system decouples the LLM structured generation contract from the internal execution runtime:

* **LLM Planning Contract (`LLMPlan`, `PlannedTask`, `ToolInput` in `app/models/schemas.py`):**
  Defines an explicitly typed closed schema where tool parameters (`query`, `url`, `max_results`) are declared as concrete fields rather than arbitrary dictionaries (`Dict[str, Any]`).
* **Runtime Execution State (`Plan`, `Task`):**
  The agent converts validated `LLMPlan` instances into runtime `Plan` models used by the LangGraph execution loop and Tool Registry.

This decoupling guarantees that the LLM produces valid, parseable task definitions while retaining dynamic runtime flexibility.

---

## Security & Robustness

The codebase implements the following concrete security and resilience controls:

* **SSRF Guardrails:** Custom socket-level DNS verification prevents connection to private, internal, loopback, or cloud metadata network interfaces.
* **Scheme Whitelisting:** Restricts outgoing connections strictly to `http` and `https`.
* **Payload Size Ceiling:** 2 MB streaming transfer limit per HTTP request.
* **Extraction Bounds:** 50,000-character content extraction ceiling per page.
* **Tool Authorization Whitelist:** Registry rejects unauthorized tool names.
* **Pydantic Schema Validation:** Strict type enforcement on tool input parameters.
* **Closed Gemini Schemas:** Eliminates open-ended schema dictionaries, preventing model serialization faults.
* **Step Budget Guard:** Maximum ceiling of 10 execution steps per research session.
* **Task Retry Bound:** Maximum of 2 retries per task before transitioning to replanning.
* **Credential Protection:** Environment credentials (`GEMINI_API_KEY`, `TAVILY_API_KEY`) are managed via `.env`, excluded by `.gitignore`, and redacted from logs and trace outputs.

---

## Testing

The test suite contains **66 automated tests** that execute completely offline with zero external network dependencies in approximately 3.0 seconds:

```bash
.venv/bin/pytest -v
```

### Major Test Suites

* **Agent Execution Loop (`tests/test_agent_loop.py` - 17 tests):**
  Validates Tool Registry authorization, dynamic argument derivation, executor dispatch, full LangGraph state machine progression, step limits, and the complete evaluator decision matrix (`CONTINUE`, `RETRY`, `REPLAN`, `COMPLETE`, `FAIL`).
* **Evidence Pipeline & Deduplication (`tests/test_evidence.py` - 15 tests):**
  Validates paragraph extraction, relevance thresholding, exact SHA-256 deduplication, token Jaccard similarity filtering, and synthesis schema aggregation.
* **Planning Schemas & Gemini Compatibility (`tests/test_planning_schema.py` - 6 tests):**
  Validates that `LLMPlan`, `PlannedTask`, and `ToolInput` contain no `additionalProperties`, verifying compatibility with Gemini Developer API constraints.
* **Tools & Security Guardrails (`tests/test_tools.py` - 17 tests):**
  Validates Tavily search parsing, error handling, page fetcher parsing, 2 MB size caps, SSRF private IP blocking, loopback blocking, and metadata URL rejection.
* **Goal Analysis & Planner Integration (`tests/test_phase2.py` - 6 tests):**
  Validates goal decomposition, prompt construction, and plan generation using mock backends.
* **Smoke Tests (`tests/test_smoke.py` - 5 tests):**
  Verifies environment configuration, package imports, and fundamental state models.

Deterministic testing is achieved through `MockLLMProvider` and `MockSearchProvider`, which support configurable fault simulation without consuming API quota.

---

## Quick Start

### 1. Prerequisites
* Python 3.12+
* Virtual environment tool (`venv`)

### 2. Environment Setup
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure API Credentials
Create a `.env` file in the project root based on `.env.example`:

```bash
cp .env.example .env
```

Set your credentials in `.env`:
```env
# LLM Configuration
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite

# Search Tool Configuration
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=your_actual_tavily_api_key_here
```

*Note: Never commit `.env` to version control. The repository `.gitignore` ensures credentials remain local.*

---

## Running the Agent

### Live Research Execution
To run an autonomous research investigation using live Gemini 3.5 Flash-Lite and Tavily Search:

```bash
python app/main.py "Research recent advances in agentic AI systems, focusing on planning, tool use, memory, and self-correction." --provider gemini --search-provider tavily
```

A simpler query example:
```bash
python app/main.py "Research recent developments in transformer context windows" --provider gemini --search-provider tavily
```

### Offline Execution (Mock Mode)
To run the full planning, tool execution, evidence processing, and synthesis cycle without API credentials:

```bash
python app/main.py "Investigate autonomous agents" --provider mock --search-provider mock
```

---

## Failure Simulation

The repository includes built-in fault injection to demonstrate deterministic error handling and autonomous recovery without external API calls:

```bash
python app/main.py "Research agentic workflows" --provider mock --search-provider mock --simulate-failure timeout
```

**What this demonstrates:**
1. The search provider injects a synthetic 15-second network timeout on its first tool call.
2. The Evaluator detects the transient timeout and issues a `RETRY` decision (attempt 1/2).
3. The agent re-executes the search on Step 2 (`(RETRY)`), which succeeds.
4. The agent proceeds to page fetching, evidence deduplication, and report synthesis.

*Note: Mock runs and failure simulations are intended for testing and verification; they generate synthetic data and do not represent external web research.*

---

## Output

Generated research reports are exported as formatted Markdown documents to:

```text
reports/
```

Filenames are automatically derived from the sanitized research query (for example: `reports/research_recent_advances_in_agentic_ai_systems_focusing_on_p.md`). Reports include an executive summary, structured key findings, architectural insights, actionable takeaways, and a complete bibliography of cited source URLs.

---

## Assessment Evidence

The following formal documentation artifacts accompany this implementation:

| Artifact | File Formats | Purpose & Scope |
| :--- | :--- | :--- |
| **Architecture Diagram** | `Autonomous_Research_Agent_Architecture.png`<br>`Autonomous_Research_Agent_Architecture.pdf`<br>`Autonomous_Research_Agent_Architecture.mmd` | Visual system architecture diagram showing all components, LangGraph nodes, tool interfaces, evaluator decision loops, and evidence pipelines. |
| **Design Write-up** | `Autonomous_Research_Agent_Design_Writeup.md`<br>`Autonomous_Research_Agent_Design_Writeup.pdf` | Concise 1-page engineering design document detailing architecture decisions, failure handling, security controls, testing strategy, and design philosophy. |
| **Sample Run Transcripts** | `Autonomous_Research_Agent_Sample_Run_Transcripts.md`<br>`Autonomous_Research_Agent_Sample_Run_Transcripts.pdf` | Verbatim execution logs covering three core scenarios: 1) Live nominal research run; 2) Deliberate timeout fault injection and retry; 3) Live HTTP 404 error and dynamic replanning. |
| **Labeled Test Traces** | `Autonomous_Research_Agent_Test_Traces.md`<br>`Autonomous_Research_Agent_Test_Traces.pdf` | Detailed trace matrix documenting `TRACE-001` (mock integration), `TRACE-002` (synthetic retry), and `TRACE-003` (live 404 replan), with mock mechanics and verified test assertions. |

---

## Limitations

* **CLI-First Interface:** The prototype operates via terminal command-line interface; it does not provide an interactive web dashboard or real-time GUI.
* **Lexical Relevance Scoring:** Relevance filtering relies on keyword density metrics rather than learned dense embedding rerankers.
* **Lexical Deduplication:** Content deduplication uses exact SHA-256 hashing and token Jaccard similarity rather than semantic vector cosine similarity.
* **Single-Agent Execution Topology:** The agent orchestrates tools through a centralized state machine rather than a hierarchical multi-agent supervisor pattern with concurrent sub-agents.
* **External Provider Dependency:** Live mode requires network availability and active credentials for the Google Gemini Developer API and Tavily Search API.
* **Synthesis Latency:** Report generation processes accumulated evidence in a single context window call; latency increases proportionally with large evidence sets.

*This project is an engineering prototype developed for technical assessment purposes and is not intended as a multi-tenant commercial production service.*

---

## Project Structure

```text
Autonomous_Research_Agent/
├── app/
│   ├── main.py                  # CLI entry point, argument parsing, runtime loop trigger
│   ├── agent/
│   │   ├── evaluator.py         # Evaluator node & 5-state decision engine (CONTINUE/RETRY/REPLAN/COMPLETE/FAIL)
│   │   ├── evidence.py          # Candidate chunk extraction, relevance filtering, evidence pool
│   │   ├── executor.py          # Tool call resolution & step execution dispatcher
│   │   ├── graph.py             # LangGraph StateGraph assembly, node bindings, conditional routing
│   │   ├── llm.py               # GeminiProvider (gemini-3.5-flash-lite) & MockLLMProvider
│   │   ├── planner.py           # Goal analysis, dynamic plan generation, dynamic replanning
│   │   ├── report_writer.py     # Markdown report export and filesystem management
│   │   ├── state.py             # ResearchAgentState definition & LangGraph channels
│   │   └── synthesizer.py       # Evidence-grounded research report synthesis
│   ├── models/
│   │   └── schemas.py           # Pydantic schemas (GoalAnalysis, LLMPlan, runtime Plan/Task, EvidenceItem, Report)
│   ├── tools/
│   │   ├── page_fetcher.py      # HTTP fetcher with SSRF firewall, 2 MB payload cap, text extraction
│   │   ├── registry.py          # ToolRegistry whitelist & Pydantic input validation
│   │   └── web_search.py        # TavilySearchProvider & MockSearchProvider with fault simulation
│   └── utils/
│       ├── deduplication.py     # SHA-256 and token Jaccard similarity deduplication algorithms
│       └── logging.py           # Rich-based formatted logging and execution trace panels
├── tests/
│   ├── conftest.py              # Pytest fixtures and mock environment initialization
│   ├── test_agent_loop.py       # 17 tests: Evaluator matrix, retry exhaustion, replanning, loop execution
│   ├── test_evidence.py         # 15 tests: Extraction, relevance threshold, SHA-256 & Jaccard deduplication
│   ├── test_phase2.py           # 6 tests: Goal analysis, prompt formatting, planner integration
│   ├── test_planning_schema.py  # 6 tests: Closed schema validation, no additionalProperties
│   ├── test_smoke.py            # 5 tests: Package imports, configuration loading, basic schema tests
│   └── test_tools.py            # 17 tests: Tavily parsing, page fetcher, SSRF blocking, 2 MB limit
├── reports/                     # Directory for generated markdown research reports (.gitignored)
├── .env.example                 # Environment configuration template
├── .gitignore                   # Excludes .env, virtualenvs, __pycache__, reports/
├── pyproject.toml               # Project metadata and pytest configuration
└── requirements.txt             # Python runtime dependencies
```
