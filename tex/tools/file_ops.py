"""File operation tools."""

from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


def list_files(path: str, show_hidden: bool = False) -> tuple[bool, str]:
    """List files in a directory."""
    p = Path(path).expanduser()
    if not p.exists():
        return False, f"Path does not exist: {path}"
    if not p.is_dir():
        return False, f"Not a directory: {path}"

    entries = sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name))
    lines = []
    for entry in entries:
        if not show_hidden and entry.name.startswith("."):
            continue
        kind = "[dir]" if entry.is_dir() else "[file]"
        lines.append(f"{kind}  {entry.name}")
    return True, "\n".join(lines) if lines else "(empty directory)"


def read_file(path: str, lines: int = 0) -> tuple[bool, str]:
    """Read a file's contents. If lines > 0, return first N lines."""
    p = Path(path).expanduser()
    if not p.exists():
        return False, f"File does not exist: {path}"
    if not p.is_file():
        return False, f"Not a file: {path}"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if lines > 0:
            text = "\n".join(text.splitlines()[:lines])
        return True, text
    except PermissionError:
        return False, f"Permission denied reading: {path}"


def copy_file(source: str, destination: str) -> tuple[bool, str]:
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()
    if not src.exists():
        return False, f"Source does not exist: {source}"
    try:
        shutil.copy2(src, dst)
        return True, f"Copied {source} → {destination}"
    except Exception as e:
        return False, str(e)


def move_file(source: str, destination: str) -> tuple[bool, str]:
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()
    if not src.exists():
        return False, f"Source does not exist: {source}"
    try:
        shutil.move(str(src), str(dst))
        return True, f"Moved {source} → {destination}"
    except Exception as e:
        return False, str(e)


def delete_file(path: str) -> tuple[bool, str]:
    p = Path(path).expanduser()
    if not p.exists():
        return False, f"File does not exist: {path}"
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return True, f"Deleted: {path}"
    except Exception as e:
        return False, str(e)
