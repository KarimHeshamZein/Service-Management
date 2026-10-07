"""Administrator-only, search-first operational and user activity report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_admin
from ..helpers import entity_id, paginate, render, to_utc_from_display
from ..logs_report_exports import build_logs_report_pdf, build_logs_report_xlsx
from ..models import AuditEvent, Site, User, UserRole
from ..technician_audit import load_technician_audit, normalize_audit_filters


router = APIRouter()
EXPORT_LIMIT = 5000


def _event_summary(event: AuditEvent) -> str:
    action = event.action.replace("_", " ").title()
    target = event.entity_label or event.entity_type or event.module.replace("_", " ").title()
    if event.entity_id and f"{event.entity_id}" not in target:
        target = f"{target} #{event.entity_id}"
    return f"{action}: {target}"


def _activity_filters(request: Request) -> dict[str, str]:
    params = request.query_params
    return {
        "searched": "1" if params.get("searched") == "1" else "",
        "view": "activity",
        "q": str(params.get("q") or "").strip(),
        "actor": str(params.get("actor") or "").strip(),
        "role": str(params.get("role") or "").strip(),
        "module": str(params.get("module") or "").strip(),
        "action": str(params.get("action") or "").strip(),
        "entity_type": str(params.get("entity_type") or "").strip(),
        "status": str(params.get("status") or "").strip(),
        "log_type": str(params.get("log_type") or "all").strip(),
        "ip_address": str(params.get("ip_address") or "").strip(),
        "from_at": str(params.get("from_at") or "").strip(),
        "to_at": str(params.get("to_at") or "").strip(),
    }


def _has_activity_criteria(filters: dict[str, str]) -> bool:
    return any(
        filters[key]
        for key in (
            "q", "actor", "role", "module", "action", "entity_type",
            "status", "ip_address", "from_at", "to_at",
        )
    ) or filters["log_type"] in {"user", "system"}


def _activity_conditions(filters: dict[str, str]) -> list:
    conditions = []
    if filters["q"]:
        like = f"%{filters['q']}%"
        conditions.append(
            AuditEvent.path.ilike(like)
            | AuditEvent.entity_label.ilike(like)
            | AuditEvent.entity_id.ilike(like)
            | AuditEvent.actor_name.ilike(like)
            | AuditEvent.changes_json.ilike(like)
            | AuditEvent.action.ilike(like)
            | AuditEvent.module.ilike(like)
        )
    if filters["actor"]:
        conditions.append(AuditEvent.actor_name == filters["actor"])
    if filters["role"]:
        conditions.append(AuditEvent.actor_role == filters["role"])
    if filters["module"]:
        conditions.append(AuditEvent.module == filters["module"])
    if filters["action"]:
        conditions.append(AuditEvent.action == filters["action"])
    if filters["entity_type"]:
        conditions.append(AuditEvent.entity_type == filters["entity_type"])
    if filters["ip_address"]:
        conditions.append(AuditEvent.ip_address.ilike(f"%{filters['ip_address']}%"))
    if filters["status"] == "success":
        conditions.append(AuditEvent.status_code < 400)
    elif filters["status"] == "failed":
        conditions.append(AuditEvent.status_code >= 400)
    elif filters["status"].isdigit():
        conditions.append(AuditEvent.status_code == int(filters["status"]))
    if filters["log_type"] == "user":
        conditions.append(
            or_(
                AuditEvent.actor_user_id.is_not(None),
                AuditEvent.action.in_(("login", "login_failed", "logout")),
            )
        )
    elif filters["log_type"] == "system":
        conditions.append(
            or_(
                AuditEvent.status_code >= 500,
                AuditEvent.module.in_(("settings", "system", "deployment")),
                (
                    AuditEvent.actor_user_id.is_(None)
                    & AuditEvent.action.not_in(("login", "login_failed", "logout"))
                ),
            )
        )
    for key, is_end in (("from_at", False), ("to_at", True)):
        raw = filters[key]
        if not raw:
            continue
        try:
            value = to_utc_from_display(datetime.fromisoformat(raw))
        except ValueError:
            continue
        conditions.append(
            AuditEvent.created_at < value + timedelta(seconds=1)
            if is_end else AuditEvent.created_at >= value
        )
    return conditions


def _filter_options(db: Session) -> dict:
    return {
        "actors": list(db.scalars(select(AuditEvent.actor_name).distinct().order_by(AuditEvent.actor_name))),
        "roles": list(db.scalars(select(AuditEvent.actor_role).where(AuditEvent.actor_role.is_not(None)).distinct().order_by(AuditEvent.actor_role))),
        "modules": list(db.scalars(select(AuditEvent.module).distinct().order_by(AuditEvent.module))),
        "actions": list(db.scalars(select(AuditEvent.action).distinct().order_by(AuditEvent.action))),
        "entity_types": list(db.scalars(select(AuditEvent.entity_type).where(AuditEvent.entity_type.is_not(None)).distinct().order_by(AuditEvent.entity_type))),
    }


def _technical_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role == UserRole.TECHNICAL).order_by(User.is_active.desc(), User.full_name, User.username)))


def _technician_context(request: Request, db: Session, admin: User) -> dict:
    technician_id = str(request.query_params.get("technician_id") or "").strip()
    technician_pk = entity_id(technician_id)
    technician = db.get(User, technician_pk) if technician_pk else None
    if technician is not None and technician.role != UserRole.TECHNICAL:
        technician = None
    filters = normalize_audit_filters(
        start=request.query_params.get("start") or "",
        end=request.query_params.get("end") or "",
        record_type=request.query_params.get("type") or "",
        project_id=request.query_params.get("project_id") or "",
    )
    project = db.get(Site, filters["project_id"]) if filters["project_id"] else None
    if filters["project_id"] and project is None:
        filters["project_id"] = None
        filters["project_id_value"] = ""
    filters["project_name"] = project.name if project else ""
    searched = request.query_params.get("searched") == "1"
    return {
        "active_nav": "logs_report",
        "logs_report_view": "technician",
        "technicians": _technical_users(db),
        "technician_id": technician_id if technician else "",
        "projects": list(db.scalars(select(Site).order_by(Site.name))),
        "filters": filters,
        "audit": load_technician_audit(db, admin, technician, filters) if searched and technician is not None else None,
        "searched": searched,
        "missing_technician": searched and technician is None,
        "search_action": "/management/logs-report",
        "clear_url": "/management/logs-report?view=technician",
        "pdf_action": "/management/logs-report/technician.pdf",
    }


@router.get("/management/logs-report")
def logs_report(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if request.query_params.get("view") == "technician":
        return render(request, "technician_audit.html", _technician_context(request, db, user))
    filters = _activity_filters(request)
    searched = filters["searched"] == "1"
    has_criteria = _has_activity_criteria(filters)
    events: list[AuditEvent] = []
    try:
        page_number = max(1, int(request.query_params.get("page", "1")))
    except ValueError:
        page_number = 1
    paging = paginate(0, page_number, 50)
    if searched and has_criteria:
        conditions = _activity_conditions(filters)
        total = int(db.scalar(select(func.count()).select_from(AuditEvent).where(*conditions)) or 0)
        paging = paginate(total, page_number, 50)
        events = list(db.scalars(select(AuditEvent).where(*conditions).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).offset(paging["offset"]).limit(paging["per_page"])))
    context = {
        "active_nav": "logs_report",
        "logs_report_view": "activity",
        "events": [{"event": event, "summary": _event_summary(event)} for event in events],
        "page": paging,
        "filters": filters,
        "searched": searched,
        "has_criteria": has_criteria,
        "missing_criteria": searched and not has_criteria,
        **_filter_options(db),
    }
    return render(request, "audit_log.html", context)


def _export_events(request: Request, db: Session) -> tuple[list[AuditEvent], dict[str, str]]:
    filters = _activity_filters(request)
    if filters["searched"] != "1" or not _has_activity_criteria(filters):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Search before exporting logs.")
    events = list(db.scalars(select(AuditEvent).where(*_activity_conditions(filters)).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(EXPORT_LIMIT + 1)))
    if len(events) > EXPORT_LIMIT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"The export exceeds {EXPORT_LIMIT} events. Narrow the search filters.")
    return events, filters


@router.get("/management/logs-report/pdf")
def logs_report_pdf(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    events, filters = _export_events(request, db)
    content = build_logs_report_pdf(events, filters, user.full_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="logs-report-{timestamp}.pdf"', "Cache-Control": "no-store"})


@router.get("/management/logs-report/excel")
def logs_report_excel(request: Request, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    events, filters = _export_events(request, db)
    content = build_logs_report_xlsx(events, filters, user.full_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return Response(content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="logs-report-{timestamp}.xlsx"', "Cache-Control": "no-store"})


@router.get("/management/logs-report/events/{event_id}")
def logs_report_detail(request: Request, event_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    event = db.get(AuditEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return render(request, "audit_log_detail.html", {"active_nav": "logs_report", "event": event, "summary": _event_summary(event)})


@router.get("/admin/audit-log")
def legacy_audit_log(request: Request, user: User = Depends(require_admin)):
    target = "/management/logs-report"
    if request.url.query:
        target += f"?searched=1&{request.url.query}"
    return RedirectResponse(target, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/admin/audit-log/{event_id}")
def legacy_audit_log_detail(event_id: int, user: User = Depends(require_admin)):
    return RedirectResponse(f"/management/logs-report/events/{event_id}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
