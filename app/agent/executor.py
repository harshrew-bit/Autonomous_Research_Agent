"""
Executor node responsible for task resolution, dynamic tool argument determination,
tool dispatch, observation recording, and state synchronization.
"""

from typing import Dict, Any, Optional, List
from app.agent.state import ResearchAgentState
from app.models.schemas import (
    Task,
    TaskStatus,
    ToolCall,
    Observation,
    SearchResultItem,
    SearchResponse,
    FetchedPage,
)
from app.tools.registry import TOOL_REGISTRY, ToolRegistry
from app.utils.logging import TraceLogger, get_logger

logger = get_logger("executor")


def resolve_tool_call(task: Task, state: ResearchAgentState) -> ToolCall:
    """
    Dynamically determines tool name and arguments for the active task.

    For 'web_search': derives the search query from task input, description, or global query.
    For 'page_fetcher': selects the most relevant unvisited URL from accumulated search results.

    Raises:
        ValueError: If tool cannot be resolved or prerequisite arguments are missing.
    """
    raw_tool = getattr(task, "suggested_tool", getattr(task, "tool_name", "web_search"))
    tool_name = raw_tool.strip().lower()

    # Normalization of synonyms
    if "search" in tool_name:
        tool_name = "web_search"
    elif "fetch" in tool_name or "scrape" in tool_name or "page" in tool_name:
        tool_name = "page_fetcher"

    tool_input = dict(getattr(task, "tool_input", {}) or {})
    visited_urls = set(state.get("visited_urls", []))

    if tool_name == "web_search":
        query = tool_input.get("query")
        if not query:
            # Extract core research topic from goal analysis or user query
            goal_analysis = state.get("goal_analysis")
            core_topic = getattr(goal_analysis, "topic", "") or state.get("query", "")
            core_topic = core_topic.strip()

            # Clean task description of generic boilerplate prefixes
            cleaned_desc = task.description.strip()
            for prefix in ("Search for", "Search", "Find", "Look up", "Gather info on", "Gather sources on", "Investigate"):
                if cleaned_desc.lower().startswith(prefix.lower()):
                    cleaned_desc = cleaned_desc[len(prefix):].strip()
                    break

            # If task description already mentions the topic, use it; otherwise combine with topic
            topic_lower = core_topic.lower()
            desc_lower = cleaned_desc.lower()
            topic_words = {w for w in topic_lower.split() if len(w) > 3}
            desc_words = {w for w in desc_lower.split() if len(w) > 3}
            overlap = topic_words.intersection(desc_words)

            if overlap or topic_lower in desc_lower:
                query = cleaned_desc
            elif cleaned_desc:
                query = f"{core_topic} {cleaned_desc}"
            else:
                query = core_topic

        max_results = tool_input.get("max_results", 5)
        return ToolCall(
            tool_name="web_search",
            arguments={"query": query.strip(), "max_results": max_results},
            purpose=task.objective or task.description,
        )

    elif tool_name == "page_fetcher":
        url = tool_input.get("url")
        if not url:
            # Select first unvisited URL from accumulated search results
            search_results: List[SearchResultItem] = state.get("search_results", [])
            for res in search_results:
                candidate_url = res.url
                if candidate_url and candidate_url not in visited_urls:
                    url = candidate_url
                    break

        if not url:
            raise ValueError(
                f"Cannot execute page_fetcher for task '{task.id}': No candidate URL available. "
                "Search must precede page fetching or a valid URL must be provided."
            )

        return ToolCall(
            tool_name="page_fetcher",
            arguments={"url": url},
            purpose=task.objective or task.description,
        )

    return ToolCall(
        tool_name=tool_name,
        arguments=tool_input,
        purpose=task.objective or task.description,
    )


async def execute_step(
    state: ResearchAgentState,
    tool_registry: Optional[ToolRegistry] = None,
) -> Dict[str, Any]:
    """
    Executes the current active task in the agent's plan using the registered tools.

    Records the tool execution outcome as an Observation and updates accumulated evidence.
    """
    registry = tool_registry or TOOL_REGISTRY
    plan = state.get("plan")
    if not plan or not plan.tasks:
        logger.warning("execute_step invoked with no plan or empty task sequence.")
        return {"status": "completed", "is_complete": True}

    task_idx = state.get("current_task_index", 0)
    if task_idx >= len(plan.tasks):
        logger.info(f"All {len(plan.tasks)} plan tasks have been processed.")
        return {"status": "completed", "is_complete": True}

    task = plan.tasks[task_idx]
    step_count = state.get("step_count", 0) + 1
    retry_count = getattr(task, "retry_count", 0)
    is_retry = retry_count > 0

    # Display execution trace header
    TraceLogger.print_step_header(
        step_number=step_count,
        task_desc=task.description,
        tool_name=task.suggested_tool or task.tool_name,
        is_retry=is_retry,
    )

    # 1. Resolve and validate tool call
    try:
        tool_call = resolve_tool_call(task, state)
    except Exception as e:
        err_msg = str(e)
        logger.error(f"Failed to resolve tool call for task {task.id}: {err_msg}")
        observation = Observation(
            tool=task.suggested_tool or "unknown",
            success=False,
            summary=f"Tool argument resolution failed: {err_msg}",
            error=err_msg,
        )
        TraceLogger.print_step_outcome(False, err_msg)
        TraceLogger.print_observation_box(observation.summary)
        return {
            "step_count": step_count,
            "current_task": task,
            "last_observation": observation,
            "tool_results": [{"task_id": task.id, "error": err_msg}],
        }

    # 2. Execute tool through safe registry
    new_search_results: List[SearchResultItem] = []
    new_fetched_pages: List[FetchedPage] = []
    new_evidence: List[Dict[str, Any]] = []
    new_visited_urls: List[str] = []

    try:
        raw_result = await registry.execute(tool_call.tool_name, tool_call.arguments)

        if isinstance(raw_result, SearchResponse):
            if raw_result.success:
                new_search_results = raw_result.results
                summary = f"Retrieved {len(raw_result.results)} search results for '{tool_call.arguments.get('query')}'"
                observation = Observation(
                    tool="web_search",
                    success=True,
                    summary=summary,
                    data_count=len(raw_result.results),
                    details={"query": raw_result.query, "result_count": len(raw_result.results)},
                )
            else:
                summary = f"Search failed: {raw_result.error}"
                observation = Observation(
                    tool="web_search",
                    success=False,
                    summary=summary,
                    error=raw_result.error,
                )

        elif isinstance(raw_result, FetchedPage):
            if raw_result.success:
                new_fetched_pages = [raw_result]
                new_visited_urls = [raw_result.url]
                if raw_result.final_url and raw_result.final_url != raw_result.url:
                    new_visited_urls.append(raw_result.final_url)

                new_evidence = [
                    {
                        "source_url": raw_result.final_url or raw_result.url,
                        "title": raw_result.title or "Untitled",
                        "content_chunk": raw_result.content[:2000],
                        "relevance_score": 1.0,
                    }
                ]
                summary = f"Extracted {raw_result.text_length} chars from '{raw_result.title or raw_result.url}'"
                observation = Observation(
                    tool="page_fetcher",
                    success=True,
                    summary=summary,
                    data_count=raw_result.text_length,
                    details={"url": raw_result.url, "title": raw_result.title},
                )
            else:
                summary = f"Fetch failed for {raw_result.url}: {raw_result.error}"
                observation = Observation(
                    tool="page_fetcher",
                    success=False,
                    summary=summary,
                    error=raw_result.error,
                )

        else:
            summary = f"Tool {tool_call.tool_name} returned unhandled result type."
            observation = Observation(
                tool=tool_call.tool_name,
                success=True,
                summary=summary,
                details={"result_type": type(raw_result).__name__},
            )

    except Exception as e:
        err_msg = str(e)
        logger.error(f"Tool execution exception for task {task.id}: {err_msg}")
        summary = f"Execution crashed: {err_msg}"
        observation = Observation(
            tool=tool_call.tool_name,
            success=False,
            summary=summary,
            error=err_msg,
        )

    # 3. Print operational trace
    TraceLogger.print_step_outcome(observation.success, observation.summary)
    TraceLogger.print_observation_box(observation.summary)

    # 4. Construct state updates
    execution_event = {
        "step": step_count,
        "task_id": task.id,
        "tool": tool_call.tool_name,
        "arguments": tool_call.arguments,
        "success": observation.success,
        "summary": observation.summary,
    }

    state_update: Dict[str, Any] = {
        "step_count": step_count,
        "current_task": task,
        "last_observation": observation,
        "tool_results": [execution_event],
        "execution_history": [execution_event],
    }

    if new_search_results:
        state_update["search_results"] = new_search_results
    if new_fetched_pages:
        state_update["fetched_pages"] = new_fetched_pages
    if new_evidence:
        state_update["evidence"] = new_evidence
    if new_visited_urls:
        state_update["visited_urls"] = new_visited_urls

    return state_update
