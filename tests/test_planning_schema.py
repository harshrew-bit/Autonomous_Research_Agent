"""
Regression tests for Gemini Developer API closed planning schema and runtime conversion.
"""

import json
import pytest
from app.models.schemas import (
    GoalAnalysis,
    Plan,
    Task,
    ToolInput,
    PlannedTask,
    LLMPlan,
    ResearchReport,
    TaskStatus,
)
from app.agent.llm import MockLLMProvider
from app.agent.planner import generate_plan
from app.agent.executor import resolve_tool_call


def test_gemini_facing_schemas_have_no_additional_properties():
    """Verify that all schemas sent to Gemini Developer API contain no additionalProperties."""
    for model_cls in [GoalAnalysis, ToolInput, PlannedTask, LLMPlan, ResearchReport]:
        schema = model_cls.model_json_schema()
        schema_str = json.dumps(schema)
        assert "additionalProperties" not in schema_str, (
            f"Schema for {model_cls.__name__} contains 'additionalProperties' which breaks Gemini Developer API!"
        )
        assert "additional_properties" not in schema_str, (
            f"Schema for {model_cls.__name__} contains 'additional_properties'!"
        )


def test_planned_task_to_runtime_task_conversion():
    """Verify conversion of PlannedTask to runtime Task model."""
    planned = PlannedTask(
        id="task_1",
        description="Search for agentic AI architectures",
        objective="Find recent papers",
        expected_output="Paper links",
        suggested_tool="web_search",
        dependencies=[],
        tool_input=ToolInput(query="Agentic AI planning tool use", max_results=5),
    )

    runtime_task = planned.to_runtime_task()
    assert isinstance(runtime_task, Task)
    assert runtime_task.id == "task_1"
    assert runtime_task.description == "Search for agentic AI architectures"
    assert runtime_task.suggested_tool == "web_search"
    assert runtime_task.tool_input == {"query": "Agentic AI planning tool use", "max_results": 5, "timeout_seconds": 15}
    assert runtime_task.status == TaskStatus.PENDING
    assert runtime_task.result is None
    assert runtime_task.error is None


def test_llm_plan_to_runtime_plan_conversion():
    """Verify conversion of LLMPlan to runtime Plan model."""
    llm_plan = LLMPlan(
        query="Research Agentic AI",
        rationale="Multi-phase research strategy",
        tasks=[
            PlannedTask(
                id="task_1",
                description="Search authoritative sources",
                suggested_tool="web_search",
                tool_input=ToolInput(query="Agentic AI systems"),
            ),
            PlannedTask(
                id="task_2",
                description="Fetch contents from top source",
                suggested_tool="page_fetcher",
                dependencies=["task_1"],
                tool_input=ToolInput(),
            ),
        ],
    )

    plan = llm_plan.to_runtime_plan()
    assert isinstance(plan, Plan)
    assert plan.query == "Research Agentic AI"
    assert plan.rationale == "Multi-phase research strategy"
    assert len(plan.tasks) == 2
    assert all(isinstance(t, Task) for t in plan.tasks)
    assert plan.tasks[0].suggested_tool == "web_search"
    assert plan.tasks[1].suggested_tool == "page_fetcher"
    assert plan.tasks[1].dependencies == ["task_1"]


@pytest.mark.asyncio
async def test_mock_llm_provider_llm_plan_generation():
    """Verify MockLLMProvider can generate and parse LLMPlan."""
    provider = MockLLMProvider()
    plan_obj = await provider.generate_structured(
        prompt="User Query:\n\"Research recent advances in agentic AI systems\"",
        response_schema=LLMPlan,
    )
    assert isinstance(plan_obj, LLMPlan)
    assert len(plan_obj.tasks) >= 2
    assert all(isinstance(t, PlannedTask) for t in plan_obj.tasks)


@pytest.mark.asyncio
async def test_planner_generate_plan_produces_valid_runtime_plan():
    """Verify planner node generate_plan produces a runtime Plan via LLMPlan."""
    provider = MockLLMProvider()
    initial_state = {
        "query": "Research recent advances in agentic AI systems",
        "goal_analysis": GoalAnalysis(
            objective="Research agentic AI systems",
            topic="Agentic AI Systems",
        ),
        "plan": None,
    }

    state_update = await generate_plan(initial_state, llm_provider=provider)
    assert "plan" in state_update
    runtime_plan = state_update["plan"]
    assert isinstance(runtime_plan, Plan)
    assert len(runtime_plan.tasks) > 0
    assert all(isinstance(t, Task) for t in runtime_plan.tasks)
    assert state_update["status"] == "executing"
    assert state_update["current_task"] == runtime_plan.tasks[0]


def test_resolve_tool_call_with_converted_task():
    """Verify that tasks converted from PlannedTask resolve cleanly into ToolCalls."""
    planned = PlannedTask(
        id="task_search",
        description="Search for memory architectures in agents",
        suggested_tool="web_search",
        tool_input=ToolInput(query="agent memory architectures episodic semantic"),
    )
    task = planned.to_runtime_task()

    tool_call = resolve_tool_call(task, {"query": "Agentic AI"})
    assert tool_call.tool_name == "web_search"
    assert tool_call.arguments["query"] == "agent memory architectures episodic semantic"
    assert tool_call.arguments["max_results"] == 5
