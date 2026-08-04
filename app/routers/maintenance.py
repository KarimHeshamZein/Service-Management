"""The Preventive Maintenance module: submit evidence, list it, review it."""
from __future__ import annotations

from datetime import datetime as dt, time as dt_time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.datastructures import UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin, require_record_submitter
from ..helpers import (
    entity_id,
    flash,
    localized_json,
    next_record_number,
    paginate,
    parse_date,
    render,
    to_utc_from_display,
)
from ..models import (
    DeviceCatalog,
    EvidencePhotoStage,
    InstalledDevice,
    InstallationRecord,
    MaintenanceParticipant,
    MaintenanceItemPhoto,
    MaintenancePhoto,
    MaintenanceRecord,
    MaintenanceRecordAdditionalDevice,
    MaintenanceRecordDevice,
    MaintenanceRecordItem,
    PricingItem,
    MaintenanceRecordSite,
    MaintenanceResult,
    NEEDS_ISSUE_DETAIL,
    ServiceType,
    Site,
    User,
    WorkSite,
    utcnow,
)
from ..participant_selection import (
    selected_ids_for_names,
    technical_user_choices,
    validate_participant_ids,
)
from ..quotation_references import quotation_choices, resolve_quotation_reference
from ..record_mutations import add_revision, changed, revisions_for
from ..security import (
    consume_form_token,
    csrf_valid,
    form_token_available,
    issue_form_token,
)
from ..uploads import UploadError, delete_stored, resolve_storage_path, store_image

router = APIRouter()

MAX_NOTE_LENGTH = 5000
MAX_PARTICIPANTS = 20
MAX_DEVICES_PER_RECORD = 20


def _is_ajax(request: Request) -> bool:
    return request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"


def _active_sites(db: Session) -> list[Site]:
    return list(db.scalars(select(Site).where(Site.is_active.is_(True)).order_by(Site.name)))


def _active_services(db: Session) -> list[ServiceType]:
    return list(
        db.scalars(select(ServiceType).where(ServiceType.is_active.is_(True)).order_by(ServiceType.name))
    )


def _active_work_sites(db: Session) -> list[WorkSite]:
    return list(
        db.scalars(
            select(WorkSite).where(WorkSite.is_active.is_(True)).order_by(WorkSite.name)
        )
    )


def _installed_devices(db: Session) -> list[InstalledDevice]:
    return list(
        db.scalars(
            select(InstalledDevice)
            .options(
                selectinload(InstalledDevice.work_site_evidence),
                selectinload(InstalledDevice.installation_record).selectinload(
                    InstallationRecord.work_site_evidence
                ),
            )
            .where(InstalledDevice.is_active.is_(True))
            .order_by(
                InstalledDevice.customer_name,
                InstalledDevice.site_name,
                InstalledDevice.device_name,
            )
        )
    )


def _form_context(
    request: Request,
    db: Session,
    form: dict | None = None,
    errors: dict | None = None,
    form_token: str | None = None,
) -> dict:
    return {
        "active_nav": "maintenance",
        "projects": _active_sites(db),
        "work_sites": _active_work_sites(db),
        "services": _active_services(db),
        "installed_devices": _installed_devices(db),
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


# ---------------------------------------------------------------- submit


@router.get("/maintenance")
def maintenance_module(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    """The Preventive Maintenance module opens directly on its data-entry form."""
    return render(request, "preventive_maintenance_entry.html", _form_context(request, db))


@router.get("/maintenance/submit")
def submit_form(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    return render(request, "preventive_maintenance_entry.html", _form_context(request, db))


@router.post("/maintenance/submit")
async def submit_record(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    form = await request.form()
    errors: dict[str, str] = {}

    project_id_raw = (form.get("project_id") or form.get("site_id") or "").strip()
    quotation_number_raw = str(form.get("quotation_number") or "").strip()
    work_site_id_raw = (form.get("work_site_id") or "").strip()
    installed_device_ids = [
        str(value).strip() for value in form.getlist("installed_device_id")
    ]
    service_ids = [str(value).strip() for value in form.getlist("service_type_id")]
    notes_values = [str(value).strip() for value in form.getlist("notes")]
    issue_values = [str(value).strip() for value in form.getlist("issue_description")]
    recommendation_values = [
        str(value).strip() for value in form.getlist("recommendations")
    ]
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
        errors["form"] = "This preventive maintenance record was already submitted. Check your records list."

    project: Site | None = None
    if not project_id_raw:
        errors["project_id"] = "Select the project."
    else:
        project_id = entity_id(project_id_raw)
        project = db.get(Site, project_id) if project_id is not None else None
        if project is None:
            errors["project_id"] = "That project no longer exists."
        elif not project.is_active:
            errors["project_id"] = "That project is deactivated and cannot receive new records."

    quotation, quotation_error = resolve_quotation_reference(
        db,
        quotation_number_raw,
        project.id if project else None,
    )
    if quotation_error:
        errors["quotation_number"] = quotation_error

    work_site: WorkSite | None = None
    if not work_site_id_raw:
        errors["work_site_id"] = "Select the site where the maintenance was performed."
    else:
        work_site_id = entity_id(work_site_id_raw)
        work_site = (
            db.get(WorkSite, work_site_id) if work_site_id is not None else None
        )
        if work_site is None:
            errors["work_site_id"] = "That site no longer exists."
        elif not work_site.is_active:
            errors["work_site_id"] = "That site is deactivated and cannot receive new records."

    item_count = max(len(installed_device_ids), len(service_ids), len(notes_values), 1)
    if item_count > MAX_DEVICES_PER_RECORD:
        errors["form"] = f"Add at most {MAX_DEVICES_PER_RECORD} devices to one record."
        item_count = MAX_DEVICES_PER_RECORD
    for values in (
        installed_device_ids,
        service_ids,
        notes_values,
        issue_values,
        recommendation_values,
    ):
        values.extend([""] * (item_count - len(values)))

    device_entries: list[dict] = []
    seen_devices: set[int] = set()
    for index in range(item_count):
        installed_raw = installed_device_ids[index]
        service_raw = service_ids[index]
        result_raw = (
            str(form.get(f"result_{index}") or form.get("result") or "").strip()
            if index == 0
            else str(form.get(f"result_{index}") or "").strip()
        )
        notes = notes_values[index]
        issue_description = issue_values[index]
        recommendations = recommendation_values[index]
        suffix = f"_{index}"

        installed_id = entity_id(installed_raw)
        installed_device = (
            db.get(InstalledDevice, installed_id)
            if installed_id is not None
            else None
        )
        if not installed_raw:
            errors[f"installed_device_id{suffix}"] = "Select the device you maintained."
        elif installed_device is None:
            errors[f"installed_device_id{suffix}"] = "That installed device no longer exists."
        elif not installed_device.is_active:
            errors[f"installed_device_id{suffix}"] = "That installed device is deactivated."
        elif project and installed_device.site_id != project.id:
            errors[f"installed_device_id{suffix}"] = (
                "Select a device installed for that project."
            )
        elif work_site and installed_device.effective_work_site_id != work_site.id:
            errors[f"installed_device_id{suffix}"] = "Select a device installed at that site."
        elif installed_device.id in seen_devices:
            errors[f"installed_device_id{suffix}"] = (
                "Each device can appear only once in this record."
            )
        if installed_device:
            seen_devices.add(installed_device.id)

        service_id = entity_id(service_raw)
        service = db.get(ServiceType, service_id) if service_id is not None else None
        if not service_raw:
            errors[f"service_type_id{suffix}"] = "Select the service performed."
        elif service is None:
            errors[f"service_type_id{suffix}"] = "That service no longer exists."
        elif not service.is_active:
            errors[f"service_type_id{suffix}"] = "That service is deactivated."

        result: MaintenanceResult | None = None
        try:
            result = MaintenanceResult(result_raw)
        except ValueError:
            errors[f"result{suffix}"] = "Select the maintenance result."
        if result in NEEDS_ISSUE_DETAIL and not issue_description:
            errors[f"issue_description_{index}"] = (
                "Describe the issue or observation for this result."
            )

        if not notes:
            errors[f"notes{suffix}"] = "Describe the maintenance you performed."
        elif len(notes) > MAX_NOTE_LENGTH:
            errors[f"notes{suffix}"] = f"Keep notes under {MAX_NOTE_LENGTH} characters."

        device_entries.append(
            {
                "installed_device_id": installed_raw,
                "service_type_id": service_raw,
                "result": result_raw,
                "notes": notes,
                "issue_description": issue_description,
                "recommendations": recommendations,
                "installed_device": installed_device,
                "service": service,
                "result_value": result,
            }
        )

    uploads_by_item: list[list[tuple[EvidencePhotoStage, UploadFile]]] = []
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
        uploads = [
            *((EvidencePhotoStage.BEFORE, upload) for upload in before_uploads),
            *((EvidencePhotoStage.AFTER, upload) for upload in after_uploads),
            *((EvidencePhotoStage.LEGACY, upload) for upload in legacy_uploads),
        ]
        uploads_by_item.append(uploads)
        if not uploads:
            errors[f"photos_{index}"] = "Attach at least one proof photo."
        elif len(before_uploads) > settings.max_photos_per_record:
            errors[f"before_photos_{index}"] = "Attach at most 10 before photos."
        elif len(after_uploads) > settings.max_photos_per_record:
            errors[f"after_photos_{index}"] = "Attach at most 10 after photos."
        elif len(legacy_uploads) > settings.max_photos_per_record:
            errors[f"photos_{index}"] = "Attach at most 10 photos."

    stored_by_item: list[list] = [[] for _ in range(item_count)]
    if not errors:
        for index, uploads in enumerate(uploads_by_item):
            for stage, upload in uploads:
                data = await upload.read()
                try:
                    stored_by_item[index].append(
                        (stage, store_image(upload.filename, data))
                    )
                except UploadError as exc:
                    errors[f"photos_{index}"] = str(exc)
                    break
            if errors:
                delete_stored(
                    *[
                        stored.storage_key
                        for item_stored in stored_by_item
                        for _, stored in item_stored
                    ],
                    *[
                        stored.thumbnail_key
                        for item_stored in stored_by_item
                        for _, stored in item_stored
                    ],
                )
                stored_by_item = [[] for _ in range(item_count)]
                break

    if errors:
        payload = {
            "project_id": project_id_raw,
            "quotation_number": quotation_number_raw,
            "work_site_id": work_site_id_raw,
            "devices": [
                {
                    "installed_device_id": entry["installed_device_id"],
                    "service_type_id": entry["service_type_id"],
                    "result": entry["result"],
                    "notes": entry["notes"],
                    "issue_description": entry["issue_description"],
                    "recommendations": entry["recommendations"],
                }
                for entry in device_entries
            ],
            "participants": participant_ids,
        }
        fresh_token = issue_form_token(request)
        if _is_ajax(request):
            # A fresh token, or the retry would be rejected as a duplicate.
            return localized_json(request,
                {"ok": False, "errors": errors, "form_token": fresh_token}, status_code=422
            )
        return render(
            request,
            "preventive_maintenance_entry.html",
            _form_context(request, db, payload, errors, fresh_token),
            status_code=422,
        )

    if not consume_form_token(request, form.get("form_token")):
        delete_stored(
            *[s.storage_key for group in stored_by_item for _, s in group],
            *[s.thumbnail_key for group in stored_by_item for _, s in group],
        )
        message = (
            "This preventive maintenance record was already submitted. "
            "Check your records list."
        )
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
            "preventive_maintenance_entry.html",
            _form_context(request, db, payload, {"form": message}, fresh_token),
            status_code=422,
        )

    assert project and work_site
    assert quotation
    assert all(
        entry["service"] and entry["installed_device"] and entry["result_value"]
        for entry in device_entries
    )
    first = device_entries[0]
    first_service: ServiceType = first["service"]
    first_device: InstalledDevice = first["installed_device"]
    now = utcnow()
    record = MaintenanceRecord(
        record_number=next_record_number(db, now),
        site_id=project.id,
        service_type_id=first_service.id,
        submitted_by_id=user.id,
        quotation_id=quotation.id,
        quotation_number=quotation.quotation_number,
        site_name=work_site.name,
        customer_name=project.name,
        site_address=project.address,
        service_name=first_service.name,
        team_leader_name=user.full_name,
        result=first["result_value"],
        notes=first["notes"],
        issue_description=first["issue_description"] or None,
        recommendations=first["recommendations"] or None,
        submitted_at=now,          # server clock only
        created_at=now,
    )
    record.participants = [
        MaintenanceParticipant(user_id=int(user_id), name=name)
        for user_id, name in zip(participant_ids, participants)
    ]
    record.photos = [
        MaintenancePhoto(
            storage_key=s.storage_key,
            thumbnail_key=s.thumbnail_key,
            original_filename=s.original_filename,
            content_type=s.content_type,
            file_size=s.file_size,
            uploaded_at=now,
        )
        for _, s in stored_by_item[0]
    ]
    record.device_evidence = MaintenanceRecordDevice(
        installed_device_id=first_device.id,
        device_id=first_device.device_id,
        device_name=first_device.device_name,
        manufacturer=first_device.manufacturer,
        device_model=first_device.device_model,
        serial_number=first_device.serial_number,
    )
    record.work_site_evidence = MaintenanceRecordSite(
        site_id=work_site.id,
        site_name=work_site.name,
    )
    for entry in device_entries[1:]:
        item_device: InstalledDevice = entry["installed_device"]
        item_service: ServiceType = entry["service"]
        record.additional_device_evidence.append(
            MaintenanceRecordAdditionalDevice(
                installed_device_id=item_device.id,
                service_type_id=item_service.id,
                service_name=item_service.name,
                device_id=item_device.device_id,
                device_name=item_device.device_name,
                manufacturer=item_device.manufacturer,
                device_model=item_device.device_model,
                serial_number=item_device.serial_number,
            )
        )
    for index, entry in enumerate(device_entries):
        item_device: InstalledDevice = entry["installed_device"]
        item_service: ServiceType = entry["service"]
        item = MaintenanceRecordItem(
            installed_device_id=item_device.id,
            service_type_id=item_service.id,
            position=index,
            service_name=item_service.name,
            device_id=item_device.device_id,
            device_name=item_device.device_name,
            manufacturer=item_device.manufacturer,
            device_model=item_device.device_model,
            serial_number=item_device.serial_number,
            result=entry["result_value"],
            notes=entry["notes"],
            issue_description=entry["issue_description"] or None,
            recommendations=entry["recommendations"] or None,
        )
        item.photos = [
            MaintenanceItemPhoto(
                storage_key=stored.storage_key,
                thumbnail_key=stored.thumbnail_key,
                original_filename=stored.original_filename,
                content_type=stored.content_type,
                file_size=stored.file_size,
                stage=stage,
                uploaded_at=now,
            )
            for stage, stored in stored_by_item[index]
        ]
        record.work_items.append(item)

    db.add(record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_stored(
            *[
                stored.storage_key
                for item_stored in stored_by_item
                for _, stored in item_stored
            ],
            *[
                stored.thumbnail_key
                for item_stored in stored_by_item
                for _, stored in item_stored
            ],
        )
        message = "The record could not be saved. Try again."
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
            "preventive_maintenance_entry.html",
            _form_context(request, db, payload, {"form": message}),
            status_code=500,
        )

    db.refresh(record)
    flash(request, f"Preventive maintenance record {record.record_number} saved.")
    target = f"/maintenance/records/{record.id}"
    if _is_ajax(request):
        return localized_json(request,
            {"ok": True, "redirect": target, "record_number": record.record_number}, status_code=201
        )
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


# ----------------------------------------------------------------- list


@router.get("/maintenance/records")
def records_list(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    params = dict(request.query_params)
    q = (params.get("q") or "").strip()
    project_id = (params.get("project_id") or params.get("site_id") or "").strip()
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

    stmt = select(MaintenanceRecord)
    count_stmt = select(func.count(MaintenanceRecord.id))
    conditions = []

    if user.is_customer:
        conditions.append(MaintenanceRecord.site_id.in_(user.assigned_project_ids))

    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                MaintenanceRecord.record_number.ilike(like),
                MaintenanceRecord.site_name.ilike(like),
                MaintenanceRecord.customer_name.ilike(like),
                MaintenanceRecord.service_name.ilike(like),
                MaintenanceRecord.team_leader_name.ilike(like),
                MaintenanceRecord.device_evidence.has(
                    or_(
                        MaintenanceRecordDevice.device_name.ilike(like),
                        MaintenanceRecordDevice.manufacturer.ilike(like),
                        MaintenanceRecordDevice.device_model.ilike(like),
                        MaintenanceRecordDevice.serial_number.ilike(like),
                    )
                ),
                MaintenanceRecord.additional_device_evidence.any(
                    or_(
                        MaintenanceRecordAdditionalDevice.service_name.ilike(like),
                        MaintenanceRecordAdditionalDevice.device_name.ilike(like),
                        MaintenanceRecordAdditionalDevice.manufacturer.ilike(like),
                        MaintenanceRecordAdditionalDevice.device_model.ilike(like),
                        MaintenanceRecordAdditionalDevice.serial_number.ilike(like),
                    )
                ),
                MaintenanceRecord.work_items.any(
                    or_(
                        MaintenanceRecordItem.service_name.ilike(like),
                        MaintenanceRecordItem.device_name.ilike(like),
                        MaintenanceRecordItem.manufacturer.ilike(like),
                        MaintenanceRecordItem.device_model.ilike(like),
                        MaintenanceRecordItem.serial_number.ilike(like),
                        MaintenanceRecordItem.notes.ilike(like),
                        MaintenanceRecordItem.issue_description.ilike(like),
                        MaintenanceRecordItem.recommendations.ilike(like),
                    )
                ),
            )
        )
    if (project_value := entity_id(project_id)) is not None:
        conditions.append(MaintenanceRecord.site_id == project_value)
    if (work_site_value := entity_id(work_site_id)) is not None:
        conditions.append(
            MaintenanceRecord.work_site_evidence.has(
                MaintenanceRecordSite.site_id == work_site_value
            )
        )
    if (service_value := entity_id(service_id)) is not None:
        conditions.append(
            or_(
                MaintenanceRecord.service_type_id == service_value,
                MaintenanceRecord.additional_device_evidence.any(
                    MaintenanceRecordAdditionalDevice.service_type_id == service_value
                ),
                MaintenanceRecord.work_items.any(
                    MaintenanceRecordItem.service_type_id == service_value
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
                MaintenanceRecord.device_evidence.has(
                    MaintenanceRecordDevice.device_id == device_value
                ),
                MaintenanceRecord.additional_device_evidence.any(
                    MaintenanceRecordAdditionalDevice.device_id == device_value
                ),
                MaintenanceRecord.work_items.any(
                    MaintenanceRecordItem.device_id == device_value
                ),
            )
        )
    if user.can_view_all_records and (
        leader_value := entity_id(leader_id)
    ) is not None:
        conditions.append(MaintenanceRecord.submitted_by_id == leader_value)
    if result:
        try:
            selected_result = MaintenanceResult(result)
            conditions.append(
                or_(
                    MaintenanceRecord.result == selected_result,
                    MaintenanceRecord.work_items.any(
                        MaintenanceRecordItem.result == selected_result
                    ),
                )
            )
        except ValueError:
            result = ""
    if date_from:
        conditions.append(
            MaintenanceRecord.submitted_at
            >= to_utc_from_display(dt.combine(date_from, dt_time.min))
        )
    if date_to:
        conditions.append(
            MaintenanceRecord.submitted_at
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
                selectinload(MaintenanceRecord.photos),
                selectinload(MaintenanceRecord.device_evidence),
                selectinload(MaintenanceRecord.additional_device_evidence),
                selectinload(MaintenanceRecord.work_items).selectinload(
                    MaintenanceRecordItem.photos
                ),
                selectinload(MaintenanceRecord.work_site_evidence),
            )
            .order_by(MaintenanceRecord.submitted_at.desc(), MaintenanceRecord.id.desc())
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
        "maintenance_records.html",
        {
            "active_nav": "records",
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


# --------------------------------------------------------------- details


def _load_record(db: Session, record_id: int, user: User) -> MaintenanceRecord:
    record = db.get(
        MaintenanceRecord,
        record_id,
        options=[
            selectinload(MaintenanceRecord.photos),
            selectinload(MaintenanceRecord.participants),
            selectinload(MaintenanceRecord.device_evidence),
            selectinload(MaintenanceRecord.additional_device_evidence),
            selectinload(MaintenanceRecord.work_items).selectinload(
                MaintenanceRecordItem.photos
            ),
            selectinload(MaintenanceRecord.work_site_evidence),
        ],
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preventive maintenance record not found")
    if not user.can_access_project(record.site_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This record is outside your assigned Projects",
        )
    return record


@router.get("/maintenance/records/{record_id}")
def record_details(
    record_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _load_record(db, record_id, user)
    return render(
        request,
        "maintenance_detail.html",
        {
            "active_nav": "records",
            "record": record,
            "revisions": revisions_for(db, "preventive_maintenance", record.id),
        },
    )


def _edit_items(record: MaintenanceRecord) -> list[dict]:
    if record.work_items:
        return [
            {
                "data": item,
                "photos": item.photos,
                "device_label": f"{item.device_name} — {item.device_model}",
                "service_label": item.service_name,
                "serial_number": item.serial_number,
            }
            for item in record.work_items
        ]
    device = record.device_evidence
    return [
        {
            "data": record,
            "photos": record.photos,
            "device_label": (
                f"{device.device_name} — {device.device_model}"
                if device
                else "Legacy device"
            ),
            "service_label": record.service_name,
            "serial_number": device.serial_number if device else "",
        }
    ]


def _edit_context(
    request: Request,
    db: Session,
    record: MaintenanceRecord,
    error: str = "",
    selected_participant_ids: list[str] | None = None,
) -> dict:
    choices = technical_user_choices(db, request.state.user)
    if selected_participant_ids is None:
        selected_participant_ids = selected_ids_for_names(
            choices, record.participant_names
        )
    return {
        "active_nav": "records",
        "record": record,
        "record_kind": "preventive_maintenance",
        "record_label": "Preventive maintenance record",
        "project_name": record.customer_name,
        "edit_items": _edit_items(record),
        "technical_users": choices,
        "selected_participant_ids": selected_participant_ids,
        "participant_error": error if "Technical user" in error else "",
        "results": list(MaintenanceResult),
        "detail_url": f"/maintenance/records/{record.id}",
        "edit_url": f"/maintenance/records/{record.id}/edit",
        "error": error,
    }


@router.get("/maintenance/records/{record_id}/edit")
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


@router.post("/maintenance/records/{record_id}/edit")
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
    parsed: list[tuple[MaintenanceResult, str, str, str]] = []
    removals: list[set[int]] = []
    uploads_by_item: list[list[tuple[EvidencePhotoStage, UploadFile]]] = []
    error = ""
    for index, wrapper in enumerate(wrappers):
        try:
            result = MaintenanceResult(str(form.get(f"result_{index}") or ""))
        except ValueError:
            error = f"Select a result for item {index + 1}."
            break
        notes = str(form.get(f"notes_{index}") or "").strip()
        issue = str(form.get(f"issue_description_{index}") or "").strip()
        recommendations = str(form.get(f"recommendations_{index}") or "").strip()
        if not notes or len(notes) > MAX_NOTE_LENGTH:
            error = f"Enter valid notes for item {index + 1}."
            break
        if result in NEEDS_ISSUE_DETAIL and not issue:
            error = f"Describe the issue for item {index + 1}."
            break
        if len(issue) > MAX_NOTE_LENGTH or len(recommendations) > MAX_NOTE_LENGTH:
            error = f"Keep item {index + 1} details under {MAX_NOTE_LENGTH} characters."
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
        uploads = [
            *((EvidencePhotoStage.BEFORE, upload) for upload in before_uploads),
            *((EvidencePhotoStage.AFTER, upload) for upload in after_uploads),
            *((EvidencePhotoStage.LEGACY, upload) for upload in legacy_uploads),
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
        parsed.append((result, notes, issue, recommendations))
        removals.append(remove_ids)
        uploads_by_item.append(uploads)

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
            for stage, upload in uploads:
                stored_by_item[index].append(
                    (stage, store_image(upload.filename, await upload.read()))
                )
    except UploadError as exc:
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored in group],
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
        result, notes, issue, recommendations = values
        for field, value in (
            ("result", result),
            ("notes", notes),
            ("issue_description", issue or None),
            ("recommendations", recommendations or None),
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
        for photo in removed:
            removed_keys.update(
                key for key in (photo.storage_key, photo.thumbnail_key) if key
            )
            wrapper["photos"].remove(photo)
            if record.work_items and index == 0:
                for legacy in list(record.photos):
                    if legacy.storage_key == photo.storage_key:
                        record.photos.remove(legacy)
        for stage, stored in stored_by_item[index]:
            if record.work_items:
                item.photos.append(
                    MaintenanceItemPhoto(
                        storage_key=stored.storage_key,
                        thumbnail_key=stored.thumbnail_key,
                        original_filename=stored.original_filename,
                        content_type=stored.content_type,
                        file_size=stored.file_size,
                        stage=stage,
                        uploaded_at=now,
                    )
                )
                if index == 0:
                    record.photos.append(
                        MaintenancePhoto(
                            storage_key=stored.storage_key,
                            thumbnail_key=stored.thumbnail_key,
                            original_filename=stored.original_filename,
                            content_type=stored.content_type,
                            file_size=stored.file_size,
                            uploaded_at=now,
                        )
                    )
            else:
                record.photos.append(
                    MaintenancePhoto(
                        storage_key=stored.storage_key,
                        thumbnail_key=stored.thumbnail_key,
                        original_filename=stored.original_filename,
                        content_type=stored.content_type,
                        file_size=stored.file_size,
                        uploaded_at=now,
                    )
                )
        if removed or stored_by_item[index]:
            changes[f"item_{index + 1}_photos"] = {
                "removed": [photo.original_filename for photo in removed],
                "added": [
                    f"{stage.value}: {stored.original_filename}"
                    for stage, stored in stored_by_item[index]
                ],
            }

    if record.work_items:
        first = record.work_items[0]
        record.result = first.result
        record.notes = first.notes
        record.issue_description = first.issue_description
        record.recommendations = first.recommendations

    old_names = record.participant_names
    old_user_ids = [participant.user_id for participant in record.participants]
    new_user_ids = [int(value) for value in selected_participant_ids]
    if old_names != names or old_user_ids != new_user_ids:
        changes["participants"] = {"before": old_names, "after": names}
        record.participants = [
            MaintenanceParticipant(user_id=user_id, name=name)
            for user_id, name in zip(new_user_ids, names)
        ]

    if not changes:
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored in group],
        )
        flash(request, "No changes were made.")
        return RedirectResponse(
            f"/maintenance/records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    add_revision(
        db,
        record_type="preventive_maintenance",
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
            *[stored.storage_key for group in stored_by_item for _, stored in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored in group],
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
        f"/maintenance/records/{record.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/maintenance/records/{record_id}/delete",
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
    keys = {
        key
        for photo in [*record.photos, *[p for item in record.work_items for p in item.photos]]
        for key in (photo.storage_key, photo.thumbnail_key)
        if key
    }
    record_number = record.record_number
    add_revision(
        db,
        record_type="preventive_maintenance",
        record_id=record.id,
        record_number=record_number,
        action="deleted",
        user=user,
        changes={"record": "Permanently deleted by Administrator"},
    )
    db.delete(record)
    db.commit()
    delete_stored(*keys)
    flash(request, f"{record_number} permanently deleted.")
    return RedirectResponse(
        "/maintenance/records", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/media/photo/{photo_id}")
def photo(
    photo_id: int,
    request: Request,
    size: str = "full",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo_row = db.get(MaintenancePhoto, photo_id)
    if photo_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")

    _load_record(db, photo_row.record_id, user)  # permission check

    key = photo_row.thumbnail_key if size == "thumb" and photo_row.thumbnail_key else photo_row.storage_key
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


@router.get("/media/maintenance-item-photo/{photo_id}")
def item_photo(
    photo_id: int,
    request: Request,
    size: str = "full",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo_row = db.get(MaintenanceItemPhoto, photo_id)
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
