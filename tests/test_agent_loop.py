"""
Unit tests for Phase 4 autonomous research execution loop, tool registry,
evaluator decision matrix, failure recovery, replanning, and boundary limits.
Zero external API calls; all tests execute deterministically offline using mocks.
"""

import pytest
from unittest.mock import patch, AsyncMock
from typing import Dict, Any

from app.models.schemas import (
    DecisionType,
    EvaluationDecision,
    Observation,
    Plan,
    Task,
    TaskStatus,
    SearchResultItem,
    SearchResponse,
    FetchedPage,
)
from app.tools.registry import (
    TOOL_REGISTRY,
    ToolRegistry,
    WebSearchInput,
    PageFetcherInput,
)
from app.agent.executor import resolve_tool_call, execute_step
from app.agent.evaluator import evaluate_step
from app.agent.planner import replan_research
from app.agent.graph import build_research_graph, route_evaluation
from app.agent.llm import MockLLMProvider
from app.tools.web_search import MockSearchProvider


# ==============================================================================
# 1. TOOL REGISTRY & SAFETY TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_tool_registry_authorized_execution():
    """Verify registry accepts authorized tool with valid arguments."""
    registry = ToolRegistry()
    mock_func = AsyncMock(return_value="mock_result")
    registry.register("web_search", mock_func, WebSearchInput, "Search")

    res = await registry.execute("web_search", {"query": "agentic AI", "max_results": 3})
    assert res == "mock_result"
    mock_func.assert_called_once_with(query="agentic AI", max_results=3)


@pytest.mark.asyncio
async def test_tool_registry_rejects_unknown_tool():
    """Verify registry strictly blocks unregistered tools."""
    registry = ToolRegistry()
    with pytest.raises(ValueError, match="Unauthorized or unknown tool"):
        await registry.execute("system_shell_cmd", {"command": "ls"})


@pytest.mark.asyncio
async def test_tool_registry_rejects_invalid_arguments():
    """Verify registry validates arguments against Pydantic schema."""
    registry = ToolRegistry()
    mock_func = AsyncMock()
    registry.register("page_fetcher", mock_func, PageFetcherInput, "Fetch")

    # Missing required argument 'url'
    with pytest.raises(ValueError, match="Invalid arguments"):
        await registry.execute("page_fetcher", {})


# ==============================================================================
# 2. DYNAMIC TOOL ARGUMENT RESOLUTION TESTS
# ==============================================================================

def test_resolve_tool_call_web_search():
    """Verify search query derivation from task description."""
    task = Task(
        id="task_1",
        description="Search for stateful agent benchmarks",
        suggested_tool="web_search",
    )
    state = {"query": "Agentic AI"}
    call = resolve_tool_call(task, state)

    assert call.tool_name == "web_search"
    assert "stateful agent benchmarks" in call.arguments["query"]


def test_resolve_tool_call_web_search_preserves_topic_on_generic_task():
    """Verify search query prepends the research topic if task description is generic."""
    task = Task(
        id="task_1",
        description="Find recent papers and benchmarks",
        suggested_tool="web_search",
    )
    state = {"query": "Quantum Computing"}
    call = resolve_tool_call(task, state)

    assert call.tool_name == "web_search"
    assert "Quantum Computing" in call.arguments["query"]
    assert "recent papers and benchmarks" in call.arguments["query"]


def test_resolve_tool_call_web_search_uses_explicit_tool_input():
    """Verify explicit query in task.tool_input takes highest precedence."""
    task = Task(
        id="task_1",
        description="Search for something",
        suggested_tool="web_search",
        tool_input={"query": "explicit targeted query", "max_results": 7},
    )
    state = {"query": "General AI"}
    call = resolve_tool_call(task, state)

    assert call.tool_name == "web_search"
    assert call.arguments["query"] == "explicit targeted query"
    assert call.arguments["max_results"] == 7


def test_resolve_tool_call_page_fetcher_consumes_search_results():
    """Verify page fetcher dynamically selects unvisited URL from search results."""
    task = Task(
        id="task_2",
        description="Extract content from top search result",
        suggested_tool="page_fetcher",
    )
    state = {
        "search_results": [
            SearchResultItem(title="T1", url="https://example.com/visited", snippet="s1"),
            SearchResultItem(title="T2", url="https://example.com/unvisited", snippet="s2"),
        ],
        "visited_urls": ["https://example.com/visited"],
    }
    call = resolve_tool_call(task, state)

    assert call.tool_name == "page_fetcher"
    assert call.arguments["url"] == "https://example.com/unvisited"


def test_resolve_tool_call_page_fetcher_missing_url_raises():
    """Verify error raised when page fetcher has no candidate URLs."""
    task = Task(
        id="task_2",
        description="Extract content",
        suggested_tool="page_fetcher",
    )
    state = {"search_results": [], "visited_urls": []}
    with pytest.raises(ValueError, match="No candidate URL available"):
        resolve_tool_call(task, state)


# ==============================================================================
# 3. EXECUTOR NODE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_execute_step_web_search_updates_state():
    """Verify execute_step calls search tool and populates search_results and observation."""
    registry = ToolRegistry()
    mock_search = AsyncMock(
        return_value=SearchResponse(
            query="AI agents",
            results=[SearchResultItem(title="Test", url="https://example.com", snippet="summary")],
            success=True,
        )
    )
    registry.register("web_search", mock_search, WebSearchInput, "Search")

    task = Task(id="task_1", description="Search for AI agents", suggested_tool="web_search")
    plan = Plan(query="AI agents", rationale="Test", tasks=[task])
    state = {
        "plan": plan,
        "current_task_index": 0,
        "step_count": 0,
        "visited_urls": [],
        "search_results": [],
    }

    update = await execute_step(state, tool_registry=registry)

    assert update["step_count"] == 1
    assert "last_observation" in update
    assert update["last_observation"].success is True
    assert len(update["search_results"]) == 1
    assert update["search_results"][0].url == "https://example.com"


@pytest.mark.asyncio
async def test_execute_step_page_fetcher_updates_evidence():
    """Verify execute_step calls page_fetcher and populates evidence and fetched_pages."""
    registry = ToolRegistry()
    mock_fetch = AsyncMock(
        return_value=FetchedPage(
            url="https://example.com/page",
            title="Evidence Page",
            content="Extracted evidence content",
            text_length=26,
            success=True,
        )
    )
    registry.register("page_fetcher", mock_fetch, PageFetcherInput, "Fetch")

    task = Task(id="task_2", description="Fetch page", suggested_tool="page_fetcher")
    plan = Plan(query="Test", rationale="Test", tasks=[task])
    state = {
        "plan": plan,
        "current_task_index": 0,
        "step_count": 1,
        "search_results": [SearchResultItem(title="P", url="https://example.com/page", snippet="S")],
        "visited_urls": [],
    }

    update = await execute_step(state, tool_registry=registry)

    assert update["step_count"] == 2
    assert len(update["fetched_pages"]) == 1
    assert len(update["evidence"]) == 1
    assert "https://example.com/page" in update["visited_urls"]


# ==============================================================================
# 4. EVALUATOR NODE & DECISION LOGIC TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_evaluator_continue_when_more_tasks_remain():
    """Verify evaluator decides CONTINUE when current task completes and more tasks exist."""
    task1 = Task(id="task_1", description="Search", suggested_tool="web_search")
    task2 = Task(id="task_2", description="Fetch", suggested_tool="page_fetcher")
    plan = Plan(query="Test", rationale="R", tasks=[task1, task2])

    state = {
        "step_count": 1,
        "max_steps": 10,
        "plan": plan,
        "current_task_index": 0,
        "last_observation": Observation(tool="web_search", success=True, summary="Found results"),
    }

    update = await evaluate_step(state)

    assert update["last_decision"].decision == DecisionType.CONTINUE
    assert update["current_task_index"] == 1


@pytest.mark.asyncio
async def test_evaluator_complete_when_all_tasks_done():
    """Verify evaluator decides COMPLETE when final task succeeds with evidence."""
    task1 = Task(id="task_1", description="Search", suggested_tool="web_search")
    plan = Plan(query="Test", rationale="R", tasks=[task1])

    state = {
        "step_count": 1,
        "max_steps": 10,
        "plan": plan,
        "current_task_index": 0,
        "search_results": [SearchResultItem(title="T", url="https://a.com", snippet="S")],
        "last_observation": Observation(tool="web_search", success=True, summary="Done"),
    }

    update = await evaluate_step(state)

    assert update["last_decision"].decision == DecisionType.COMPLETE
    assert update["status"] == "completed"
    assert update["is_complete"] is True


@pytest.mark.asyncio
async def test_evaluator_retry_transient_failure():
    """Verify evaluator decides RETRY when transient timeout occurs under retry limit."""
    task1 = Task(id="task_1", description="Search", suggested_tool="web_search", retry_count=0)
    plan = Plan(query="Test", rationale="R", tasks=[task1])

    state = {
        "step_count": 1,
        "max_steps": 10,
        "max_retries_per_task": 2,
        "plan": plan,
        "current_task_index": 0,
        "last_observation": Observation(
            tool="web_search",
            success=False,
            summary="Timed out",
            error="Request timed out after 10.0s",
        ),
    }

    update = await evaluate_step(state)

    assert update["last_decision"].decision == DecisionType.RETRY
    assert update["current_task"].retry_count == 1
    assert update["current_task"].status == TaskStatus.RETRYING


@pytest.mark.asyncio
async def test_evaluator_replan_when_retries_exhausted():
    """Verify evaluator triggers REPLAN when retries are exhausted."""
    task1 = Task(id="task_1", description="Search", suggested_tool="web_search", retry_count=2)
    plan = Plan(query="Test", rationale="R", tasks=[task1])

    state = {
        "step_count": 3,
        "max_steps": 10,
        "max_retries_per_task": 2,
        "plan": plan,
        "current_task_index": 0,
        "last_observation": Observation(
            tool="web_search",
            success=False,
            summary="Timed out repeatedly",
            error="Timeout",
        ),
    }

    update = await evaluate_step(state)

    assert update["last_decision"].decision == DecisionType.REPLAN
    assert update["status"] == "replanning"


@pytest.mark.asyncio
async def test_evaluator_step_limit_enforcement():
    """Verify evaluator halts execution when step_count reaches max_steps."""
    task1 = Task(id="task_1", description="Search", suggested_tool="web_search")
    plan = Plan(query="Test", rationale="R", tasks=[task1])

    state = {
        "step_count": 10,
        "max_steps": 10,
        "plan": plan,
        "current_task_index": 0,
        "last_observation": Observation(tool="web_search", success=True, summary="Ok"),
    }

    update = await evaluate_step(state)

    assert update["last_decision"].decision == DecisionType.FAIL
    assert update["status"] == "step_limit_reached"
    assert update["is_complete"] is True


# ==============================================================================
# 5. REPLANNING & STATE TRANSITIONS
# ==============================================================================

@pytest.mark.asyncio
async def test_replan_research_produces_new_plan():
    """Verify replan_research uses LLM to generate revised plan and resets index."""
    mock_llm = MockLLMProvider()

    state = {
        "query": "Research Agentic AI",
        "plan": Plan(query="Q", rationale="Old", tasks=[Task(id="old_1", description="Old", suggested_tool="web_search")]),
        "last_observation": Observation(tool="web_search", success=False, summary="No results"),
        "last_decision": EvaluationDecision(decision=DecisionType.REPLAN, reason="Zero results"),
        "execution_history": [],
    }

    update = await replan_research(state, llm_provider=mock_llm)

    assert "plan" in update
    assert update["current_task_index"] == 0
    assert len(update["plan"].tasks) > 0
    assert update["status"] == "executing"
    assert len(update["execution_history"]) == 1


# ==============================================================================
# 6. FULL LANGGRAPH EXECUTION LOOP TEST
# ==============================================================================

@pytest.mark.asyncio
async def test_full_autonomous_loop_execution():
    """Verify full LangGraph execution from START through planning, tools, and completion."""
    import os
    os.environ["LLM_PROVIDER"] = "mock"
    os.environ["SEARCH_PROVIDER"] = "mock"

    mock_fetch = AsyncMock(
        return_value=FetchedPage(
            url="https://example.com",
            title="Agentic AI Article",
            content="Key findings on autonomous LLM agents.",
            text_length=38,
            success=True,
        )
    )

    with patch.object(TOOL_REGISTRY._tools["page_fetcher"], "func", mock_fetch):
        graph = build_research_graph()

        initial_state = {
            "query": "Investigate Agentic AI Frameworks",
            "goal_analysis": None,
            "plan": None,
            "current_task_index": 0,
            "current_task": None,
            "completed_tasks": [],
            "search_results": [],
            "fetched_pages": [],
            "evidence": [],
            "visited_urls": [],
            "tool_results": [],
            "last_observation": None,
            "last_decision": None,
            "step_count": 0,
            "max_steps": 10,
            "retry_count": 0,
            "max_retries_per_task": 2,
            "execution_history": [],
            "is_complete": False,
            "status": "planning",
            "error": None,
            "final_report": None,
        }

        final_state = await graph.ainvoke(initial_state)

        assert final_state["is_complete"] is True
        assert final_state["status"] == "completed"
        assert len(final_state["search_results"]) > 0
        assert len(final_state["fetched_pages"]) > 0
        assert len(final_state["evidence"]) > 0
        assert final_state["step_count"] >= 2
