"""
Comprehensive unit tests for Phase 5 evidence processing pipeline, relevance scoring,
multi-signal deduplication, structured research report synthesis, and Markdown export.
All tests are 100% deterministic and execute offline without external APIs.
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.models.schemas import (
    EvidenceItem,
    KeyFinding,
    SourceCitation,
    ResearchReport,
    FetchedPage,
    SearchResultItem,
    GoalAnalysis,
)
from app.utils.deduplication import (
    compute_content_hash,
    calculate_text_similarity,
    deduplicate_evidence,
)
from app.agent.evidence import (
    calculate_relevance_score,
    extract_candidate_evidence_from_text,
    filter_relevant_evidence,
    process_evidence_pipeline,
    classify_evidence_type,
)
from app.tools.report_writer import (
    format_markdown_report,
    export_report,
    sanitize_filename,
    generate_report_filename,
)
from app.agent.llm import MockLLMProvider
from app.agent.synthesizer import synthesize_report, export_report_artifact
from app.agent.graph import build_research_graph


# ==============================================================================
# 1. EVIDENCE EXTRACTION & TRACEABILITY TESTS
# ==============================================================================

def test_extract_valid_evidence():
    """Verify clean paragraph text extracts into structured EvidenceItem with hash and domain."""
    sample_text = (
        "Agentic reasoning frameworks decompose complex goals into autonomous planning loops. "
        "These architectures continuously evaluate tool observations and adjust intermediate steps. "
        "Empirical benchmarks demonstrate a 35% improvement in multi-step task success rates."
    )
    items = extract_candidate_evidence_from_text(
        content=sample_text,
        source_url="https://arxiv.org/abs/2401.00001",
        source_title="Advances in Autonomous Agent Frameworks",
        query="Agentic reasoning frameworks",
        topic="AI Systems",
    )

    assert len(items) == 1
    ev = items[0]
    assert ev.source_url == "https://arxiv.org/abs/2401.00001"
    assert ev.source_domain == "arxiv.org"
    assert ev.source_title == "Advances in Autonomous Agent Frameworks"
    assert "Agentic reasoning frameworks" in ev.claim
    assert "35% improvement" in ev.supporting_text
    assert ev.evidence_type in ("statistical", "benchmark", "architectural")
    assert len(ev.content_hash) == 64  # Valid SHA-256 hash


def test_extract_empty_or_poor_page_returns_empty():
    """Verify empty pages, boilerplate, or tiny snippets produce zero candidate evidence."""
    # Empty content
    assert extract_candidate_evidence_from_text("", "https://example.com", "Title", "AI") == []

    # Whitespace / tiny length
    assert extract_candidate_evidence_from_text("   short   ", "https://example.com", "Title", "AI") == []

    # Pure boilerplate
    boilerplate = "Cookie policy. All rights reserved. Please sign in to your account. Click here to enable JavaScript."
    assert extract_candidate_evidence_from_text(boilerplate, "https://example.com", "Title", "AI") == []


def test_content_hash_consistency():
    """Verify content hash is invariant to whitespace and case variations."""
    t1 = "Deterministic Evidence Analysis 2026."
    t2 = "  deterministic evidence analysis 2026.  "
    assert compute_content_hash(t1) == compute_content_hash(t2)


# ==============================================================================
# 2. RELEVANCE SCORING & FILTERING TESTS
# ==============================================================================

def test_relevance_scoring_and_filtering():
    """Verify relevant text receives high score and irrelevant text is partitioned out."""
    relevant_text = (
        "Quantum computing algorithms exploit entanglement and superposition to achieve exponential speedups "
        "in integer factorization and chemical simulation compared to classical algorithms."
    )
    irrelevant_text = (
        "The recipe calls for three cups of flour, two eggs, and unsalted butter baked at 350 degrees "
        "until golden brown on top."
    )

    query = "Quantum computing algorithms"
    topic = "Physics & Computing"

    score_rel = calculate_relevance_score(relevant_text, query, topic)
    score_irrel = calculate_relevance_score(irrelevant_text, query, topic)

    assert score_rel >= 0.5
    assert score_irrel < 0.25

    item_rel = EvidenceItem(
        source_url="https://quantum.org",
        source_title="Quantum Speedup",
        claim="Quantum computing achieves exponential speedups",
        supporting_text=relevant_text,
        relevance_score=score_rel,
        content_hash=compute_content_hash(relevant_text),
    )
    item_irrel = EvidenceItem(
        source_url="https://baking.com",
        source_title="Cake Recipe",
        claim="Bake at 350 degrees",
        supporting_text=irrelevant_text,
        relevance_score=score_irrel,
        content_hash=compute_content_hash(irrelevant_text),
    )

    accepted, rejected = filter_relevant_evidence([item_rel, item_irrel], min_relevance=0.35)
    assert len(accepted) == 1
    assert accepted[0].source_url == "https://quantum.org"
    assert len(rejected) == 1
    assert rejected[0].source_url == "https://baking.com"


def test_relevance_arbitrary_topics():
    """Verify relevance scoring works dynamically on non-AI arbitrary topics."""
    text = "Photosynthesis converts solar energy into chemical carbohydrates inside plant chloroplasts."
    score = calculate_relevance_score(text, query="Botanical photosynthesis mechanisms", topic="Biology")
    assert score >= 0.4


# ==============================================================================
# 3. DEDUPLICATION TESTS
# ==============================================================================

def test_deduplicate_exact_duplicates():
    """Verify exact duplicate content hashes are completely eliminated."""
    ev1 = EvidenceItem(
        source_url="https://example.com/doc1",
        source_title="Doc 1",
        claim="LLM agents use tools.",
        supporting_text="LLM agents use tools.",
        relevance_score=0.8,
        content_hash="hash_identical",
    )
    ev2 = EvidenceItem(
        source_url="https://example.com/mirror",
        source_title="Mirror",
        claim="LLM agents use tools.",
        supporting_text="LLM agents use tools.",
        relevance_score=0.7,
        content_hash="hash_identical",
    )
    deduped = deduplicate_evidence([ev1, ev2])
    assert len(deduped) == 1


def test_deduplicate_near_identical_text():
    """Verify highly similar claims across sources collapse into single best evidence."""
    ev1 = EvidenceItem(
        source_url="https://a.com/p",
        source_title="A",
        claim="Autonomous agents improve tool usage by thirty percent in benchmarks.",
        supporting_text="Autonomous agents improve tool usage by thirty percent in benchmarks across evaluations.",
        relevance_score=0.9,
        content_hash="h1",
    )
    ev2 = EvidenceItem(
        source_url="https://b.com/p",
        source_title="B",
        claim="Autonomous agents improve tool usage by thirty percent in benchmark tests.",
        supporting_text="Autonomous agents improve tool usage by thirty percent in benchmark tests across evaluations.",
        relevance_score=0.7,
        content_hash="h2",
    )
    deduped = deduplicate_evidence([ev1, ev2], similarity_threshold=0.70)
    assert len(deduped) == 1
    assert deduped[0].relevance_score == 0.9


def test_deduplicate_preserves_distinct_claims_from_same_url():
    """Verify different claims from the same domain or URL are NOT collapsed."""
    ev1 = EvidenceItem(
        source_url="https://example.com/comprehensive-guide",
        source_title="Agent Guide",
        claim="Planning nodes decompose goals into discrete dependency graphs.",
        supporting_text="Planning nodes decompose goals into discrete dependency graphs.",
        relevance_score=0.85,
        content_hash="hash_planning",
    )
    ev2 = EvidenceItem(
        source_url="https://example.com/comprehensive-guide",
        source_title="Agent Guide",
        claim="Memory buffers preserve conversational turns across episodic boundaries.",
        supporting_text="Memory buffers preserve conversational turns across episodic boundaries.",
        relevance_score=0.82,
        content_hash="hash_memory",
    )
    deduped = deduplicate_evidence([ev1, ev2])
    assert len(deduped) == 2


def test_deduplicate_live_like_syndicated_and_repeated_evidence():
    """
    Regression test: verify multi-signal deduplication eliminates exact mirrors
    and near-duplicate syndicated snippets while preserving distinct claims.
    """
    original_text = (
        "Modern agentic AI systems integrate external tools and APIs dynamically through "
        "function calling protocols and structured execution environments."
    )
    # Syndicated mirror with minor trailing attribution
    mirror_text = (
        "Modern agentic AI systems integrate external tools and APIs dynamically through "
        "function calling protocols and structured execution environments. Published by TechNews."
    )
    # Completely different claim from the same domain
    same_domain_different_claim = (
        "Long-term memory architectures utilize vector databases and knowledge graphs to "
        "maintain cross-session state and episodic recall."
    )
    # Different claim from another domain
    other_domain_claim = (
        "Self-correction loops evaluate intermediate tool outputs and trigger autonomous replanning "
        "upon encountering execution barriers."
    )

    ev_original = EvidenceItem(
        source_url="https://technews.io/articles/agentic-tools",
        source_title="Agentic Tools in 2026",
        claim="Modern agentic AI systems integrate external tools dynamically",
        supporting_text=original_text,
        relevance_score=0.90,
        content_hash=compute_content_hash(f"Modern agentic AI systems integrate external tools dynamically {original_text}"),
    )
    # Exact duplicate (same content hash)
    ev_exact_dup = EvidenceItem(
        source_url="https://aggregator.net/copy",
        source_title="Mirror Copy",
        claim="Modern agentic AI systems integrate external tools dynamically",
        supporting_text=original_text,
        relevance_score=0.75,
        content_hash=compute_content_hash(f"Modern agentic AI systems integrate external tools dynamically {original_text}"),
    )
    # Near-duplicate syndicated rephrase
    ev_near_dup = EvidenceItem(
        source_url="https://syndicate.org/feed",
        source_title="Syndicated Feed",
        claim="Modern agentic AI systems integrate external tools dynamically through function calling",
        supporting_text=mirror_text,
        relevance_score=0.70,
        content_hash=compute_content_hash(f"Modern agentic AI systems integrate external tools dynamically through function calling {mirror_text}"),
    )
    # Distinct claim from same domain
    ev_same_domain = EvidenceItem(
        source_url="https://technews.io/articles/agentic-memory",
        source_title="Agentic Memory in 2026",
        claim="Long-term memory architectures utilize vector databases and knowledge graphs",
        supporting_text=same_domain_different_claim,
        relevance_score=0.88,
        content_hash=compute_content_hash(f"Long-term memory architectures utilize vector databases and knowledge graphs {same_domain_different_claim}"),
    )
    # Distinct claim from different domain
    ev_other_domain = EvidenceItem(
        source_url="https://ai-research.org/self-correction",
        source_title="Self-Correction in Agents",
        claim="Self-correction loops evaluate intermediate tool outputs",
        supporting_text=other_domain_claim,
        relevance_score=0.92,
        content_hash=compute_content_hash(f"Self-correction loops evaluate intermediate tool outputs {other_domain_claim}"),
    )

    items = [ev_original, ev_exact_dup, ev_near_dup, ev_same_domain, ev_other_domain]
    deduped = deduplicate_evidence(items, similarity_threshold=0.75)

    # ev_exact_dup and ev_near_dup should be removed (2 duplicates removed)
    assert len(deduped) == 3
    # Original should be retained over the lower-relevance mirror/duplicates
    urls = {item.source_url for item in deduped}
    assert "https://technews.io/articles/agentic-tools" in urls
    assert "https://technews.io/articles/agentic-memory" in urls
    assert "https://ai-research.org/self-correction" in urls
    assert "https://aggregator.net/copy" not in urls
    assert "https://syndicate.org/feed" not in urls


# ==============================================================================
# 4. STRUCTURED REPORT & MARKDOWN EXPORT TESTS
# ==============================================================================

def test_research_report_schema_validation():
    """Verify ResearchReport strongly typed fields, citations, and backward compat properties."""
    findings = [
        KeyFinding(
            claim="Autonomous agents require evaluation loops.",
            explanation="Without evaluation, agents cannot detect tool failures.",
            supporting_source_urls=["https://arxiv.org/abs/2401.00001"],
        )
    ]
    citations = [
        SourceCitation(
            url="https://arxiv.org/abs/2401.00001",
            title="Agentic Evaluation Paper",
            domain="arxiv.org",
            relevant_excerpts_count=3,
        )
    ]
    report = ResearchReport(
        research_question="How do autonomous agents evaluate tool results?",
        topic="Agent Evaluation",
        executive_summary="Executive overview of tool evaluation loops.",
        key_findings=findings,
        important_evidence=[],
        sources=citations,
        actionable_insights=["Incorporate dynamic evaluator nodes."],
        limitations=["Only tested against text tools."],
    )

    assert report.research_question == "How do autonomous agents evaluate tool results?"
    assert len(report.key_findings) == 1
    assert report.key_findings[0].supporting_source_urls[0] == "https://arxiv.org/abs/2401.00001"
    assert report.key_points == ["Autonomous agents require evaluation loops."]
    assert len(report.sources) == 1


def test_markdown_report_formatting_and_export():
    """Verify markdown report rendering contains all required sections and citations."""
    report = ResearchReport(
        research_question="Evaluate stateful agent frameworks",
        topic="Stateful Agents",
        executive_summary="Stateful architectures enable long-horizon task execution.",
        key_findings=[
            KeyFinding(
                claim="State persistence reduces redundant tool invocations.",
                explanation="Retaining past observations avoids re-fetching identical web pages.",
                supporting_source_urls=["https://frameworks.io/state"],
            )
        ],
        important_evidence=[
            EvidenceItem(
                source_url="https://frameworks.io/state",
                source_title="Frameworks Documentation",
                source_domain="frameworks.io",
                claim="State persistence reduces redundant tool invocations.",
                supporting_text="Retaining past observations avoids re-fetching identical web pages.",
                relevance_score=0.92,
                content_hash="abc123hash",
            )
        ],
        sources=[
            SourceCitation(
                url="https://frameworks.io/state",
                title="Frameworks Documentation",
                domain="frameworks.io",
                relevant_excerpts_count=1,
            )
        ],
        actionable_insights=["Implement state checkpoints in production."],
        limitations=["Storage overhead increases with long conversation histories."],
    )

    md = format_markdown_report(report)
    assert "# Research Report: Stateful Agents" in md
    assert "## Research Question" in md
    assert "## Executive Summary" in md
    assert "## Key Findings" in md
    assert "## Important Evidence" in md
    assert "## Sources" in md
    assert "## Actionable Insights" in md
    assert "## Limitations" in md
    assert "https://frameworks.io/state" in md

    # Test file export
    with tempfile.TemporaryDirectory() as tmp_dir:
        exported_path = export_report(report, output_dir=tmp_dir)
        assert os.path.isfile(exported_path)
        content = Path(exported_path).read_text(encoding="utf-8")
        assert "Stateful Agents" in content


def test_generate_report_filename_slug_derivation():
    """Verify filename is dynamically derived from research question, safe, slugified, and limited in length."""
    q1 = "Research recent advances in multimodal reasoning"
    fn1 = generate_report_filename(q1)
    assert fn1 == "research_recent_advances_in_multimodal_reasoning.md"

    # Query with punctuation and symbols
    q2 = "What are the latest AI agents? (2026 update) [v2.0] & benchmarks!"
    fn2 = generate_report_filename(q2)
    assert fn2 == "what_are_the_latest_ai_agents_2026_update_v20_benchmarks.md"
    assert "?" not in fn2
    assert "[" not in fn2
    assert "&" not in fn2

    # Super long query gets capped cleanly at 60 chars
    q3 = "This is an extremely long research query designed to test whether the slug generator correctly limits the overall length of the output file name"
    fn3 = generate_report_filename(q3)
    assert fn3.endswith(".md")
    assert len(fn3) <= 64  # 60 slug chars + 4 ext chars


@pytest.mark.asyncio
async def test_mock_synthesis_does_not_claim_unsupported_real_world_research():
    """Verify mock synthesis explicitly identifies simulated evaluation and avoids fabricating empirical research."""
    mock_llm = MockLLMProvider()
    q = "Investigate quantum error correction thresholds"
    report = await mock_llm.synthesize_research_report(
        research_question=q,
        goal_analysis=None,
        evidence=[],
        sources=[],
    )

    # Must be honest about simulated / mock mode
    exec_summary_lower = report.executive_summary.lower()
    assert "simulated" in exec_summary_lower or "mock" in exec_summary_lower

    # Limitations must clearly declare mock nature
    limitations_text = " ".join(report.limitations).lower()
    assert "simulated" in limitations_text or "mock" in limitations_text


def test_source_traceability_retained_in_report():
    """Verify findings in report link directly back to valid source citation URLs."""
    citation_url = "https://verified-source.org/paper-1"
    ev = EvidenceItem(
        source_url=citation_url,
        source_title="Verified Paper",
        source_domain="verified-source.org",
        claim="Specific empirical claim.",
        supporting_text="Full context quote supporting the claim.",
        relevance_score=0.95,
        content_hash="hash_verified",
    )
    finding = KeyFinding(
        claim="Specific empirical claim.",
        explanation="Explanation based on paper.",
        supporting_source_urls=[citation_url],
    )
    citation = SourceCitation(
        url=citation_url,
        title="Verified Paper",
        domain="verified-source.org",
        relevant_excerpts_count=1,
    )
    report = ResearchReport(
        research_question="Verify citations",
        executive_summary="Summary",
        key_findings=[finding],
        important_evidence=[ev],
        sources=[citation],
        actionable_insights=[],
        limitations=[],
    )

    # Finding source URL must exist in report.sources
    source_urls_in_report = {s.url for s in report.sources}
    for f in report.key_findings:
        for u in f.supporting_source_urls:
            assert u in source_urls_in_report
            assert u == ev.source_url


# ==============================================================================
# 5. INTEGRATION PIPELINE TEST
# ==============================================================================

@pytest.mark.asyncio
async def test_full_evidence_processing_and_synthesis_pipeline():
    """
    End-to-end integration test:
      fetched pages & search snippets
      -> candidate extraction
      -> relevance filtering
      -> deduplication
      -> structured report synthesis
      -> markdown artifact export
    """
    mock_llm = MockLLMProvider()

    state = {
        "query": "Research Agentic Workflows",
        "goal_analysis": GoalAnalysis(
            objective="Analyze workflows",
            topic="Agentic Workflows",
            constraints=[],
            output_requirements=[],
            success_criteria=[],
        ),
        "fetched_pages": [
            FetchedPage(
                url="https://research.org/agentic-ai",
                title="Agentic AI Workflows",
                content=(
                    "Autonomous agentic workflows rely on dynamic planning, tool selection, and reflection. "
                    "In contrast to static chains, agents evaluate intermediate results before deciding next actions. "
                    "Recent studies indicate an 80% task completion rate on complex multi-hop question answering."
                ),
                text_length=240,
                success=True,
            )
        ],
        "search_results": [
            SearchResultItem(
                title="Agentic Survey",
                url="https://research.org/agentic-ai",
                snippet="Autonomous agentic workflows rely on dynamic planning, tool selection, and reflection.",
                source="research.org",
            ),
            SearchResultItem(
                title="Unrelated Recipe",
                url="https://cooking.com/bread",
                snippet="Bake bread with water, yeast, salt, and flour at high temperature.",
                source="cooking.com",
            ),
        ],
        "step_count": 2,
        "max_steps": 10,
    }

    # 1. Execute evidence processing pipeline
    ev_update = await process_evidence_pipeline(state)
    assert "evidence_items" in ev_update
    assert len(ev_update["evidence_items"]) > 0
    assert ev_update["evidence_stats"]["relevant"] >= 1
    assert ev_update["evidence_stats"]["final"] >= 1

    # Update state with processed evidence
    state.update(ev_update)

    # 2. Execute report synthesis
    synth_update = await synthesize_report(state, llm_provider=mock_llm)
    assert "final_report" in synth_update
    report = synth_update["final_report"]
    assert isinstance(report, ResearchReport)
    assert len(report.key_findings) > 0
    assert len(report.sources) > 0

    state.update(synth_update)

    # 3. Export report artifact
    with tempfile.TemporaryDirectory() as tmp_dir:
        export_update = await export_report_artifact(state, output_dir=tmp_dir)
        assert export_update["status"] == "completed"
        assert export_update["is_complete"] is True
        assert os.path.isfile(export_update["report_file_path"])
