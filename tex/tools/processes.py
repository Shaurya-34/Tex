"""Process inspection tools."""

from __future__ import annotations
import os
import signal
import subprocess


def list_processes(filter: str = "") -> tuple[bool, str]:
    """List running processes, optionally filtered by name."""
    result = subprocess.run(
        ["ps", "aux", "--sort=-%mem"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()

    lines = result.stdout.splitlines()
    if len(lines) < 2:
        return True, "(no processes found)"

    body = lines[1:]  # skip header

    if filter:
        body = [l for l in body if filter.lower() in l.lower()]

    if not body:
        return True, f"No processes found matching '{filter}'"

    # Parse and format as a clean table
    rows = []
    for line in body[:25]:  # cap at 25 rows
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        user, pid, cpu, mem = parts[0], parts[1], parts[2], parts[3]
        cmd = parts[10].split("/")[-1]  # basename of command
        cmd = cmd[:55] + "…" if len(cmd) > 55 else cmd  # truncate long names
        rows.append((user, pid, cpu + "%", mem + "%", cmd))

    # Build a plain-text table with fixed-width columns
    header = f"{'USER':<12} {'PID':>7}  {'CPU':>5}  {'MEM':>5}  COMMAND"
    sep = "─" * 75
    table_lines = [header, sep]
    for user, pid, cpu, mem, cmd in rows:
        table_lines.append(f"{user:<12} {pid:>7}  {cpu:>5}  {mem:>5}  {cmd}")

    return True, "\n".join(table_lines)



def kill_process(pid: int | str) -> tuple[bool, str]:
    """Send SIGTERM to a process by PID.

    SECURITY: PIDs 1–99 are reserved for the kernel and core system daemons
    (systemd is PID 1, kernel threads occupy low PIDs).  Tex will never send
    a signal to these processes regardless of what the LLM outputs.
    """
    try:
        pid = int(pid)
    except ValueError:
        return False, f"Invalid PID: {pid} — must be an integer."

    # Block negative PIDs and PID 0 — these have special OS semantics:
    # negative PID → signal sent to the entire process group (dangerous)
    # PID 0        → signal sent to all processes in the calling process group
    if pid <= 0:
        return False, (
            f"PID {pid} is not a valid target. Negative PIDs and PID 0 have "
            f"special OS semantics (process group signals) and are blocked by Tex."
        )

    # Block signals to privileged system PIDs (systemd is 1, kernel threads
    # occupy the low range — nothing below 100 is a safe user target)
    _MIN_SAFE_PID = 100
    if pid < _MIN_SAFE_PID:
        return False, (
            f"PID {pid} is in the reserved system range (1–99). "
            f"Tex will not send signals to system or kernel processes."
        )

    try:
        os.kill(pid, signal.SIGTERM)
        return True, f"Sent SIGTERM to PID {pid}"
    except ProcessLookupError:
        return False, f"No process with PID {pid}"
    except PermissionError:
        return False, f"Permission denied — cannot send signal to PID {pid} (process is owned by another user or requires elevated privileges)."



def read_journal(
    unit: str = "",
    lines: int = 50,
    since: str = "",
) -> tuple[bool, str]:
    """Read systemd journal logs."""
    cmd = ["journalctl", "-n", str(lines), "--no-pager"]
    if unit:
        cmd += ["-u", unit]
    if since:
        cmd += ["--since", since]

    result = subprocess.run(cmd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    return result.returncode == 0, output.strip()
