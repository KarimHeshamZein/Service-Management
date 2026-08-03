"""Technical-user choices and validation for record participants."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import User, UserRole


def technical_user_choices(db: Session, current_user: User) -> list[User]:
    """Return active Technical users, excluding the person submitting the form."""
    return list(
        db.scalars(
            select(User)
            .where(
                User.role == UserRole.TECHNICAL,
                User.is_active.is_(True),
                User.id != current_user.id,
            )
            .order_by(User.full_name, User.username)
        )
    )


def validate_participant_ids(
    db: Session,
    current_user: User,
    raw_values: Iterable[object],
    *,
    maximum: int = 20,
) -> tuple[list[str], list[str], str]:
    """Resolve submitted account IDs to snapshot names.

    Returns ``(names, selected_ids, error)``. Any forged or unavailable account
    makes the full selection invalid instead of silently accepting part of it.
    """
    submitted = [str(value).strip() for value in raw_values if str(value).strip()]
    selected_ids = list(dict.fromkeys(submitted))
    if len(selected_ids) > maximum:
        return [], selected_ids[:maximum], f"Select at most {maximum} Technical users."
    if any(not value.isdigit() for value in selected_ids):
        return [], selected_ids, "Select people from the Technical users list."

    choices = {str(choice.id): choice for choice in technical_user_choices(db, current_user)}
    if any(value not in choices for value in selected_ids):
        return [], selected_ids, (
            "One selected person is no longer an active Technical user. "
            "Review the selection and try again."
        )
    return [choices[value].full_name for value in selected_ids], selected_ids, ""


def selected_ids_for_names(choices: list[User], names: Iterable[str]) -> list[str]:
    """Best-effort mapping for participant snapshots on an existing record."""
    unused = list(choices)
    selected: list[str] = []
    for name in names:
        match = next((choice for choice in unused if choice.full_name == name), None)
        if match is not None:
            selected.append(str(match.id))
            unused.remove(match)
    return selected
