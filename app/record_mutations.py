"""Shared, append-only audit helpers for controlled record mutations."""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import RecordRevision, User

MAX_PARTICIPANTS = 20


def participant_names(raw: str) -> list[str]:
    """Parse one participant per line, trim blanks and preserve first occurrence."""
    names: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        name = line.strip()
        key = name.casefold()
        if not name or key in seen:
            continue
        names.append(name[:120])
        seen.add(key)
        if len(names) == MAX_PARTICIPANTS:
            break
    return names


def changed(before, after) -> dict | None:
    """Return a compact before/after value only when a field changed."""
    if before == after:
        return None
    return {"before": before, "after": after}


def add_revision(
    db: Session,
    *,
    record_type: str,
    record_id: int,
    record_number: str,
    action: str,
    user: User,
    changes: dict,
) -> RecordRevision:
    revision = RecordRevision(
        record_type=record_type,
        record_id=record_id,
        record_number=record_number,
        action=action,
        edited_by_id=user.id,
        editor_name=user.full_name,
        changes_json=json.dumps(changes, ensure_ascii=False, default=str),
    )
    db.add(revision)
    return revision


def revisions_for(
    db: Session, record_type: str, record_id: int
) -> list[RecordRevision]:
    return list(
        db.scalars(
            select(RecordRevision)
            .where(
                RecordRevision.record_type == record_type,
                RecordRevision.record_id == record_id,
            )
            .order_by(RecordRevision.created_at.desc(), RecordRevision.id.desc())
        )
    )
