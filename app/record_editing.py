"""Presentation helpers for the nested service-record editor."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from .entry_data_tables import (
    MAX_DATA_ROWS_PER_SITE,
    MAX_IDENTIFIER_LENGTH,
    MAX_ITEM_LENGTH,
    MAX_NOTES_LENGTH,
    SIM_TYPES,
)


def grouped_edit_scopes(record: Any, wrappers: list[dict]) -> list[dict]:
    """Group editable item/photo wrappers and browser-table rows by saved Site."""
    items_by_scope: dict[int, list[dict]] = defaultdict(list)
    for wrapper in wrappers:
        item = wrapper["data"]
        items_by_scope[int(getattr(item, "scope_position", 0) or 0)].append(wrapper)

    rows_by_scope: dict[int, list[Any]] = defaultdict(list)
    for row in getattr(record, "device_data_rows", []):
        rows_by_scope[int(row.scope_position or 0)].append(row)

    positions = sorted(set(items_by_scope) | set(rows_by_scope) or {0})
    scopes: list[dict] = []
    for position in positions:
        wrappers_for_scope = items_by_scope.get(position, [])
        source = wrappers_for_scope[0]["data"] if wrappers_for_scope else None
        row = rows_by_scope.get(position, [None])[0]
        project_id = getattr(source, "project_id", None) or getattr(row, "project_id", None) or record.site_id
        project_name = (
            getattr(source, "project_name", None)
            or getattr(row, "project_name", None)
            or getattr(record, "customer_name", None)
            or getattr(record, "project_name", None)
        )
        sub_project_id = getattr(source, "sub_project_id", None) or getattr(row, "sub_project_id", None)
        sub_project_name = (
            getattr(source, "sub_project_name", None)
            or getattr(row, "sub_project_name", None)
            or getattr(record, "sub_project_name", None)
            or "General"
        )
        work_site_id = (
            getattr(source, "work_site_id", None)
            or getattr(row, "work_site_id", None)
            or getattr(record, "work_site_id", None)
            or getattr(getattr(record, "work_site_evidence", None), "site_id", None)
        )
        work_site_name = (
            getattr(source, "work_site_name", None)
            or getattr(row, "work_site_name", None)
            or record.site_name
        )
        scopes.append(
            {
                "position": position,
                "project_id": project_id,
                "project_name": project_name,
                "sub_project_id": sub_project_id,
                "sub_project_name": sub_project_name,
                "work_site_id": work_site_id,
                "work_site_name": work_site_name,
                "quotation_number": getattr(source, "quotation_number", None),
                "items": wrappers_for_scope,
                "data_rows": rows_by_scope.get(position, []),
            }
        )
    return scopes


def parse_saved_table_rows(form: Any, valid_scopes: set[int], *, installation: bool) -> tuple[list[dict], str]:
    """Parse the editable browser tables that already belong to saved Sites."""
    scope_values = [str(value or "").strip() for value in form.getlist("existing_data_scope_position")]
    item_values = [str(value or "").strip() for value in form.getlist("existing_data_item_name")]
    field_names = (
        "model", "serial_number", "imei", "iccid", "sim_type", "remarks"
    ) if installation else ("quantity", "notes")
    columns = {
        name: [str(value or "").strip() for value in form.getlist(f"existing_data_{name}")]
        for name in field_names
    }
    count = max(len(scope_values), len(item_values), *(len(values) for values in columns.values()), 0)
    scope_values.extend([""] * (count - len(scope_values)))
    item_values.extend([""] * (count - len(item_values)))
    for values in columns.values():
        values.extend([""] * (count - len(values)))
    positions: dict[int, int] = defaultdict(int)
    rows: list[dict] = []
    for index in range(count):
        item_name = item_values[index]
        values = {name: columns[name][index] for name in field_names}
        meaningful = any(value for name, value in values.items() if not (name == "quantity" and value == "1"))
        if not item_name and not meaningful:
            continue
        try:
            scope_position = int(scope_values[index])
        except ValueError:
            return [], f"Table row {index + 1} is not assigned to a valid Site."
        if scope_position not in valid_scopes:
            return [], f"Table row {index + 1} belongs to a removed or invalid Site."
        if not item_name or len(item_name) > MAX_ITEM_LENGTH:
            return [], f"Enter a valid item name in table row {index + 1}."
        if positions[scope_position] >= MAX_DATA_ROWS_PER_SITE:
            return [], f"A Site table can contain at most {MAX_DATA_ROWS_PER_SITE} rows."
        row = {
            "scope_position": scope_position,
            "position": positions[scope_position],
            "item_name": item_name,
        }
        positions[scope_position] += 1
        if installation:
            if any(len(values[name]) > MAX_IDENTIFIER_LENGTH for name in ("model", "serial_number", "imei", "iccid")):
                return [], f"An identifier in table row {index + 1} is too long."
            sim_type = values["sim_type"]
            if sim_type and sim_type.casefold() not in SIM_TYPES:
                return [], f"Choose Zain, Mobily or STC in table row {index + 1}."
            if len(values["remarks"]) > MAX_NOTES_LENGTH:
                return [], f"The notes in table row {index + 1} are too long."
            row.update(
                model=values["model"] or None,
                serial_number=values["serial_number"] or None,
                imei=values["imei"] or None,
                iccid=values["iccid"] or None,
                sim_type=SIM_TYPES.get(sim_type.casefold()) if sim_type else None,
                remarks=values["remarks"] or None,
            )
        else:
            try:
                quantity = int(values["quantity"] or "1")
            except ValueError:
                quantity = 0
            if quantity < 1 or quantity > 999999:
                return [], f"Enter a valid quantity in table row {index + 1}."
            if len(values["notes"]) > MAX_NOTES_LENGTH:
                return [], f"The notes in table row {index + 1} are too long."
            row.update(quantity=quantity, notes=values["notes"] or None)
        rows.append(row)
    return rows, ""


def appended_scope_targets(
    form: Any, scope_count: int, existing_positions: set[int]
) -> dict[int, int]:
    """Map submitted creation-form scope indexes to existing or newly allocated Sites."""
    requested = [str(value or "").strip() for value in form.getlist("append_scope_position")]
    requested.extend([""] * max(0, scope_count - len(requested)))
    next_position = max(existing_positions, default=-1) + 1
    targets: dict[int, int] = {}
    for index in range(scope_count):
        try:
            candidate = int(requested[index])
        except (TypeError, ValueError):
            candidate = -1
        if candidate in existing_positions:
            targets[index] = candidate
        else:
            targets[index] = next_position
            next_position += 1
    return targets


def sync_legacy_photo_mirror(record: Any, photo_model: Any) -> None:
    """Keep the legacy parent-level photo mirror aligned without duplicate inserts.

    Grouped records store authoritative photos on each work item. Older views
    still read ``record.photos`` as a mirror of the first remaining item. Reusing
    matching legacy rows is important because each legacy storage key is unique;
    clearing and recreating the collection in one flush can insert the replacement
    before PostgreSQL deletes the old row.
    """
    desired = list(record.work_items[0].photos) if record.work_items else []
    desired_keys = {photo.storage_key for photo in desired}
    existing_by_key = {photo.storage_key: photo for photo in record.photos}

    for legacy in list(record.photos):
        if legacy.storage_key not in desired_keys:
            record.photos.remove(legacy)

    for position, source in enumerate(desired):
        legacy = existing_by_key.get(source.storage_key)
        if legacy is None:
            legacy = photo_model(
                storage_key=source.storage_key,
                thumbnail_key=source.thumbnail_key,
                original_filename=source.original_filename,
                content_type=source.content_type,
                file_size=source.file_size,
                description=source.description,
                is_issue_found=bool(getattr(source, "is_issue_found", False)),
                position=position,
                uploaded_at=source.uploaded_at,
            )
            record.photos.append(legacy)
            continue
        legacy.thumbnail_key = source.thumbnail_key
        legacy.original_filename = source.original_filename
        legacy.content_type = source.content_type
        legacy.file_size = source.file_size
        legacy.description = source.description
        legacy.is_issue_found = bool(getattr(source, "is_issue_found", False))
        legacy.position = position
        legacy.uploaded_at = source.uploaded_at
