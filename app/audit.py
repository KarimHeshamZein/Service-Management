"""Append-only request auditing with explicit rich-change context support."""
from __future__ import annotations

import json
import re
from typing import Any

from fastapi import Request

from .database import SessionLocal
from .models import AuditEvent, User, utcnow
from .security import current_user_id


SENSITIVE_DOWNLOAD_MARKERS = ("/pdf", "/export", "/device-template", "/diagnostics", "/backup")
ENTITY_ID_RE = re.compile(r"/(\d+)(?:/|$)")


def set_audit_context(
    request: Request,
    *,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    entity_label: str | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    request.state.audit_context = {
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "entity_label": entity_label,
        "changes": changes or {},
    }


def _module(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return "application"
    if parts[0] == "general-maintenance":
        return "maintenance"
    if parts[0] == "maintenance":
        return "preventive_maintenance"
    if parts[0] == "installations":
        return "installation"
    if parts[0] == "pricing" and len(parts) > 1:
        return f"pricing_{parts[1].replace('-', '_')}"
    return parts[0].replace("-", "_")


def _default_action(method: str, path: str, status_code: int) -> str:
    if path == "/login":
        return "login" if status_code < 400 else "login_failed"
    if path == "/logout":
        return "logout"
    if status_code >= 400:
        return "request_failed"
    tail = path.rstrip("/").split("/")[-1]
    if tail in {"delete", "remove", "remove-image"}:
        return "delete"
    if tail in {"edit", "settings"}:
        return "update"
    if tail == "toggle":
        return "toggle"
    if method == "DELETE":
        return "delete"
    if method in {"PUT", "PATCH"}:
        return "update"
    if method == "GET":
        return "download"
    return "create_or_submit"


def should_audit(request: Request) -> bool:
    path = request.url.path
    if path.startswith("/static"):
        return False
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    return request.method == "GET" and any(marker in path for marker in SENSITIVE_DOWNLOAD_MARKERS)


def write_request_audit(request: Request, status_code: int) -> None:
    if not should_audit(request):
        return
    context = getattr(request.state, "audit_context", {}) or {}
    with SessionLocal() as db:
        try:
            actor = getattr(request.state, "user", None)
            if actor is None:
                user_id = getattr(request.state, "audit_actor_id", None) or current_user_id(request)
                actor = db.get(User, user_id) if user_id else None
            path = request.url.path
            match = ENTITY_ID_RE.search(path)
            db.add(
                AuditEvent(
                    actor_user_id=actor.id if actor else None,
                    actor_name=actor.full_name if actor else "Anonymous",
                    actor_role=(actor.role.value if actor and hasattr(actor.role, "value") else str(actor.role) if actor else None),
                    action=context.get("action") or _default_action(request.method, path, status_code),
                    module=_module(path),
                    entity_type=context.get("entity_type"),
                    entity_id=context.get("entity_id") or (match.group(1) if match else None),
                    entity_label=context.get("entity_label"),
                    method=request.method,
                    path=path[:500],
                    status_code=status_code,
                    ip_address=(request.client.host[:64] if request.client else None),
                    user_agent=(request.headers.get("user-agent") or "")[:255] or None,
                    changes_json=json.dumps(context.get("changes") or {}, ensure_ascii=False, default=str),
                    created_at=utcnow(),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
