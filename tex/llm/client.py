"""Ollama LLM client for Tex."""

from __future__ import annotations
import json
import ollama
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.live import Live
from tex.config import config
from tex.llm.prompts import SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT, build_user_message

console = Console()

# Conversation history — list of {"role": ..., "content": ...} dicts
# Shared across calls in the same session (chat mode maintains state here)
_history: list[dict] = []

# Max turns to keep in history to avoid context bloat slowing things down
_MAX_HISTORY_TURNS = 10


def reset_history() -> None:
    """Clear conversation history (call at start of a new session)."""
    _history.clear()


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

    # Stream tokens live — user sees output immediately
    with Live(
        Panel("", title="[bold cyan]Tex[/bold cyan]", border_style="cyan", padding=(1, 2)),
        console=console,
        refresh_per_second=15,
        vertical_overflow="visible",
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

    console.print()  # newline after panel

    # Save assistant turn to history
    _history.append({"role": "assistant", "content": full_response})
    return full_response
