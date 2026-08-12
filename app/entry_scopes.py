"""Validation helpers for one-click, multi-site service submissions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from .helpers import entity_id
from .models import Site, SubProject, WorkSite
from .project_hierarchy import resolve_entry_sub_project
from .quotation_references import resolve_quotation_reference


@dataclass(slots=True)
class EntryScope:
    index: int
    project: Site
    sub_project: SubProject | None
    site: WorkSite
    quotation: Any | None


def validate_entry_scopes(
    form: Any,
    db: Session,
    *,
    require_quotation: bool = True,
) -> tuple[list[EntryScope], dict[str, str]]:
    project_values = [str(value or "").strip() for value in form.getlist("project_id")]
    sub_values = [str(value or "").strip() for value in form.getlist("sub_project_id")]
    site_values = [str(value or "").strip() for value in form.getlist("work_site_id")]
    quotation_values = (
        [str(value or "").strip() for value in form.getlist("quotation_number")]
        if require_quotation
        else []
    )
    count = max(
        len(project_values),
        len(sub_values),
        len(site_values),
        len(quotation_values) if require_quotation else 0,
        1,
    )
    for values in (project_values, sub_values, site_values):
        values.extend([""] * (count - len(values)))
    if require_quotation:
        quotation_values.extend([""] * (count - len(quotation_values)))

    scopes: list[EntryScope] = []
    errors: dict[str, str] = {}
    for index in range(count):
        suffix = "" if index == 0 else f"_scope_{index}"
        project_id = entity_id(project_values[index])
        project = db.get(Site, project_id) if project_id else None
        if not project_values[index]:
            errors[f"project_id{suffix}"] = "Select the project."
        elif project is None:
            errors[f"project_id{suffix}"] = "That project no longer exists."
        elif not project.is_active:
            errors[f"project_id{suffix}"] = "That project is deactivated."

        site_id = entity_id(site_values[index])
        site = db.get(WorkSite, site_id) if site_id else None
        if not site_values[index]:
            errors[f"work_site_id{suffix}"] = "Select the site."
        elif site is None:
            errors[f"work_site_id{suffix}"] = "That site no longer exists."
        elif not site.is_active:
            errors[f"work_site_id{suffix}"] = "That site is deactivated."

        sub_project, sub_error = resolve_entry_sub_project(
            db, project, site, sub_values[index]
        )
        if sub_error:
            errors[f"sub_project_id{suffix}"] = sub_error

        quotation = None
        if require_quotation:
            quotation, quotation_error = resolve_quotation_reference(
                db, quotation_values[index], project.id if project else None
            )
            if quotation_error or quotation is None:
                errors[f"quotation_number{suffix}"] = quotation_error or "Select a valid quotation."

        if project and site and (quotation or not require_quotation) and not sub_error:
            scopes.append(EntryScope(index, project, sub_project, site, quotation))

    if len(scopes) != count and count > 1:
        selection_names = "Main Project, Sub Project, Site, and quotation" if require_quotation else "Main Project, Sub Project, and Site"
        errors.setdefault("form", f"Review the highlighted {selection_names} selections.")
    return scopes, errors


def item_scope_indexes(form: Any, item_count: int, scope_count: int) -> tuple[list[int], dict[str, str]]:
    raw_values = [str(value or "").strip() for value in form.getlist("item_scope_index")]
    raw_values.extend(["0"] * (item_count - len(raw_values)))
    indexes: list[int] = []
    errors: dict[str, str] = {}
    for index, raw in enumerate(raw_values[:item_count]):
        try:
            scope_index = int(raw)
        except ValueError:
            scope_index = -1
        if scope_index < 0 or scope_index >= scope_count:
            errors[f"item_scope_index_{index}"] = "Select a valid Site assignment."
            scope_index = 0
        indexes.append(scope_index)
    for scope_index in range(scope_count):
        if scope_index not in indexes:
            errors[f"site_scope_{scope_index}"] = "Add at least one item to this Site."
    if any(key.startswith("site_scope_") for key in errors):
        errors.setdefault("form", "Every Site must contain at least one device.")
    return indexes, errors


def apply_scope_snapshot(item: Any, scope: EntryScope) -> None:
    """Attach immutable hierarchy evidence to one device/item row."""
    item.scope_position = scope.index
    item.project_id = scope.project.id
    item.project_name = scope.project.name
    item.project_address = scope.project.address
    item.sub_project_id = scope.sub_project.id if scope.sub_project else None
    item.sub_project_name = scope.sub_project.name if scope.sub_project else "General"
    item.work_site_id = scope.site.id
    item.work_site_name = scope.site.name
    item.quotation_id = scope.quotation.id if scope.quotation else None
    item.quotation_number = scope.quotation.quotation_number if scope.quotation else None
