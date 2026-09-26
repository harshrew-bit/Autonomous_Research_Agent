"""
CLI entry point for the Autonomous Research Agent (Phase 4).
"""

import argparse
import asyncio
import os
from pathlib import Path
import sys
from dotenv import load_dotenv

# Ensure project root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.graph import build_research_graph
from app.utils.logging import get_logger, console

logger = get_logger("main")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for research topic and runtime flags."""
    parser = argparse.ArgumentParser(
        description="Autonomous Research Agent - Dynamic planning and autonomous tool execution"
    )
    parser.add_argument(
        "query",
        type=str,
        nargs="?",
        help="Research topic or question to investigate",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=10,
        help="Maximum agent execution steps allowed (default: 10)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Directory where research reports will be saved (default: reports)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider to use (e.g. 'gemini', 'mock'). Overrides LLM_PROVIDER env variable.",
    )
    parser.add_argument(
        "--search-provider",
        type=str,
        default=None,
        help="Search provider to use (e.g. 'tavily', 'mock'). Overrides SEARCH_PROVIDER env variable.",
    )
    parser.add_argument(
        "--simulate-failure",
        type=str,
        choices=["timeout", "empty", "none"],
        default=None,
        help="Deliberately induce a tool failure mode for resilience demonstration.",
    )
    return parser.parse_args()


async def run_agent(
    query: str,
    max_steps: int,
    output_dir: str,
    provider: str = None,
    search_provider: str = None,
    simulate_failure: str = None,
) -> dict:
    """Initializes state graph and runs autonomous research execution loop."""
    if provider:
        os.environ["LLM_PROVIDER"] = provider
    if search_provider:
        os.environ["SEARCH_PROVIDER"] = search_provider
    if simulate_failure and simulate_failure != "none":
        os.environ["SIMULATE_FAILURE"] = simulate_failure

    if output_dir:
        os.environ["OUTPUT_DIR"] = output_dir

    console.rule("[bold cyan]AUTONOMOUS RESEARCH AGENT[/bold cyan]")
    console.print(f"[bold white]User Research Query:[/bold white] {query}\n")

    graph = build_research_graph()

    initial_state = {
        "query": query,
        "goal_analysis": None,
        "plan": None,
        "current_task_index": 0,
        "current_task": None,
        "completed_tasks": [],
        "search_results": [],
        "fetched_pages": [],
        "evidence": [],
        "evidence_items": [],
        "evidence_stats": None,
        "visited_urls": [],
        "tool_results": [],
        "last_observation": None,
        "last_decision": None,
        "step_count": 0,
        "max_steps": max_steps,
        "retry_count": 0,
        "max_retries_per_task": 2,
        "execution_history": [],
        "is_complete": False,
        "status": "planning",
        "error": None,
        "final_report": None,
        "report_file_path": None,
    }

    logger.info("Executing LangGraph autonomous research loop...")
    final_state = await graph.ainvoke(initial_state)
    logger.info("LangGraph execution loop concluded.")

    # Final execution status summary banner
    status = final_state.get("status", "unknown")
    steps = final_state.get("step_count", 0)
    search_count = len(final_state.get("search_results", []))
    evidence_count = len(final_state.get("evidence_items", []))
    ev_stats = final_state.get("evidence_stats") or {}
    report = final_state.get("final_report")
    report_path = final_state.get("report_file_path")
    replans = [e for e in final_state.get("execution_history", []) if e.get("event") == "replan"]

    console.rule(style="bold green")
    console.print(f"[bold green]EXECUTION SUMMARY[/bold green]")
    console.print(f"  • [bold]Status:[/bold] {status.upper()}")
    console.print(f"  • [bold]Research Execution Steps:[/bold] {steps}/{max_steps}")
    console.print(f"  • [bold]Search Results Acquired:[/bold] {search_count}")
    if ev_stats:
        console.print(f"  • [bold cyan]Evidence Processing:[/bold cyan] [bold green]COMPLETED[/bold green]")
        console.print(f"    - Candidate evidence chunks: {ev_stats.get('candidates', 0)}")
        console.print(f"    - Relevant evidence identified: {ev_stats.get('relevant', 0)}")
        console.print(f"    - Duplicates removed: {ev_stats.get('duplicates_removed', 0)}")
        console.print(f"    - Final verified evidence set: {ev_stats.get('final', evidence_count)}")
    else:
        console.print(f"  • [bold]Evidence Items:[/bold] {evidence_count}")

    if report:
        console.print(f"  • [bold cyan]Report Synthesis:[/bold cyan] [bold green]COMPLETED[/bold green]")
        console.print(f"    - Key Findings: {len(report.key_findings)}")
        console.print(f"    - Sources Cited: {len(report.sources)}")
        console.print(f"    - Actionable Insights: {len(report.actionable_insights)}")

    if report_path:
        console.print(f"  • [bold green]Report Written To:[/bold green] [underline]{report_path}[/underline]")

    if replans:
        console.print(f"  • [bold magenta]Replanning Events:[/bold magenta] {len(replans)}")
    if final_state.get("error"):
        console.print(f"  • [bold red]Final Error:[/bold red] {final_state.get('error')}")
    console.rule(style="bold green")

    return final_state


def main() -> None:
    """CLI entry point."""
    load_dotenv()
    args = parse_args()

    if not args.query:
        console.print("[bold red]Error:[/bold red] Please provide a research query.")
        console.print("Example: python app/main.py \"Research recent developments in Agentic AI\"")
        sys.exit(1)

    try:
        asyncio.run(
            run_agent(
                query=args.query,
                max_steps=args.max_steps,
                output_dir=args.output_dir,
                provider=args.provider,
                search_provider=args.search_provider,
                simulate_failure=args.simulate_failure,
            )
        )
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        console.print(f"[bold red]Execution Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
