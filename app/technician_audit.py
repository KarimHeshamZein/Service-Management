"""Administrator-only technician activity aggregation."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .helpers import entity_id
from .models import RecordRevision, User
from .record_views import (
    VALID_RECORD_TYPES,
    count_record_views,
    load_record_views,
)

REVISION_RECORD_KEYS = {
    "installation": "installation",
    "preventive_maintenance": "maintenance",
    "maintenance": "general_maintenance",
}


def _date_value(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw.strip())
    except (AttributeError, ValueError):
        return None


def normalize_audit_filters(
    *,
    start: str = "",
    end: str = "",
    record_type: str = "",
    project_id: str = "",
) -> dict[str, Any]:
    start_date = _date_value(start)
    end_date = _date_value(end)
    normalized_type = record_type.strip()
    if normalized_type not in VALID_RECORD_TYPES:
        normalized_type = ""
    normalized_project_id = entity_id(str(project_id).strip())
    return {
        "start": start_date.isoformat() if start_date else "",
        "end": end_date.isoformat() if end_date else "",
        "start_date": start_date,
        "end_date": end_date,
        "type": normalized_type,
        "project_id": normalized_project_id,
        "project_id_value": str(normalized_project_id or ""),
    }


def _utc_bounds(filters: dict[str, Any]) -> tuple[datetime | None, datetime | None]:
    start_at = None
    end_before = None
    if filters["start_date"]:
        start_at = datetime.combine(filters["start_date"], time.min) - (
            settings.display_tz_offset
        )
    if filters["end_date"]:
        end_before = datetime.combine(
            filters["end_date"] + timedelta(days=1),
            time.min,
        ) - settings.display_tz_offset
    return start_at, end_before


def _inside_period(
    value: datetime,
    start_at: datetime | None,
    end_before: datetime | None,
) -> bool:
    return (start_at is None or value >= start_at) and (
        end_before is None or value < end_before
    )


def _count_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"label": label, "count": count}
        for label, count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0].casefold()),
        )
    ]


def load_technician_audit(
    db: Session,
    admin: User,
    technician: User,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Return a filtered technician work ledger and review metrics."""
    start_at, end_before = _utc_bounds(filters)
    records = load_record_views(
        db,
        admin,
        record_type=filters["type"],
        include_evidence=True,
        technician_id=technician.id,
        start_at=start_at,
        end_before=end_before,
        project_id=filters["project_id"],
    )

    activity: list[dict[str, Any]] = []
    for record in records:
        if record["submitted_by_id"] == technician.id:
            role = "Led"
        else:
            role = "Assisted"

        record["technician_role"] = role
        record["device_count"] = len(record["items"])
        record["photo_count"] = sum(
            len(item["photos"]) for item in record["items"]
        )
        activity.append(record)

    activity_keys = {
        (record["record_key"], record["id"]) for record in activity
    }
    revision_stmt = (
        select(RecordRevision)
        .where(RecordRevision.edited_by_id == technician.id)
        .order_by(RecordRevision.created_at.desc(), RecordRevision.id.desc())
    )
    revisions = []
    for revision in db.scalars(revision_stmt):
        revision_key = REVISION_RECORD_KEYS.get(
            revision.record_type,
            revision.record_type,
        )
        if filters["type"] and revision_key != filters["type"]:
            continue
        if not _inside_period(revision.created_at, start_at, end_before):
            continue
        if filters["project_id"] and (
            revision_key,
            revision.record_id,
        ) not in activity_keys:
            continue
        revisions.append(revision)

    record_types = Counter(record["record_type"] for record in activity)
    projects = Counter(record["customer_name"] for record in activity)
    sites = Counter(
        record["work_site_name"] or record["site_name"] for record in activity
    )
    services: Counter[str] = Counter()
    devices: Counter[str] = Counter()
    results: Counter[str] = Counter()
    total_devices = 0
    total_photos = 0
    for record in activity:
        total_devices += record["device_count"]
        total_photos += record["photo_count"]
        for item in record["items"]:
            services[item["service_name"]] += 1
            device_label = item["device_name"]
            if item["device_model"]:
                device_label += f" - {item['device_model']}"
            devices[device_label] += 1
            results[item["result"].label] += 1

    revision_actions = Counter(revision.action.title() for revision in revisions)
    summary = {
        "total_visits": len(activity),
        "led_visits": sum(
            record["technician_role"] == "Led" for record in activity
        ),
        "assisted_visits": sum(
            record["technician_role"] == "Assisted" for record in activity
        ),
        "total_devices": total_devices,
        "total_photos": total_photos,
        "total_edits": len(revisions),
        "record_types": _count_rows(record_types),
        "projects": _count_rows(projects),
        "sites": _count_rows(sites),
        "services": _count_rows(services),
        "devices": _count_rows(devices),
        "results": _count_rows(results),
        "revision_actions": _count_rows(revision_actions),
    }
    return {
        "technician": technician,
        "filters": filters,
        "records": activity,
        "revisions": revisions,
        "summary": summary,
    }


def technician_audit_record_count(
    db: Session,
    admin: User,
    technician: User,
    filters: dict[str, Any],
) -> int:
    start_at, end_before = _utc_bounds(filters)
    return count_record_views(
        db,
        admin,
        record_type=filters["type"],
        technician_id=technician.id,
        start_at=start_at,
        end_before=end_before,
        project_id=filters["project_id"],
    )
