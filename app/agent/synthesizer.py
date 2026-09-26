"""
Synthesizer and export nodes for the LangGraph autonomous research workflow.
Consumes processed, deduplicated evidence and produces validated ResearchReport artifacts.
"""

from typing import Dict, Any, Optional, List
import os

from app.agent.state import ResearchAgentState
from app.agent.llm import get_llm_provider, LLMProvider
from app.models.schemas import ResearchReport, EvidenceItem
from app.tools.report_writer import export_report
from app.utils.logging import get_logger, TraceLogger

logger = get_logger("synthesizer")


async def synthesize_report(
    state: ResearchAgentState,
    llm_provider: Optional[LLMProvider] = None,
) -> Dict[str, Any]:
    """
    LangGraph node: Synthesizes final structured ResearchReport from gathered evidence items.

    Args:
        state: Active research state containing evidence_items and query.
        llm_provider: Optional injected LLMProvider.

    Returns:
        State update dictionary containing 'final_report'.
    """
    provider = llm_provider or get_llm_provider()
    query = state.get("query", "")
    goal_analysis = state.get("goal_analysis")

    evidence_items: List[EvidenceItem] = state.get("evidence_items", [])
    raw_evidence: List[Dict[str, Any]] = state.get("evidence", [])
    search_results = state.get("search_results", [])

    # If evidence_items is empty, convert legacy raw evidence dicts to EvidenceItem
    if not evidence_items and raw_evidence:
        for ev in raw_evidence:
            try:
                evidence_items.append(EvidenceItem.model_validate(ev))
            except Exception:
                pass

    sources = [
        {"url": r.url, "title": r.title, "source": getattr(r, "source", None) or "web"}
        for r in search_results
    ]

    TraceLogger.print_pipeline_stage(
        "REPORT SYNTHESIS",
        f"Synthesizing structured research report for '{query}'",
    )
    logger.info(f"[synthesize_report] Synthesizing report across {len(evidence_items)} evidence items...")

    report: ResearchReport = await provider.synthesize_research_report(
        research_question=query,
        goal_analysis=goal_analysis,
        evidence=evidence_items,
        sources=sources,
    )

    TraceLogger.print_tool_success(
        "llm_synthesis",
        f"Generated ResearchReport with {len(report.key_findings)} key findings and {len(report.sources)} sources."
    )

    return {
        "final_report": report,
    }


async def export_report_artifact(
    state: ResearchAgentState,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    LangGraph node: Writes the synthesized ResearchReport to disk as a Markdown artifact.

    Args:
        state: Active research state containing final_report.
        output_dir: Optional explicit directory path.

    Returns:
        State update dictionary containing 'report_file_path', 'status', and 'is_complete'.
    """
    report: Optional[ResearchReport] = state.get("final_report")
    out_dir = output_dir or os.getenv("OUTPUT_DIR", "reports")

    if not report:
        logger.warning("[export_report_artifact] No final_report present in state; skipping export.")
        return {
            "status": "completed_without_report",
            "is_complete": True,
        }

    file_path = export_report(report, output_dir=out_dir)

    TraceLogger.print_tool_success("report_writer", f"Report saved to: {file_path}")

    return {
        "report_file_path": file_path,
        "status": "completed",
        "is_complete": True,
    }
