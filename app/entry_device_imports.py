"""Shared Excel import endpoints and signed-preview helpers for Data Entry."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import UploadFile

from .config import settings
from .database import get_db
from .deps import require_record_submitter
from .device_import import build_device_template, validate_device_workbook
from .helpers import entity_id, localized_json
from .models import DeviceCatalog, InstalledDevice, PricingItem, Site, SubProject, User, WorkSite
from .project_hierarchy import resolve_entry_sub_project
from .security import csrf_valid


router = APIRouter()
IMPORT_TOKEN_MAX_AGE = 2 * 60 * 60
ENTRY_LABELS = {
    "installation": "Installation",
    "maintenance": "Maintenance",
    "preventive-maintenance": "Preventive Maintenance",
}


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="service-entry-device-import-v1")


def available_items(db: Session) -> list[PricingItem]:
    return list(
        db.scalars(
            select(PricingItem)
            .options(selectinload(PricingItem.legacy_device))
            .where(
                PricingItem.is_active.is_(True),
                PricingItem.service_enabled.is_(True),
                PricingItem.device_catalog_id.is_not(None),
            )
            .order_by(PricingItem.name, PricingItem.model)
        )
    )


def _active_sites(db: Session) -> list[WorkSite]:
    return list(
        db.scalars(
            select(WorkSite)
            .where(WorkSite.is_active.is_(True))
            .order_by(WorkSite.name)
        )
    )


def _active_main_project_names(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(Site.name)
            .where(Site.is_active.is_(True))
            .order_by(Site.name)
        )
    )


def _active_sub_project_names(db: Session) -> list[str]:
    return list(
        db.scalars(
            select(SubProject.name)
            .where(SubProject.is_active.is_(True))
            .order_by(SubProject.name)
        )
    )


def _kind(value: str) -> str:
    if value not in ENTRY_LABELS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Data Entry type not found.")
    return value


@router.get("/data-entry/{entry_kind}/device-template")
def device_template(
    entry_kind: str,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    kind = _kind(entry_kind)
    content = build_device_template(
        available_items(db),
        _active_sites(db),
        entry_label=ENTRY_LABELS[kind],
        main_project_names=_active_main_project_names(db),
        sub_project_names=_active_sub_project_names(db),
    )
    filename = f"{kind}-device-data-template.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/data-entry/{entry_kind}/device-import-preview")
async def device_import_preview(
    entry_kind: str,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    kind = _kind(entry_kind)
    form = await request.form()
    if not csrf_valid(request, form.get("csrf_token")):
        return localized_json(
            request,
            {"ok": False, "errors": ["Your session expired. Reload the page and try again."]},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    project_id = entity_id(str(form.get("project_id") or ""))
    sub_project_raw = str(form.get("sub_project_id") or "").strip()
    site_id = entity_id(str(form.get("work_site_id") or ""))
    project = db.get(Site, project_id) if project_id else None
    site = db.get(WorkSite, site_id) if site_id else None
    errors: list[str] = []
    if project is None or not project.is_active:
        errors.append("Select an active Main Project before previewing the Excel file.")
    if site is None or not site.is_active:
        errors.append("Select an active Site before previewing the Excel file.")
    sub_project, sub_error = resolve_entry_sub_project(db, project, site, sub_project_raw)
    if sub_error or sub_project is None:
        errors.append(sub_error or "Select a Sub Project before previewing the Excel file.")
    upload = form.get("device_file")
    if not isinstance(upload, UploadFile) or not upload.filename:
        errors.append("Choose a completed Excel .xlsx file.")
    if errors:
        return localized_json(
            request,
            {"ok": False, "errors": errors},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    assert project and site and sub_project and isinstance(upload, UploadFile)
    rows, structural_errors = validate_device_workbook(
        await upload.read(),
        filename=upload.filename or "",
        db=db,
        items=available_items(db),
        project_id=project.id,
        site=site,
        entry_kind=kind,
    )
    row_messages = [
        f"Row {row.row_number}: {message}"
        for row in rows
        for message in row.errors
    ]
    preview_errors = [*structural_errors, *row_messages]
    row_errors = bool(row_messages)
    token = ""
    if rows and not structural_errors and not row_errors:
        token = _serializer().dumps(
            {
                "entry_kind": kind,
                "project_id": project.id,
                "sub_project_id": sub_project.id,
                "site_id": site.id,
                "rows": [row.token_payload() for row in rows],
            }
        )
    return localized_json(
        request,
        {
            "ok": bool(token),
            "token": token,
            "errors": preview_errors,
            "has_asset_conflicts": any(row.asset_conflicts for row in rows),
            "rows": [
                {
                    **row.token_payload(),
                    "errors": row.errors,
                    "warnings": row.warnings,
                }
                for row in rows
            ],
        },
        status_code=(
            status.HTTP_200_OK
            if token
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        ),
    )


def load_entry_import(
    token: str,
    *,
    entry_kind: str,
    project_id: int,
    sub_project_id: int | None,
    site_id: int,
) -> tuple[list[dict[str, Any]], str]:
    if not token:
        return [], ""
    try:
        payload = _serializer().loads(token, max_age=IMPORT_TOKEN_MAX_AGE)
    except SignatureExpired:
        return [], "The Excel preview expired. Upload the completed template again."
    except BadSignature:
        return [], "The Excel preview is invalid. Upload the completed template again."
    expected = (entry_kind, project_id, sub_project_id, site_id)
    actual = (
        payload.get("entry_kind"),
        payload.get("project_id"),
        payload.get("sub_project_id"),
        payload.get("site_id"),
    )
    rows = payload.get("rows")
    if actual != expected or not isinstance(rows, list):
        return [], "The selected Main Project, Sub Project or Site changed after Excel preview. Preview the file again."
    return rows, ""


def validate_current_import_rows(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    entry_kind: str,
    project_id: int,
    site_id: int,
) -> str:
    for row in rows:
        item = db.get(PricingItem, row.get("pricing_item_id"))
        device = db.get(DeviceCatalog, row.get("device_id"))
        if (
            item is None
            or device is None
            or not item.is_active
            or not item.service_enabled
            or not device.is_active
            or item.device_catalog_id != device.id
        ):
            return "One Excel item is no longer available. Download and preview a new template."
        matched_id = row.get("installed_device_id")
        if entry_kind == "installation":
            identifier_checks = [
                func.lower(InstalledDevice.serial_number)
                == str(row.get("serial_number") or "").casefold()
            ]
            if row.get("imei"):
                identifier_checks.append(InstalledDevice.imei == row["imei"])
            if row.get("iccid"):
                identifier_checks.append(InstalledDevice.iccid == row["iccid"])
            existing = db.scalar(
                select(InstalledDevice).where(
                    or_(*identifier_checks)
                )
            )
            if existing:
                return "One Excel device identifier was registered after preview. Preview the file again."
        elif matched_id:
            matched = db.get(InstalledDevice, matched_id)
            if (
                matched is None
                or not matched.is_active
                or matched.site_id != project_id
                or matched.effective_work_site_id != site_id
                or matched.device_id != device.id
                or (matched.serial_number or "").casefold()
                != str(row.get("serial_number") or "").casefold()
            ):
                return "One matching Installed Asset changed after preview. Preview the file again."
    return ""


def apply_asset_metadata(
    db: Session,
    row: dict[str, Any],
    *,
    allow_overwrite: bool,
) -> InstalledDevice | None:
    asset_id = row.get("installed_device_id")
    asset = db.get(InstalledDevice, asset_id) if asset_id else None
    if asset is None:
        return None
    for attribute in ("imei", "iccid", "sim_type", "remarks"):
        incoming = row.get(attribute)
        if incoming and (not getattr(asset, attribute) or allow_overwrite):
            setattr(asset, attribute, incoming)
    return asset
