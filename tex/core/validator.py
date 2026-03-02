"""Schema validation layer — rejects any LLM output that doesn't
match the ToolCall schema or references an unknown tool."""

from __future__ import annotations
from pydantic import ValidationError
from tex.tools.registry import ToolCall, get_tool, ToolDefinition
from tex.config import config

# Argument keys that carry free-form natural language content.
# These legitimately produce long values (full chat responses, detailed
# explanations) so they get a much higher cap than structural args like
# paths, package names, or PIDs.
#
# The multiplier is intentionally generous — the goal is to block
# runaway/adversarial output, not to constrain normal LLM responses.
_LONG_CONTENT_ARGS: frozenset[str] = frozenset({"message", "explanation"})
_LONG_CONTENT_MULTIPLIER = 16   # 1024 * 16 = 16 384 chars by default


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
      4. Check no argument value exceeds safe length limits
         - Structural args (paths, names, PIDs): config.max_arg_value_len
           (default 1024, overridable via TEX_MAX_ARG_LEN in .env)
         - Free-text content args (message, explanation): 16x that limit
           since these hold full LLM responses and can legitimately be long
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

    # Step 4: Argument value length guard
    #
    # Explicit str() conversion happens here so that non-string types (int,
    # bool, list) are consistently measured.  The limit applied depends on
    # whether the key is a known long-content field or a structural argument.
    base_limit = config.max_arg_value_len
    for key, value in tool_call.arguments.items():
        str_value = str(value)
        limit = (
            base_limit * _LONG_CONTENT_MULTIPLIER
            if key in _LONG_CONTENT_ARGS
            else base_limit
        )
        if len(str_value) > limit:
            return ValidationResult(
                valid=False,
                error=(
                    f"Argument '{key}' value exceeds the maximum allowed length "
                    f"({len(str_value)} > {limit} characters). "
                    f"This request has been aborted. "
                    f"If this is a legitimate use case, raise TEX_MAX_ARG_LEN in .env."
                ),
            )

    return ValidationResult(valid=True, tool_call=tool_call, tool_def=tool_def)
