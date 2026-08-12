"""Validation and persistence helpers for browser-entered Site data tables."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from .entry_scopes import EntryScope


MAX_DATA_ROWS_PER_SITE = 100
MAX_ITEM_LENGTH = 160
MAX_IDENTIFIER_LENGTH = 160
MAX_NOTES_LENGTH = 5000
SIM_TYPES = {"zain": "Zain", "mobily": "Mobily", "stc": "STC"}


def _values(form: Any, name: str, count: int) -> list[str]:
    values = [str(value or "").strip() for value in form.getlist(name)]
    values.extend([""] * (count - len(values)))
    return values[:count]


def parse_entry_data_rows(
    form: Any,
    scopes: list[EntryScope],
    *,
    installation: bool,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Parse independent browser-table rows and bind each to a validated Site scope."""
    raw_scopes = [str(value or "").strip() for value in form.getlist("data_scope_index")]
    item_names = [str(value or "").strip() for value in form.getlist("data_item_name")]
    field_names = (
        "data_model",
        "data_serial_number",
        "data_imei",
        "data_iccid",
        "data_sim_type",
        "data_remarks",
    ) if installation else ("data_quantity", "data_notes")
    count = max(len(raw_scopes), len(item_names), *(len(form.getlist(name)) for name in field_names), 0)
    raw_scopes.extend([""] * (count - len(raw_scopes)))
    item_names.extend([""] * (count - len(item_names)))
    columns = {name: _values(form, name, count) for name in field_names}
    rows: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    per_scope: defaultdict[int, int] = defaultdict(int)

    for index in range(count):
        item_name = item_names[index]
        values = {name.removeprefix("data_"): columns[name][index] for name in field_names}
        meaningful = any(
            value
            for key, value in values.items()
            if not (not installation and key == "quantity" and value == "1")
        )
        if not item_name and not meaningful:
            continue
        try:
            scope_index = int(raw_scopes[index])
        except (TypeError, ValueError):
            scope_index = -1
        if scope_index < 0 or scope_index >= len(scopes):
            errors[f"data_row_{index}"] = "This row is not assigned to a valid Site."
            continue
        if not item_name:
            errors[f"data_item_name_{index}"] = "Enter the item name."
        elif len(item_name) > MAX_ITEM_LENGTH:
            errors[f"data_item_name_{index}"] = f"Keep the item name under {MAX_ITEM_LENGTH} characters."
        if per_scope[scope_index] >= MAX_DATA_ROWS_PER_SITE:
            errors[f"data_row_{index}"] = f"Add at most {MAX_DATA_ROWS_PER_SITE} rows to one Site."
        per_scope[scope_index] += 1

        row: dict[str, Any] = {
            "scope_index": scope_index,
            "position": per_scope[scope_index] - 1,
            "item_name": item_name,
        }
        if installation:
            for field in ("model", "serial_number", "imei", "iccid"):
                if len(values[field]) > MAX_IDENTIFIER_LENGTH:
                    errors[f"data_{field}_{index}"] = (
                        f"Keep this value under {MAX_IDENTIFIER_LENGTH} characters."
                    )
            sim_type = values["sim_type"]
            if sim_type and sim_type.casefold() not in SIM_TYPES:
                errors[f"data_sim_type_{index}"] = "Choose Zain, Mobily or STC."
            if len(values["remarks"]) > MAX_NOTES_LENGTH:
                errors[f"data_remarks_{index}"] = (
                    f"Keep notes under {MAX_NOTES_LENGTH} characters."
                )
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
                errors[f"data_quantity_{index}"] = "Enter a quantity from 1 to 999999."
            if len(values["notes"]) > MAX_NOTES_LENGTH:
                errors[f"data_notes_{index}"] = (
                    f"Keep notes under {MAX_NOTES_LENGTH} characters."
                )
            row.update(quantity=quantity, notes=values["notes"] or None)
        rows.append(row)
    return rows, errors


def rows_for_scope(rows: Iterable[dict[str, Any]], scope_index: int) -> list[dict[str, Any]]:
    return [row for row in rows if row["scope_index"] == scope_index]


def row_model_values(row: dict[str, Any], scope: EntryScope) -> dict[str, Any]:
    return {
        **{key: value for key, value in row.items() if key != "scope_index"},
        "scope_position": scope.index,
        "project_id": scope.project.id,
        "project_name": scope.project.name,
        "sub_project_id": scope.sub_project.id if scope.sub_project else None,
        "sub_project_name": scope.sub_project.name if scope.sub_project else "General",
        "work_site_id": scope.site.id,
        "work_site_name": scope.site.name,
    }


def serialize_data_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "scope_index": row.scope_position,
                "position": row.position,
                "project_id": row.project_id,
                "project_name": row.project_name,
                "sub_project_id": row.sub_project_id,
                "sub_project_name": row.sub_project_name,
                "work_site_id": row.work_site_id,
                "work_site_name": row.work_site_name,
                "item_name": row.item_name,
                "model": getattr(row, "model", None),
                "serial_number": getattr(row, "serial_number", None),
                "imei": getattr(row, "imei", None),
                "iccid": getattr(row, "iccid", None),
                "sim_type": getattr(row, "sim_type", None),
                "remarks": getattr(row, "remarks", None),
                "quantity": getattr(row, "quantity", None),
                "notes": getattr(row, "notes", None),
            }
        )
    return result
