"""A unified read-only view across the specific record modules."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..helpers import render
from ..models import User
from ..record_views import load_record_page, normalize_record_filters

router = APIRouter()


@router.get("/records")
def all_records(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    filters = normalize_record_filters(
        request.query_params.get("q") or "",
        request.query_params.get("type") or "",
    )
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
        "records.html",
        {
            "active_nav": "all_records",
            "records": records,
            "page_info": page_info,
            "filters": filters,
            "has_filters": any(filters.values()),
        },
    )
