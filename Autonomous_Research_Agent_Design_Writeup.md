# Autonomous Research Agent — Design Write-up

## 1. Problem & Goal
Conducting comprehensive technical research requires decomposing complex queries, exploring heterogeneous sources, tolerating live execution failures, filtering redundant data, and synthesizing coherent findings. This system implements an **autonomous web research agent** that accepts a high-level research goal, dynamically plans search and retrieval tasks, autonomously recovers from runtime errors, deduplicates and verifies collected evidence, and compiles an evidence-backed final research report.

## 2. Architecture & Design Decisions
The architecture adheres to a clean separation of concerns: **the LLM reasons and plans, while deterministic code orchestrates state transitions, enforces security boundaries, and manages execution.**

```
User Query ──► [Goal Analysis] ──► [Dynamic Planning] ──► [LangGraph Engine]
                                                               │  ▲
                                  ┌─── Evaluator Matrix ◄──────┘  │
                                  │   (CONTINUE/RETRY/REPLAN)    │
                                  ▼                               │
                            [Tool Registry] ──────────────────────┘
                       (Tavily Search / SSRF Page Fetch)
                                  │
                                  ▼
                        [Evidence Pipeline] ──► [Report Synthesis]
```

* **Reasoning Backbone (Gemini 3.5 Flash-Lite):** Chosen for fast inference, strong reasoning, and native structured outputs (`GoalAnalysis`, `LLMPlan`, `ResearchReport`).
* **Closed-Schema Planning:** To comply with Gemini Developer API constraints (which reject open-ended `additionalProperties`), planning models define strict closed schemas (`ToolInput`, `PlannedTask`, `LLMPlan`) with typed arguments (`query`, `url`, `max_results`) that map deterministically to runtime executable `Plan` and `Task` entities.
* **LangGraph Orchestration (`ResearchAgentState`):** State transitions run over a cyclic directed graph. Bounded execution loops allow dynamic replanning and retries while preserving accumulated state (`goal_analysis`, `plan`, `evidence_pool`, `trace`).
* **Tool Abstraction (`ToolRegistry`):** Strict whitelist-based tool registry with Pydantic payload validation:
  * `web_search`: Powered by Tavily API (or configurable offline mocks).
  * `page_fetcher`: Resilient HTTP client featuring an **SSRF firewall** (blocks loopback, private IPv4/IPv6, link-local, and AWS metadata addresses), a 2MB payload cap, and a 50,000-character truncation ceiling.
* **Evidence Processing Pipeline:** Raw web text is normalized into discrete chunks. Chunks undergo **relevance filtering** (query keyword density threshold $\ge 0.30$) and **multi-signal deduplication** (exact SHA-256 hash matching and token Jaccard similarity $\ge 0.75$).

## 3. Autonomous Recovery & Failure Handling
Tool execution is never assumed to succeed. The deterministic `Evaluator` inspects every step result and routes execution across five discrete states:
* `CONTINUE`: Task succeeded and returned valid evidence; advances execution index.
* `RETRY`: Transient network timeout, parse glitch, or rate limit detected; retries up to `max_retries = 2` with preserved context.
* `REPLAN`: Persistent failure (e.g., HTTP 404, invalid domain) or zero useful evidence; invokes Gemini to generate replacement tasks targeting alternative sources without aborting the research run.
* `COMPLETE`: All planned tasks finished or sufficient high-quality evidence accumulated.
* `FAIL`: Hard circuit breaker tripped if execution exceeds `max_steps = 10`, preventing infinite loops or budget depletion.

**Empirical Failure Recovery:**
1. *Induced Timeout Recovery:* Validated with `--simulate-failure timeout`, triggering an immediate `RETRY` cycle that successfully fetched fallback data on attempt two.
2. *Runtime 404 Replanning:* During live validation, an unresolvable URL from search results triggered `REPLAN`, prompting the agent to discard the broken link, generate revised search parameters, and complete report generation without human intervention.

## 4. Security & Robustness
* **SSRF Guardrails:** Custom socket-level DNS resolver validates target IPs before making requests, rejecting `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, and loopback `::1`.
* **Bounded Resource Utilization:** Fixed execution ceiling (`max_steps=10`, `max_retries=2`), 2MB streaming HTTP download limit, and maximum evidence pool sizes safeguard memory and API quotas.
* **Credential Isolation:** API keys (`GEMINI_API_KEY`, `TAVILY_API_KEY`) are loaded via environment variables, strictly ignored by version control (`.gitignore`), and scrubbed from execution logs and traces.

## 5. Testing & Validation Strategy
* **66/66 Automated Tests Passing:** Comprehensive pytest suite runs 100% offline in ~3.0s using dependency-injected `MockLLMProvider` and `MockSearchProvider` with deterministic fault injection.
* **Multi-Layer Coverage:** Validates goal analysis, closed-schema serialization, tool whitelisting, SSRF blocking, evaluator decision paths, evidence deduplication, and markdown report synthesis.
* **Live End-to-End Validation:** Fully verified against live Gemini 3.5 Flash-Lite and Tavily Search APIs on complex multi-hop research queries.

## 6. Known Limitations & Future Improvements
* **Lexical vs. Dense Semantic Matching:** Relevance and deduplication utilize lexical keyword density and Jaccard metrics; migrating to dense vector embeddings would improve semantic nuance.
* **Single-Agent Topology:** Tasks execute linearly through a central LangGraph state; a hierarchical multi-agent supervisor could run specialized sub-agents (e.g., dedicated crawler, factual verifier) in parallel.
* **Synthesis Latency on Large Corpuses:** Report synthesis processes all accumulated evidence in a single context window; recursive map-reduce summarization would support massive multi-document corpora.

## 7. Conclusion
The Autonomous Research Agent delivers reliable, bounded, and secure autonomous investigation by pairing **Gemini 3.5 Flash-Lite's reasoning** with **strict deterministic orchestration in LangGraph**. By treating tool failure and replanning as first-class citizens, the system maintains high autonomy without compromising predictability or safety.
