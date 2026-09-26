"""
Structured logging and execution trace utilities using Python standard logging and Rich.
"""

import logging
import sys
from typing import Optional
from rich.console import Console
from rich.panel import Panel

console = Console()


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Returns a configured logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] [%(name)s] [%(levelname)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


class TraceLogger:
    """Utility for displaying visible planning and step execution traces in CLI."""

    @staticmethod
    def print_plan(query: str, rationale: str, tasks: list) -> None:
        """Display formatted plan decomposition trace."""
        lines = [f"[bold cyan]Research Query:[/bold cyan] {query}", f"[bold yellow]Rationale:[/bold yellow] {rationale}\n", "[bold green]Decomposed Tasks:[/bold green]"]
        for idx, task in enumerate(tasks, 1):
            tool = getattr(task, "tool_name", "unknown")
            desc = getattr(task, "description", str(task))
            lines.append(f"  {idx}. [bold]{tool}[/bold] -> {desc}")
        console.print(Panel("\n".join(lines), title="[bold blue]Agent Execution Plan[/bold blue]", expand=False))

    @staticmethod
    def print_step(step_number: int, task_desc: str, tool_name: str) -> None:
        """Display step start trace."""
        console.print(f"[bold green]▶ Step {step_number}:[/bold green] Invoking tool [cyan]{tool_name}[/cyan] for '{task_desc}'")

    @staticmethod
    def print_observation(status: str, detail: str) -> None:
        """Display step outcome observation."""
        color = "green" if status.lower() in ("completed", "success") else "red"
        console.print(f"  [{color}]↳ Observation ({status}):[/{color}] {detail}")

    @staticmethod
    def print_recovery(reason: str) -> None:
        """Display failure recovery or replanning trace."""
        console.print(f"  [bold magenta]⚠ Recovery triggered:[/bold magenta] {reason}")
