"""
Evaluator node responsible for assessing step outcomes, enforcing retry limits,
detecting failures, and determining next actions (continue, retry, replan, complete, fail).
"""

from typing import Dict, Any
from app.agent.state import ResearchAgentState
from app.models.schemas import (
    DecisionType,
    EvaluationDecision,
    Observation,
    TaskStatus,
)
from app.utils.logging import TraceLogger, get_logger

logger = get_logger("evaluator")


async def evaluate_step(state: ResearchAgentState) -> Dict[str, Any]:
    """
    Evaluates the most recent step observation against the agent plan, execution limits,
    and quality goals to decide whether to continue, retry, replan, or finish.
    """
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 10)
    max_retries = state.get("max_retries_per_task", 2)
    plan = state.get("plan")
    task_idx = state.get("current_task_index", 0)
    last_obs: Observation = state.get("last_observation")

    # 1. Step limit guard: prevent infinite execution loops
    if step_count >= max_steps:
        reason = f"Execution reached maximum allowed step limit ({max_steps}). Terminating execution."
        decision = EvaluationDecision(
            decision=DecisionType.FAIL,
            reason=reason,
            confidence=1.0,
            next_action="Halt execution to prevent runaway loop.",
        )
        TraceLogger.print_decision(decision.decision.value, decision.reason)
        return {
            "last_decision": decision,
            "status": "step_limit_reached",
            "is_complete": True,
            "error": reason,
        }

    # If no plan exists or no tasks
    if not plan or not plan.tasks:
        reason = "No plan available to evaluate."
        decision = EvaluationDecision(decision=DecisionType.FAIL, reason=reason)
        TraceLogger.print_decision(decision.decision.value, decision.reason)
        return {"last_decision": decision, "status": "failed", "is_complete": True}

    current_task = plan.tasks[task_idx] if task_idx < len(plan.tasks) else None

    # 2. Evaluate failure cases
    if last_obs and not last_obs.success:
        current_retries = getattr(current_task, "retry_count", 0) if current_task else 0
        err_text = (last_obs.error or "").lower()

        # Transient errors eligible for retry
        is_transient = any(w in err_text for w in ("timeout", "timed out", "rate limit", "429", "connection", "network"))

        if is_transient and current_retries < max_retries and current_task:
            current_task.retry_count += 1
            current_task.status = TaskStatus.RETRYING
            reason = f"Transient failure detected ('{last_obs.error}'); retrying task '{current_task.id}' (attempt {current_task.retry_count}/{max_retries})."
            decision = EvaluationDecision(
                decision=DecisionType.RETRY,
                reason=reason,
                confidence=0.9,
                next_action=f"Retry {current_task.id}",
            )
            TraceLogger.print_decision(decision.decision.value, decision.reason)
            return {
                "last_decision": decision,
                "current_task": current_task,
            }

        # Structural failures or retry limit exceeded -> trigger REPLAN
        reason = f"Task '{current_task.id if current_task else 'current'}' could not be completed ({last_obs.summary}). Triggering dynamic replanning."
        decision = EvaluationDecision(
            decision=DecisionType.REPLAN,
            reason=reason,
            confidence=0.85,
            next_action="Formulate alternative research tasks.",
        )
        TraceLogger.print_decision(decision.decision.value, decision.reason)
        return {
            "last_decision": decision,
            "status": "replanning",
        }

    # 3. Evaluate success cases
    if current_task:
        current_task.status = TaskStatus.COMPLETED
        current_task.result = last_obs.details if last_obs else None

    next_task_idx = task_idx + 1

    # Check if more tasks remain in plan
    if next_task_idx < len(plan.tasks):
        reason = f"Task completed successfully. Advancing to step {next_task_idx + 1} of {len(plan.tasks)}."
        decision = EvaluationDecision(
            decision=DecisionType.CONTINUE,
            reason=reason,
            confidence=1.0,
            next_action=f"Execute task {plan.tasks[next_task_idx].id}",
        )
        TraceLogger.print_decision(decision.decision.value, decision.reason)
        return {
            "current_task_index": next_task_idx,
            "current_task": plan.tasks[next_task_idx],
            "last_decision": decision,
        }

    # 4. All planned tasks executed: check if goal was sufficiently met
    evidence_count = len(state.get("evidence", []))
    search_count = len(state.get("search_results", []))

    if evidence_count > 0 or search_count > 0:
        reason = f"All {len(plan.tasks)} planned tasks executed successfully. Sufficient research evidence gathered."
        decision = EvaluationDecision(
            decision=DecisionType.COMPLETE,
            reason=reason,
            confidence=1.0,
            next_action="Conclude research execution.",
        )
        TraceLogger.print_decision(decision.decision.value, decision.reason)
        return {
            "current_task_index": next_task_idx,
            "last_decision": decision,
            "status": "completed",
            "is_complete": True,
        }
    else:
        # All tasks finished but zero evidence collected -> trigger replan
        reason = "All planned tasks completed, but zero evidence or sources were collected. Replanning with alternate approach."
        decision = EvaluationDecision(
            decision=DecisionType.REPLAN,
            reason=reason,
            confidence=0.8,
            next_action="Generate expanded search plan.",
        )
        TraceLogger.print_decision(decision.decision.value, decision.reason)
        return {
            "last_decision": decision,
            "status": "replanning",
        }


# Backwards compatibility alias
evaluate_step_result = evaluate_step
