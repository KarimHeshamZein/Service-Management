"""Operational dashboard for Administrators and Technical users."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_dashboard_access
from ..helpers import display_today_bounds, render
from ..models import (
    GeneralMaintenancePhoto,
    GeneralMaintenanceItem,
    GeneralMaintenanceRecord,
    InstallationItemPhoto,
    InstallationRecordItem,
    InstallationPhoto,
    InstallationRecord,
    MaintenanceItemPhoto,
    MaintenanceRecordItem,
    MaintenancePhoto,
    MaintenanceRecord,
    MaintenanceResult,
    User,
)
from ..record_views import count_record_views, load_record_page

router = APIRouter()

RECENT_LIMIT = 8
GROUP_LIMIT = 6


RECORD_MODELS = (MaintenanceRecord, InstallationRecord, GeneralMaintenanceRecord)
PHOTO_MODELS = (
    MaintenancePhoto,
    MaintenanceItemPhoto,
    InstallationPhoto,
    InstallationItemPhoto,
    GeneralMaintenancePhoto,
)


def _result_counts(db: Session, user: User) -> dict[str, int]:
    project_ids = user.assigned_project_ids
    combined = union_all(
        *(
            select(model.result.label("result")).where(model.site_id.in_(project_ids))
            if not user.is_admin
            else select(model.result.label("result"))
            for model in RECORD_MODELS
        )
    ).subquery()
    stmt = select(combined.c.result, func.count()).group_by(combined.c.result)
    raw = {row[0]: row[1] for row in db.execute(stmt).all()}
    return {member.value: int(raw.get(member.value, raw.get(member, 0)) or 0) for member in MaintenanceResult}


def _recent(db: Session, user: User) -> list[dict]:
    records, _ = load_record_page(
        db,
        user,
        page=1,
        per_page=RECENT_LIMIT,
    )
    return records


def _grouped(db: Session, column_name: str) -> list[tuple[str, int]]:
    combined = union_all(
        *(
            select(getattr(model, column_name).label("name"))
            for model in RECORD_MODELS
        )
    ).subquery()
    stmt = (
        select(combined.c.name, func.count())
        .group_by(combined.c.name)
        .order_by(func.count().desc(), combined.c.name.asc())
        .limit(GROUP_LIMIT)
    )
    return [(row[0], int(row[1])) for row in db.execute(stmt).all()]


def _photo_total(db: Session, user: User) -> int:
    if user.is_admin:
        return sum(int(db.scalar(select(func.count(model.id))) or 0) for model in PHOTO_MODELS)
    project_ids = user.assigned_project_ids
    statements = (
        select(func.count(MaintenancePhoto.id)).join(MaintenanceRecord).where(MaintenanceRecord.site_id.in_(project_ids)),
        select(func.count(MaintenanceItemPhoto.id)).join(MaintenanceRecordItem).join(MaintenanceRecord).where(MaintenanceRecord.site_id.in_(project_ids)),
        select(func.count(InstallationPhoto.id)).join(InstallationRecord).where(InstallationRecord.site_id.in_(project_ids)),
        select(func.count(InstallationItemPhoto.id)).join(InstallationRecordItem).join(InstallationRecord).where(InstallationRecord.site_id.in_(project_ids)),
        select(func.count(GeneralMaintenancePhoto.id)).join(GeneralMaintenanceItem).join(GeneralMaintenanceRecord).where(GeneralMaintenanceRecord.site_id.in_(project_ids)),
    )
    return sum(int(db.scalar(statement) or 0) for statement in statements)


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
    day_start, day_end = display_today_bounds()
    total = count_record_views(db, user)
    today = count_record_views(
        db,
        user,
        start_at=day_start,
        end_before=day_end,
    )

    counts = _result_counts(db, user)
    photo_total = _photo_total(db, user)

    context = {
        "active_nav": "dashboard",
        "total": total,
        "today": today,
        "counts": counts,
        "photo_total": photo_total,
        "recent": _recent(db, user),
    }

    if user.can_view_all_records:
        context.update(
            {
                "by_service": _grouped(db, "service_name"),
                "by_site": _grouped(db, "site_name"),
                "by_leader": _grouped(db, "team_leader_name"),
            }
        )
        return render(request, "dashboard_admin.html", context)

    return render(request, "dashboard_leader.html", context)
