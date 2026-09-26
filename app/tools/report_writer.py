"""
Tool module for exporting structured research reports to Markdown (and optionally PDF).
"""

from typing import Optional
from app.models.schemas import ResearchReport


def export_report(report: ResearchReport, output_path: str, format_type: str = "markdown") -> str:
    """
    Exports a structured ResearchReport to disk in the specified format.

    Args:
        report: The structured ResearchReport instance.
        output_path: File path to save the generated report.
        format_type: Output format ('markdown' or 'pdf').

    Returns:
        Absolute path to the created file.
    """
    raise NotImplementedError("report_writer tool implementation pending Phase 2.")
