"""New Installations: submit immutable evidence, list it, and review it."""
from __future__ import annotations

import logging

from datetime import datetime as dt, time as dt_time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import UploadFile

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin, require_record_submitter
from ..helpers import (
    entity_id,
    flash,
    localized_json,
    next_installation_record_number,
    paginate,
    parse_date,
    render,
    to_utc_from_display,
)
from ..entry_device_imports import load_entry_import, validate_current_import_rows
from ..entry_data_tables import parse_entry_data_rows, row_model_values, rows_for_scope
from ..entry_scopes import apply_scope_snapshot, EntryScope, item_scope_indexes, validate_entry_scopes
from ..models import (
    DeviceCatalog,
    EvidencePhotoStage,
    InstallationParticipant,
    InstallationDataRow,
    InstallationItemPhoto,
    InstallationPhoto,
    InstallationRecord,
    InstallationRecordAdditionalDevice,
    InstallationRecordItem,
    InstallationRecordSite,
    GeneralMaintenanceItem,
    InstalledDevice,
    InstalledDeviceSite,
    MaintenanceResult,
    MaintenanceRecordAdditionalDevice,
    MaintenanceRecordDevice,
    MaintenanceRecordItem,
    PricingItem,
    ServiceReportRecord,
    ServiceType,
    Site,
    SubProject,
    User,
    UserRole,
    WorkSite,
    utcnow,
)
from ..participant_selection import (
    selected_ids_for_names,
    technical_user_choices,
    validate_participant_ids,
)
from ..project_hierarchy import active_project_hierarchy, hierarchy_json, resolve_entry_sub_project
from ..quotation_references import quotation_choices, resolve_quotation_reference
from ..record_mutations import add_revision, changed, revisions_for
from ..record_photo_edits import (
    existing_photo_descriptions,
    grouped_photos,
    new_photo_descriptions,
)
from ..saved_report_deletion import delete_linked_reports, linked_reports
from ..security import (
    consume_form_token,
    csrf_valid,
    form_token_available,
    issue_form_token,
)
from ..uploads import UploadError, delete_stored, resolve_storage_path, store_image

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 5000
MAX_EQUIPMENT_LENGTH = 160
MAX_PARTICIPANTS = 20
MAX_DEVICES_PER_RECORD = 20


def _is_ajax(request: Request) -> bool:
    return request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"


def _active_sites(db: Session) -> list[Site]:
    return list(db.scalars(select(Site).where(Site.is_active.is_(True)).order_by(Site.name)))


def _active_services(db: Session) -> list[ServiceType]:
    return list(
        db.scalars(
            select(ServiceType)
            .where(ServiceType.is_active.is_(True))
            .order_by(ServiceType.name)
        )
    )


def _active_devices(db: Session) -> list[PricingItem]:
    return list(
        db.scalars(
            select(PricingItem)
            .options(
                selectinload(PricingItem.legacy_device),
                selectinload(PricingItem.category),
            )
            .where(
                PricingItem.is_active.is_(True),
                PricingItem.service_enabled.is_(True),
                PricingItem.device_catalog_id.is_not(None),
            )
            .order_by(PricingItem.name, PricingItem.model)
        )
    )


def _active_work_sites(db: Session) -> list[WorkSite]:
    return list(
        db.scalars(
            select(WorkSite)
            .where(WorkSite.is_active.is_(True))
            .order_by(WorkSite.name)
        )
    )


def _form_context(
    request: Request,
    db: Session,
    form: dict | None = None,
    errors: dict | None = None,
    form_token: str | None = None,
) -> dict:
    projects = active_project_hierarchy(db)
    return {
        "active_nav": "installation_submit",
        "projects": projects,
        "project_hierarchy": hierarchy_json(projects),
        "work_sites": _active_work_sites(db),
        "services": _active_services(db),
        "devices": _active_devices(db),
        "quotations": quotation_choices(db),
        "form": form or {"participants": [], "devices": [{}]},
        "technical_users": technical_user_choices(db, request.state.user),
        "selected_participant_ids": [
            str(value) for value in (form or {}).get("participants", [])
        ],
        "participant_error": (errors or {}).get("participant_ids", ""),
        "errors": errors or {},
        "form_token": form_token or issue_form_token(request),
    }


@router.get("/installations")
def installations_root(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    """The Installations module opens directly on its data-entry form."""
    return render(request, "installation_entry.html", _form_context(request, db))


@router.get("/installations/submit")
def submit_form(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    return render(request, "installation_entry.html", _form_context(request, db))


@router.get("/service-items/{item_id}/image")
def service_item_image(
    item_id: int,
    size: str = "original",
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    item = db.get(PricingItem, item_id)
    if (
        item is None
        or not item.is_active
        or not item.service_enabled
        or not item.image_storage_key
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item image not found.")
    key = (
        item.image_thumbnail_key
        if size == "thumb" and item.image_thumbnail_key
        else item.image_storage_key
    )
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item image not found.")
    return FileResponse(
        path,
        media_type=(
            "image/jpeg"
            if key == item.image_thumbnail_key
            else item.image_content_type
        ),
        headers={"Cache-Control": "private, max-age=600"},
    )


def _new_installation_record(
    db: Session,
    *,
    scope: EntryScope,
    entries: list[dict],
    imported_rows: list[dict],
    stored_by_item: list[list],
    user: User,
    participant_ids: list[str],
    participants: list[str],
    now: dt,
    record_number: str | None = None,
) -> InstallationRecord:
    first = entries[0]
    first_import = imported_rows[0] if imported_rows else {}
    first_service: ServiceType = first["service"]
    first_device: DeviceCatalog = first["device"]
    project, sub_project, work_site, quotation = (
        scope.project,
        scope.sub_project,
        scope.site,
        scope.quotation,
    )
    record = InstallationRecord(
        record_number=record_number or next_installation_record_number(db, now),
        site_id=project.id,
        sub_project_id=sub_project.id if sub_project else None,
        sub_project_name=sub_project.name if sub_project else "General",
        service_type_id=first_service.id,
        submitted_by_id=user.id,
        quotation_id=quotation.id,
        quotation_number=quotation.quotation_number,
        site_name=work_site.name,
        customer_name=project.name,
        site_address=project.address,
        service_name=first_service.name,
        team_leader_name=user.full_name,
        equipment_model=first_device.display_label,
        serial_number=first["serial_number"],
        warranty_start=first["warranty_date"],
        result=first["result_value"],
        notes=first["notes"],
        handover_notes=first["handover_notes"] or None,
        submitted_at=now,
        created_at=now,
    )
    record.participants = [
        InstallationParticipant(user_id=int(user_id), name=name)
        for user_id, name in zip(participant_ids, participants)
    ]
    record.photos = [
        InstallationPhoto(
            storage_key=stored.storage_key,
            thumbnail_key=stored.thumbnail_key,
            original_filename=stored.original_filename,
            content_type=stored.content_type,
            file_size=stored.file_size,
            description=description or None,
            position=position,
            uploaded_at=now,
        )
        for _, stored, description, position in stored_by_item[0]
    ]
    installed_devices: list[InstalledDevice] = []
    for index, entry in enumerate(entries):
        item_device: DeviceCatalog = entry["device"]
        imported = imported_rows[index] if imported_rows else {}
        installed = InstalledDevice(
            site_id=project.id,
            sub_project_id=sub_project.id if sub_project else None,
            sub_project_name=sub_project.name if sub_project else "General",
            device_id=item_device.id,
            customer_name=project.name,
            site_name=work_site.name,
            device_name=item_device.name,
            manufacturer=item_device.manufacturer,
            device_model=item_device.model,
            serial_number=entry["serial_number"],
            imei=imported.get("imei"),
            iccid=imported.get("iccid"),
            sim_type=imported.get("sim_type"),
            phone_number=imported.get("phone_number"),
            remarks=imported.get("remarks"),
            warranty_start=entry["warranty_date"],
            installed_at=now,
        )
        installed.work_site_evidence = InstalledDeviceSite(site_id=work_site.id, site_name=work_site.name)
        installed_devices.append(installed)
    record.installed_device = installed_devices[0]
    record.work_site_evidence = InstallationRecordSite(site_id=work_site.id, site_name=work_site.name)
    for index, installed in enumerate(installed_devices[1:], 1):
        service: ServiceType = entries[index]["service"]
        record.additional_devices.append(
            InstallationRecordAdditionalDevice(
                installed_device=installed,
                service_type_id=service.id,
                service_name=service.name,
            )
        )
    for index, (entry, installed) in enumerate(zip(entries, installed_devices)):
        item_device: DeviceCatalog = entry["device"]
        service: ServiceType = entry["service"]
        imported = imported_rows[index] if imported_rows else {}
        item = InstallationRecordItem(
            installed_device=installed,
            service_type_id=service.id,
            position=index,
            service_name=service.name,
            device_name=item_device.name,
            manufacturer=item_device.manufacturer,
            device_model=item_device.model,
            serial_number=entry["serial_number"],
            imei=imported.get("imei"),
            iccid=imported.get("iccid"),
            sim_type=imported.get("sim_type"),
            phone_number=imported.get("phone_number"),
            location_name=imported.get("site") or work_site.name,
            remarks=imported.get("remarks"),
            imported_from_excel=bool(imported_rows),
            warranty_start=entry["warranty_date"],
            result=entry["result_value"],
            notes=entry["notes"],
            handover_notes=entry["handover_notes"] or None,
        )
        item.photos = [
            InstallationItemPhoto(
                storage_key=stored.storage_key,
                thumbnail_key=stored.thumbnail_key,
                original_filename=stored.original_filename,
                content_type=stored.content_type,
                file_size=stored.file_size,
                stage=stage,
                description=description or None,
                position=position,
                uploaded_at=now,
            )
            for stage, stored, description, position in stored_by_item[index]
        ]
        record.work_items.append(item)
    return record


@router.post("/installations/submit")
async def submit_record(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    form = await request.form()
    errors: dict[str, str] = {}

    project_id_raw = str(form.get("project_id") or form.get("site_id") or "").strip()
    sub_project_id_raw = str(form.get("sub_project_id") or "").strip()
    device_import_token = str(form.get("device_import_token") or "").strip()
    quotation_number_raw = str(form.get("quotation_number") or "").strip()
    work_site_id_raw = str(form.get("work_site_id") or "").strip()
    service_ids = [str(value).strip() for value in form.getlist("service_type_id")]
    device_ids = [str(value).strip() for value in form.getlist("device_id")]
    serial_numbers = [str(value).strip() for value in form.getlist("serial_number")]
    warranty_starts = [str(value).strip() for value in form.getlist("warranty_start")]
    notes_values = [str(value).strip() for value in form.getlist("notes")]
    handover_values = [str(value).strip() for value in form.getlist("handover_notes")]
    participants, participant_ids, participant_error = validate_participant_ids(
        db,
        user,
        form.getlist("participant_ids"),
        maximum=MAX_PARTICIPANTS,
    )
    if participant_error:
        errors["participant_ids"] = participant_error

    if not csrf_valid(request, form.get("csrf_token")):
        errors["form"] = "Your session expired. Reload the page and submit again."
    if not form_token_available(request, form.get("form_token")):
        errors["form"] = "This installation record was already submitted. Check your records list."

    scopes, scope_errors = validate_entry_scopes(form, db)
    errors.update(scope_errors)
    data_rows, data_row_errors = parse_entry_data_rows(
        form, scopes, installation=True
    )
    errors.update(data_row_errors)
    project = scopes[0].project if scopes else None
    sub_project = scopes[0].sub_project if scopes else None
    work_site = scopes[0].site if scopes else None
    quotation = scopes[0].quotation if scopes else None

    item_count = max(
        len(service_ids),
        len(device_ids),
        len(serial_numbers),
        len(warranty_starts),
        len(notes_values),
        1,
    )
    if item_count > MAX_DEVICES_PER_RECORD:
        errors["form"] = f"Add at most {MAX_DEVICES_PER_RECORD} devices to one record."
        item_count = MAX_DEVICES_PER_RECORD
    for values in (
        service_ids,
        device_ids,
        serial_numbers,
        warranty_starts,
        notes_values,
        handover_values,
    ):
        values.extend([""] * (item_count - len(values)))
    scope_count = max(len(form.getlist("project_id")), 1)
    item_scopes, item_scope_errors = item_scope_indexes(form, item_count, scope_count)
    errors.update(item_scope_errors)

    device_entries: list[dict] = []
    seen_serials: set[str] = set()
    for index in range(item_count):
        service_raw = service_ids[index]
        device_raw = device_ids[index]
        serial_number = serial_numbers[index]
        warranty_raw = warranty_starts[index]
        result_raw = (
            str(form.get(f"result_{index}") or form.get("result") or "").strip()
            if index == 0
            else str(form.get(f"result_{index}") or "").strip()
        )
        notes = notes_values[index]
        handover_notes = handover_values[index]
        suffix = f"_{index}"

        service_id = entity_id(service_raw)
        service = db.get(ServiceType, service_id) if service_id is not None else None
        if not service_raw:
            errors[f"service_type_id{suffix}"] = "Select the installation type."
        elif service is None:
            errors[f"service_type_id{suffix}"] = "That service no longer exists."
        elif not service.is_active:
            errors[f"service_type_id{suffix}"] = "That service is deactivated."

        item_id = entity_id(device_raw)
        item = db.get(PricingItem, item_id) if item_id is not None else None
        device = item.legacy_device if item is not None else None
        if not device_raw:
            errors[f"device_id{suffix}"] = "Select the device being installed."
        elif item is None or device is None:
            errors[f"device_id{suffix}"] = "That item no longer exists."
        elif not item.is_active or not item.service_enabled or not device.is_active:
            errors[f"device_id{suffix}"] = "That item is unavailable for service records."

        serial_key = serial_number.lower()
        if serial_number and len(serial_number) > MAX_EQUIPMENT_LENGTH:
            errors[f"serial_number{suffix}"] = (
                f"Keep the serial number under {MAX_EQUIPMENT_LENGTH} characters."
            )
        elif serial_number and serial_key in seen_serials:
            errors[f"serial_number{suffix}"] = "Serial numbers must be unique in this record."
        elif serial_number and db.scalar(
            select(InstalledDevice).where(
                func.lower(InstalledDevice.serial_number) == serial_key
            )
        ):
            errors[f"serial_number{suffix}"] = "That serial number is already registered."
        if serial_number:
            seen_serials.add(serial_key)

        warranty_start = parse_date(warranty_raw)
        if warranty_raw and warranty_start is None:
            errors[f"warranty_start{suffix}"] = "Enter a valid warranty start date."

        result: MaintenanceResult | None = None
        try:
            result = MaintenanceResult(result_raw)
        except ValueError:
            errors[f"result{suffix}"] = "Select the installation result."

        if len(notes) > MAX_TEXT_LENGTH:
            errors[f"notes{suffix}"] = f"Keep notes under {MAX_TEXT_LENGTH} characters."
        if len(handover_notes) > MAX_TEXT_LENGTH:
            errors[f"handover_notes{suffix}"] = (
                f"Keep handover notes under {MAX_TEXT_LENGTH} characters."
            )

        device_entries.append(
            {
                "service_type_id": service_raw,
                "device_id": device_raw,
                "serial_number": serial_number or None,
                "warranty_start": warranty_raw,
                "result": result_raw,
                "notes": notes,
                "handover_notes": handover_notes,
                "service": service,
                "device": device,
                "pricing_item": item,
                "warranty_date": warranty_start,
                "result_value": result,
                "scope_index": item_scopes[index],
            }
        )

    imported_by_item: list[dict] = [{} for _ in range(item_count)]
    device_import_tokens = [str(value or "").strip() for value in form.getlist("device_import_token")]
    device_import_tokens.extend([""] * (scope_count - len(device_import_tokens)))
    for scope in scopes:
        token = device_import_tokens[scope.index]
        if not token:
            continue
        scope_rows, import_error = load_entry_import(
            token,
            entry_kind="installation",
            project_id=scope.project.id,
            sub_project_id=scope.sub_project.id if scope.sub_project else None,
            site_id=scope.site.id,
        )
        error_key = "device_import_token" if scope.index == 0 else f"device_import_token_scope_{scope.index}"
        if import_error:
            errors[error_key] = import_error
            continue
        current_error = validate_current_import_rows(
            db, scope_rows, entry_kind="installation", project_id=scope.project.id, site_id=scope.site.id
        )
        indexes = [index for index, entry in enumerate(device_entries) if entry["scope_index"] == scope.index]
        if current_error:
            errors[error_key] = current_error
        elif len(scope_rows) != len(indexes):
            errors[error_key] = "The Excel preview and installation item count do not match. Preview the file again."
        else:
            for index, imported in zip(indexes, scope_rows):
                entry = device_entries[index]
                imported_by_item[index] = imported
                if (
                    entry["pricing_item"] is None
                    or entry["pricing_item"].id != imported.get("pricing_item_id")
                    or (
                        entry["serial_number"]
                        and entry["serial_number"].casefold()
                        != str(imported.get("serial_number") or "").casefold()
                    )
                ):
                    errors[f"device_id_{index}"] = "This item no longer matches the Excel preview. Preview the file again."
                elif not entry["serial_number"]:
                    entry["serial_number"] = str(imported.get("serial_number") or "").strip()
    device_import_token = device_import_tokens[0] if device_import_tokens else ""
    if any(key.startswith("device_import_token_scope_") for key in errors):
        errors.setdefault("form", "Review the Excel import in each Site section.")

    uploads_by_item: list[list[tuple[EvidencePhotoStage, UploadFile, str, int]]] = []
    for index in range(item_count):
        before_uploads = [
            upload for upload in form.getlist(f"before_photos_{index}")
            if isinstance(upload, UploadFile) and upload.filename
        ]
        after_uploads = [
            upload for upload in form.getlist(f"after_photos_{index}")
            if isinstance(upload, UploadFile) and upload.filename
        ]
        legacy_uploads = [
            upload
            for upload in (
                form.getlist(f"photos_{index}")
                or (form.getlist("photos") if index == 0 else [])
            )
            if isinstance(upload, UploadFile) and upload.filename
        ]
        before_descriptions = [
            str(value).strip()
            for value in form.getlist(f"before_photo_descriptions_{index}")
        ]
        after_descriptions = [
            str(value).strip()
            for value in form.getlist(f"after_photo_descriptions_{index}")
        ]
        before_descriptions.extend([""] * (len(before_uploads) - len(before_descriptions)))
        after_descriptions.extend([""] * (len(after_uploads) - len(after_descriptions)))
        before_descriptions = before_descriptions[: len(before_uploads)]
        after_descriptions = after_descriptions[: len(after_uploads)]
        uploads = [
            *((EvidencePhotoStage.BEFORE, upload, before_descriptions[position], position) for position, upload in enumerate(before_uploads)),
            *((EvidencePhotoStage.AFTER, upload, after_descriptions[position], position) for position, upload in enumerate(after_uploads)),
            *((EvidencePhotoStage.LEGACY, upload, "", position) for position, upload in enumerate(legacy_uploads)),
        ]
        uploads_by_item.append(uploads)
        if not uploads:
            errors[f"photos_{index}"] = "Attach at least one installation photo."
        elif len(before_uploads) > settings.max_photos_per_record:
            errors[f"before_photos_{index}"] = "Attach at most 10 before photos."
        elif len(after_uploads) > settings.max_photos_per_record:
            errors[f"after_photos_{index}"] = "Attach at most 10 after photos."
        elif len(legacy_uploads) > settings.max_photos_per_record:
            errors[f"photos_{index}"] = "Attach at most 10 photos."
        elif any(len(description) > MAX_TEXT_LENGTH for description in before_descriptions + after_descriptions):
            errors[f"photos_{index}"] = f"Keep each photo description under {MAX_TEXT_LENGTH} characters."

    stored_by_item: list[list] = [[] for _ in range(item_count)]
    if not errors:
        for index, uploads in enumerate(uploads_by_item):
            for stage, upload, description, position in uploads:
                data = await upload.read()
                try:
                    stored_by_item[index].append(
                        (stage, store_image(upload.filename, data), description, position)
                    )
                except UploadError as exc:
                    errors[f"photos_{index}"] = str(exc)
                    break
            if errors:
                delete_stored(
                    *[
                        stored.storage_key
                        for item_stored in stored_by_item
                        for _, stored, _, _ in item_stored
                    ],
                    *[
                        stored.thumbnail_key
                        for item_stored in stored_by_item
                        for _, stored, _, _ in item_stored
                    ],
                )
                stored_by_item = [[] for _ in range(item_count)]
                break

    payload = {
        "project_id": project_id_raw,
        "sub_project_id": sub_project_id_raw,
        "device_import_token": device_import_token,
        "quotation_number": quotation_number_raw,
        "work_site_id": work_site_id_raw,
        "devices": [
            {
                key: entry[key]
                for key in (
                    "service_type_id",
                    "device_id",
                    "serial_number",
                    "warranty_start",
                    "result",
                    "notes",
                    "handover_notes",
                )
            }
            for entry in device_entries
        ],
        "participants": participant_ids,
    }

    if errors:
        fresh_token = issue_form_token(request)
        if _is_ajax(request):
            return localized_json(request,
                {"ok": False, "errors": errors, "form_token": fresh_token},
                status_code=422,
            )
        return render(
            request,
            "installation_entry.html",
            _form_context(request, db, payload, errors, fresh_token),
            status_code=422,
        )

    if not consume_form_token(request, form.get("form_token")):
        delete_stored(
            *[s.storage_key for group in stored_by_item for _, s, _, _ in group],
            *[s.thumbnail_key for group in stored_by_item for _, s, _, _ in group],
        )
        message = "This installation record was already submitted. Check your records list."
        fresh_token = issue_form_token(request)
        if _is_ajax(request):
            return localized_json(request,
                {
                    "ok": False,
                    "errors": {"form": message},
                    "form_token": fresh_token,
                },
                status_code=422,
            )
        return render(
            request,
            "installation_entry.html",
            _form_context(request, db, payload, {"form": message}, fresh_token),
            status_code=422,
        )

    assert project and work_site
    assert quotation
    assert all(
        entry["service"] and entry["device"] and entry["result_value"]
        for entry in device_entries
    )
    all_device_entries = device_entries
    all_stored_by_item = stored_by_item
    first_indexes = [
        index for index, entry in enumerate(all_device_entries)
        if entry["scope_index"] == 0
    ]
    device_entries = [all_device_entries[index] for index in first_indexes]
    stored_by_item = [all_stored_by_item[index] for index in first_indexes]
    imported_rows = (
        [imported_by_item[index] for index in first_indexes]
        if device_import_token
        else []
    )
    first = device_entries[0]
    first_import = imported_rows[0] if imported_rows else {}
    first_service: ServiceType = first["service"]
    first_device: DeviceCatalog = first["device"]
    now = utcnow()
    record = InstallationRecord(
        record_number=next_installation_record_number(db, now),
        site_id=project.id,
        sub_project_id=sub_project.id if sub_project else None,
        sub_project_name=sub_project.name if sub_project else "General",
        service_type_id=first_service.id,
        submitted_by_id=user.id,
        quotation_id=quotation.id,
        quotation_number=quotation.quotation_number,
        site_name=work_site.name,
        customer_name=project.name,
        site_address=project.address,
        service_name=first_service.name,
        team_leader_name=user.full_name,
        equipment_model=first_device.display_label,
        serial_number=first["serial_number"],
        warranty_start=first["warranty_date"],
        result=first["result_value"],
        notes=first["notes"],
        handover_notes=first["handover_notes"] or None,
        submitted_at=now,
        created_at=now,
    )
    record.participants = [
        InstallationParticipant(user_id=int(user_id), name=name)
        for user_id, name in zip(participant_ids, participants)
    ]
    record.photos = [
        InstallationPhoto(
            storage_key=s.storage_key,
            thumbnail_key=s.thumbnail_key,
            original_filename=s.original_filename,
            content_type=s.content_type,
            file_size=s.file_size,
            description=description or None,
            position=position,
            uploaded_at=now,
        )
        for _, s, description, position in stored_by_item[0]
    ]
    record.installed_device = InstalledDevice(
        site_id=project.id,
        sub_project_id=sub_project.id if sub_project else None,
        sub_project_name=sub_project.name if sub_project else "General",
        device_id=first_device.id,
        customer_name=project.name,
        site_name=work_site.name,
        device_name=first_device.name,
        manufacturer=first_device.manufacturer,
        device_model=first_device.model,
        serial_number=first["serial_number"],
        imei=first_import.get("imei"),
        iccid=first_import.get("iccid"),
        sim_type=first_import.get("sim_type"),
        phone_number=first_import.get("phone_number"),
        remarks=first_import.get("remarks"),
        warranty_start=first["warranty_date"],
        installed_at=now,
    )
    record.work_site_evidence = InstallationRecordSite(
        site_id=work_site.id,
        site_name=work_site.name,
    )
    record.installed_device.work_site_evidence = InstalledDeviceSite(
        site_id=work_site.id,
        site_name=work_site.name,
    )
    installed_devices_for_items = [record.installed_device]
    for item_index, entry in enumerate(device_entries[1:], 1):
        item_device: DeviceCatalog = entry["device"]
        item_service: ServiceType = entry["service"]
        installed = InstalledDevice(
            site_id=project.id,
            sub_project_id=sub_project.id if sub_project else None,
            sub_project_name=sub_project.name if sub_project else "General",
            device_id=item_device.id,
            customer_name=project.name,
            site_name=work_site.name,
            device_name=item_device.name,
            manufacturer=item_device.manufacturer,
            device_model=item_device.model,
            serial_number=entry["serial_number"],
            imei=(imported_rows[item_index].get("imei") if imported_rows else None),
            iccid=(imported_rows[item_index].get("iccid") if imported_rows else None),
            sim_type=(imported_rows[item_index].get("sim_type") if imported_rows else None),
            phone_number=(imported_rows[item_index].get("phone_number") if imported_rows else None),
            remarks=(imported_rows[item_index].get("remarks") if imported_rows else None),
            warranty_start=entry["warranty_date"],
            installed_at=now,
        )
        installed.work_site_evidence = InstalledDeviceSite(
            site_id=work_site.id,
            site_name=work_site.name,
        )
        record.additional_devices.append(
            InstallationRecordAdditionalDevice(
                installed_device=installed,
                service_type_id=item_service.id,
                service_name=item_service.name,
            )
        )
        installed_devices_for_items.append(installed)

    for index, (entry, installed) in enumerate(
        zip(device_entries, installed_devices_for_items)
    ):
        item_device: DeviceCatalog = entry["device"]
        item_service: ServiceType = entry["service"]
        item = InstallationRecordItem(
            installed_device=installed,
            service_type_id=item_service.id,
            position=index,
            service_name=item_service.name,
            device_name=item_device.name,
            manufacturer=item_device.manufacturer,
            device_model=item_device.model,
            serial_number=entry["serial_number"],
            imei=(imported_rows[index].get("imei") if imported_rows else None),
            iccid=(imported_rows[index].get("iccid") if imported_rows else None),
            sim_type=(imported_rows[index].get("sim_type") if imported_rows else None),
            phone_number=(imported_rows[index].get("phone_number") if imported_rows else None),
            location_name=(imported_rows[index].get("site") if imported_rows else work_site.name),
            remarks=(imported_rows[index].get("remarks") if imported_rows else None),
            imported_from_excel=bool(imported_rows),
            warranty_start=entry["warranty_date"],
            result=entry["result_value"],
            notes=entry["notes"],
            handover_notes=entry["handover_notes"] or None,
        )
        item.photos = [
            InstallationItemPhoto(
                storage_key=stored.storage_key,
                thumbnail_key=stored.thumbnail_key,
                original_filename=stored.original_filename,
                content_type=stored.content_type,
                file_size=stored.file_size,
                stage=stage,
                description=description or None,
                position=position,
                uploaded_at=now,
            )
            for stage, stored, description, position in stored_by_item[index]
        ]
        record.work_items.append(item)

    for item in record.work_items:
        apply_scope_snapshot(item, scopes[0])
    db.add(record)
    for scope in scopes[1:]:
        indexes = [
            index for index, entry in enumerate(all_device_entries)
            if entry["scope_index"] == scope.index
        ]
        additional = _new_installation_record(
            db,
            scope=scope,
            entries=[all_device_entries[index] for index in indexes],
            imported_rows=(
                [imported_by_item[index] for index in indexes]
                if device_import_tokens[scope.index]
                else []
            ),
            stored_by_item=[all_stored_by_item[index] for index in indexes],
            user=user,
            participant_ids=participant_ids,
            participants=participants,
            now=now,
            record_number=record.record_number,
        )
        scoped_items = list(additional.work_items)
        primary_installed = additional.installed_device
        extra_device_links = list(additional.additional_devices)
        additional.work_items = []
        additional.additional_devices = []
        additional.installed_device = None
        if primary_installed is not None:
            record.additional_devices.append(
                InstallationRecordAdditionalDevice(
                    installed_device=primary_installed,
                    service_type_id=scoped_items[0].service_type_id,
                    service_name=scoped_items[0].service_name,
                )
            )
        record.additional_devices.extend(extra_device_links)
        for scoped_item in scoped_items:
            scoped_item.position = len(record.work_items)
            apply_scope_snapshot(scoped_item, scope)
            record.work_items.append(scoped_item)
    record.device_data_rows = [
        InstallationDataRow(**row_model_values(row, scopes[row["scope_index"]]))
        for row in data_rows
    ]
    row_lookup = {
        (row.scope_position, row.position): row for row in record.device_data_rows
    }
    local_positions: dict[int, int] = {}
    for item in record.work_items:
        scope_position = item.scope_position or 0
        local_position = local_positions.get(scope_position, 0)
        local_positions[scope_position] = local_position + 1
        data_row = row_lookup.get((scope_position, local_position))
        if data_row is None:
            continue
        item.serial_number = item.serial_number or data_row.serial_number
        item.imei = data_row.imei
        item.iccid = data_row.iccid
        item.sim_type = data_row.sim_type
        item.location_name = data_row.work_site_name
        item.remarks = data_row.remarks
        installed = item.installed_device
        if installed is not None:
            installed.serial_number = installed.serial_number or data_row.serial_number
            installed.imei = data_row.imei
            installed.iccid = data_row.iccid
            installed.sim_type = data_row.sim_type.casefold() if data_row.sim_type else None
            installed.remarks = data_row.remarks
    try:
        db.commit()
    except Exception:
        logger.exception("Could not save installation record")
        db.rollback()
        delete_stored(
            *[
                stored.storage_key
                for item_stored in all_stored_by_item
                for _, stored, _, _ in item_stored
            ],
            *[
                stored.thumbnail_key
                for item_stored in all_stored_by_item
                for _, stored, _, _ in item_stored
            ],
        )
        message = "The installation record could not be saved. Try again."
        if _is_ajax(request):
            return localized_json(request,
                {
                    "ok": False,
                    "errors": {"form": message},
                    "form_token": issue_form_token(request),
                },
                status_code=500,
            )
        return render(
            request,
            "installation_entry.html",
            _form_context(request, db, payload, {"form": message}),
            status_code=500,
        )

    db.refresh(record)
    record_numbers = [record.record_number]
    flash(request, f"Installation record {record.record_number} saved.")
    target = f"/installations/records/{record.id}"
    if _is_ajax(request):
        return localized_json(request,
            {"ok": True, "redirect": target, "record_number": record.record_number, "record_numbers": record_numbers},
            status_code=201,
        )
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/installations/records")
def records_list(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    params = dict(request.query_params)
    q = (params.get("q") or "").strip()
    project_id = (params.get("project_id") or "").strip()
    work_site_id = (params.get("work_site_id") or "").strip()
    device_id = (params.get("device_id") or "").strip()
    service_id = (params.get("service_type_id") or "").strip()
    leader_id = (params.get("leader_id") or "").strip()
    result = (params.get("result") or "").strip()
    date_from = parse_date(params.get("date_from"))
    date_to = parse_date(params.get("date_to"))
    try:
        page = max(1, int(params.get("page", 1)))
    except ValueError:
        page = 1

    stmt = select(InstallationRecord)
    count_stmt = select(func.count(InstallationRecord.id))
    conditions = []

    if user.is_customer:
        conditions.append(InstallationRecord.site_id.in_(user.assigned_project_ids))
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                InstallationRecord.record_number.ilike(like),
                InstallationRecord.site_name.ilike(like),
                InstallationRecord.customer_name.ilike(like),
                InstallationRecord.service_name.ilike(like),
                InstallationRecord.team_leader_name.ilike(like),
                InstallationRecord.equipment_model.ilike(like),
                InstallationRecord.serial_number.ilike(like),
                InstallationRecord.installed_device.has(
                    or_(
                        InstalledDevice.device_name.ilike(like),
                        InstalledDevice.manufacturer.ilike(like),
                        InstalledDevice.device_model.ilike(like),
                        InstalledDevice.serial_number.ilike(like),
                    )
                ),
                InstallationRecord.additional_devices.any(
                    or_(
                        InstallationRecordAdditionalDevice.service_name.ilike(like),
                        InstallationRecordAdditionalDevice.installed_device.has(
                            or_(
                                InstalledDevice.device_name.ilike(like),
                                InstalledDevice.manufacturer.ilike(like),
                                InstalledDevice.device_model.ilike(like),
                                InstalledDevice.serial_number.ilike(like),
                            )
                        ),
                    )
                ),
                InstallationRecord.work_items.any(
                    or_(
                        InstallationRecordItem.service_name.ilike(like),
                        InstallationRecordItem.device_name.ilike(like),
                        InstallationRecordItem.manufacturer.ilike(like),
                        InstallationRecordItem.device_model.ilike(like),
                        InstallationRecordItem.serial_number.ilike(like),
                        InstallationRecordItem.notes.ilike(like),
                        InstallationRecordItem.handover_notes.ilike(like),
                    )
                ),
            )
        )
    if (project_value := entity_id(project_id)) is not None:
        conditions.append(InstallationRecord.site_id == project_value)
    if (work_site_value := entity_id(work_site_id)) is not None:
        conditions.append(
            InstallationRecord.work_site_evidence.has(
                InstallationRecordSite.site_id == work_site_value
            )
        )
    if (service_value := entity_id(service_id)) is not None:
        conditions.append(
            or_(
                InstallationRecord.service_type_id == service_value,
                InstallationRecord.additional_devices.any(
                    InstallationRecordAdditionalDevice.service_type_id == service_value
                ),
                InstallationRecord.work_items.any(
                    InstallationRecordItem.service_type_id == service_value
                ),
            )
        )
    selected_item = (
        db.get(PricingItem, entity_id(device_id)) if entity_id(device_id) is not None else None
    )
    if selected_item is not None and selected_item.device_catalog_id is not None:
        device_value = selected_item.device_catalog_id
        conditions.append(
            or_(
                InstallationRecord.installed_device.has(
                    InstalledDevice.device_id == device_value
                ),
                InstallationRecord.additional_devices.any(
                    InstallationRecordAdditionalDevice.installed_device.has(
                        InstalledDevice.device_id == device_value
                    )
                ),
                InstallationRecord.work_items.any(
                    InstallationRecordItem.installed_device.has(
                        InstalledDevice.device_id == device_value
                    )
                ),
            )
        )
    if user.can_view_all_records and (
        leader_value := entity_id(leader_id)
    ) is not None:
        conditions.append(InstallationRecord.submitted_by_id == leader_value)
    if result:
        try:
            selected_result = MaintenanceResult(result)
            conditions.append(
                or_(
                    InstallationRecord.result == selected_result,
                    InstallationRecord.work_items.any(
                        InstallationRecordItem.result == selected_result
                    ),
                )
            )
        except ValueError:
            result = ""
    if date_from:
        conditions.append(
            InstallationRecord.submitted_at
            >= to_utc_from_display(dt.combine(date_from, dt_time.min))
        )
    if date_to:
        conditions.append(
            InstallationRecord.submitted_at
            < to_utc_from_display(dt.combine(date_to, dt_time.min) + timedelta(days=1))
        )

    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)

    total = int(db.scalar(count_stmt) or 0)
    page_info = paginate(total, page, settings.page_size)
    records = list(
        db.scalars(
            stmt.options(
                selectinload(InstallationRecord.photos),
                selectinload(InstallationRecord.installed_device),
                selectinload(InstallationRecord.additional_devices).selectinload(
                    InstallationRecordAdditionalDevice.installed_device
                ),
                selectinload(InstallationRecord.work_items).selectinload(
                    InstallationRecordItem.photos
                ),
                selectinload(InstallationRecord.work_site_evidence),
            )
            .order_by(InstallationRecord.submitted_at.desc(), InstallationRecord.id.desc())
            .offset(page_info["offset"])
            .limit(page_info["per_page"])
        )
    )
    filters = {
        "q": q,
        "project_id": project_id,
        "work_site_id": work_site_id,
        "device_id": device_id,
        "service_type_id": service_id,
        "leader_id": leader_id if user.can_view_all_records else "",
        "result": result,
        "date_from": params.get("date_from", ""),
        "date_to": params.get("date_to", ""),
    }
    return render(
        request,
        "installation_records.html",
        {
            "active_nav": "installation_records",
            "records": records,
            "page_info": page_info,
            "filters": filters,
            "has_filters": any(filters.values()),
            "projects": list(
                db.scalars(
                    (
                        select(Site).where(
                            Site.id.in_(user.assigned_project_ids)
                        )
                        if user.is_customer
                        else select(Site)
                    ).order_by(Site.name)
                )
            ),
            "work_sites": list(db.scalars(select(WorkSite).order_by(WorkSite.name))),
            "devices": list(
                db.scalars(select(PricingItem).order_by(PricingItem.name, PricingItem.model))
            ),
            "services": list(db.scalars(select(ServiceType).order_by(ServiceType.name))),
            "leaders": (
                list(
                    db.scalars(
                        select(User).order_by(User.full_name)
                    )
                )
                if user.can_view_all_records
                else []
            ),
        },
    )


def _load_record(db: Session, record_id: int, user: User) -> InstallationRecord:
    record = db.get(
        InstallationRecord,
        record_id,
        options=[
            selectinload(InstallationRecord.photos),
            selectinload(InstallationRecord.participants),
            selectinload(InstallationRecord.installed_device),
            selectinload(InstallationRecord.additional_devices).selectinload(
                InstallationRecordAdditionalDevice.installed_device
            ),
            selectinload(InstallationRecord.work_items).selectinload(
                InstallationRecordItem.photos
            ),
            selectinload(InstallationRecord.work_site_evidence),
        ],
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Installation record not found")
    project_ids = {item.project_id or record.site_id for item in record.work_items} or {record.site_id}
    if not all(user.can_access_project(project_id) for project_id in project_ids):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This record is outside your assigned Projects",
        )
    return record


@router.get("/installations/records/{record_id}")
def record_details(
    record_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _load_record(db, record_id, user)
    return render(
        request,
        "installation_detail.html",
        {
            "active_nav": "installation_records",
            "record": record,
            "revisions": revisions_for(db, "installation", record.id),
            "linked_reports": linked_reports(
                db, ServiceReportRecord.installation_record_id, record.id
            ),
        },
    )


def _edit_items(record: InstallationRecord) -> list[dict]:
    if record.work_items:
        return [
            {
                "data": item,
                "photos": item.photos,
                "photo_groups": grouped_photos(item.photos),
                "photo_media_path": "/media/installation-item-photo",
                "device_label": f"{item.device_name} — {item.device_model}",
                "service_label": item.service_name,
                "serial_number": item.serial_number,
            }
            for item in record.work_items
        ]
    device = record.installed_device
    return [
        {
            "data": record,
            "photos": record.photos,
            "photo_groups": grouped_photos(record.photos),
            "photo_media_path": "/media/installation-photo",
            "device_label": (
                f"{device.device_name} — {device.device_model}"
                if device
                else record.equipment_model
            ),
            "service_label": record.service_name,
            "serial_number": record.serial_number,
        }
    ]


def _edit_context(
    request: Request,
    db: Session,
    record: InstallationRecord,
    error: str = "",
    selected_participant_ids: list[str] | None = None,
) -> dict:
    choices = technical_user_choices(db, request.state.user)
    if selected_participant_ids is None:
        selected_participant_ids = selected_ids_for_names(
            choices, (participant.name for participant in record.participants)
        )
    return {
        "active_nav": "installation_records",
        "record": record,
        "record_kind": "installation",
        "record_label": "Installation record",
        "project_name": record.customer_name,
        "edit_items": _edit_items(record),
        "technical_users": choices,
        "selected_participant_ids": selected_participant_ids,
        "participant_error": error if "Technical user" in error else "",
        "results": list(MaintenanceResult),
        "detail_url": f"/installations/records/{record.id}",
        "edit_url": f"/installations/records/{record.id}/edit",
        "error": error,
    }


@router.get("/installations/records/{record_id}/edit")
def edit_record_form(
    record_id: int,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "record_edit.html",
        _edit_context(request, db, _load_record(db, record_id, user)),
    )


@router.post("/installations/records/{record_id}/edit")
async def edit_record(
    record_id: int,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    record = _load_record(db, record_id, user)
    form = await request.form()
    if not csrf_valid(request, form.get("csrf_token")):
        return render(
            request,
            "record_edit.html",
            _edit_context(
                request,
                db,
                record,
                "Your session expired. Reload and try again.",
            ),
            status_code=403,
        )

    names, selected_participant_ids, participant_error = validate_participant_ids(
        db,
        user,
        form.getlist("participant_ids"),
        maximum=MAX_PARTICIPANTS,
    )
    if participant_error:
        return render(
            request,
            "record_edit.html",
            _edit_context(
                request,
                db,
                record,
                participant_error,
                selected_participant_ids,
            ),
            status_code=422,
        )

    wrappers = _edit_items(record)
    parsed: list[tuple[MaintenanceResult, str, str]] = []
    removals: list[set[int]] = []
    uploads_by_item: list[list[tuple[EvidencePhotoStage, UploadFile, str]]] = []
    description_updates_by_item: list[dict[int, str]] = []
    error = ""
    for index, wrapper in enumerate(wrappers):
        try:
            result = MaintenanceResult(str(form.get(f"result_{index}") or ""))
        except ValueError:
            error = f"Select a result for item {index + 1}."
            break
        notes = str(form.get(f"notes_{index}") or "").strip()
        handover = str(form.get(f"handover_notes_{index}") or "").strip()
        if not notes or len(notes) > MAX_TEXT_LENGTH:
            error = f"Enter valid notes for item {index + 1}."
            break
        if len(handover) > MAX_TEXT_LENGTH:
            error = f"Keep item {index + 1} handover notes under {MAX_TEXT_LENGTH} characters."
            break
        remove_ids = {
            int(value)
            for value in form.getlist(f"remove_photo_{index}")
            if str(value).isdigit()
        }
        current_ids = {photo.id for photo in wrapper["photos"]}
        if not remove_ids.issubset(current_ids):
            error = f"One selected photo for item {index + 1} no longer exists."
            break
        description_updates, description_error = existing_photo_descriptions(
            form, wrapper["photos"], maximum=MAX_TEXT_LENGTH
        )
        if description_error:
            error = f"Item {index + 1}: {description_error}"
            break
        before_uploads = [
            upload for upload in form.getlist(f"add_before_photos_{index}")
            if isinstance(upload, UploadFile) and upload.filename
        ]
        after_uploads = [
            upload for upload in form.getlist(f"add_after_photos_{index}")
            if isinstance(upload, UploadFile) and upload.filename
        ]
        legacy_uploads = [
            upload for upload in form.getlist(f"add_photos_{index}")
            if isinstance(upload, UploadFile) and upload.filename
        ]
        before_descriptions, description_error = new_photo_descriptions(
            form,
            f"add_before_photo_descriptions_{index}",
            len(before_uploads),
            maximum=MAX_TEXT_LENGTH,
        )
        after_descriptions, description_error = new_photo_descriptions(
            form,
            f"add_after_photo_descriptions_{index}",
            len(after_uploads),
            maximum=MAX_TEXT_LENGTH,
        ) if description_error is None else ([], description_error)
        if description_error:
            error = f"Item {index + 1}: {description_error}"
            break
        uploads = [
            *((EvidencePhotoStage.BEFORE, upload, before_descriptions[position]) for position, upload in enumerate(before_uploads)),
            *((EvidencePhotoStage.AFTER, upload, after_descriptions[position]) for position, upload in enumerate(after_uploads)),
            *((EvidencePhotoStage.LEGACY, upload, "") for upload in legacy_uploads),
        ]
        kept = [photo for photo in wrapper["photos"] if photo.id not in remove_ids]
        before_count = sum(
            getattr(photo, "stage", EvidencePhotoStage.LEGACY)
            == EvidencePhotoStage.BEFORE for photo in kept
        )
        after_count = sum(
            getattr(photo, "stage", EvidencePhotoStage.LEGACY)
            == EvidencePhotoStage.AFTER for photo in kept
        )
        if not kept and not uploads:
            error = f"Item {index + 1} must keep at least one photo."
            break
        if before_count + len(before_uploads) > settings.max_photos_per_record:
            error = f"Item {index + 1} can keep at most 10 before photos."
            break
        if after_count + len(after_uploads) > settings.max_photos_per_record:
            error = f"Item {index + 1} can keep at most 10 after photos."
            break
        parsed.append((result, notes, handover))
        removals.append(remove_ids)
        uploads_by_item.append(uploads)
        description_updates_by_item.append(description_updates)
    if error:
        return render(
            request,
            "record_edit.html",
            _edit_context(request, db, record, error, selected_participant_ids),
            status_code=422,
        )

    stored_by_item: list[list] = [[] for _ in wrappers]
    try:
        for index, uploads in enumerate(uploads_by_item):
            for stage, upload, description in uploads:
                stored_by_item[index].append(
                    (stage, store_image(upload.filename, await upload.read()), description)
                )
    except UploadError as exc:
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored, _ in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored, _ in group],
        )
        return render(
            request,
            "record_edit.html",
            _edit_context(
                request, db, record, str(exc), selected_participant_ids
            ),
            status_code=422,
        )

    changes: dict = {}
    removed_keys: set[str] = set()
    now = utcnow()
    for index, (wrapper, values) in enumerate(zip(wrappers, parsed)):
        item = wrapper["data"]
        result, notes, handover = values
        for field, value in (
            ("result", result),
            ("notes", notes),
            ("handover_notes", handover or None),
        ):
            before = getattr(item, field)
            before_value = before.value if isinstance(before, MaintenanceResult) else before
            after_value = value.value if isinstance(value, MaintenanceResult) else value
            delta = changed(before_value, after_value)
            if delta:
                changes[f"item_{index + 1}_{field}"] = delta
                setattr(item, field, value)

        removed = [
            photo for photo in list(wrapper["photos"]) if photo.id in removals[index]
        ]
        photo_note_changes = []
        for photo in wrapper["photos"]:
            if photo.id in removals[index]:
                continue
            value = description_updates_by_item[index][photo.id] or None
            delta = changed(photo.description, value)
            if delta:
                photo_note_changes.append({"photo_id": photo.id, **delta})
                photo.description = value
                if record.work_items and index == 0:
                    for legacy in record.photos:
                        if legacy.storage_key == photo.storage_key:
                            legacy.description = value
        for photo in removed:
            removed_keys.update(
                key for key in (photo.storage_key, photo.thumbnail_key) if key
            )
            wrapper["photos"].remove(photo)
            if record.work_items and index == 0:
                for legacy in list(record.photos):
                    if legacy.storage_key == photo.storage_key:
                        record.photos.remove(legacy)
        for stage, stored, description in stored_by_item[index]:
            position = sum(
                getattr(photo, "stage", EvidencePhotoStage.LEGACY) == stage
                for photo in wrapper["photos"]
            )
            if record.work_items:
                item.photos.append(
                    InstallationItemPhoto(
                        storage_key=stored.storage_key,
                        thumbnail_key=stored.thumbnail_key,
                        original_filename=stored.original_filename,
                        content_type=stored.content_type,
                        file_size=stored.file_size,
                        stage=stage,
                        description=description or None,
                        position=position,
                        uploaded_at=now,
                    )
                )
                if index == 0:
                    record.photos.append(
                        InstallationPhoto(
                            storage_key=stored.storage_key,
                            thumbnail_key=stored.thumbnail_key,
                            original_filename=stored.original_filename,
                            content_type=stored.content_type,
                            file_size=stored.file_size,
                            description=description or None,
                            position=position,
                            uploaded_at=now,
                        )
                    )
            else:
                record.photos.append(
                    InstallationPhoto(
                        storage_key=stored.storage_key,
                        thumbnail_key=stored.thumbnail_key,
                        original_filename=stored.original_filename,
                        content_type=stored.content_type,
                        file_size=stored.file_size,
                        description=description or None,
                        position=position,
                        uploaded_at=now,
                    )
                )
        if removed or stored_by_item[index] or photo_note_changes:
            changes[f"item_{index + 1}_photos"] = {
                "removed": [photo.original_filename for photo in removed],
                "added": [
                    f"{stage.value}: {stored.original_filename}"
                    for stage, stored, _ in stored_by_item[index]
                ],
                "notes_edited": photo_note_changes,
            }

    if record.work_items:
        first = record.work_items[0]
        record.result = first.result
        record.notes = first.notes
        record.handover_notes = first.handover_notes

    old_names = [p.name for p in record.participants]
    old_user_ids = [p.user_id for p in record.participants]
    new_user_ids = [int(value) for value in selected_participant_ids]
    if old_names != names or old_user_ids != new_user_ids:
        changes["participants"] = {"before": old_names, "after": names}
        record.participants = [
            InstallationParticipant(user_id=user_id, name=name)
            for user_id, name in zip(new_user_ids, names)
        ]

    if not changes:
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored, _ in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored, _ in group],
        )
        flash(request, "No changes were made.")
        return RedirectResponse(
            f"/installations/records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    add_revision(
        db,
        record_type="installation",
        record_id=record.id,
        record_number=record.record_number,
        action="edited",
        user=user,
        changes=changes,
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored, _ in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored, _ in group],
        )
        return render(
            request,
            "record_edit.html",
            _edit_context(
                request,
                db,
                record,
                "The changes could not be saved. Try again.",
                selected_participant_ids,
            ),
            status_code=500,
        )
    delete_stored(*removed_keys)
    flash(request, f"{record.record_number} updated and added to change history.")
    return RedirectResponse(
        f"/installations/records/{record.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/installations/records/{record_id}/delete",
    dependencies=[Depends(require_admin)],
)
async def delete_record(
    record_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if not csrf_valid(request, form.get("csrf_token")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
    record = _load_record(db, record_id, user)
    devices = [
        device
        for device in [
            record.installed_device,
            *[
                link.installed_device
                for link in record.additional_devices
                if link.installed_device
            ],
        ]
        if device
    ]
    device_ids = [device.id for device in devices]
    referenced = False
    if device_ids:
        referenced = any(
            db.scalar(select(model.id).where(column.in_(device_ids)).limit(1))
            is not None
            for model, column in (
                (MaintenanceRecordDevice, MaintenanceRecordDevice.installed_device_id),
                (
                    MaintenanceRecordAdditionalDevice,
                    MaintenanceRecordAdditionalDevice.installed_device_id,
                ),
                (MaintenanceRecordItem, MaintenanceRecordItem.installed_device_id),
                (GeneralMaintenanceItem, GeneralMaintenanceItem.installed_device_id),
            )
        )
    if referenced:
        flash(
            request,
            "This installation cannot be deleted because one of its devices "
            "is referenced by a maintenance record.",
            "error",
        )
        return RedirectResponse(
            f"/installations/records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    keys = {
        key
        for photo in [*record.photos, *[p for item in record.work_items for p in item.photos]]
        for key in (photo.storage_key, photo.thumbnail_key)
        if key
    }
    additional_devices = [
        link.installed_device for link in record.additional_devices if link.installed_device
    ]
    record_number = record.record_number
    deleted_reports = delete_linked_reports(
        db, ServiceReportRecord.installation_record_id, record.id
    )
    add_revision(
        db,
        record_type="installation",
        record_id=record.id,
        record_number=record_number,
        action="deleted",
        user=user,
        changes={"record": "Permanently deleted by Administrator"},
    )
    db.delete(record)
    db.flush()
    for device in additional_devices:
        db.delete(device)
    db.commit()
    delete_stored(*keys)
    report_note = (
        f" {len(deleted_reports)} linked generated report(s) were also deleted."
        if deleted_reports
        else ""
    )
    flash(request, f"{record_number} permanently deleted.{report_note}")
    return RedirectResponse(
        "/installations/records", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/media/installation-photo/{photo_id}")
def photo(
    photo_id: int,
    request: Request,
    size: str = "full",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo_row = db.get(InstallationPhoto, photo_id)
    if photo_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")

    _load_record(db, photo_row.record_id, user)
    key = (
        photo_row.thumbnail_key
        if size == "thumb" and photo_row.thumbnail_key
        else photo_row.storage_key
    )
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")

    media_type = "image/jpeg" if key.endswith("_thumb.jpg") else photo_row.content_type
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=600",
            "Content-Disposition": f'inline; filename="{photo_row.original_filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/media/installation-item-photo/{photo_id}")
def item_photo(
    photo_id: int,
    request: Request,
    size: str = "full",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo_row = db.get(InstallationItemPhoto, photo_id)
    if photo_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    _load_record(db, photo_row.item.record_id, user)
    key = (
        photo_row.thumbnail_key
        if size == "thumb" and photo_row.thumbnail_key
        else photo_row.storage_key
    )
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    media_type = "image/jpeg" if key.endswith("_thumb.jpg") else photo_row.content_type
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, max-age=600",
            "Content-Disposition": f'inline; filename="{photo_row.original_filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
