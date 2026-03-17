"""Systemd service management tools.

SECURITY MODEL
--------------
All service names are validated before being passed to systemctl:

  1. Only alphanumeric characters, hyphens, underscores, dots, and the @
     suffix separator are allowed. This blocks shell injection via malformed
     service names (e.g. "nginx; rm -rf ~").
  2. Service names are capped at 128 characters.
  3. Destructive operations (stop, restart, disable) are marked as such in
     the registry so the executor always prompts for confirmation.
  4. All commands run without sudo by default. systemctl operations on
     user-owned services work without sudo; system services will fail with
     a PermissionError that is surfaced cleanly to the user.
"""

from __future__ import annotations
import re
import subprocess

# Allowlist pattern for safe service names.
# Covers: nginx, sshd, postgresql-14, user@1000, bluetooth.target, etc.
_SAFE_SERVICE_NAME = re.compile(r'^[\w\-\.@]+$')
_MAX_SERVICE_NAME_LEN = 128


def _validate_service_name(name: str) -> tuple[bool, str] | None:
    """
    Return (False, error_msg) if the name is unsafe, None if it's valid.
    Callers should check: err = _validate_service_name(name); if err: return err
    """
    name = name.strip()
    if not name:
        return False, "Service name cannot be empty."
    if len(name) > _MAX_SERVICE_NAME_LEN:
        return False, f"Service name is too long ({len(name)} chars, max {_MAX_SERVICE_NAME_LEN})."
    if not _SAFE_SERVICE_NAME.match(name):
        return False, (
            f"Service name '{name}' contains invalid characters. "
            f"Only letters, numbers, hyphens, underscores, dots, and @ are allowed."
        )
    return None


def _run_systemctl(*args: str) -> tuple[bool, str]:
    """Run a systemctl command and return (success, output)."""
    result = subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


# ── Public tool functions ─────────────────────────────────────────────────────

def service_status(name: str) -> tuple[bool, str]:
    """Show the status of a systemd service."""
    if err := _validate_service_name(name):
        return err
    ok, output = _run_systemctl("status", name, "--no-pager", "-l")
    # systemctl status returns exit code 3 for inactive (not an error for us)
    return True, output if output else f"No status information for '{name}'."


def start_service(name: str) -> tuple[bool, str]:
    """Start a systemd service."""
    if err := _validate_service_name(name):
        return err
    ok, output = _run_systemctl("start", name)
    if ok:
        return True, f"Service '{name}' started successfully."
    return False, output or f"Failed to start '{name}'. Try: systemctl status {name}"


def stop_service(name: str) -> tuple[bool, str]:
    """Stop a running systemd service."""
    if err := _validate_service_name(name):
        return err
    ok, output = _run_systemctl("stop", name)
    if ok:
        return True, f"Service '{name}' stopped."
    return False, output or f"Failed to stop '{name}'."


def restart_service(name: str) -> tuple[bool, str]:
    """Restart a systemd service (stop then start)."""
    if err := _validate_service_name(name):
        return err
    ok, output = _run_systemctl("restart", name)
    if ok:
        return True, f"Service '{name}' restarted successfully."
    return False, output or f"Failed to restart '{name}'."


def enable_service(name: str) -> tuple[bool, str]:
    """Enable a service to start automatically on boot."""
    if err := _validate_service_name(name):
        return err
    ok, output = _run_systemctl("enable", name)
    if ok:
        return True, f"Service '{name}' will now start on boot."
    return False, output or f"Failed to enable '{name}'."


def disable_service(name: str) -> tuple[bool, str]:
    """Disable a service so it does not start on boot."""
    if err := _validate_service_name(name):
        return err
    ok, output = _run_systemctl("disable", name)
    if ok:
        return True, f"Service '{name}' will no longer start on boot."
    return False, output or f"Failed to disable '{name}'."


def list_services(filter: str = "", state: str = "") -> tuple[bool, str]:
    """
    List systemd services, optionally filtered by name or state.

    state: "running", "stopped", "enabled", "failed", or "" for all.
    """
    cmd = ["list-units", "--type=service", "--no-pager", "--no-legend"]

    if state == "running":
        cmd += ["--state=running"]
    elif state == "stopped":
        cmd += ["--state=inactive,dead"]
    elif state == "failed":
        cmd += ["--state=failed"]
    elif state == "enabled":
        # list-unit-files is better for enabled state
        ok, output = _run_systemctl(
            "list-unit-files", "--type=service", "--state=enabled", "--no-pager", "--no-legend"
        )
        lines = [l for l in output.splitlines() if filter.lower() in l.lower()] if filter else output.splitlines()
        if not lines:
            msg = f"No enabled services found matching '{filter}'." if filter else "No enabled services found."
            return True, msg
        return True, "\n".join(lines[:40])

    ok, output = _run_systemctl(*cmd)
    if not ok:
        return False, output or "Failed to list services."

    lines = output.splitlines()
    if filter:
        lines = [l for l in lines if filter.lower() in l.lower()]

    if not lines:
        msg = f"No services found matching '{filter}'." if filter else "No services found."
        return True, msg

    return True, "\n".join(lines[:40])  # cap at 40 rows
