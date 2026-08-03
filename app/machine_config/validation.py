"""Authoritative validation shared by the console and setup wizard."""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Mapping

from app.deployment_config import default_profile, validate_profile

POSTGRES_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _text(value: Any) -> str:
    return str(value or "").strip()


def validate_network(
    values: Mapping[str, Any],
    *,
    base: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate a complete deployment profile from partial machine input."""
    merged = {**(dict(base) if base is not None else default_profile()), **values}
    return validate_profile(merged)


def validate_database(values: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate PostgreSQL connection and optional application-database fields."""
    errors: dict[str, str] = {}
    cleaned: dict[str, Any] = {
        "host": _text(values.get("host")),
        "port": _port(values.get("port"), errors),
        "database": _text(values.get("database")),
        "username": _text(values.get("username")),
        "password": str(values.get("password") or ""),
    }
    _validate_host(cleaned["host"], errors)
    for field in ("database", "username"):
        if not POSTGRES_IDENTIFIER_RE.fullmatch(cleaned[field]):
            errors[field] = (
                "Use 1 to 63 letters, numbers or underscores, starting with a letter "
                "or underscore."
            )
    if not cleaned["password"]:
        errors["password"] = "Enter the PostgreSQL password."
    return cleaned, errors


def _port(value: Any, errors: dict[str, str]) -> int:
    text = _text(value)
    if not text.isdigit() or not 1 <= int(text) <= 65535:
        errors["port"] = "Enter a port from 1 to 65535."
        return 0
    return int(text)


def _validate_host(host: str, errors: dict[str, str]) -> None:
    if not host:
        errors["host"] = "Enter the PostgreSQL host or IP address."
        return
    try:
        ipaddress.ip_address(host)
        return
    except ValueError:
        pass
    labels = host.rstrip(".").split(".")
    valid = all(
        label
        and len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", label)
        for label in labels
    )
    if len(host) > 253 or not valid:
        errors["host"] = "Enter a valid PostgreSQL host or IP address."
