"""Tool dispatcher — maps a validated ToolCall to its implementation."""

from __future__ import annotations
from tex.tools.registry import ToolCall
from tex.tools import packages, file_ops, processes, sysinfo


def dispatch(tool_call: ToolCall) -> tuple[bool, str]:
    """
    Route a validated ToolCall to its implementation.
    Returns (success, output).
    All tools return (bool, str) — never raise.
    """
    name = tool_call.tool
    args = tool_call.arguments

    match name:
        # ── Package management ────────────────────────────────────────
        case "install_package":
            return packages.install_package(args["name"])

        case "remove_package":
            return packages.remove_package(args["name"])

        case "search_package":
            return packages.search_package(args["query"])

        # ── File operations ───────────────────────────────────────────
        case "list_files":
            return file_ops.list_files(
                args["path"],
                show_hidden=args.get("show_hidden", False),
            )

        case "read_file":
            return file_ops.read_file(
                args["path"],
                lines=int(args.get("lines", 0)),
            )

        case "copy_file":
            return file_ops.copy_file(args["source"], args["destination"])

        case "move_file":
            return file_ops.move_file(args["source"], args["destination"])

        case "delete_file":
            return file_ops.delete_file(args["path"])

        # ── Process inspection ────────────────────────────────────────
        case "list_processes":
            return processes.list_processes(filter=args.get("filter", ""))

        case "kill_process":
            return processes.kill_process(args["pid"])

        case "read_journal":
            return processes.read_journal(
                unit=args.get("unit", ""),
                lines=int(args.get("lines", 50)),
                since=args.get("since", ""),
            )

        # ── Education ─────────────────────────────────────────────────
        case "explain_command":
            # explain_command doesn't execute anything —
            # the explanation is shown directly from the tool_call itself
            return True, (
                f"Command: [bold]{args.get('command', '')}[/bold]\n\n"
                "This command was not executed. Use [cyan]tex ask[/cyan] to run it."
            )

        # ── System information ────────────────────────────────────────
        case "get_system_info":
            return sysinfo.get_system_info()

        case "list_installed_packages":
            return sysinfo.list_installed_packages(
                filter=args.get("filter", "")
            )

        # ── Conversation ───────────────────────────────────────────────
        case "chat_response":
            # Pass the message through — executor renders it as a chat bubble
            return True, args.get("message", "")