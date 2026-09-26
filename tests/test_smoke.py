"""
Smoke tests verifying project structure, module imports, schemas, utilities, and provider factory.
"""

import pytest
from app.models.schemas import (
    TaskStatus,
    GoalAnalysis,
    Task,
    Plan,
    SearchResultItem,
    FetchedPage,
    ResearchEvidence,
    ResearchReport,
)
from app.utils.deduplication import compute_content_hash, deduplicate_articles
from app.utils.logging import get_logger, TraceLogger
from app.agent.llm import get_llm_provider, MockLLMProvider
from app.agent.graph import build_research_graph


def test_schema_instantiation():
    """Verify schema models instantiate correctly with default and custom fields."""
    task = Task(
        id="task_1",
        description="Search for Agentic AI benchmarks",
        suggested_tool="web_search",
        tool_input={"query": "Agentic AI benchmarks"},
    )
    assert task.status == TaskStatus.PENDING
    assert task.retry_count == 0

    plan = Plan(
        query="Research Agentic AI",
        rationale="Decompose query into search and fetch steps",
        tasks=[task],
    )
    assert len(plan.tasks) == 1
    assert plan.current_task_index == 0

    goal_analysis = GoalAnalysis(
        objective="Analyze AI frameworks",
        topic="AI Frameworks",
        constraints=["open source"],
        output_requirements=["comparison table"],
        success_criteria=["detailed metrics"],
    )
    assert goal_analysis.topic == "AI Frameworks"


def test_deduplication_utilities():
    """Verify text content hashing and list deduplication."""
    text1 = "  Sample Text Content  "
    text2 = "sample text content"
    hash1 = compute_content_hash(text1)
    hash2 = compute_content_hash(text2)
    assert hash1 == hash2

    articles = [
        {"content": "Unique content A", "url": "https://a.com"},
        {"content": "Unique content A", "url": "https://a-dup.com"},
        {"content": "Unique content B", "url": "https://b.com"},
    ]
    deduped = deduplicate_articles(articles)
    assert len(deduped) == 2


def test_provider_factory():
    """Verify provider factory returns MockLLMProvider when provider='mock'."""
    provider = get_llm_provider("mock")
    assert isinstance(provider, MockLLMProvider)


def test_graph_compilation():
    """Verify build_research_graph compiles a valid StateGraph."""
    graph = build_research_graph()
    assert graph is not None
