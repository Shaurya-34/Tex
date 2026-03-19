"""Execution layer — shows the plan, asks for confirmation, runs the tool."""

from __future__ import annotations
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from tex.tools.registry import ToolCall, ToolDefinition
from tex.core.dispatcher import dispatch
from tex.core.logger import log_action, log_rejection
from tex.config import config
from tex.llm.client import interpret_output

console = Console()


def show_plan(tool_call: ToolCall, tool_def: ToolDefinition) -> None:
    """Display what Tex is about to do in a clear panel."""
    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Key", style="bold cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Tool", f"[bold yellow]{tool_call.tool}[/bold yellow]")

    for k, v in tool_call.arguments.items():
        table.add_row(k, str(v))

    if tool_call.requires_sudo:
        table.add_row("Privileges", "[bold red]requires sudo[/bold red]")

    if tool_def.destructive:
        table.add_row("Warning", "[bold red]This action is destructive[/bold red]")

    panel = Panel(
        table,
        title="[bold]Tex Plan[/bold]",
        subtitle=f"[dim]{tool_call.explanation}[/dim]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def ask_confirmation(destructive: bool = False) -> bool:
    """Prompt the user for explicit confirmation."""
    if destructive:
        console.print(
            "\n[bold red]This action is DESTRUCTIVE and cannot be undone.[/bold red]"
        )
        answer = typer.prompt(
            "Type 'yes' to confirm, anything else to cancel",
            default="no",
        )
        return answer.strip().lower() == "yes"
    else:
        return typer.confirm("Execute this plan?", default=True)


def execute(tool_call: ToolCall, tool_def: ToolDefinition, original_query: str = "") -> None:
    """Show plan → confirm → run → log result → optionally interpret.

    original_query is the user's raw input string, used by the two-pass
    interpretation path to give the LLM context for its analysis.
    For conversational tools (chat_response), skips plan/confirmation entirely.
    """
    # ── Conversational fast path ──────────────────────────────────────
    if tool_def.is_conversational:
        success, output = dispatch(tool_call)
        from rich.markdown import Markdown
        console.print(
            Panel(
                Markdown(output) if output else "(no response)",
                title="[bold cyan]Tex[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        log_action(
            tool=tool_call.tool,
            arguments=tool_call.arguments,
            status="success" if success else "failure",
            output=output,
        )
        return

    # ── Task execution path ───────────────────────────────────────────
    show_plan(tool_call, tool_def)

    if config.require_confirm:
        confirmed = ask_confirmation(destructive=tool_def.destructive)
        if not confirmed:
            console.print("\n[yellow]Cancelled. Nothing was executed.[/yellow]")
            log_rejection(f"User cancelled: tool={tool_call.tool}")
            return

    console.print()
    with console.status("[bold green]Running...[/bold green]", spinner="dots"):
        success, output = dispatch(tool_call)

    log_action(
        tool=tool_call.tool,
        arguments=tool_call.arguments,
        status="success" if success else "failure",
        output=output,
    )

    if success:
        console.print(
            Panel(
                output or "(no output)",
                title="[bold green]Output[/bold green]",
                border_style="green",
                padding=(1, 2),
            )
        )
        # ── Two-pass interpretation ───────────────────────────────────────
        # If this tool is marked interpretable and we have the user's original
        # question, stream an LLM analysis of the output below the raw panel.
        if tool_def.is_interpretable and original_query and output:
            interpret_output(
                original_query=original_query,
                tool_name=tool_call.tool,
                tool_output=output,
            )
    else:
        console.print(
            Panel(
                output or "(no error details)",
                title="[bold red]Error[/bold red]",
                border_style="red",
                padding=(1, 2),
            )
        )
