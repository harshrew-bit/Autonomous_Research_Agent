"""
Report writer module for exporting structured ResearchReport instances to Markdown documents.
"""

import os
import re
from typing import Optional
from pathlib import Path

from app.models.schemas import ResearchReport
from app.utils.logging import get_logger

logger = get_logger("report_writer")


def generate_report_filename(research_question: str, extension: str = ".md") -> str:
    """
    Generates a deterministic, filesystem-safe filename derived directly from the user's research question.

    Normalizes whitespace, removes unsafe filesystem characters, converts to a clean slug,
    limits length to 60 characters, and appends the extension.

    Example:
        'Research recent advances in multimodal reasoning' -> 'research_recent_advances_in_multimodal_reasoning.md'
    """
    cleaned = re.sub(r"[^\w\s-]", "", research_question.strip().lower())
    slug = re.sub(r"[-\s]+", "_", cleaned).strip("_")
    slug = slug[:60].rstrip("_") or "research_report"
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{slug}{ext}"


def sanitize_filename(name: str) -> str:
    """Sanitizes a string into a clean, safe filename slug (alias for generate_report_filename)."""
    return generate_report_filename(name, extension="").rstrip(".")


def format_markdown_report(report: ResearchReport) -> str:
    """
    Renders a structured ResearchReport into GitHub-flavored Markdown.

    Args:
        report: Validated ResearchReport instance.

    Returns:
        Formatted Markdown string.
    """
    lines = []

    # Title
    topic = report.topic or report.research_question
    lines.append(f"# Research Report: {topic.strip()}")
    lines.append("")

    # Research Question
    lines.append("## Research Question")
    lines.append(f"> {report.research_question.strip()}")
    lines.append("")

    # Executive Summary
    lines.append("## Executive Summary")
    lines.append(report.executive_summary.strip())
    lines.append("")

    # Key Findings
    lines.append("## Key Findings")
    if report.key_findings:
        for idx, finding in enumerate(report.key_findings, 1):
            claim = finding.claim.strip()
            explanation = finding.explanation.strip()
            sources_md = ""
            if finding.supporting_source_urls:
                source_links = [f"[[{i+1}]]({url})" for i, url in enumerate(finding.supporting_source_urls)]
                sources_md = f" (Sources: {', '.join(source_links)})"
            lines.append(f"### {idx}. {claim}")
            lines.append(f"{explanation}{sources_md}")
            lines.append("")
    else:
        lines.append("*No key findings were synthesized.*")
        lines.append("")

    # Important Evidence
    if report.important_evidence:
        lines.append("## Important Evidence")
        for ev in report.important_evidence:
            domain = ev.source_domain or "web"
            lines.append(f"- **[{ev.source_title}]({ev.source_url})** ({domain}) - *Relevance: {ev.relevance_score:.2f}*")
            lines.append(f"  - **Claim:** {ev.claim}")
            lines.append(f"  - **Context:** \"{ev.supporting_text[:300]}{'...' if len(ev.supporting_text) > 300 else ''}\"")
        lines.append("")

    # Sources
    lines.append("## Sources")
    if report.sources:
        for idx, src in enumerate(report.sources, 1):
            count_info = f" ({src.relevant_excerpts_count} excerpts)" if src.relevant_excerpts_count > 1 else ""
            lines.append(f"{idx}. [{src.title}]({src.url}){count_info}")
    else:
        lines.append("*No external sources cited.*")
    lines.append("")

    # Actionable Insights
    lines.append("## Actionable Insights")
    if report.actionable_insights:
        for insight in report.actionable_insights:
            lines.append(f"- {insight.strip()}")
    else:
        lines.append("*No actionable insights provided.*")
    lines.append("")

    # Limitations
    lines.append("## Limitations")
    if report.limitations:
        for limitation in report.limitations:
            lines.append(f"- {limitation.strip()}")
    else:
        lines.append("*No explicit limitations identified.*")
    lines.append("")

    return "\n".join(lines)


def export_report(
    report: ResearchReport,
    output_path: Optional[str] = None,
    output_dir: str = "reports",
    format_type: str = "markdown",
) -> str:
    """
    Exports a structured ResearchReport to disk.

    Args:
        report: The structured ResearchReport instance.
        output_path: Optional explicit file path.
        output_dir: Directory where reports are stored if output_path is not specified.
        format_type: Output format ('markdown' supported; 'pdf' in future).

    Returns:
        Absolute path to the created file.
    """
    if format_type.lower() != "markdown":
        raise ValueError(f"Unsupported format '{format_type}'. Only 'markdown' is currently supported.")

    if not output_path:
        filename = generate_report_filename(report.research_question)
        output_path = os.path.join(output_dir, filename)

    path_obj = Path(output_path).resolve()
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    markdown_content = format_markdown_report(report)
    path_obj.write_text(markdown_content, encoding="utf-8")

    logger.info(f"Research report exported successfully to: {path_obj}")
    return str(path_obj)
