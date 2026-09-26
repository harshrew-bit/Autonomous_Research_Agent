"""
LangGraph state definitions for the autonomous research agent.
"""

from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
import operator

from app.models.schemas import Plan, Task, ResearchEvidence, ResearchReport


class ResearchAgentState(TypedDict):
    """
    Central state container passed between nodes in the LangGraph workflow.
    """
    # User input
    query: str

    # Planning & task execution state
    plan: Optional[Plan]
    current_task: Optional[Task]
    completed_tasks: Annotated[List[Task], operator.add]

    # Accumulated knowledge / evidence memory
    evidence: Annotated[List[Dict[str, Any]], operator.add]
    visited_urls: Annotated[List[str], operator.add]

    # Execution control state
    step_count: int
    max_steps: int
    retry_count: int
    is_complete: bool
    error: Optional[str]

    # Final output artifact
    final_report: Optional[ResearchReport]
