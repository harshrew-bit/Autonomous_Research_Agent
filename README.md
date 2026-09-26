# Autonomous Research Agent

> A production-ready, autonomous research agent built with **LangGraph**, **Pydantic**, and Python 3.12 for the Agentic AI Engineer Intern technical assessment.

## Overview

The **Autonomous Research Agent** accepts high-level user research queries, extracts structured goal parameters, autonomously formulates dynamic execution plans, and presents a visible planning trace before executing tools.

---

## Architectural Principles (Phase 2)

1. **LLM Provider Abstraction (`app/agent/llm.py`)**: Provider-agnostic interface (`LLMProvider`) supporting Google Gemini (`GeminiProvider`) and deterministic mock backends (`MockLLMProvider`) for offline testing without API keys.
2. **Goal Analysis (`app/agent/planner.py`)**: High-level goal breakdown extracting objective, domain topic, scope constraints, time boundaries, output requirements, and success criteria.
3. **Dynamic Decomposition & Planning**: The LLM dynamically constructs tailored task sequences with sub-objectives, tool recommendations, and dependencies based on user intent.
4. **Structured Validation & Recovery**: Uses Pydantic schema validation for LLM outputs with bounded retry recovery.
5. **Visible Planning Trace (`app/utils/logging.py`)**: Renders clean, user-facing goal breakdowns and step execution tables using `Rich`.

---

## Intended State Graph Cycle

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
                      +-------------------+
                      | Visible Trace CLI |
                      +-------------------+
```

---

## Installation & Setup

### 1. Virtual Environment & Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and set your preferred LLM provider:

```bash
cp .env.example .env
```

To run with live Google Gemini:
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_actual_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
```

To run offline without API keys (using Mock provider):
```env
LLM_PROVIDER=mock
```

---

## Running the Planner (CLI)

### Test A: Research Query
```bash
python app/main.py "Research the latest developments in Agentic AI"
```

### Test B: Framework Comparison Query
```bash
python app/main.py "Compare the current leading Python web frameworks for a beginner building an API"
```

### Test C: RAG Advances Query
```bash
python app/main.py "Find recent developments in RAG and identify practical applications for software engineering"
```

### Force Mock Mode via CLI Flag
```bash
python app/main.py "Research quantum computing" --provider mock
```

---

## Running Tests

Run the full pytest suite (no API keys required):

```bash
pytest
```
