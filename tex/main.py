"""Tex CLI — entry point."""

from __future__ import annotations
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from pathlib import Path
from tex import __version__
from tex.core.logger import setup_logger, log_error
from tex.core.validator import validate
from tex.core.executor import execute
from tex.llm.client import query_llm, reset_history, stream_chat_response, warmup_ollama
from tex.tools.registry import all_tool_names, TOOL_REGISTRY
from tex.config import config

app = typer.Typer(
    name="tex",
    help="Transparent, Local, Explainable Linux Task Assistant.",
    rich_markup_mode="rich",
)

console = Console()

_ASCII_BANNER = """
 [bold cyan]████████╗███████╗██╗  ██╗[/bold cyan]
 [bold cyan]╚══██╔══╝██╔════╝╚██╗██╔╝[/bold cyan]
 [bold cyan]   ██║   █████╗   ╚███╔╝ [/bold cyan]
 [bold cyan]   ██║   ██╔══╝   ██╔██╗ [/bold cyan]
 [bold cyan]   ██║   ███████╗██╔╝ ██╗[/bold cyan]
 [bold cyan]   ╚═╝   ╚══════╝╚═╝  ╚═╝[/bold cyan]
"""


def _header() -> None:
    console.print(_ASCII_BANNER)
    console.print(
        f"  [dim]v{__version__} "
    )


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    setup_logger()
    if ctx.invoked_subcommand is None:
        # No subcommand given — drop into interactive session.
        # 'tex' alone is the main daily-driver interface.
        # Use 'tex --help' to see all subcommands.
        chat()


# ── Commands ──────────────────────────────────────────────────────────────────

@app.command()
def ask(
    query: str = typer.Argument(..., help="What do you want to do?"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Show the plan without executing anything.",
    ),
    no_confirm: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip confirmation prompt (use with caution).",
    ),
) -> None:
    """Ask Tex to perform a Linux task in plain English."""
    warmup_ollama()  # start loading model weights in background immediately

    # Override config for this run if flags are set
    if no_confirm:
        config.require_confirm = False

    console.print(f"[dim]Query:[/dim] {query}\n")

    # 1. LLM
    try:
        raw = query_llm(query)
    except ValueError as e:
        console.print(
            Panel(str(e), title="[red]LLM Error[/red]", border_style="red")
        )
        log_error(str(e))
        raise typer.Exit(1)

    # 2. Validate
    result = validate(raw)
    if not result.valid:
        console.print(
            Panel(
                result.error,
                title="[red]Validation Failed[/red]",
                border_style="red",
                padding=(1, 2),
            )
        )
        log_error(result.error)
        raise typer.Exit(1)

    # 3. Execute (or dry-run)
    if dry_run:
        from tex.core.executor import show_plan
        show_plan(result.tool_call, result.tool_def)
        console.print("[yellow]Dry run — nothing executed.[/yellow]\n")
    else:
        execute(result.tool_call, result.tool_def)


@app.command()
def explain(
    command: str = typer.Argument(..., help="Shell command to explain"),
) -> None:
    """Ask Tex to explain what a shell command does (no execution)."""

    prompt = f"Explain what this command does: {command}"
    try:
        raw = query_llm(prompt)
    except ValueError as e:
        console.print(Panel(str(e), title="[red]LLM Error[/red]", border_style="red"))
        raise typer.Exit(1)

    result = validate(raw)
    if result.valid:
        console.print(
            Panel(
                result.tool_call.explanation,
                title=f"[cyan]Explanation: {command}[/cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
    else:
        # Fallback: show the raw explanation if present
        explanation = raw.get("explanation", "No explanation available.")
        console.print(
            Panel(
                explanation,
                title=f"[cyan]Explanation: {command}[/cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )


@app.command()
def tools() -> None:
    """List all tools available to Tex."""

    table = Table(
        title="Available Tools",
        box=box.ROUNDED,
        border_style="cyan",
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Tool", style="bold yellow", no_wrap=True)
    table.add_column("Description")
    table.add_column("Args", style="dim")
    table.add_column("Flags", justify="center")

    for name, t in TOOL_REGISTRY.items():
        flags = []
        if t.destructive:
            flags.append("[red]destructive[/red]")
        if t.needs_sudo:
            flags.append("[yellow]sudo[/yellow]")

        table.add_row(
            name,
            t.description,
            ", ".join(t.parameters) or "-",
            " ".join(flags) or "[green]safe[/green]",
        )

    console.print(table)
    console.print(f"\n[dim]Total: {len(TOOL_REGISTRY)} tools[/dim]\n")


@app.command()
def history(
    lines: int = typer.Option(50, "--lines", "-n", help="Number of log lines to show"),
) -> None:
    """View the Tex action log."""

    log_path = Path(config.log_file)
    if not log_path.exists():
        console.print("[yellow]No log file found yet. Run a command first.[/yellow]")
        raise typer.Exit()

    all_lines = log_path.read_text().splitlines()
    shown = all_lines[-lines:]

    console.print(
        Panel(
            "\n".join(shown) or "(empty)",
            title=f"[cyan]Action Log[/cyan] [dim]{log_path}[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


@app.command()
def version() -> None:
    """Show Tex version."""
    console.print(f"[bold cyan]Tex[/bold cyan] v{__version__}")


@app.command()
def chat() -> None:
    """Start an interactive chat session with Tex.
    
    You can mix tasks and conversation freely.
    Tex remembers context across turns in this session.
    Type 'exit' or 'quit' to end the session.
    """
    warmup_ollama()  # start loading model weights in background immediately
    reset_history()

    _header()
    console.print(
        Panel(
            "[bold]Interactive mode[/bold] — ask anything or give me a task.\n"
            "[dim]Mix questions and commands freely. I remember context across turns.\n"
            "Type [bold]exit[/bold] or [bold]quit[/bold] to end the session.\n"
            "Run [bold]tex --help[/bold] in another terminal to see all subcommands.[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()

    while True:
        try:
            user_input = console.input("[bold cyan]you[/bold cyan] › ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session ended.[/dim]")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "q", ":q"}:
            console.print("[dim]Session ended.[/dim]")
            break

        # ── Route: chat question vs system task ──────────────────────────
        # Heuristic: if input looks like a question or conversational message,
        # stream directly for instant response. Otherwise go through the full
        # LLM→JSON→validate→execute pipeline.
        if _looks_like_chat(user_input):
            stream_chat_response(user_input)
            continue

        # 1. LLM (with history) — full JSON task pipeline
        try:
            raw = query_llm(user_input, maintain_history=True)
        except ValueError as e:
            console.print(
                Panel(str(e), title="[red]LLM Error[/red]", border_style="red")
            )
            log_error(str(e))
            continue

        # 2. Validate
        result = validate(raw)
        if not result.valid:
            console.print(
                Panel(
                    result.error,
                    title="[red]Validation Failed[/red]",
                    border_style="red",
                    padding=(1, 2),
                )
            )
            log_error(result.error)
            continue

        # If the LLM chose chat_response anyway, stream it
        if result.tool_call.tool == "chat_response":
            message = result.tool_call.arguments.get("message", "")
            from rich.markdown import Markdown
            from rich.panel import Panel as _Panel
            console.print(
                _Panel(
                    Markdown(message),
                    title="[bold cyan]Tex[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )
            console.print()
            continue

        # 3. Execute task
        execute(result.tool_call, result.tool_def)
        console.print()


def _looks_like_chat(text: str) -> bool:
    """
    Fast heuristic — returns True if the input looks conversational rather
    than a system command/task. Errs on the side of using the task pipeline
    when ambiguous (false negatives are fine; false positives would skip tasks).
    """
    t = text.lower().strip()

    # Question starters
    if t.startswith(("what ", "why ", "how ", "when ", "who ", "where ",
                      "is ", "are ", "can ", "could ", "do ", "does ",
                      "should ", "would ", "tell me", "explain ",
                      "what's ", "what is ", "what are ")):
        return True

    # Contains a question mark and no action verbs at the start
    _task_verbs = {"install", "remove", "uninstall", "delete", "kill",
                   "copy", "move", "list", "read", "show", "open", "run",
                   "start", "stop", "search", "find", "check"}
    first_word = t.split()[0] if t.split() else ""
    if "?" in t and first_word not in _task_verbs:
        return True

    return False


if __name__ == "__main__":
    app()
