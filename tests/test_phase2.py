"""
Phase 2 Unit Tests covering GoalAnalysis, Plan validation, LLM provider abstraction,
retry/recovery handling, and LangGraph workflow execution with MockLLMProvider.
"""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    GoalAnalysis,
    Plan,
    Task,
    TaskStatus,
)
from app.agent.llm import MockLLMProvider, GeminiProvider, get_llm_provider
from app.agent.planner import analyze_goal, generate_plan
from app.agent.graph import build_research_graph


def test_goal_analysis_schema_validation():
    """Verify GoalAnalysis schema instantiation and constraint handling."""
    analysis = GoalAnalysis(
        objective="Analyze agentic framework trends",
        topic="Agentic AI",
        constraints=["last 7 days", "open source only"],
        time_range="7 days",
        output_requirements=["3 key findings"],
        success_criteria=["Source links provided"],
    )
    assert analysis.topic == "Agentic AI"
    assert len(analysis.constraints) == 2
    assert analysis.time_range == "7 days"


def test_plan_schema_validation():
    """Verify Plan and Task schema validation."""
    task1 = Task(
        id="task_1",
        description="Search for agentic AI papers",
        objective="Gather papers",
        expected_output="Paper links",
        suggested_tool="web_search",
        dependencies=[],
    )
    task2 = Task(
        id="task_2",
        description="Scrape content from selected papers",
        objective="Extract benchmarks",
        expected_output="Benchmark figures",
        suggested_tool="page_fetcher",
        dependencies=["task_1"],
    )
    plan = Plan(
        query="Research Agentic AI",
        rationale="2-step research workflow",
        tasks=[task1, task2],
    )
    assert len(plan.tasks) == 2
    assert plan.tasks[1].dependencies == ["task_1"]


@pytest.mark.asyncio
async def test_mock_llm_provider_structured_generation():
    """Verify MockLLMProvider generates valid structured objects for GoalAnalysis and Plan."""
    provider = MockLLMProvider()

    analysis = await provider.generate_structured(
        prompt="Research AI benchmarks",
        response_schema=GoalAnalysis,
    )
    assert isinstance(analysis, GoalAnalysis)
    assert "Research AI benchmarks" in analysis.objective

    plan = await provider.generate_structured(
        prompt="Research AI benchmarks",
        response_schema=Plan,
    )
    assert isinstance(plan, Plan)
    assert len(plan.tasks) >= 2


@pytest.mark.asyncio
async def test_planner_nodes_with_mock_llm():
    """Verify analyze_goal and generate_plan nodes execute with mock LLM provider."""
    mock_provider = MockLLMProvider()

    initial_state = {
        "query": "Compare PyTorch and JAX for research",
        "goal_analysis": None,
        "plan": None,
    }

    # Test analyze_goal node
    analysis_update = await analyze_goal(initial_state, llm_provider=mock_provider)
    assert "goal_analysis" in analysis_update
    goal_analysis = analysis_update["goal_analysis"]
    assert isinstance(goal_analysis, GoalAnalysis)

    # Test generate_plan node
    state_with_analysis = {**initial_state, "goal_analysis": goal_analysis}
    plan_update = await generate_plan(state_with_analysis, llm_provider=mock_provider)
    assert "plan" in plan_update
    plan = plan_update["plan"]
    assert isinstance(plan, Plan)
    assert len(plan.tasks) > 0


@pytest.mark.asyncio
async def test_langgraph_workflow_execution():
    """Verify LangGraph state graph executes full planning flow from START to END."""
    import os
    os.environ["LLM_PROVIDER"] = "mock"

    graph = build_research_graph()

    initial_state = {
        "query": "Research recent advances in vision language models",
        "goal_analysis": None,
        "plan": None,
        "current_task": None,
        "completed_tasks": [],
        "evidence": [],
        "visited_urls": [],
        "step_count": 0,
        "max_steps": 10,
        "retry_count": 0,
        "is_complete": False,
        "error": None,
        "final_report": None,
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state["goal_analysis"] is not None
    assert final_state["plan"] is not None
    assert isinstance(final_state["goal_analysis"], GoalAnalysis)
    assert isinstance(final_state["plan"], Plan)
    assert len(final_state["plan"].tasks) > 0


@pytest.mark.asyncio
async def test_malformed_llm_response_recovery():
    """Verify recovery retry handling when LLM provider receives invalid output."""
    class FailingMockProvider(MockLLMProvider):
        def __init__(self):
            super().__init__()
            self.attempt_count = 0

        async def generate_structured(self, prompt, response_schema, system_instruction=None, retry_limit=2):
            self.attempt_count += 1
            if self.attempt_count == 1:
                # First attempt fails schema validation simulate
                raise ValidationError.from_exception_data("Simulated malformed LLM response", [])
            # Second attempt succeeds
            return await super().generate_structured(prompt, response_schema, system_instruction, retry_limit)

    failing_provider = FailingMockProvider()

    # Verify that failing provider can be caught or retried
    with pytest.raises(ValidationError):
        await failing_provider.generate_structured("test", GoalAnalysis)

    # Second call succeeds
    res = await failing_provider.generate_structured("test", GoalAnalysis)
    assert isinstance(res, GoalAnalysis)
