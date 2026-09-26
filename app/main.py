"""
CLI entry point for the Autonomous Research Agent.
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
    return parser.parse_args()


async def run_agent(query: str, max_steps: int, output_dir: str) -> None:
    """Initializes state graph and runs research cycle."""
    console.print(f"[bold green]Autonomous Research Agent[/bold green] - Starting research query: [bold]{query}[/bold]")
    raise NotImplementedError("run_agent CLI execution pending Phase 2.")


def main() -> None:
    """CLI entry point."""
    load_dotenv()
    args = parse_args()
    if not args.query:
        console.print("[bold red]Error:[/bold red] Please provide a research query.")
        sys.exit(1)
    try:
        asyncio.run(run_agent(args.query, args.max_steps, args.output_dir))
    except NotImplementedError as e:
        console.print(f"[yellow]Phase 1 Initialized successfully:[/yellow] {e}")
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
