"""
LangGraph state graph assembly for autonomous research execution, evidence processing, and synthesis.
"""

from typing import Any
from langgraph.graph import StateGraph, START, END

from app.agent.state import ResearchAgentState
from app.agent.planner import analyze_goal, generate_plan, replan_research
from app.agent.executor import execute_step
from app.agent.evaluator import evaluate_step
from app.agent.evidence import process_evidence_pipeline
from app.agent.synthesizer import synthesize_report, export_report_artifact
from app.models.schemas import DecisionType
from app.utils.logging import get_logger

logger = get_logger("graph")


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
    elif decision == DecisionType.COMPLETE:
        return "process_evidence"
    else:
        # DecisionType.FAIL (e.g. step limit reached)
        # If any search/pages were collected, proceed to process evidence & synthesize report with limitations
        if state.get("search_results") or state.get("fetched_pages"):
            return "process_evidence"
        return END


def route_after_evidence(state: ResearchAgentState) -> str:
    """
    Routes from evidence processing: if evidence is insufficient and step budget remains,
    triggers adaptive replanning; otherwise proceeds to report synthesis.
    """
    evidence_items = state.get("evidence_items", [])
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 10)

    # If zero evidence items and step budget remains, trigger replan
    if len(evidence_items) == 0 and step_count < max_steps - 1:
        logger.info("[graph] Insufficient evidence collected; routing back to replan_research.")
        return "replan_research"

    return "synthesize_report"


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
                                                    | (complete)
                                                    v
                                             process_evidence
                                                    | (insufficient evidence & budget remains)
                                                    +-----> replan_research
                                                    | (sufficient evidence or budget limit)
                                                    v
                                             synthesize_report
                                                    |
                                                    v
                                             export_report
                                                    |
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
    workflow.add_node("process_evidence", process_evidence_pipeline)
    workflow.add_node("synthesize_report", synthesize_report)
    workflow.add_node("export_report", export_report_artifact)

    # 2. Add sequential transitions
    workflow.add_edge(START, "analyze_goal")
    workflow.add_edge("analyze_goal", "generate_plan")
    workflow.add_edge("generate_plan", "execute_step")
    workflow.add_edge("execute_step", "evaluate_step")
    workflow.add_edge("replan_research", "execute_step")
    workflow.add_edge("synthesize_report", "export_report")
    workflow.add_edge("export_report", END)

    # 3. Add conditional routing from evaluation node
    workflow.add_conditional_edges(
        "evaluate_step",
        route_evaluation,
        {
            "execute_step": "execute_step",
            "replan_research": "replan_research",
            "process_evidence": "process_evidence",
            END: END,
        }
    )

    # 4. Add conditional routing from evidence processing node
    workflow.add_conditional_edges(
        "process_evidence",
        route_after_evidence,
        {
            "replan_research": "replan_research",
            "synthesize_report": "synthesize_report",
        }
    )

    return workflow.compile()
