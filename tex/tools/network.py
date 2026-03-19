"""Network diagnostic tools — show_network_info, ping_host, check_port."""

from __future__ import annotations
import re
import socket
import subprocess

# Hostname/IP allowlist — covers FQDNs, IPv4, IPv6, localhost
_SAFE_HOST = re.compile(r'^[\w.\-:]+$')
_MAX_HOST_LEN = 253  # RFC 1035


def _validate_host(host: str) -> tuple[bool, str] | None:
    """Return an error tuple if host is invalid, else None."""
    host = host.strip()
    if not host:
        return False, "Host cannot be empty."
    if len(host) > _MAX_HOST_LEN:
        return False, f"Host too long ({len(host)} chars, max {_MAX_HOST_LEN})."
    if not _SAFE_HOST.match(host):
        return False, (
            f"Host '{host}' contains invalid characters. "
            f"Only letters, digits, dots, hyphens, and colons are allowed."
        )
    return None


def show_network_info() -> tuple[bool, str]:
    """Show network interfaces, routing, DNS, and listening TCP services."""
    sections: list[str] = []

    # Interfaces and IPs (brief format is cleaner than full `ip addr show`)
    r = subprocess.run(["ip", "-brief", "addr"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        sections.append("Network interfaces:\n" + r.stdout.strip())

    # Default gateway
    r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        sections.append("Default route:\n" + r.stdout.strip())

    # DNS resolvers (nameserver lines from resolv.conf)
    try:
        resolv = open("/etc/resolv.conf").read()
        ns_lines = [l for l in resolv.splitlines() if l.startswith("nameserver")]
        if ns_lines:
            sections.append("DNS nameservers:\n" + "\n".join(ns_lines))
    except OSError:
        pass

    # Listening TCP ports
    r = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        sections.append("Listening TCP services:\n" + r.stdout.strip())

    if not sections:
        return False, "Could not retrieve network information."

    return True, "\n\n".join(sections)


def ping_host(host: str, count: int | str = 4) -> tuple[bool, str]:
    """
    Ping a host and return latency statistics.

    Args:
        host:  Hostname or IP address to ping.
        count: Number of ICMP packets to send (1–10, default 4).
    """
    err = _validate_host(host)
    if err is not None:
        return err

    try:
        count = max(1, min(int(count), 10))  # clamp to a safe range
    except (ValueError, TypeError):
        count = 4

    try:
        r = subprocess.run(
            ["ping", "-c", str(count), host],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False, f"Ping to '{host}' timed out after 20 seconds."

    output = (r.stdout + r.stderr).strip()
    return r.returncode == 0, output or f"No response from '{host}'."


def check_port(host: str, port: int | str) -> tuple[bool, str]:
    """
    Check whether a TCP port is reachable on a host.

    Uses a direct Python socket connection — no subprocess, no shell injection.

    Args:
        host: Hostname or IP address.
        port: TCP port number (1–65535).
    """
    err = _validate_host(host)
    if err is not None:
        return err

    try:
        port = int(port)
    except (ValueError, TypeError):
        return False, f"Port '{port}' is not a valid integer."

    if not (1 <= port <= 65535):
        return False, f"Port {port} is out of valid range (1–65535)."

    try:
        with socket.create_connection((host, port), timeout=5):
            return True, f"Port {port} on {host} is OPEN."
    except ConnectionRefusedError:
        return True, f"Port {port} on {host} is CLOSED (connection refused)."
    except socket.timeout:
        return True, f"Port {port} on {host} timed out — port may be filtered."
    except socket.gaierror as e:
        return False, f"Could not resolve '{host}': {e}"
    except OSError as e:
        return False, f"Connection error: {e}"
