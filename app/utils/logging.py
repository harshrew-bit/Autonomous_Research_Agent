"""
Structured logging and execution trace utilities using Python standard logging and Rich.
"""

import logging
import sys
from typing import Optional, List, Any
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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
    def print_goal_analysis(goal_analysis: Any) -> None:
        """Display formatted goal breakdown trace."""
        lines = [
            f"[bold cyan]Objective:[/bold cyan] {getattr(goal_analysis, 'objective', '')}",
            f"[bold yellow]Topic:[/bold yellow] {getattr(goal_analysis, 'topic', '')}",
        ]
        constraints = getattr(goal_analysis, "constraints", [])
        if constraints:
            lines.append(f"[bold magenta]Constraints:[/bold magenta] {', '.join(constraints)}")
        
        time_range = getattr(goal_analysis, "time_range", None)
        if time_range:
            lines.append(f"[bold blue]Time Range:[/bold blue] {time_range}")

        output_reqs = getattr(goal_analysis, "output_requirements", [])
        if output_reqs:
            lines.append(f"[bold green]Output Requirements:[/bold green] {', '.join(output_reqs)}")

        criteria = getattr(goal_analysis, "success_criteria", [])
        if criteria:
            lines.append(f"[bold white]Success Criteria:[/bold white] {', '.join(criteria)}")

        console.print(Panel("\n".join(lines), title="[bold blue]1. GOAL ANALYSIS[/bold blue]", expand=False))

    @staticmethod
    def print_plan(query: str, rationale: str, tasks: List[Any]) -> None:
        """Display formatted dynamic plan decomposition table."""
        console.print(f"\n[bold green]2. DYNAMIC RESEARCH PLAN GENERATED[/bold green]")
        console.print(f"[bold yellow]Rationale:[/bold yellow] {rationale}\n")

        table = Table(title="Autonomous Plan Execution Trace", show_header=True, header_style="bold cyan")
        table.add_column("Step ID", style="dim", width=10)
        table.add_column("Description", width=35)
        table.add_column("Suggested Tool", style="bold green", width=16)
        table.add_column("Expected Output", style="italic", width=30)
        table.add_column("Status", width=12)

        for task in tasks:
            step_id = getattr(task, "id", "task_N")
            desc = getattr(task, "description", "")
            tool = getattr(task, "suggested_tool", getattr(task, "tool_name", "unknown"))
            expected = getattr(task, "expected_output", "")
            status = getattr(task, "status", "pending")
            status_str = status.value if hasattr(status, "value") else str(status)

            table.add_row(step_id, desc, tool, expected, f"[yellow]{status_str.upper()}[/yellow]")

        console.print(table)
        console.print("[dim green]✔ Plan generated successfully and ready for orchestration.[/dim green]\n")

    @staticmethod
    def print_tool_start(tool_name: str, target: str) -> None:
        """Display concise tool execution initiation."""
        console.print(f"\n[bold cyan][TOOL][/bold cyan] [bold]{tool_name}[/bold]")
        console.print(f"  [dim]Target/Input:[/dim] {target}")

    @staticmethod
    def print_tool_success(tool_name: str, summary: str) -> None:
        """Display tool completion summary."""
        console.print(f"  [bold green]✓ {tool_name} completed:[/bold green] {summary}")

    @staticmethod
    def print_tool_error(tool_name: str, target: str, error: str, recovery_hint: Optional[str] = None) -> None:
        """Display tool execution failure with optional recovery hint."""
        console.print(f"\n[bold red][TOOL ERROR][/bold red] [bold]{tool_name}[/bold]")
        console.print(f"  [dim]Target:[/dim] {target}")
        console.print(f"  [red]✗ Failure:[/red] {error}")
        if recovery_hint:
            console.print(f"  [magenta]↳ Recovery hint:[/magenta] {recovery_hint}")

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
