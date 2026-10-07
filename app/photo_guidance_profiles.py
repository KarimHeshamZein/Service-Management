"""Shared selection and validation for independent Photo Guidance Profiles."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .helpers import entity_id
from .models import ProjectPhotoGuidanceRule


def profile_choices(db: Session) -> list[ProjectPhotoGuidanceRule]:
    return list(
        db.scalars(
            select(ProjectPhotoGuidanceRule).order_by(
                ProjectPhotoGuidanceRule.project_id,
                ProjectPhotoGuidanceRule.name,
            )
        )
    )


def resolve_profile(
    db: Session, raw_value: str, project_id: int | None
) -> tuple[ProjectPhotoGuidanceRule | None, str | None]:
    value = str(raw_value or "").strip()
    if not value:
        return None, None
    profile_id = entity_id(value)
    profile = db.get(ProjectPhotoGuidanceRule, profile_id) if profile_id else None
    if profile is None or project_id is None or profile.project_id != project_id:
        return None, "Choose a Photo Guidance Profile belonging to the selected Main Project."
    return profile, None
