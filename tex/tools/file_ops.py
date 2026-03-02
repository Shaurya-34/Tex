"""File operation tools.

SECURITY MODEL
--------------
All path arguments supplied by the LLM are passed through _safe_path() before
any filesystem operation. _safe_path() enforces the following rules:

  1. The resolved (absolute, symlink-expanded) path must be inside the user's
     home directory.  Paths to /etc, /usr, /root, /proc, /sys, /dev, /boot,
     and similar system trees are rejected outright.
  2. Paths that resolve to the home directory root itself are rejected — a user
     should not be able to delete or overwrite their entire home.
  3. Path traversal attempts (e.g. ../../etc/passwd) are blocked by resolving
     the path first and then checking containment.

If _safe_path() rejects a path it raises ValueError with an explanation.
All public functions catch ValueError and return (False, <message>) so the
executor always receives a safe (bool, str) pair.
"""

from __future__ import annotations
import shutil
from pathlib import Path

# The one root all file operations are allowed to operate within.
_HOME = Path.home().resolve()

# Absolute paths that are always blocked regardless of user home location.
_BLOCKED_PREFIXES: tuple[Path, ...] = tuple(
    Path(p) for p in (
        "/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64",
        "/sys", "/proc", "/dev", "/boot", "/root", "/var",
        "/run", "/snap", "/opt",
    )
)


def _safe_path(raw: str) -> Path:
    """
    Resolve and validate a path supplied by the LLM.

    Returns a resolved Path that is guaranteed to live inside the user's home
    directory, or raises ValueError with a human-readable rejection reason.
    """
    p = Path(raw).expanduser().resolve()

    # Rule 1: Must be inside home directory
    try:
        p.relative_to(_HOME)
    except ValueError:
        raise ValueError(
            f"Path '{raw}' is outside your home directory and cannot be "
            f"accessed by Tex for safety reasons."
        )

    # Rule 2: Must not be the home directory itself
    if p == _HOME:
        raise ValueError(
            f"Path '{raw}' resolves to your home directory root. "
            f"Tex will not operate on the home directory itself."
        )

    # Rule 3: Blocked system prefixes (belt-and-suspenders; Rule 1 covers most).
    #
    # Two correctness fixes vs. a naive startswith() approach:
    #   a) Use Path.is_relative_to() instead of string prefix matching so that
    #      /etcetera does NOT match /etc, /opt-user does NOT match /opt, etc.
    #   b) Skip the check when _HOME itself lives inside a blocked prefix.
    #      Users on Fedora Silverblue/Kinoite have homes under /var/home/<user>,
    #      containerised environments may use /opt/<user>, etc.  In those cases
    #      Rule 1 already constrains all operations to within home — applying
    #      Rule 3 on top would only produce false positives.
    for blocked in _BLOCKED_PREFIXES:
        blocked_resolved = blocked.resolve()
        # Skip: user's home is inside this blocked tree — Rule 1 is sufficient
        if _HOME.is_relative_to(blocked_resolved):
            continue
        # Reject: the resolved target path is inside this blocked tree
        if p.is_relative_to(blocked_resolved):
            raise ValueError(
                f"Path '{raw}' is inside a protected system directory "
                f"({blocked}) and cannot be accessed by Tex."
            )


    return p


# ── Public tool functions ─────────────────────────────────────────────────────

def list_files(path: str, show_hidden: bool = False) -> tuple[bool, str]:
    """List files in a directory."""
    try:
        p = _safe_path(path)
    except ValueError as e:
        return False, str(e)

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
    """Read a file's contents. If lines > 0, return first N lines (max 500)."""
    try:
        p = _safe_path(path)
    except ValueError as e:
        return False, str(e)

    if not p.exists():
        return False, f"File does not exist: {path}"
    if not p.is_file():
        return False, f"Not a file: {path}"

    # Cap line count to prevent memory abuse
    lines = min(int(lines), 500) if lines else 0

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        if lines > 0:
            text = "\n".join(text.splitlines()[:lines])
        return True, text
    except PermissionError:
        return False, f"Permission denied reading: {path}"


def copy_file(source: str, destination: str) -> tuple[bool, str]:
    try:
        src = _safe_path(source)
        dst = _safe_path(destination)
    except ValueError as e:
        return False, str(e)

    if not src.exists():
        return False, f"Source does not exist: {source}"
    try:
        shutil.copy2(src, dst)
        return True, f"Copied {source} -> {destination}"
    except Exception as e:
        return False, str(e)


def move_file(source: str, destination: str) -> tuple[bool, str]:
    try:
        src = _safe_path(source)
        dst = _safe_path(destination)
    except ValueError as e:
        return False, str(e)

    if not src.exists():
        return False, f"Source does not exist: {source}"
    try:
        shutil.move(str(src), str(dst))
        return True, f"Moved {source} -> {destination}"
    except Exception as e:
        return False, str(e)


def delete_file(path: str) -> tuple[bool, str]:
    try:
        p = _safe_path(path)
    except ValueError as e:
        return False, str(e)

    if not p.exists():
        return False, f"Path does not exist: {path}"

    # Extra guard: never rmtree a top-level home subdirectory
    # (e.g. ~/Documents, ~/Downloads).  Require at least depth 2 from home
    # so the user must be specific (e.g. ~/Documents/old_project/).
    if p.is_dir():
        depth = len(p.relative_to(_HOME).parts)
        if depth < 2:
            return False, (
                f"'{path}' is a top-level directory in your home folder. "
                f"Tex will not delete it automatically — do this manually if intended."
            )
        try:
            shutil.rmtree(p)
            return True, f"Deleted directory: {path}"
        except Exception as e:
            return False, str(e)
    else:
        try:
            p.unlink()
            return True, f"Deleted: {path}"
        except Exception as e:
            return False, str(e)
