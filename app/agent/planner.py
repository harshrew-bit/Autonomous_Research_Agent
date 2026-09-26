"""
Planner module responsible for goal analysis, dynamic plan decomposition, and autonomous replanning.
"""

from typing import Dict, Any, Optional
from app.agent.state import ResearchAgentState
from app.agent.llm import get_llm_provider, LLMProvider
from app.models.schemas import GoalAnalysis, Plan, Task, LLMPlan
from app.utils.logging import TraceLogger, get_logger

logger = get_logger("planner")


async def analyze_goal(
    state: ResearchAgentState,
    llm_provider: Optional[LLMProvider] = None
) -> Dict[str, Any]:
    """
    Analyzes the user's research query to extract structured goal parameters, constraints, and criteria.

    Args:
        state: Current ResearchAgentState containing user query.
        llm_provider: Optional LLMProvider instance (defaults to factory lookup).

    Returns:
        State update dictionary containing 'goal_analysis'.
    """
    query = state.get("query", "")
    if not query:
        raise ValueError("Cannot analyze empty query in agent state.")

    provider = llm_provider or get_llm_provider()

    system_instruction = (
        "You are an expert AI Research Assistant. Your task is to analyze the user's high-level research goal "
        "and decompose it into a structured analysis containing objective, core topic, constraints, time boundaries, "
        "output requirements, and success verification criteria."
    )

    prompt = (
        f"User Research Query:\n\"{query}\"\n\n"
        "Decompose this request into a structured GoalAnalysis."
    )

    logger.info(f"Analyzing goal for query: '{query}'")
    goal_analysis: GoalAnalysis = await provider.generate_structured(
        prompt=prompt,
        response_schema=GoalAnalysis,
        system_instruction=system_instruction,
    )

    # Print visible trace in CLI
    TraceLogger.print_goal_analysis(goal_analysis)

    return {"goal_analysis": goal_analysis}


async def generate_plan(
    state: ResearchAgentState,
    llm_provider: Optional[LLMProvider] = None
) -> Dict[str, Any]:
    """
    Generates a dynamic, multi-step execution plan based on the goal analysis breakdown.

    Args:
        state: Current ResearchAgentState containing user query and goal_analysis.
        llm_provider: Optional LLMProvider instance.

    Returns:
        State update dictionary containing 'plan'.
    """
    query = state.get("query", "")
    goal_analysis = state.get("goal_analysis")

    provider = llm_provider or get_llm_provider()

    analysis_str = goal_analysis.model_dump_json(indent=2) if goal_analysis else "No explicit analysis"

    system_instruction = (
        "You are an Autonomous AI Plan Architect. Your task is to construct a tailored, step-by-step research plan "
        "for a given user query and goal analysis breakdown.\n\n"
        "IMPORTANT RULES:\n"
        "1. Do NOT produce a fixed or generic sequence. Construct a plan specifically tailored to the query, topic, "
        "time limits, and output criteria.\n"
        "2. Suggest appropriate tools for each step (e.g., 'web_search', 'page_fetcher').\n"
        "3. Specify clear sub-objectives, dependencies, and expected outputs for each step.\n"
        "4. Provide a clear rationale for the chosen plan architecture."
    )

    prompt = (
        f"User Query:\n\"{query}\"\n\n"
        f"Goal Analysis Breakdown:\n{analysis_str}\n\n"
        "Construct a detailed, dynamic execution plan for this research goal."
    )

    logger.info("Generating dynamic execution plan...")
    raw_plan = await provider.generate_structured(
        prompt=prompt,
        response_schema=LLMPlan,
        system_instruction=system_instruction,
    )
    plan: Plan = raw_plan.to_runtime_plan() if hasattr(raw_plan, "to_runtime_plan") else raw_plan

    # Print visible planning trace in CLI
    TraceLogger.print_plan(query=plan.query or query, rationale=plan.rationale, tasks=plan.tasks)

    return {
        "plan": plan,
        "current_task_index": 0,
        "current_task": plan.tasks[0] if plan.tasks else None,
        "status": "executing",
    }


async def replan_research(
    state: ResearchAgentState,
    llm_provider: Optional[LLMProvider] = None
) -> Dict[str, Any]:
    """
    Autonomously creates an adjusted research plan after a tool failure or insufficient findings.
    """
    query = state.get("query", "")
    last_obs = state.get("last_observation")
    last_dec = state.get("last_decision")
    prev_plan = state.get("plan")

    reason = last_dec.reason if last_dec else (last_obs.summary if last_obs else "Insufficient progress.")
    TraceLogger.print_replan_notice(reason)

    provider = llm_provider or get_llm_provider()

    system_instruction = (
        "You are an Autonomous AI Replanner. The prior research plan encountered a failure or produced insufficient evidence.\n"
        "Analyze the failure reason and formulate an updated, alternative research plan to overcome the barrier.\n"
        "Allowed tools: 'web_search', 'page_fetcher'."
    )

    prev_tasks_str = ", ".join(f"[{t.id}: {t.description}]" for t in prev_plan.tasks) if prev_plan else "None"
    prompt = (
        f"Original Query: \"{query}\"\n"
        f"Reason for Replanning: {reason}\n"
        f"Prior Tasks: {prev_tasks_str}\n\n"
        "Formulate a revised, adaptive research plan with alternative search keywords or sources."
    )

    logger.info("Generating revised plan via LLM...")
    raw_revised_plan = await provider.generate_structured(
        prompt=prompt,
        response_schema=LLMPlan,
        system_instruction=system_instruction,
    )
    revised_plan: Plan = raw_revised_plan.to_runtime_plan() if hasattr(raw_revised_plan, "to_runtime_plan") else raw_revised_plan

    TraceLogger.print_plan(
        query=revised_plan.query or query,
        rationale=f"REVISED PLAN: {revised_plan.rationale}",
        tasks=revised_plan.tasks,
    )

    replan_event = {
        "event": "replan",
        "reason": reason,
        "new_task_count": len(revised_plan.tasks),
    }

    return {
        "plan": revised_plan,
        "current_task_index": 0,
        "current_task": revised_plan.tasks[0] if revised_plan.tasks else None,
        "status": "executing",
        "execution_history": [replan_event],
    }


# Backwards compatibility alias
plan_research = generate_plan
