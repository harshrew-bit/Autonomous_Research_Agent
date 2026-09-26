"""
Planner module responsible for goal analysis, dynamic plan decomposition, and replanning.
"""

from typing import Dict, Any, Optional
from app.agent.state import ResearchAgentState
from app.agent.llm import get_llm_provider, LLMProvider
from app.models.schemas import GoalAnalysis, Plan
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
        "2. Suggest appropriate tools for each step (e.g., 'web_search', 'page_fetcher', 'evaluator', 'report_writer', "
        "'synthesizer', 'calculator').\n"
        "3. Specify clear sub-objectives, dependencies, and expected outputs for each step.\n"
        "4. Provide a clear rationale for the chosen plan architecture."
    )

    prompt = (
        f"User Query:\n\"{query}\"\n\n"
        f"Goal Analysis Breakdown:\n{analysis_str}\n\n"
        "Construct a detailed, dynamic execution plan for this research goal."
    )

    logger.info("Generating dynamic execution plan...")
    plan: Plan = await provider.generate_structured(
        prompt=prompt,
        response_schema=Plan,
        system_instruction=system_instruction,
    )

    # Print visible planning trace in CLI
    TraceLogger.print_plan(query=plan.query or query, rationale=plan.rationale, tasks=plan.tasks)

    return {"plan": plan}


async def plan_research(state: ResearchAgentState) -> Dict[str, Any]:
    """Legacy alias wrapping generate_plan for backward compatibility."""
    return await generate_plan(state)


async def replan_research(state: ResearchAgentState) -> Dict[str, Any]:
    """
    Revises active plan based on execution failures or evidence gaps.
    """
    logger.info("Replanning requested.")
    # Stub for execution phases
    return {}
