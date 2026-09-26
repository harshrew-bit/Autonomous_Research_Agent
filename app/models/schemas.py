"""
Pydantic schemas and data types defining state, goal analysis, tasks, plans, tool IO,
tool calls, observations, evaluations, and output reports.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class DecisionType(str, Enum):
    CONTINUE = "continue"
    RETRY = "retry"
    REPLAN = "replan"
    COMPLETE = "complete"
    FAIL = "fail"


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


class ToolCall(BaseModel):
    """Structured declaration of a tool invocation request."""
    tool_name: str = Field(description="Name of registered tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Validated argument map for the tool")
    purpose: str = Field(default="", description="Specific reason or goal for this tool call")


class Observation(BaseModel):
    """Structured record of the outcome of a tool execution step."""
    tool: str = Field(description="Name of tool that was executed")
    success: bool = Field(description="Whether the tool execution completed successfully")
    summary: str = Field(description="Concise summary of the result or failure")
    data_count: int = Field(default=0, description="Count of discrete items retrieved (e.g. results or chars)")
    error: Optional[str] = Field(default=None, description="Error message if execution failed")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional structured execution metadata")


class EvaluationDecision(BaseModel):
    """Assessment decision reached after evaluating the latest execution step."""
    decision: DecisionType = Field(description="Action to take next (continue, retry, replan, complete, fail)")
    reason: str = Field(description="Concise operational reason for the decision")
    confidence: float = Field(default=1.0, description="Confidence score [0.0 - 1.0]")
    next_action: str = Field(default="", description="Description of the subsequent planned action")


class SearchResultItem(BaseModel):
    """A single result item returned from a web search provider."""
    title: str = Field(description="Page or article title")
    url: str = Field(description="Canonical URL of search result")
    snippet: str = Field(description="Short text summary or snippet")
    source: Optional[str] = Field(default=None, description="Source domain or publication name")
    published_at: Optional[str] = Field(default=None, description="Publication timestamp if available")
    relevance_score: Optional[float] = Field(default=None, description="Relevance score from provider if available")


class SearchResponse(BaseModel):
    """Structured response container for web search queries."""
    query: str = Field(description="Original search query string")
    results: List[SearchResultItem] = Field(default_factory=list, description="List of search result items")
    provider: str = Field(default="tavily", description="Name of search provider used")
    success: bool = Field(default=True, description="Whether the search request succeeded")
    error: Optional[str] = Field(default=None, description="Error message if search failed")


class FetchedPage(BaseModel):
    """Structured result returned by the page fetcher tool."""
    url: str = Field(description="Target URL requested")
    final_url: Optional[str] = Field(default=None, description="Final URL after following redirects")
    title: Optional[str] = Field(default=None, description="Page title extracted from DOM")
    content: str = Field(default="", description="Cleaned readable text content extracted from page")
    content_hash: str = Field(default="", description="SHA-256 hash of extracted text for deduplication")
    text_length: int = Field(default=0, description="Character count of extracted content")
    status_code: Optional[int] = Field(default=None, description="HTTP response status code")
    content_type: Optional[str] = Field(default=None, description="MIME content type header")
    success: bool = Field(default=True, description="Whether page fetching and extraction succeeded")
    error: Optional[str] = Field(default=None, description="Error message if fetching failed")
    fetched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 UTC timestamp of fetch operation"
    )


class ResearchEvidence(BaseModel):
    """Structured evidence excerpt extracted from an external source."""
    source_url: str = Field(description="URL source of the evidence chunk")
    title: str = Field(description="Source document title")
    content_chunk: str = Field(description="Extracted relevant text excerpt")
    relevance_score: float = Field(default=1.0, description="Estimated relevance score [0.0 - 1.0]")


class ResearchReport(BaseModel):
    """Final structured report synthesized at the conclusion of research."""
    topic: str = Field(description="Main research topic")
    key_points: List[str] = Field(default_factory=list, description="High-level bullet points")
    important_findings: List[str] = Field(default_factory=list, description="Detailed discoveries and findings")
    sources: List[str] = Field(default_factory=list, description="List of referenced URLs or sources")
    actionable_insights: List[str] = Field(default_factory=list, description="Practical takeaways or recommendations")
