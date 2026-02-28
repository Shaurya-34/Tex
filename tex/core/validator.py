"""Schema validation layer — rejects any LLM output that doesn't
match the ToolCall schema or references an unknown tool."""

from __future__ import annotations
from pydantic import ValidationError
from tex.tools.registry import ToolCall, get_tool, ToolDefinition


class ValidationResult:
    def __init__(
        self,
        valid: bool,
        tool_call: ToolCall | None = None,
        tool_def: ToolDefinition | None = None,
        error: str = "",
    ):
        self.valid = valid
        self.tool_call = tool_call
        self.tool_def = tool_def
        self.error = error


def validate(raw: dict) -> ValidationResult:
    """
    Validate raw LLM JSON output against our ToolCall schema and registry.

    Steps:
      1. Parse against Pydantic ToolCall model
      2. Check tool name exists in registry
      3. Check required arguments are present
    """
    # Step 1: Schema shape
    try:
        tool_call = ToolCall(**raw)
    except ValidationError as e:
        return ValidationResult(
            valid=False,
            error=f"Response did not match expected schema: {e}",
        )

    # Step 2: Whitelist check
    tool_def = get_tool(tool_call.tool)
    if tool_def is None:
        return ValidationResult(
            valid=False,
            error=(
                f"Tool '{tool_call.tool}' is not in the allowed tool registry.\n"
                f"This is a safety violation — the request has been aborted."
            ),
        )

    # Step 3: Required args present
    missing = [
        arg for arg in tool_def.parameters
        if arg not in tool_call.arguments
    ]
    if missing:
        return ValidationResult(
            valid=False,
            error=f"Tool '{tool_call.tool}' is missing required arguments: {missing}",
        )

    return ValidationResult(valid=True, tool_call=tool_call, tool_def=tool_def)
