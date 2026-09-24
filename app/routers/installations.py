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
from ..entry_data_tables import parse_entry_data_rows, row_model_values, rows_for_scope, serialize_data_rows
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
from ..photo_guidance_profiles import profile_choices, resolve_profile
from ..quotation_references import quotation_choices, resolve_quotation_reference
from ..record_mutations import add_revision, changed
from ..record_editing import (
    appended_scope_targets,
    grouped_edit_scopes,
    parse_saved_table_rows,
    sync_legacy_photo_mirror,
)
from ..audit import set_audit_context
from ..record_photo_edits import (
    existing_photo_descriptions,
    existing_photo_issue_flags,
    grouped_photos,
    new_photo_descriptions,
    new_photo_issue_flags,
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
        "photo_guidance_profiles": profile_choices(db),
        "quotations": quotation_choices(db),
        "form": form or {"participants": [], "devices": [{}]},
        "technical_users": technical_user_choices(db, request.state.user),
        "selected_participant_ids": [
            str(value) for value in (form or {}).get("participants", [])
        ],
        "participant_error": (errors or {}).get("participant_ids", ""),
        "errors": errors or {},
        "form_token": form_token or issue_form_token(request),
        "append_record_id": (form or {}).get("append_record_id", ""),
        "append_record_number": (form or {}).get("append_record_number", ""),
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
    append_to: int | None = None,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    form = None
    if append_to is not None:
        record = _load_record(db, append_to, user)
        choices = technical_user_choices(db, user)
        form = {
            "participants": selected_ids_for_names(
                choices, (participant.name for participant in record.participants)
            ),
            "devices": [{}],
            "append_record_id": str(record.id),
            "append_record_number": record.record_number,
        }
    return render(request, "installation_entry.html", _form_context(request, db, form))


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
            is_issue_found=is_issue_found,
            position=position,
            uploaded_at=now,
        )
        for _, stored, description, position, is_issue_found in stored_by_item[0]
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
            photo_guidance_profile_id=(entry["photo_guidance_profile"].id if entry["photo_guidance_profile"] else None),
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
                is_issue_found=is_issue_found,
                position=position,
                uploaded_at=now,
            )
            for stage, stored, description, position, is_issue_found in stored_by_item[index]
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
    append_record_id_raw = str(form.get("append_record_id") or "").strip()
    append_record = None
    if append_record_id_raw:
        append_record_id = entity_id(append_record_id_raw)
        if append_record_id is None:
            errors["form"] = "The installation record being edited is invalid."
        else:
            append_record = _load_record(db, append_record_id, user)

    project_id_raw = str(form.get("project_id") or form.get("site_id") or "").strip()
    sub_project_id_raw = str(form.get("sub_project_id") or "").strip()
    device_import_token = str(form.get("device_import_token") or "").strip()
    quotation_number_raw = str(form.get("quotation_number") or "").strip()
    work_site_id_raw = str(form.get("work_site_id") or "").strip()
    service_ids = [str(value).strip() for value in form.getlist("service_type_id")]
    device_ids = [str(value).strip() for value in form.getlist("device_id")]
    serial_numbers = [str(value).strip() for value in form.getlist("serial_number")]
    warranty_starts = [str(value).strip() for value in form.getlist("warranty_start")]
    photo_guidance_profile_ids = [str(value).strip() for value in form.getlist("photo_guidance_profile_id")]
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
        len(photo_guidance_profile_ids),
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
        photo_guidance_profile_ids,
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
        profile_raw = photo_guidance_profile_ids[index]
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

        assigned_scope = scopes[item_scopes[index]] if item_scopes[index] < len(scopes) else None
        photo_guidance_profile, profile_error = resolve_profile(
            db,
            profile_raw,
            assigned_scope.project.id if assigned_scope is not None else None,
        )
        if profile_error:
            errors[f"photo_guidance_profile_id{suffix}"] = profile_error

        device_entries.append(
            {
                "service_type_id": service_raw,
                "device_id": device_raw,
                "serial_number": serial_number or None,
                "warranty_start": warranty_raw,
                "result": result_raw,
                "notes": notes,
                "handover_notes": handover_notes,
                "photo_guidance_profile_id": profile_raw,
                "service": service,
                "device": device,
                "pricing_item": item,
                "photo_guidance_profile": photo_guidance_profile,
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

    uploads_by_item: list[list[tuple[EvidencePhotoStage, UploadFile, str, int, bool]]] = []
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
        before_issue_flags, before_issue_error = new_photo_issue_flags(
            form, f"before_photo_issue_found_{index}", before_descriptions
        )
        after_issue_flags, after_issue_error = new_photo_issue_flags(
            form, f"after_photo_issue_found_{index}", after_descriptions
        )
        issue_error = before_issue_error or after_issue_error
        uploads = [
            *((EvidencePhotoStage.BEFORE, upload, before_descriptions[position], position, before_issue_flags[position]) for position, upload in enumerate(before_uploads)),
            *((EvidencePhotoStage.AFTER, upload, after_descriptions[position], position, after_issue_flags[position]) for position, upload in enumerate(after_uploads)),
            *((EvidencePhotoStage.LEGACY, upload, "", position, False) for position, upload in enumerate(legacy_uploads)),
        ]
        uploads_by_item.append(uploads)
        if issue_error:
            errors[f"photos_{index}"] = issue_error
        elif not uploads:
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
            for stage, upload, description, position, is_issue_found in uploads:
                data = await upload.read()
                try:
                    stored_by_item[index].append(
                        (stage, store_image(upload.filename, data), description, position, is_issue_found)
                    )
                except UploadError as exc:
                    errors[f"photos_{index}"] = str(exc)
                    break
            if errors:
                delete_stored(
                    *[
                        stored.storage_key
                        for item_stored in stored_by_item
                        for _, stored, _, _, _ in item_stored
                    ],
                    *[
                        stored.thumbnail_key
                        for item_stored in stored_by_item
                        for _, stored, _, _, _ in item_stored
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
                    "photo_guidance_profile_id",
                )
            }
            for entry in device_entries
        ],
        "participants": participant_ids,
        "append_record_id": append_record_id_raw,
        "append_record_number": append_record.record_number if append_record else "",
    }

    if errors:
        if append_record is not None:
            details = list(dict.fromkeys(
                message for key, message in errors.items() if key != "form" and message
            ))
            reason = f" Reason: {' '.join(details[:3])}" if details else ""
            errors.setdefault(
                "form",
                "The new Site was not saved."
                f"{reason} Correct the fields, then select Save additions again.",
            )
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
            *[s.storage_key for group in stored_by_item for _, s, _, _, _ in group],
            *[s.thumbnail_key for group in stored_by_item for _, s, _, _, _ in group],
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
            is_issue_found=is_issue_found,
            position=position,
            uploaded_at=now,
        )
        for _, s, description, position, is_issue_found in stored_by_item[0]
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
            photo_guidance_profile_id=(entry["photo_guidance_profile"].id if entry["photo_guidance_profile"] else None),
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
                is_issue_found=is_issue_found,
                position=position,
                uploaded_at=now,
            )
            for stage, stored, description, position, is_issue_found in stored_by_item[index]
        ]
        record.work_items.append(item)

    for item in record.work_items:
        apply_scope_snapshot(item, scopes[0])
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
    appended_report_numbers: list[str] = []
    if append_record is not None:
        created_record = record
        existing_positions = {
            *(item.scope_position or 0 for item in append_record.work_items),
            *(row.scope_position or 0 for row in append_record.device_data_rows),
        }
        scope_targets = appended_scope_targets(form, len(scopes), existing_positions)
        new_items = list(created_record.work_items)
        primary_installed = created_record.installed_device
        extra_device_links = list(created_record.additional_devices)
        new_rows = list(created_record.device_data_rows)
        created_record.work_items = []
        created_record.additional_devices = []
        created_record.device_data_rows = []
        created_record.installed_device = None
        if primary_installed is not None and new_items:
            append_record.additional_devices.append(
                InstallationRecordAdditionalDevice(
                    installed_device=primary_installed,
                    service_type_id=new_items[0].service_type_id,
                    service_name=new_items[0].service_name,
                )
            )
        append_record.additional_devices.extend(extra_device_links)
        for item in new_items:
            item.scope_position = scope_targets[item.scope_position or 0]
            item.position = len(append_record.work_items)
            append_record.work_items.append(item)
        for row in new_rows:
            row.scope_position = scope_targets[row.scope_position or 0]
            append_record.device_data_rows.append(row)
        append_record.participants = [
            InstallationParticipant(user_id=int(user_id), name=name)
            for user_id, name in zip(participant_ids, participants)
        ]
        appended_report_numbers = delete_linked_reports(
            db, ServiceReportRecord.installation_record_id, append_record.id
        )
        add_revision(
            db,
            record_type="installation",
            record_id=append_record.id,
            record_number=append_record.record_number,
            action="items_added",
            user=user,
            changes={
                "added_sites": [scope.site.name for scope in scopes],
                "added_devices": [item.device_name for item in new_items],
                "deleted_linked_reports": appended_report_numbers,
            },
        )
        record = append_record
    else:
        db.add(record)
    try:
        db.commit()
    except Exception:
        logger.exception("Could not save installation record")
        db.rollback()
        delete_stored(
            *[
                stored.storage_key
                for item_stored in all_stored_by_item
                for _, stored, _, _, _ in item_stored
            ],
            *[
                stored.thumbnail_key
                for item_stored in all_stored_by_item
                for _, stored, _, _, _ in item_stored
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
    if append_record is not None:
        message = f"Sites and devices added to installation record {record.record_number}."
        if appended_report_numbers:
            message += " Linked reports were removed; generate a new report with the updated record."
        flash(request, message)
    else:
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
            selectinload(InstallationRecord.device_data_rows),
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
    wrappers = _edit_items(record)
    pricing_by_catalog = {
        item.device_catalog_id: item.id for item in _active_devices(db)
    }
    for wrapper in wrappers:
        installed = getattr(wrapper["data"], "installed_device", None)
        wrapper["selected_device_id"] = pricing_by_catalog.get(
            getattr(installed, "device_id", None), ""
        )
    projects = active_project_hierarchy(db)
    return {
        "active_nav": "installation_records",
        "record": record,
        "record_kind": "installation",
        "record_label": "Installation record",
        "project_name": record.customer_name,
        "edit_items": wrappers,
        "edit_scopes": grouped_edit_scopes(record, wrappers),
        "projects": projects,
        "project_hierarchy": hierarchy_json(projects),
        "work_sites": _active_work_sites(db),
        "services": _active_services(db),
        "devices": _active_devices(db),
        "photo_guidance_profiles": profile_choices(db),
        "quotations": quotation_choices(db),
        "technical_users": choices,
        "selected_participant_ids": selected_participant_ids,
        "participant_error": error if "Technical user" in error else "",
        "results": list(MaintenanceResult),
        "detail_url": f"/installations/records/{record.id}",
        "edit_url": f"/installations/records/{record.id}/edit",
        "can_remove_existing": request.state.user.is_admin,
        "form_token": issue_form_token(request),
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

    all_wrappers = _edit_items(record)
    wrappers_by_id = {
        wrapper["data"].id: wrapper for wrapper in all_wrappers
        if getattr(wrapper["data"], "id", None) is not None
    }
    raw_existing_ids = form.getlist("existing_item_id")
    submitted_ids = [int(value) for value in raw_existing_ids if str(value).isdigit()]
    if not raw_existing_ids:
        submitted_ids = list(wrappers_by_id)
    if len(submitted_ids) != len(set(submitted_ids)) or any(item_id not in wrappers_by_id for item_id in submitted_ids):
        return render(request, "record_edit.html", _edit_context(request, db, record, "One saved device is invalid or duplicated."), status_code=422)
    removed_ids = set(wrappers_by_id) - set(submitted_ids)
    if removed_ids and not user.is_admin:
        return render(request, "record_edit.html", _edit_context(request, db, record, "Only an Administrator can remove saved devices or Sites."), status_code=403)
    if not submitted_ids and not form.getlist("service_type_id"):
        return render(request, "record_edit.html", _edit_context(request, db, record, "Keep at least one device, or delete the complete record."), status_code=422)
    wrappers = [wrappers_by_id[item_id] for item_id in submitted_ids]
    parsed: list[tuple[MaintenanceResult, str, str, int | None]] = []
    removals: list[set[int]] = []
    uploads_by_item: list[list[tuple[EvidencePhotoStage, UploadFile, str, bool]]] = []
    description_updates_by_item: list[dict[int, str]] = []
    issue_updates_by_item: list[dict[int, bool]] = []
    error = ""
    for index, wrapper in enumerate(wrappers):
        try:
            result = MaintenanceResult(str(form.get(f"existing_result_{wrapper['data'].id}") or form.get(f"result_{index}") or ""))
        except ValueError:
            error = f"Select a result for item {index + 1}."
            break
        item_id = wrapper["data"].id
        notes = str(form.get(f"existing_notes_{item_id}") or form.get(f"notes_{index}") or "").strip()
        handover = str(form.get(f"existing_handover_notes_{item_id}") or form.get(f"handover_notes_{index}") or "").strip()
        profile_raw = str(form.get(f"existing_photo_guidance_profile_id_{item_id}") or "").strip()
        profile, profile_error = resolve_profile(
            db,
            profile_raw,
            getattr(wrapper["data"], "project_id", None) or record.site_id,
        )
        if profile_error:
            error = f"Item {index + 1}: {profile_error}"
            break
        if len(notes) > MAX_TEXT_LENGTH:
            error = f"Keep notes for item {index + 1} under {MAX_TEXT_LENGTH} characters."
            break
        if len(handover) > MAX_TEXT_LENGTH:
            error = f"Keep item {index + 1} handover notes under {MAX_TEXT_LENGTH} characters."
            break
        remove_ids = {
            int(value)
            for value in (form.getlist(f"existing_remove_photo_{item_id}") or form.getlist(f"remove_photo_{index}"))
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
        issue_updates, issue_error = existing_photo_issue_flags(
            form,
            wrapper["photos"],
            description_updates,
            removed_ids=remove_ids,
        )
        if issue_error:
            error = f"Item {index + 1}: {issue_error}"
            break
        before_uploads = [
            upload for upload in (form.getlist(f"existing_add_before_photos_{item_id}") or form.getlist(f"add_before_photos_{index}"))
            if isinstance(upload, UploadFile) and upload.filename
        ]
        after_uploads = [
            upload for upload in (form.getlist(f"existing_add_after_photos_{item_id}") or form.getlist(f"add_after_photos_{index}"))
            if isinstance(upload, UploadFile) and upload.filename
        ]
        legacy_uploads = [
            upload for upload in form.getlist(f"add_photos_{index}")
            if isinstance(upload, UploadFile) and upload.filename
        ]
        before_descriptions, description_error = new_photo_descriptions(
            form,
            f"existing_add_before_photo_descriptions_{item_id}" if form.getlist(f"existing_add_before_photo_descriptions_{item_id}") else f"add_before_photo_descriptions_{index}",
            len(before_uploads),
            maximum=MAX_TEXT_LENGTH,
        )
        after_descriptions, description_error = new_photo_descriptions(
            form,
            f"existing_add_after_photo_descriptions_{item_id}" if form.getlist(f"existing_add_after_photo_descriptions_{item_id}") else f"add_after_photo_descriptions_{index}",
            len(after_uploads),
            maximum=MAX_TEXT_LENGTH,
        ) if description_error is None else ([], description_error)
        if description_error:
            error = f"Item {index + 1}: {description_error}"
            break
        before_issue_flags, before_issue_error = new_photo_issue_flags(
            form,
            (
                f"existing_add_before_photo_issue_found_{item_id}"
                if form.getlist(f"existing_add_before_photos_{item_id}")
                else f"add_before_photo_issue_found_{index}"
            ),
            before_descriptions,
        )
        after_issue_flags, after_issue_error = new_photo_issue_flags(
            form,
            (
                f"existing_add_after_photo_issue_found_{item_id}"
                if form.getlist(f"existing_add_after_photos_{item_id}")
                else f"add_after_photo_issue_found_{index}"
            ),
            after_descriptions,
        )
        if before_issue_error or after_issue_error:
            error = f"Item {index + 1}: {before_issue_error or after_issue_error}"
            break
        uploads = [
            *((EvidencePhotoStage.BEFORE, upload, before_descriptions[position], before_issue_flags[position]) for position, upload in enumerate(before_uploads)),
            *((EvidencePhotoStage.AFTER, upload, after_descriptions[position], after_issue_flags[position]) for position, upload in enumerate(after_uploads)),
            *((EvidencePhotoStage.LEGACY, upload, "", False) for upload in legacy_uploads),
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
        parsed.append((result, notes, handover, profile.id if profile else None))
        removals.append(remove_ids)
        uploads_by_item.append(uploads)
        description_updates_by_item.append(description_updates)
        issue_updates_by_item.append(issue_updates)
    if error:
        return render(
            request,
            "record_edit.html",
            _edit_context(request, db, record, error, selected_participant_ids),
            status_code=422,
        )

    scope_map = {scope["position"]: scope for scope in grouped_edit_scopes(record, all_wrappers)}
    valid_scope_positions = {
        int(getattr(wrapper["data"], "scope_position", 0) or 0) for wrapper in wrappers
    }
    saved_rows, table_error = parse_saved_table_rows(form, valid_scope_positions, installation=True)
    if table_error:
        return render(request, "record_edit.html", _edit_context(request, db, record, table_error, selected_participant_ids), status_code=422)

    stored_by_item: list[list] = [[] for _ in wrappers]
    try:
        for index, uploads in enumerate(uploads_by_item):
            for stage, upload, description, is_issue_found in uploads:
                stored_by_item[index].append(
                    (stage, store_image(upload.filename, await upload.read()), description, is_issue_found)
                )
    except UploadError as exc:
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored, _, _ in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored, _, _ in group],
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
    removed_wrappers = [wrappers_by_id[item_id] for item_id in sorted(removed_ids)]
    if removed_wrappers:
        changes["removed_devices"] = []
        removed_assets = set()
        for wrapper in removed_wrappers:
            item = wrapper["data"]
            installed = item.installed_device
            changes["removed_devices"].append(
                {
                    "item_id": item.id,
                    "asset_id": installed.id if installed else None,
                    "site": item.work_site_name or record.site_name,
                    "device": item.device_name,
                    "serial_number": item.serial_number,
                    "asset_action": "deactivated_and_detached",
                }
            )
            removed_keys.update(
                key for photo in wrapper["photos"] for key in (photo.storage_key, photo.thumbnail_key) if key
            )
            if installed is not None:
                removed_assets.add(installed.id)
                installed.is_active = False
                if record.installed_device is installed:
                    record.installed_device = None
            if item in record.work_items:
                record.work_items.remove(item)
        record.additional_devices = [
            link for link in record.additional_devices
            if link.installed_device_id not in removed_assets
        ]
        remaining_items = list(record.work_items)
        record.additional_devices = []
        if remaining_items:
            primary = remaining_items[0].installed_device
            record.installed_device = primary
            for remaining in remaining_items[1:]:
                record.additional_devices.append(
                    InstallationRecordAdditionalDevice(
                        installed_device=remaining.installed_device,
                        service_type_id=remaining.service_type_id,
                        service_name=remaining.service_name,
                    )
                )
    for index, (wrapper, values) in enumerate(zip(wrappers, parsed)):
        item = wrapper["data"]
        result, notes, handover, profile_id = values
        for field, value in (
            ("result", result),
            ("notes", notes),
            ("handover_notes", handover or None),
            ("photo_guidance_profile_id", profile_id),
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
        photo_issue_changes = []
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
            issue_value = issue_updates_by_item[index][photo.id]
            issue_delta = changed(bool(photo.is_issue_found), issue_value)
            if issue_delta:
                photo_issue_changes.append({"photo_id": photo.id, **issue_delta})
                photo.is_issue_found = issue_value
                if record.work_items and index == 0:
                    for legacy in record.photos:
                        if legacy.storage_key == photo.storage_key:
                            legacy.is_issue_found = issue_value
        for photo in removed:
            removed_keys.update(
                key for key in (photo.storage_key, photo.thumbnail_key) if key
            )
            wrapper["photos"].remove(photo)
            if record.work_items and index == 0:
                for legacy in list(record.photos):
                    if legacy.storage_key == photo.storage_key:
                        record.photos.remove(legacy)
        for stage, stored, description, is_issue_found in stored_by_item[index]:
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
                        is_issue_found=is_issue_found,
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
                            is_issue_found=is_issue_found,
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
                        is_issue_found=is_issue_found,
                        position=position,
                        uploaded_at=now,
                    )
                )
        if removed or stored_by_item[index] or photo_note_changes or photo_issue_changes:
            changes[f"item_{index + 1}_photos"] = {
                "removed": [photo.original_filename for photo in removed],
                "added": [
                    f"{stage.value}: {stored.original_filename}"
                    for stage, stored, _, _ in stored_by_item[index]
                ],
                "notes_edited": photo_note_changes,
                "issue_markers_edited": photo_issue_changes,
            }

    if removed_wrappers:
        sync_legacy_photo_mirror(record, InstallationPhoto)
    if record.work_items:
        first = record.work_items[0]
        record.result = first.result
        record.notes = first.notes
        record.handover_notes = first.handover_notes

    before_table = serialize_data_rows(record.device_data_rows)
    replacement_rows = []
    for row in saved_rows:
        scope = scope_map[row["scope_position"]]
        replacement_rows.append(
            InstallationDataRow(
                **row,
                project_id=scope["project_id"], project_name=scope["project_name"],
                sub_project_id=scope["sub_project_id"], sub_project_name=scope["sub_project_name"],
                work_site_id=scope["work_site_id"], work_site_name=scope["work_site_name"],
            )
        )
    after_table = serialize_data_rows(replacement_rows)
    if before_table != after_table:
        changes["online_tables"] = {"before": before_table, "after": after_table}
        record.device_data_rows = replacement_rows

    old_names = [p.name for p in record.participants]
    old_user_ids = [p.user_id for p in record.participants]
    new_user_ids = [int(value) for value in selected_participant_ids]
    if old_names != names or old_user_ids != new_user_ids:
        changes["participants"] = {"before": old_names, "after": names}
        record.participants = [
            InstallationParticipant(user_id=user_id, name=name)
            for user_id, name in zip(new_user_ids, names)
        ]

    # Detect the added device row itself, not only a selected Service.  This
    # keeps incomplete additions on the Edit page with their exact validation
    # errors instead of reporting "No changes were made".
    has_additions = bool(form.getlist("item_scope_index"))
    if not changes and not has_additions:
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored, _, _ in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored, _, _ in group],
        )
        flash(request, "No changes were made.")
        if _is_ajax(request):
            return localized_json(
                request,
                {"ok": True, "redirect": f"/installations/records/{record.id}"},
            )
        return RedirectResponse(
            f"/installations/records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    deleted_reports = delete_linked_reports(
        db, ServiceReportRecord.installation_record_id, record.id
    ) if changes else []
    if deleted_reports:
        changes["deleted_linked_reports"] = deleted_reports
    if changes:
        add_revision(db, record_type="installation", record_id=record.id, record_number=record.record_number, action="edited", user=user, changes=changes)
    if has_additions:
        response = await submit_record(request, user, db)
        if response.status_code < 400:
            delete_stored(*removed_keys)
            appended_changes = dict((getattr(request.state, "audit_context", {}) or {}).get("changes") or {})
            set_audit_context(request, action="update", entity_type="installation_record", entity_id=record.id, entity_label=record.record_number, changes={**changes, **appended_changes})
        else:
            db.rollback()
            delete_stored(
                *[stored.storage_key for group in stored_by_item for _, stored, _, _ in group],
                *[stored.thumbnail_key for group in stored_by_item for _, stored, _, _ in group],
            )
        return response
    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored, _, _ in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored, _, _ in group],
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
    set_audit_context(request, action="update", entity_type="installation_record", entity_id=record.id, entity_label=record.record_number, changes=changes)
    flash(request, f"{record.record_number} updated successfully.")
    if _is_ajax(request):
        return localized_json(
            request,
            {"ok": True, "redirect": f"/installations/records/{record.id}"},
        )
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
