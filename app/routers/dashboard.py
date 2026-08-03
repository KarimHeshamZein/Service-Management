"""Operational dashboard for Administrators and Technical users."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user, require_dashboard_access
from ..helpers import display_today_bounds, render
from ..models import MaintenancePhoto, MaintenanceRecord, MaintenanceResult, User

router = APIRouter()

RECENT_LIMIT = 8
GROUP_LIMIT = 6


def _result_counts(db: Session, leader_id: int | None) -> dict[str, int]:
    stmt = select(MaintenanceRecord.result, func.count()).group_by(MaintenanceRecord.result)
    if leader_id is not None:
        stmt = stmt.where(MaintenanceRecord.submitted_by_id == leader_id)
    raw = {row[0]: row[1] for row in db.execute(stmt).all()}
    return {member.value: int(raw.get(member.value, raw.get(member, 0)) or 0) for member in MaintenanceResult}


def _recent(db: Session, leader_id: int | None) -> list[MaintenanceRecord]:
    stmt = (
        select(MaintenanceRecord)
        .options(selectinload(MaintenanceRecord.photos))
        .order_by(MaintenanceRecord.submitted_at.desc())
        .limit(RECENT_LIMIT)
    )
    if leader_id is not None:
        stmt = stmt.where(MaintenanceRecord.submitted_by_id == leader_id)
    return list(db.scalars(stmt))


def _grouped(db: Session, column) -> list[tuple[str, int]]:
    stmt = (
        select(column, func.count())
        .group_by(column)
        .order_by(func.count().desc(), column.asc())
        .limit(GROUP_LIMIT)
    )
    return [(row[0], int(row[1])) for row in db.execute(stmt).all()]


@router.get("/")
def root(request: Request, user: User = Depends(get_current_user)):
    from fastapi.responses import RedirectResponse

    target = "/records" if user.is_customer else "/dashboard"
    return RedirectResponse(target, status_code=303)


@router.get("/dashboard")
def dashboard(
    request: Request,
    user: User = Depends(require_dashboard_access),
    db: Session = Depends(get_db),
):
    leader_id = None
    day_start, day_end = display_today_bounds()

    base = select(func.count(MaintenanceRecord.id))
    if leader_id is not None:
        base = base.where(MaintenanceRecord.submitted_by_id == leader_id)

    total = int(db.scalar(base) or 0)
    today = int(
        db.scalar(
            base.where(
                MaintenanceRecord.submitted_at >= day_start,
                MaintenanceRecord.submitted_at < day_end,
            )
        )
        or 0
    )

    counts = _result_counts(db, leader_id)
    photo_total = int(
        db.scalar(
            select(func.count(MaintenancePhoto.id))
            .join(MaintenanceRecord, MaintenanceRecord.id == MaintenancePhoto.record_id)
            .where(*([MaintenanceRecord.submitted_by_id == leader_id] if leader_id else []))
        )
        or 0
    )

    context = {
        "active_nav": "dashboard",
        "total": total,
        "today": today,
        "counts": counts,
        "photo_total": photo_total,
        "recent": _recent(db, leader_id),
    }

    if user.can_view_all_records:
        context.update(
            {
                "by_service": _grouped(db, MaintenanceRecord.service_name),
                "by_site": _grouped(db, MaintenanceRecord.site_name),
                "by_leader": _grouped(db, MaintenanceRecord.team_leader_name),
            }
        )
        return render(request, "dashboard_admin.html", context)

    return render(request, "dashboard_leader.html", context)
