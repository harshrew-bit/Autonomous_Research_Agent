"""
Smoke tests verifying project structure, module imports, schemas, and utility functions.
"""

import pytest
from app.models.schemas import (
    TaskStatus,
    Task,
    Plan,
    SearchResultItem,
    FetchedPage,
    ResearchEvidence,
    ResearchReport,
)
from app.utils.deduplication import compute_content_hash, deduplicate_articles
from app.utils.logging import get_logger, TraceLogger
from app.tools.web_search import search_web
from app.tools.page_fetcher import fetch_page_content
from app.tools.report_writer import export_report
from app.agent.planner import plan_research, replan_research
from app.agent.evaluator import evaluate_step_result
from app.agent.graph import build_research_graph


def test_schema_instantiation():
    """Verify schema models instantiate correctly with default and custom fields."""
    task = Task(
        id="task_1",
        description="Search for Agentic AI benchmarks",
        tool_name="web_search",
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

    report = ResearchReport(
        topic="Agentic AI",
        key_points=["Point 1"],
        important_findings=["Finding 1"],
        sources=["https://example.com"],
        actionable_insights=["Insight 1"],
    )
    assert report.topic == "Agentic AI"
    assert len(report.sources) == 1


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


def test_logger_utility():
    """Verify logger setup."""
    logger = get_logger("test_logger")
    assert logger.name == "test_logger"


@pytest.mark.asyncio
async def test_placeholder_stubs_raise_not_implemented():
    """Verify tool and agent placeholder stubs raise NotImplementedError for Phase 1."""
    with pytest.raises(NotImplementedError):
        await search_web("test query")

    with pytest.raises(NotImplementedError):
        await fetch_page_content("https://example.com")

    with pytest.raises(NotImplementedError):
        export_report(
            ResearchReport(topic="t", key_points=[], important_findings=[], sources=[], actionable_insights=[]),
            "output.md"
        )

    with pytest.raises(NotImplementedError):
        await plan_research({"query": "test"})

    with pytest.raises(NotImplementedError):
        await replan_research({"query": "test"})

    with pytest.raises(NotImplementedError):
        await evaluate_step_result({"query": "test"})

    with pytest.raises(NotImplementedError):
        build_research_graph()
