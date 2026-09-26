"""
Pydantic schemas and data types defining state, goal analysis, tasks, plans, tool IO, and output reports.
"""

from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class GoalAnalysis(BaseModel):
    """Structured breakdown of a user's high-level research goal."""
    objective: str = Field(description="Primary objective of the research request")
    topic: str = Field(description="Core domain or subject matter of the research")
    constraints: List[str] = Field(
        default_factory=list,
        description="Boundaries, filters, or specific scope limits (e.g. timeframes, level of detail)"
    )
    time_range: Optional[str] = Field(
        default=None,
        description="Temporal boundary if specified in the user request (e.g. 'last 7 days')"
    )
    output_requirements: List[str] = Field(
        default_factory=list,
        description="Required format, deliverables, or key sections requested"
    )
    success_criteria: List[str] = Field(
        default_factory=list,
        description="Specific verification criteria to determine when the research is complete"
    )


class Task(BaseModel):
    """An individual task within an autonomous execution plan."""
    id: str = Field(description="Unique identifier for the task, e.g. task_1")
    description: str = Field(description="Clear action-oriented task description")
    objective: str = Field(default="", description="Specific sub-goal this task aims to accomplish")
    expected_output: str = Field(default="", description="Description of expected deliverable/data from this step")
    suggested_tool: str = Field(description="Name of the tool suggested for executing this step")
    dependencies: List[str] = Field(
        default_factory=list,
        description="IDs of prerequisite tasks that must be completed before this step"
    )
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="Input parameters passed to the tool")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="Current execution status")
    result: Optional[Any] = Field(default=None, description="Observed output from tool execution")
    error: Optional[str] = Field(default=None, description="Error message if task failed")
    retry_count: int = Field(default=0, description="Number of retry attempts made")


class Plan(BaseModel):
    """Dynamically generated sequence of tasks to achieve the user's research goal."""
    query: str = Field(description="Original research topic or query submitted by user")
    rationale: str = Field(description="Explanation of why this dynamic plan decomposition was selected")
    tasks: List[Task] = Field(default_factory=list, description="Sequence of subtasks to execute")
    current_task_index: int = Field(default=0, description="Index of task currently under execution")


class SearchResultItem(BaseModel):
    title: str = Field(description="Page or article title")
    url: str = Field(description="Canonical URL of search result")
    snippet: str = Field(description="Short text summary or snippet")


class FetchedPage(BaseModel):
    url: str = Field(description="URL of fetched web page")
    title: Optional[str] = Field(default=None, description="Page title extracted from DOM")
    content: str = Field(description="Cleaned main text content")
    content_hash: str = Field(description="SHA-256 hash of extracted text for deduplication")
    text_length: int = Field(description="Character count of extracted content")


class ResearchEvidence(BaseModel):
    source_url: str = Field(description="URL source of the evidence chunk")
    title: str = Field(description="Source document title")
    content_chunk: str = Field(description="Extracted relevant text excerpt")
    relevance_score: float = Field(default=1.0, description="Estimated relevance score [0.0 - 1.0]")


class ResearchReport(BaseModel):
    topic: str = Field(description="Main research topic")
    key_points: List[str] = Field(default_factory=list, description="High-level bullet points")
    important_findings: List[str] = Field(default_factory=list, description="Detailed discoveries and findings")
    sources: List[str] = Field(default_factory=list, description="List of referenced URLs or sources")
    actionable_insights: List[str] = Field(default_factory=list, description="Practical takeaways or recommendations")
