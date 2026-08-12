"""Shared helpers for the audited service-record photo editor."""
from __future__ import annotations

from typing import Any, Iterable

from .models import EvidencePhotoStage


PHOTO_STAGES = (
    EvidencePhotoStage.BEFORE,
    EvidencePhotoStage.AFTER,
    EvidencePhotoStage.LEGACY,
)


def grouped_photos(photos: Iterable[Any]) -> list[dict[str, Any]]:
    rows = list(photos)
    groups: list[dict[str, Any]] = []
    for stage in PHOTO_STAGES:
        matches = [
            photo
            for photo in rows
            if getattr(photo, "stage", EvidencePhotoStage.LEGACY) == stage
        ]
        if matches or stage != EvidencePhotoStage.LEGACY:
            groups.append({"stage": stage, "photos": matches})
    return groups


def existing_photo_descriptions(
    form: Any,
    photos: Iterable[Any],
    *,
    maximum: int,
) -> tuple[dict[int, str], str | None]:
    descriptions: dict[int, str] = {}
    for photo in photos:
        field_name = f"photo_description_{photo.id}"
        value = (
            str(form.get(field_name) or "").strip()
            if field_name in form
            else str(getattr(photo, "description", None) or "").strip()
        )
        if len(value) > maximum:
            return {}, f"Keep each photo note under {maximum} characters."
        descriptions[photo.id] = value
    return descriptions, None


def new_photo_descriptions(
    form: Any,
    field_name: str,
    count: int,
    *,
    maximum: int,
) -> tuple[list[str], str | None]:
    values = [str(value).strip() for value in form.getlist(field_name)]
    values.extend([""] * (count - len(values)))
    values = values[:count]
    if any(len(value) > maximum for value in values):
        return [], f"Keep each photo note under {maximum} characters."
    return values, None
