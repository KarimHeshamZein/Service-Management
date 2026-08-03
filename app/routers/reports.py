"""Read-only filtered reports and PDF evidence exports."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..helpers import entity_id, render
from ..models import Site, User, UserRole
from ..record_views import (
    count_record_views,
    load_record_page,
    normalize_record_filters,
)
from ..report_pdf import build_records_pdf, build_technician_audit_pdf
from ..technician_audit import (
    load_technician_audit,
    normalize_audit_filters,
    technician_audit_record_count,
)

router = APIRouter()


def _filters(request: Request) -> dict[str, str]:
    return normalize_record_filters(
        request.query_params.get("q") or "",
        request.query_params.get("type") or "",
    )


@router.get("/reports")
def reports_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = _filters(request)
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    records, page_info = load_record_page(
        db,
        user,
        q=filters["q"],
        record_type=filters["type"],
        page=page,
        per_page=settings.page_size,
    )
    return render(
        request,
        "reports.html",
        {
            "active_nav": "reports",
            "records": records,
            "page_info": page_info,
            "filters": filters,
            "has_filters": any(filters.values()),
        },
    )


@router.get("/reports/pdf")
def reports_pdf(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = _filters(request)
    total = count_record_views(
        db,
        user,
        q=filters["q"],
        record_type=filters["type"],
    )
    if total > settings.max_pdf_records:
        records, page_info = load_record_page(
            db,
            user,
            q=filters["q"],
            record_type=filters["type"],
            page=1,
            per_page=settings.page_size,
        )
        return render(
            request,
            "reports.html",
            {
                "active_nav": "reports",
                "records": records,
                "page_info": page_info,
                "filters": filters,
                "has_filters": any(filters.values()),
                "export_error": (
                    f"The report matches {total} records, which exceeds the "
                    f"{settings.max_pdf_records}-record export limit. "
                    "Narrow the filters and try again."
                ),
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    records, _ = load_record_page(
        db,
        user,
        q=filters["q"],
        record_type=filters["type"],
        page=1,
        per_page=settings.max_pdf_records,
        include_evidence=True,
    )
    include_quotation = (
        user.can_access_pricing
        and (request.query_params.get("include_quotation") or "").lower()
        in {"1", "true", "on", "yes"}
    )
    content = build_records_pdf(
        records,
        filters,
        user.full_name,
        include_quotation=include_quotation,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="service-records-{timestamp}.pdf"'
            ),
            "Cache-Control": "no-store",
        },
    )


def _technical_users(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.role == UserRole.TECHNICAL)
            .order_by(User.is_active.desc(), User.full_name, User.username)
        )
    )


def _audit_filters(request: Request) -> dict:
    return normalize_audit_filters(
        start=request.query_params.get("start") or "",
        end=request.query_params.get("end") or "",
        record_type=request.query_params.get("type") or "",
        project_id=request.query_params.get("project_id") or "",
    )


def _selected_technician(
    db: Session,
    raw_id: str,
) -> User | None:
    user_id = entity_id(raw_id)
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or user.role != UserRole.TECHNICAL:
        return None
    return user


@router.get(
    "/reports/technician-audit",
    dependencies=[Depends(require_admin)],
)
def technician_audit_page(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    technician_id = (request.query_params.get("technician_id") or "").strip()
    technician = _selected_technician(db, technician_id)
    filters = _audit_filters(request)
    projects = list(db.scalars(select(Site).order_by(Site.name)))
    project = (
        db.get(Site, filters["project_id"])
        if filters["project_id"] is not None
        else None
    )
    if filters["project_id"] is not None and project is None:
        filters["project_id"] = None
        filters["project_id_value"] = ""
    filters["project_name"] = project.name if project else ""
    audit = (
        load_technician_audit(db, admin, technician, filters)
        if technician is not None
        else None
    )
    return render(
        request,
        "technician_audit.html",
        {
            "active_nav": "technician_audit",
            "technicians": _technical_users(db),
            "technician_id": technician_id if technician else "",
            "projects": projects,
            "filters": filters,
            "audit": audit,
        },
    )


@router.get(
    "/reports/technician-audit/pdf",
    dependencies=[Depends(require_admin)],
)
def technician_audit_pdf(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    technician = _selected_technician(
        db,
        (request.query_params.get("technician_id") or "").strip(),
    )
    if technician is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Select a Technical user.",
        )
    filters = _audit_filters(request)
    project = (
        db.get(Site, filters["project_id"])
        if filters["project_id"] is not None
        else None
    )
    if filters["project_id"] is not None and project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That Project does not exist.")
    filters["project_name"] = project.name if project else ""
    total = technician_audit_record_count(
        db,
        admin,
        technician,
        filters,
    )
    if total > settings.max_pdf_records:
        return render(
            request,
            "technician_audit.html",
            {
                "active_nav": "technician_audit",
                "technicians": _technical_users(db),
                "technician_id": str(technician.id),
                "projects": list(db.scalars(select(Site).order_by(Site.name))),
                "filters": filters,
                "audit": None,
                "export_error": (
                    f"The audit matches {total} records, which exceeds the "
                    f"{settings.max_pdf_records}-record export limit. "
                    "Narrow the filters and try again."
                ),
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    audit = load_technician_audit(db, admin, technician, filters)
    include_photos = (
        request.query_params.get("include_photos", "").lower()
        in {"1", "true", "on"}
    )
    content = build_technician_audit_pdf(
        audit,
        admin.full_name,
        include_photos=include_photos,
    )
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="technician-activity-'
                f'{technician.id}-{timestamp}.pdf"'
            ),
            "Cache-Control": "no-store",
        },
    )
