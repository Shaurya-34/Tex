"""Tool registry — the single whitelist of allowed tools.

The LLM can ONLY call tools listed here. Any tool name not in this
registry will be rejected by the validator before execution.
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


# ── Tool Call Schema ──────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    """Schema every LLM response must conform to."""
    tool: str = Field(..., description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(default_factory=dict)
    explanation: str = Field(..., description="Plain-English explanation shown to user")
    requires_sudo: bool = Field(False, description="Whether this tool needs sudo")


# ── Tool Definitions ──────────────────────────────────────────────────────────

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: list[str]          # required arg names
    optional: list[str] = []       # optional arg names
    destructive: bool = False      # extra confirmation prompt
    needs_sudo: bool = False
    is_conversational: bool = False  # no plan panel, no confirmation
    is_interpretable: bool = False   # pass output back to LLM for analysis


TOOL_REGISTRY: dict[str, ToolDefinition] = {
    # Package management
    "install_package": ToolDefinition(
        name="install_package",
        description="Install a package using dnf",
        parameters=["name"],
        needs_sudo=True,
    ),
    "remove_package": ToolDefinition(
        name="remove_package",
        description="Remove an installed package using dnf",
        parameters=["name"],
        destructive=True,
        needs_sudo=True,
    ),
    "search_package": ToolDefinition(
        name="search_package",
        description="Search for packages matching a keyword",
        parameters=["query"],
    ),

    # File operations
    "list_files": ToolDefinition(
        name="list_files",
        description="List files in a directory",
        parameters=["path"],
        optional=["show_hidden"],
    ),
    "read_file": ToolDefinition(
        name="read_file",
        description="Read and display a file's contents",
        parameters=["path"],
        optional=["lines"],
    ),
    "copy_file": ToolDefinition(
        name="copy_file",
        description="Copy a file from source to destination",
        parameters=["source", "destination"],
    ),
    "move_file": ToolDefinition(
        name="move_file",
        description="Move or rename a file",
        parameters=["source", "destination"],
        destructive=True,
    ),
    "delete_file": ToolDefinition(
        name="delete_file",
        description="Delete a file permanently",
        parameters=["path"],
        destructive=True,
    ),

    # Process inspection
    "list_processes": ToolDefinition(
        name="list_processes",
        description="Show running processes, optionally filtered by name",
        parameters=[],
        optional=["filter"],
        is_interpretable=True,
    ),
    "kill_process": ToolDefinition(
        name="kill_process",
        description="Kill a process by its PID",
        parameters=["pid"],
        destructive=True,
        needs_sudo=False,
    ),

    # System logs
    "read_journal": ToolDefinition(
        name="read_journal",
        description="Read systemd journal logs",
        parameters=[],
        optional=["unit", "lines", "since"],
        is_interpretable=True,
    ),

    # Education
    "explain_command": ToolDefinition(
        name="explain_command",
        description="Explain what a shell command does without executing it",
        parameters=["command"],
    ),

    # Conversation — used when the user's intent is general chat, not a task
    "chat_response": ToolDefinition(
        name="chat_response",
        description="Respond conversationally when the user is not requesting a system action",
        parameters=["message"],
        is_conversational=True,
    ),

    #System info
    "get_system_info": ToolDefinition(
        name="get_system_info",
        description="Get a snapshot of the system CPU, GPU, RAM, Disk, OS",
        parameters=[],
        is_interpretable=True,
    ),
    "list_installed_packages": ToolDefinition(
        name="list_installed_packages",
        description="List installed packages via dnf, optionally filtered by name",
        parameters=[],
        optional=["filter"],
        is_interpretable=True,
    ),

    # Service management
    "service_status": ToolDefinition(
        name="service_status",
        description="Show the status of a systemd service (active, inactive, failed, logs)",
        parameters=["name"],
        is_interpretable=True,
    ),
    "start_service": ToolDefinition(
        name="start_service",
        description="Start a systemd service",
        parameters=["name"],
        needs_sudo=True,
    ),
    "stop_service": ToolDefinition(
        name="stop_service",
        description="Stop a running systemd service",
        parameters=["name"],
        destructive=True,
        needs_sudo=True,
    ),
    "restart_service": ToolDefinition(
        name="restart_service",
        description="Restart a systemd service (stop then start)",
        parameters=["name"],
        destructive=True,
        needs_sudo=True,
    ),
    "enable_service": ToolDefinition(
        name="enable_service",
        description="Enable a service to start automatically on boot",
        parameters=["name"],
        needs_sudo=True,
    ),
    "disable_service": ToolDefinition(
        name="disable_service",
        description="Disable a service so it does not start on boot",
        parameters=["name"],
        destructive=True,
        needs_sudo=True,
    ),
    "list_services": ToolDefinition(
        name="list_services",
        description="List systemd services, optionally filtered by name or state (running/stopped/enabled/failed)",
        parameters=[],
        optional=["filter", "state"],
        is_interpretable=True,
    ),
    "analyze_boot": ToolDefinition(
        name="analyze_boot",
        description="Show system boot time breakdown and per-service startup times using systemd-analyze",
        parameters=[],
        is_interpretable=True,
    ),

    # Network tools
    "show_network_info": ToolDefinition(
        name="show_network_info",
        description="Show network interfaces, IP addresses, default route, DNS nameservers, and listening TCP services",
        parameters=[],
        is_interpretable=True,
    ),
    "ping_host": ToolDefinition(
        name="ping_host",
        description="Ping a hostname or IP and return latency statistics",
        parameters=["host"],
        optional=["count"],
    ),
    "check_port": ToolDefinition(
        name="check_port",
        description="Check whether a TCP port is open on a host",
        parameters=["host", "port"],
    ),
}
    

def get_tool(name: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(name)


def all_tool_names() -> list[str]:
    return list(TOOL_REGISTRY.keys())


def tools_as_json_schema() -> str:
    """Serialize all tools for injection into the LLM system prompt.

    Uses a compact one-liner format instead of full JSON to minimise prompt
    token count. Fewer tokens in the system prompt = faster model prefill =
    shorter 'Thinking...' wait time.

    Format per tool:
      tool_name(req_arg*, opt_arg) — description [flags]
    Flags: sudo | destructive | no-confirm
    * = required argument
    """
    lines = []
    for t in TOOL_REGISTRY.values():
        # Build argument list: required args marked with *, optional unmarked
        args = [f"{a}*" for a in t.parameters] + list(t.optional)
        arg_str = ", ".join(args) if args else ""

        # Build flag list
        flags = []
        if t.needs_sudo:
            flags.append("sudo")
        if t.destructive:
            flags.append("destructive")
        if t.is_conversational:
            flags.append("no-confirm")
        flag_str = f" [{', '.join(flags)}]" if flags else ""

        lines.append(f"  {t.name}({arg_str}) — {t.description}{flag_str}")

    return "\n".join(lines)
