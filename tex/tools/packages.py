"""Package management tools — wraps dnf for Fedora."""

from __future__ import annotations
import subprocess


def install_package(name: str) -> tuple[bool, str]:
    """Run: sudo dnf install -y <name>"""
    result = subprocess.run(
        ["sudo", "dnf", "install", "-y", name],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output.strip()


def remove_package(name: str) -> tuple[bool, str]:
    """Run: sudo dnf remove -y <name>"""
    result = subprocess.run(
        ["sudo", "dnf", "remove", "-y", name],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output.strip()


def search_package(query: str) -> tuple[bool, str]:
    """Run: dnf search <query>"""
    result = subprocess.run(
        ["dnf", "search", query],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output.strip()
