"""
LangGraph state definitions for the autonomous research agent.
"""

from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
import operator

from app.models.schemas import (
    GoalAnalysis,
    Plan,
    Task,
    SearchResultItem,
    FetchedPage,
    EvidenceItem,
    ResearchEvidence,
    ResearchReport,
    Observation,
    EvaluationDecision,
)


class ResearchAgentState(TypedDict):
    """
    Central state container passed between nodes in the LangGraph workflow.
    """
    # User input
    query: str

    # Goal analysis breakdown
    goal_analysis: Optional[GoalAnalysis]

    # Planning & task execution state
    plan: Optional[Plan]
    current_task_index: int
    current_task: Optional[Task]
    completed_tasks: Annotated[List[Task], operator.add]

    # Accumulated knowledge / evidence memory
    search_results: Annotated[List[SearchResultItem], operator.add]
    fetched_pages: Annotated[List[FetchedPage], operator.add]
    evidence: Annotated[List[Dict[str, Any]], operator.add]
    evidence_items: Annotated[List[EvidenceItem], operator.add]
    evidence_stats: Optional[Dict[str, int]]
    visited_urls: Annotated[List[str], operator.add]

    # Step execution observations & evaluations
    tool_results: Annotated[List[Dict[str, Any]], operator.add]
    last_observation: Optional[Observation]
    last_decision: Optional[EvaluationDecision]

    # Execution control & limits
    step_count: int
    max_steps: int
    retry_count: int
    max_retries_per_task: int
    execution_history: Annotated[List[Dict[str, Any]], operator.add]
    is_complete: bool
    status: str
    error: Optional[str]

    # Final output artifact
    final_report: Optional[ResearchReport]
    report_file_path: Optional[str]
