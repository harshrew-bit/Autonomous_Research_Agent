# Autonomous Research Agent

> A production-ready, autonomous research agent built with **LangGraph**, **Pydantic**, and Python 3.12 for the Agentic AI Engineer Intern technical assessment.

## Overview

The **Autonomous Research Agent** is designed to accept high-level research queries, autonomously formulate multi-step execution plans, dynamically select appropriate research tools, evaluate step results, detect failures/gaps, and gracefully adapt or replan until a structured final synthesis is produced.

Unlike fixed-pipeline scrapers, this system treats research as an iterative, graph-driven problem-solving loop with visible execution traces and robust error recovery mechanisms.

---

## Architectural Principles

1. **Dynamic Decomposition & Planning**: The agent analyzes high-level user queries and constructs an initial plan (array of concrete tasks). It does not follow a rigid `search -> fetch -> summarize` script.
2. **State Machine Orchestration (LangGraph)**: Uses LangGraph to manage cyclical state updates (`Planner -> Executor -> Evaluator -> Replanner/Finalizer`).
3. **Tool Isolation & Heterogeneity**: Tools (Web Search, Page Fetcher, Report Writer) are self-contained modules returning typed, validated data schemas.
4. **Active Reflection & Recovery**: An Evaluator node checks output quality, detects HTTP/content errors, deduplicates knowledge, and triggers replanning or retries upon failure.
5. **Deterministic Infrastructure, Reasoning Core**: Network requests, validation, parsing, logging, and deduplication run deterministically, while plan generation and content synthesis rely on LLM reasoning.

---

## Intended State Graph Cycle

```
                      +-------------------+
                      |   User Query      |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   Planner Node    |
                      +---------+---------+
                                |
                                v
                     +---------------------+
                     |    Executor Node    | <---+ (Retry / Next Step)
                     |  (Tool Invocation)  |     |
                     +----------+----------+     |
                                |                |
                                v                |
                     +---------------------+     |
                     |   Evaluator Node    |-----+
                     | (Reflection & Check)|
                     +----------+----------+
                                |
                +---------------+---------------+
                | (Success / Goals Met)        | (Failure / Gap Detected)
                v                               v
    +-----------------------+       +----------------------+
    | Report Synthesis Node |       |   Replanner Node     |
    +-----------+-----------+       +----------+-----------+
                |                              |
                v                              +---> Loop back to Executor
    +-----------------------+
    | Final Structured Output|
    +-----------------------+
```

---

## Project Structure

```
autonomous-research-agent/
│
├── app/
│   ├── agent/             # LangGraph state machine & reasoning nodes
│   │   ├── __init__.py
│   │   ├── state.py       # Pydantic & TypedDict state definitions
│   │   ├── graph.py       # LangGraph state graph assembly
│   │   ├── planner.py     # Plan formulation & decomposition node
│   │   └── evaluator.py   # Step evaluation & quality reflection node
│   │
│   ├── tools/             # Distinct external tools
│   │   ├── __init__.py
│   │   ├── web_search.py   # Live web search tool
│   │   ├── page_fetcher.py # Web page content extractor & parser
│   │   └── report_writer.py# Markdown/PDF report exporter
│   │
│   ├── models/            # Shared data models & Pydantic schemas
│   │   ├── __init__.py
│   │   └── schemas.py     # Plan, Task, Evidence, and Summary schemas
│   │
│   ├── utils/             # Infrastructure utilities
│   │   ├── __init__.py
│   │   ├── logging.py     # Console tracing & execution logger
│   │   └── deduplication.py# Text hashing & semantic deduplication
│   │
│   └── main.py            # CLI entry point
│
├── tests/
│   ├── __init__.py
│   └── test_smoke.py      # Environment & module import smoke tests
│
├── docs/                  # Architecture & design documentation
├── examples/              # Sample run transcripts & trace logs
├── reports/               # Default output directory for generated reports
│
├── .env.example           # Template for API keys & config
├── .gitignore             # Git ignore rule file
├── README.md              # Project documentation
├── requirements.txt       # Frozen dependencies list
└── pyproject.toml         # Package definition & pytest config
```

---

## Installation & Setup

### 1. Clone & Navigate
```bash
cd Autonomous_Research_Agent
```

### 2. Create Virtual Environment & Install Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the example environment file and fill in your API credentials:
```bash
cp .env.example .env
```

---

## Running Tests

Verify project structure and basic import integrity:
```bash
pytest
```
