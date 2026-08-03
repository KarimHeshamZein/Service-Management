"""Compute runtime endpoint settings without mutating input mappings."""
from __future__ import annotations

from typing import Any, Mapping


def endpoint_updates(profile: Mapping[str, Any]) -> dict[str, str]:
    """Return the complete HTTP endpoint update for a validated profile."""
    port = int(profile["internal_port"])
    public_enabled = bool(profile.get("public_enabled"))
    address = (
        str(profile.get("public_ip") or "").strip()
        if public_enabled
        else str(profile.get("local_ip") or "").strip()
    )
    if not address:
        address = "127.0.0.1"
    return {
        "APP_HOST": "0.0.0.0",
        "APP_PORT": str(port),
        "APP_RELOAD": "false",
        "PUBLIC_BASE_URL": f"http://{address}:{port}",
        "SESSION_HTTPS_ONLY": "false",
    }


def with_endpoint_updates(
    environment: Mapping[str, str],
    profile: Mapping[str, Any],
) -> dict[str, str]:
    """Return a new environment mapping containing recomputed endpoints."""
    return {**environment, **endpoint_updates(profile)}
