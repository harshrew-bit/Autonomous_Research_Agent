"""
CLI entry point for the Autonomous Research Agent (Phase 2).
"""

import argparse
import asyncio
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
        description="Autonomous Research Agent - Dynamic planning and iterative web research"
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
    return parser.parse_args()


async def run_agent(query: str, max_steps: int, output_dir: str, provider: str = None) -> None:
    """Initializes state graph and runs research cycle."""
    if provider:
        import os
        os.environ["LLM_PROVIDER"] = provider

    console.rule("[bold cyan]AUTONOMOUS RESEARCH AGENT[/bold cyan]")
    console.print(f"[bold white]User Research Query:[/bold white] {query}\n")

    graph = build_research_graph()

    initial_state = {
        "query": query,
        "goal_analysis": None,
        "plan": None,
        "current_task": None,
        "completed_tasks": [],
        "evidence": [],
        "visited_urls": [],
        "step_count": 0,
        "max_steps": max_steps,
        "retry_count": 0,
        "is_complete": False,
        "error": None,
        "final_report": None,
    }

    logger.info("Executing LangGraph planning pipeline...")
    final_state = await graph.ainvoke(initial_state)
    logger.info("LangGraph planning pipeline completed successfully.")


def main() -> None:
    """CLI entry point."""
    load_dotenv()
    args = parse_args()

    if not args.query:
        console.print("[bold red]Error:[/bold red] Please provide a research query.")
        console.print("Example: python app/main.py \"Research recent developments in Agentic AI\"")
        sys.exit(1)

    try:
        asyncio.run(run_agent(args.query, args.max_steps, args.output_dir, args.provider))
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        console.print(f"[bold red]Execution Error:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
