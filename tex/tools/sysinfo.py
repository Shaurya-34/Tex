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
    """
    Search for installed software across ALL package sources:
      - dnf / RPM  (system packages)
      - Flatpak    (GNOME Software, Flathub apps like Blender, Steam)
      - Snap       (snapd packages)
      - AppImage   (portable apps in ~/Applications or home dir)
      - Manual     (binaries in /opt, /usr/local/bin)
    """
    sections: list[str] = []
    found_anything = False

    # ── 1. dnf / RPM ─────────────────────────────────────────────────────
    if shutil.which("dnf"):
        result = subprocess.run(
            ["dnf", "list", "installed"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            if filter:
                lines = [l for l in lines if filter.lower() in l.lower()]
            # Skip the header line ("Installed Packages") — exact match to avoid
            # dropping RPM package names that happen to start with "Installed"
            lines = [l for l in lines if l.strip() != "Installed Packages"]
            if lines:
                found_anything = True
                sections.append(f"[dnf/RPM] ({len(lines)} match(es))")
                sections.extend(f"  {l}" for l in lines[:40])

    # ── 2. Flatpak ───────────────────────────────────────────────────────
    if shutil.which("flatpak"):
        result = subprocess.run(
            ["flatpak", "list", "--columns=application,name,version"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            if filter:
                lines = [l for l in lines if filter.lower() in l.lower()]
            if lines:
                found_anything = True
                sections.append(f"\n[Flatpak] ({len(lines)} match(es))")
                sections.extend(f"  {l}" for l in lines[:40])

    # ── 3. Snap ──────────────────────────────────────────────────────────
    if shutil.which("snap"):
        result = subprocess.run(
            ["snap", "list"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            if filter:
                lines = [l for l in lines if filter.lower() in l.lower()]
            # Skip header
            lines = [l for l in lines if not (l.strip().split(None, 1)[0:1] == ["Name"])]
            if lines:
                found_anything = True
                sections.append(f"\n[Snap] ({len(lines)} match(es))")
                sections.extend(f"  {l}" for l in lines[:40])

    # AppImage scanner covers common locations including /opt.
    # /opt is also scanned separately in section 5 for non-AppImage manual installs.
    appimage_dirs = [
        Path.home() / "Applications",
        Path.home(),
        Path("/opt"),
    ]
    appimages: list[str] = []
    for d in appimage_dirs:
        if d.exists():
            try:
                for f in d.iterdir():
                    if f.suffix.lower() == ".appimage":
                        if not filter or filter.lower() in f.name.lower():
                            appimages.append(str(f))
            except PermissionError:
                pass  # Skip directories we cannot read

    if appimages:
        found_anything = True
        sections.append(f"\n[AppImage] ({len(appimages)} found)")
        sections.extend(f"  {a}" for a in appimages[:20])

    # ── 5. Manual installs in /opt ────────────────────────────────────────
    opt = Path("/opt")
    if opt.exists():
        try:
            opt_entries = [
                e.name for e in opt.iterdir()
                if (not filter or filter.lower() in e.name.lower())
                and e.suffix.lower() != ".appimage"  # shown in AppImage section above
            ]
        except PermissionError:
            opt_entries = []
        if opt_entries:
            found_anything = True
            sections.append(f"\n[/opt — manual installs] ({len(opt_entries)} found)")
            sections.extend(f"  {e}" for e in sorted(opt_entries)[:20])

    # ── Summary ───────────────────────────────────────────────────────────
    if not found_anything:
        msg = f"No installed software found matching '{filter}'" if filter else "No installed software found."
        return True, msg

    suffix = f" for '{filter}'" if filter else ""
    header = f"Installed software search{suffix}:\n"
    return True, header + "\n".join(sections)