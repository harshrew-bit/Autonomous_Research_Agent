"""
LangGraph state graph assembly for Phase 4 autonomous research execution loop.
"""

from typing import Any
from langgraph.graph import StateGraph, START, END

from app.agent.state import ResearchAgentState
from app.agent.planner import analyze_goal, generate_plan, replan_research
from app.agent.executor import execute_step
from app.agent.evaluator import evaluate_step
from app.models.schemas import DecisionType


def route_evaluation(state: ResearchAgentState) -> str:
    """
    Conditional edge router evaluating the evaluator's decision to route the next graph node.
    """
    last_decision = state.get("last_decision")
    if not last_decision:
        return END

    decision = last_decision.decision
    if decision in (DecisionType.CONTINUE, DecisionType.RETRY):
        return "execute_step"
    elif decision == DecisionType.REPLAN:
        return "replan_research"
    else:
        return END


def build_research_graph() -> Any:
    """
    Constructs and compiles the full cyclical LangGraph state graph.

    Workflow topology:
      START -> analyze_goal -> generate_plan -> execute_step -> evaluate_step
                                                    ^             |
                                                    | (continue / retry)
                                                    +-------------+
                                                    | (replan)
                                                    v
                                             replan_research ----> execute_step
                                                    | (complete / fail)
                                                    v
                                                   END
    """
    workflow = StateGraph(ResearchAgentState)

    # 1. Register operational nodes
    workflow.add_node("analyze_goal", analyze_goal)
    workflow.add_node("generate_plan", generate_plan)
    workflow.add_node("execute_step", execute_step)
    workflow.add_node("evaluate_step", evaluate_step)
    workflow.add_node("replan_research", replan_research)

    # 2. Add sequential transitions
    workflow.add_edge(START, "analyze_goal")
    workflow.add_edge("analyze_goal", "generate_plan")
    workflow.add_edge("generate_plan", "execute_step")
    workflow.add_edge("execute_step", "evaluate_step")
    workflow.add_edge("replan_research", "execute_step")

    # 3. Add conditional routing from evaluation node
    workflow.add_conditional_edges(
        "evaluate_step",
        route_evaluation,
        {
            "execute_step": "execute_step",
            "replan_research": "replan_research",
            END: END,
        }
    )

    return workflow.compile()
