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
    ),
    "list_installed_packages": ToolDefinition(
        name="list_installed_packages",
        description="List installed packages via dnf, optionally filtered by name",
        parameters=[],
        optional=["filter"],
    ),
}
    

def get_tool(name: str) -> ToolDefinition | None:
    return TOOL_REGISTRY.get(name)


def all_tool_names() -> list[str]:
    return list(TOOL_REGISTRY.keys())


def tools_as_json_schema() -> str:
    """Serialize all tools for injection into the LLM system prompt."""
    import json
    schema = []
    for t in TOOL_REGISTRY.values():
        schema.append({
            "name": t.name,
            "description": t.description,
            "required_args": t.parameters,
            "optional_args": t.optional,
            "destructive": t.destructive,
            "needs_sudo": t.needs_sudo,
        })
    return json.dumps(schema, indent=2)
