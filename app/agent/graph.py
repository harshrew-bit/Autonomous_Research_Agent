"""
LangGraph state graph assembly and compilation module for Phase 2.
"""

from typing import Any
from langgraph.graph import StateGraph, START, END
from app.agent.state import ResearchAgentState
from app.agent.planner import analyze_goal, generate_plan


def build_research_graph() -> Any:
    """
    Constructs and compiles the LangGraph state graph for Phase 2 planning flow.

    Workflow topology:
      START -> analyze_goal -> generate_plan -> END

    Returns:
        Compiled LangGraph StateGraph instance.
    """
    workflow = StateGraph(ResearchAgentState)

    # Register nodes
    workflow.add_node("analyze_goal", analyze_goal)
    workflow.add_node("generate_plan", generate_plan)

    # Define execution edges
    workflow.add_edge(START, "analyze_goal")
    workflow.add_edge("analyze_goal", "generate_plan")
    workflow.add_edge("generate_plan", END)

    return workflow.compile()
