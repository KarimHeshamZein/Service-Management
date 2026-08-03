"""Windows TCP port availability and excluded-range inspection."""
from __future__ import annotations

import re
import socket
import subprocess
from dataclasses import dataclass
from typing import Iterable

EXCLUDED_RANGE_RE = re.compile(r"^\s*(\d+)\s+(\d+)(?:\s+\*)?\s*$")


@dataclass(frozen=True)
class PortStatus:
    port: int
    available: bool
    excluded: bool = False
    message: str = ""


def parse_excluded_port_ranges(output: str) -> tuple[range, ...]:
    """Parse the numeric rows from localized netsh excluded-range output."""
    ranges: list[range] = []
    for line in output.splitlines():
        match = EXCLUDED_RANGE_RE.fullmatch(line)
        if not match:
            continue
        start, end = (int(value) for value in match.groups())
        if 1 <= start <= end <= 65535:
            ranges.append(range(start, end + 1))
    return tuple(ranges)


def windows_excluded_port_ranges() -> tuple[range, ...]:
    """Read Windows' excluded TCP port ranges without changing network state."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        [
            "netsh.exe",
            "interface",
            "ipv4",
            "show",
            "excludedportrange",
            "protocol=tcp",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        creationflags=flags,
    )
    if result.returncode != 0:
        raise OSError("Windows excluded TCP port ranges could not be read.")
    return parse_excluded_port_ranges(result.stdout)


def check_port(
    port: int,
    *,
    host: str = "0.0.0.0",
    excluded_ranges: Iterable[range] | None = None,
) -> PortStatus:
    """Return whether a TCP port can be bound and is not Windows-reserved."""
    if not 1 <= int(port) <= 65535:
        return PortStatus(int(port), False, message="Enter a port from 1 to 65535.")
    ranges = tuple(excluded_ranges) if excluded_ranges is not None else windows_excluded_port_ranges()
    if any(port in excluded for excluded in ranges):
        return PortStatus(
            port,
            False,
            excluded=True,
            message=f"TCP port {port} is in a Windows excluded range.",
        )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, port))
    except OSError:
        return PortStatus(port, False, message=f"TCP port {port} is already in use.")
    finally:
        sock.close()
    return PortStatus(port, True, message=f"TCP port {port} is available.")
