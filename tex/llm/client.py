"""Ollama LLM client for Tex."""

from __future__ import annotations
import json
import threading
import ollama
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from tex.config import config
from tex.llm.prompts import (
    SYSTEM_PROMPT,
    CHAT_SYSTEM_PROMPT,
    INTERPRET_SYSTEM_PROMPT,
    build_user_message,
    build_interpret_message,
)

console = Console()

# Conversation history — list of {"role": ..., "content": ...} dicts
# Shared across calls in the same session (chat mode maintains state here)
_history: list[dict] = []

# Max turns to keep in history to avoid context bloat slowing things down
_MAX_HISTORY_TURNS = 10

# Background warmup thread handle — kept so we can optionally join it
_warmup_thread: threading.Thread | None = None


def warmup_ollama() -> None:
    """
    Fire a minimal 1-token request to Ollama in a daemon background thread.

    Ollama loads model weights on the FIRST request, which causes the initial
    'Thinking...' delay. By sending a throwaway ping immediately when Tex
    starts, the model loads while Python is still printing output or waiting
    for user input. The real query then hits a warm server.

    The thread is a daemon — it dies automatically when the process exits, so
    it never blocks shutdown even if Ollama is slow or unreachable.
    Call this once at the start of 'ask' and 'chat' commands.
    """
    global _warmup_thread

    def _ping() -> None:
        try:
            ollama.chat(
                model=config.model,
                messages=[{"role": "user", "content": "hi"}],
                options={
                    "num_predict": 1,
                    "num_ctx": 512,
                    "temperature": 0,
                },
            )
        except Exception:
            pass  # Silently ignore — warmup is best-effort

    _warmup_thread = threading.Thread(target=_ping, daemon=True, name="tex-warmup")
    _warmup_thread.start()


def reset_history() -> None:
    """Clear conversation history (call at start of a new session)."""
    _history.clear()


def inject_tool_result(tool: str, arguments: dict) -> None:
    """
    Inject a brief tool execution summary into conversation history.

    Called after a tool runs successfully so the LLM knows what happened
    in the previous turn. Enables follow-up references:
      - "restart it"  → after "is nginx running?" → knows target is nginx
      - "why did it fail?" → knows which tool ran and with what args
      - "show me more logs" → knows it previously read journal for a unit

    Uses the 'user' role with a [SYSTEM] prefix so the model treats it as
    context rather than a new request.  Trimmed to avoid context bloat.
    """
    # Build a compact one-line summary: tool(arg1=val1, arg2=val2)
    arg_parts = ", ".join(f"{k}={repr(v)}" for k, v in arguments.items())
    summary = f"[SYSTEM: tool executed — {tool}({arg_parts})]"
    _history.append({"role": "user", "content": summary})
    # Immediately balance with a neutral assistant ack so history stays paired
    _history.append({"role": "assistant", "content": "Understood."})


def query_llm(user_input: str, maintain_history: bool = False) -> dict:
    """
    Send the user's input to the local LLM via Ollama.

    Args:
        user_input:       The user's raw text input.
        maintain_history: If True, appends to _history for multi-turn chat.
                          If False (default), uses a fresh single-turn call.

    Returns the parsed JSON dict or raises ValueError on bad output.
    """
    user_message = {"role": "user", "content": build_user_message(user_input)}

    if maintain_history:
        _history.append(user_message)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + _history
    else:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            user_message,
        ]

    with console.status(
        "[bold cyan]Thinking...[/bold cyan]",
        spinner="dots",
    ):
        response = ollama.chat(
            model=config.model,
            messages=messages,
            options={
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
                "num_ctx": config.num_ctx,
            },
        )

    raw = response["message"]["content"].strip()

    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        # In history mode, don't append broken output
        if maintain_history:
            _history.pop()  # remove the user message we just added
        raise ValueError(
            f"LLM returned non-JSON output.\n\nRaw output:\n{raw}\n\nError: {e}"
        )

    # Append assistant's response to history so the next turn has context
    if maintain_history:
        _history.append({"role": "assistant", "content": raw})
        # Trim history to avoid context bloat on long sessions
        if len(_history) > _MAX_HISTORY_TURNS * 2:
            _history[:] = _history[-((_MAX_HISTORY_TURNS * 2)):]

    return parsed


def stream_chat_response(user_input: str) -> str:
    """
    Stream a conversational response token-by-token directly to the terminal.

    Uses a lightweight chat-only system prompt (no JSON schema overhead).
    Maintains conversation history for multi-turn context.
    Returns the full accumulated response string.
    """
    user_message = {"role": "user", "content": user_input.strip()}
    _history.append(user_message)

    # Trim history to keep context window manageable
    if len(_history) > _MAX_HISTORY_TURNS * 2:
        _history[:] = _history[-((_MAX_HISTORY_TURNS * 2)):]

    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + _history

    full_response = ""
    console.print()  # newline before response

    # Stream tokens live — user sees output immediately.
    # transient=True clears all intermediate renders from the scrollback
    # buffer when streaming ends, preventing ghost panel duplicates on scroll.
    with Live(
        Panel("", title="[bold cyan]Tex[/bold cyan]", border_style="cyan", padding=(1, 2)),
        console=console,
        refresh_per_second=15,
        vertical_overflow="visible",
        transient=True,
    ) as live:
        for chunk in ollama.chat(
            model=config.model,
            messages=messages,
            stream=True,
            options={
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
                "num_ctx": config.num_ctx,
            },
        ):
            token = chunk["message"]["content"]
            full_response += token
            live.update(
                Panel(
                    Markdown(full_response),
                    title="[bold cyan]Tex[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

    # Print the final response once, permanently, so scrollback shows it cleanly
    console.print(
        Panel(
            Markdown(full_response),
            title="[bold cyan]Tex[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()  # newline after panel

    # Save assistant turn to history
    _history.append({"role": "assistant", "content": full_response})
    return full_response


def interpret_output(original_query: str, tool_name: str, tool_output: str) -> None:
    """
    Second-pass LLM call: stream an interpretation of tool output directly to
    the terminal in response to the user's original question.

    Uses a lightweight system prompt (no tool schema) — the only job here is
    to analyse the data and give a human-readable answer.  Streams with
    transient=True so the scrollback buffer only shows the final panel.
    """
    messages = [
        {"role": "system", "content": INTERPRET_SYSTEM_PROMPT},
        {"role": "user", "content": build_interpret_message(
            original_query, tool_name, tool_output
        )},
    ]

    full_response = ""

    with Live(
        Panel("", title="[bold cyan]Tex says[/bold cyan]", border_style="cyan", padding=(1, 2)),
        console=console,
        refresh_per_second=15,
        vertical_overflow="visible",
        transient=True,
    ) as live:
        try:
            for chunk in ollama.chat(
                model=config.model,
                messages=messages,
                stream=True,
                options={
                    "temperature": 0.3,        # slightly higher than task mode for fluency
                    "num_predict": config.max_tokens * 4,  # interpretations can be longer
                    "num_ctx": config.num_ctx,
                },
            ):
                token = chunk["message"]["content"]
                full_response += token
                live.update(
                    Panel(
                        Markdown(full_response),
                        title="[bold cyan]Tex says[/bold cyan]",
                        border_style="cyan",
                        padding=(1, 2),
                    )
                )
        except Exception as e:
            # Store the error — do NOT call live.update() here.
            # With transient=True, the Live context clears everything on exit,
            # so any live.update() made just before returning would be wiped
            # before the user sees it. Print the error outside the Live block.
            error_msg = str(e)
        else:
            error_msg = None

    # Live context has now fully exited — safe to print persistently

    if error_msg is not None:
        console.print(
            Panel(
                f"[dim](interpretation unavailable: {error_msg})[/dim]",
                title="[bold cyan]Tex says[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
        console.print()
        return

    # Print final panel permanently
    if full_response:
        console.print(
            Panel(
                Markdown(full_response),
                title="[bold cyan]Tex says[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
    console.print()
