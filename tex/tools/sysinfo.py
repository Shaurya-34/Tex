"""System information tools — read-only hardware and OS inspection."""

from __future__ import annotations
import subprocess
import shutil
from pathlib import Path


def get_system_info() -> tuple[bool, str]:
    """Gather a full system snapshot: CPU, RAM, GPU, disk, OS."""
    lines = []

    # ── OS info ──────────────────────────────────────────────────────────
    os_release = Path("/etc/os-release")
    if os_release.exists():
        info = {}
        for line in os_release.read_text().splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                info[k] = v.strip('"')
        distro = info.get("PRETTY_NAME", "Unknown distro")
    else:
        distro = "Unknown distro"

    kernel = subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip()
    arch   = subprocess.run(["uname", "-m"], capture_output=True, text=True).stdout.strip()

    lines.append(f"OS:           {distro}")
    lines.append(f"Kernel:       {kernel}")
    lines.append(f"Architecture: {arch}")
    lines.append("")

    # ── CPU ──────────────────────────────────────────────────────────────
    cpu_name = "Unknown"
    cpu_cores = "?"
    result = subprocess.run(["lscpu"], capture_output=True, text=True)
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            if line.startswith("Model name"):
                cpu_name = line.split(":", 1)[1].strip()
            if line.startswith("CPU(s):"):
                cpu_cores = line.split(":", 1)[1].strip()

    lines.append(f"CPU:          {cpu_name}")
    lines.append(f"CPU cores:    {cpu_cores}")
    lines.append("")

    # ── RAM ──────────────────────────────────────────────────────────────
    mem_total = mem_avail = "?"
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text().splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                mem_total = f"{kb // 1024} MB  ({kb // (1024 * 1024)} GB)"
            if line.startswith("MemAvailable:"):
                kb = int(line.split()[1])
                mem_avail = f"{kb // 1024} MB  ({kb // (1024 * 1024)} GB)"

    lines.append(f"RAM total:    {mem_total}")
    lines.append(f"RAM free:     {mem_avail}")
    lines.append("")

    # ── GPU ──────────────────────────────────────────────────────────────
    gpu_lines = []
    lspci = subprocess.run(["lspci"], capture_output=True, text=True)
    if lspci.returncode == 0:
        for line in lspci.stdout.splitlines():
            low = line.lower()
            if "vga" in low or "3d" in low or "display" in low:
                gpu_lines.append(line.split(":", 2)[-1].strip())

    if gpu_lines:
        for g in gpu_lines:
            lines.append(f"GPU:          {g}")
    else:
        lines.append("GPU:          Not detected (lspci found nothing)")

    # Bonus: nvidia-smi if available
    if shutil.which("nvidia-smi"):
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
             "--format=csv,noheader"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            lines.append(f"NVIDIA detail: {result.stdout.strip()}")
    lines.append("")

    # ── Disk ─────────────────────────────────────────────────────────────
    df = subprocess.run(
        ["df", "-h", "--output=target,size,used,avail,pcent"],
        capture_output=True, text=True,
    )
    if df.returncode == 0:
        relevant = [
            l for l in df.stdout.splitlines()
            if l.startswith(("Mount", "/", "/home", "/boot"))
        ]
        lines.append("Disk:")
        lines.extend(f"  {l}" for l in relevant[:6])

    return True, "\n".join(lines)


def list_installed_packages(filter: str = "") -> tuple[bool, str]:
    """List installed packages via dnf, optionally filtered by name."""
    result = subprocess.run(
        ["dnf", "list", "installed"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()

    lines = result.stdout.splitlines()
    if filter:
        lines = [l for l in lines if filter.lower() in l.lower()]

    if not lines:
        return True, f"No installed packages matching '{filter}'"

    return True, "\n".join(lines[:80])  # cap output to avoid flooding terminal