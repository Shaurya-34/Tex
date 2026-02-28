"""Process inspection tools."""

from __future__ import annotations
import subprocess
import signal


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
    """Send SIGTERM to a process by PID."""
    try:
        pid = int(pid)
    except ValueError:
        return False, f"Invalid PID: {pid}"

    try:
        import os
        os.kill(pid, signal.SIGTERM)
        return True, f"Sent SIGTERM to PID {pid}"
    except ProcessLookupError:
        return False, f"No process with PID {pid}"
    except PermissionError:
        return False, f"Permission denied — try with sudo or check ownership of PID {pid}"


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
