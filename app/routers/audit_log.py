"""Administrator-only audit log browser."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..helpers import paginate, render, to_utc_from_display
from ..models import AuditEvent, User


router = APIRouter()


@router.get("/admin/audit-log")
def audit_log(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    params = request.query_params
    q = str(params.get("q") or "").strip()
    actor = str(params.get("actor") or "").strip()
    module = str(params.get("module") or "").strip()
    action = str(params.get("action") or "").strip()
    from_at = str(params.get("from_at") or "").strip()
    to_at = str(params.get("to_at") or "").strip()
    try:
        page = max(1, int(params.get("page", "1")))
    except ValueError:
        page = 1
    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(
            AuditEvent.path.ilike(like)
            | AuditEvent.entity_label.ilike(like)
            | AuditEvent.entity_id.ilike(like)
        )
    if actor:
        conditions.append(AuditEvent.actor_name == actor)
    if module:
        conditions.append(AuditEvent.module == module)
    if action:
        conditions.append(AuditEvent.action == action)
    for raw, is_end in ((from_at, False), (to_at, True)):
        if not raw:
            continue
        try:
            value = to_utc_from_display(datetime.fromisoformat(raw))
        except ValueError:
            continue
        conditions.append(AuditEvent.created_at < value + timedelta(seconds=1) if is_end else AuditEvent.created_at >= value)
    total = int(db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions)) or 0)
    paging = paginate(total, page, 50)
    events = list(
        db.scalars(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .offset(paging["offset"])
            .limit(paging["per_page"])
        )
    )
    return render(
        request,
        "audit_log.html",
        {
            "active_nav": "audit_log",
            "events": events,
            "page": paging,
            "filters": {"q": q, "actor": actor, "module": module, "action": action, "from_at": from_at, "to_at": to_at},
            "actors": list(db.scalars(select(AuditEvent.actor_name).distinct().order_by(AuditEvent.actor_name))),
            "modules": list(db.scalars(select(AuditEvent.module).distinct().order_by(AuditEvent.module))),
            "actions": list(db.scalars(select(AuditEvent.action).distinct().order_by(AuditEvent.action))),
        },
    )
