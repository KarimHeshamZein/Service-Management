"""Normal Maintenance: grouped device evidence separate from preventive maintenance."""
from __future__ import annotations

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
    next_general_maintenance_record_number,
    paginate,
    parse_date,
    render,
    to_utc_from_display,
)
from ..entry_device_imports import apply_asset_metadata, load_entry_import, validate_current_import_rows
from ..entry_data_tables import parse_entry_data_rows, row_model_values, rows_for_scope
from ..entry_scopes import apply_scope_snapshot, EntryScope, item_scope_indexes, validate_entry_scopes
from ..maintenance_items import active_catalog_items, resolve_maintenance_item
from ..models import (
    DeviceCatalog,
    EvidencePhotoStage,
    GeneralMaintenanceItem,
    GeneralMaintenanceDataRow,
    GeneralMaintenanceParticipant,
    GeneralMaintenancePhoto,
    GeneralMaintenanceRecord,
    MaintenanceResult,
    PricingItem,
    ServiceReportRecord,
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
from ..project_hierarchy import active_project_hierarchy, hierarchy_json, resolve_entry_sub_project
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
MAX_NOTE_LENGTH = 5000
MAX_PARTICIPANTS = 20
MAX_DEVICES_PER_RECORD = 20


def _is_ajax(request: Request) -> bool:
    return request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"


def _projects(db: Session) -> list[Site]:
    return list(db.scalars(select(Site).where(Site.is_active.is_(True)).order_by(Site.name)))


def _work_sites(db: Session) -> list[WorkSite]:
    return list(
        db.scalars(
            select(WorkSite).where(WorkSite.is_active.is_(True)).order_by(WorkSite.name)
        )
    )


def _services(db: Session) -> list[ServiceType]:
    return list(
        db.scalars(
            select(ServiceType).where(ServiceType.is_active.is_(True)).order_by(ServiceType.name)
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
        "active_nav": "general_maintenance",
        "projects": projects,
        "project_hierarchy": hierarchy_json(projects),
        "work_sites": _work_sites(db),
        "services": _services(db),
        "catalog_items": active_catalog_items(db),
        "form": form or {"participants": [], "devices": [{}]},
        "technical_users": technical_user_choices(db, request.state.user),
        "selected_participant_ids": [
            str(value) for value in (form or {}).get("participants", [])
        ],
        "participant_error": (errors or {}).get("participant_ids", ""),
        "errors": errors or {},
        "form_token": form_token or issue_form_token(request),
    }


@router.get("/general-maintenance")
@router.get("/general-maintenance/submit")
def entry(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    return render(request, "general_maintenance_entry.html", _form_context(request, db))


def _new_general_maintenance_record(
    db: Session,
    *,
    scope: EntryScope,
    entries: list[dict],
    imported_rows: list[dict],
    stored_by_item: list[list],
    user: User,
    participant_ids: list[str],
    participants: list[str],
    now,
    record_number: str | None = None,
) -> GeneralMaintenanceRecord:
    first = entries[0]
    project, sub_project, work_site = scope.project, scope.sub_project, scope.site
    record = GeneralMaintenanceRecord(
        record_number=record_number or next_general_maintenance_record_number(db, now),
        site_id=project.id,
        sub_project_id=sub_project.id if sub_project else None,
        sub_project_name=sub_project.name if sub_project else "General",
        work_site_id=work_site.id,
        service_type_id=first["service"].id,
        submitted_by_id=user.id,
        quotation_id=None,
        quotation_number=None,
        project_name=project.name,
        site_name=work_site.name,
        project_address=project.address,
        service_name=first["service"].name,
        team_leader_name=user.full_name,
        result=first["result_value"],
        notes=first["notes"],
        submitted_at=now,
        created_at=now,
    )
    record.participants = [
        GeneralMaintenanceParticipant(user_id=int(user_id), name=name)
        for user_id, name in zip(participant_ids, participants)
    ]
    for index, entry in enumerate(entries):
        service: ServiceType = entry["service"]
        item = GeneralMaintenanceItem(
            installed_device_id=None,
            service_type_id=service.id,
            position=index,
            service_name=service.name,
            device_id=None,
            device_name=service.name,
            manufacturer=None,
            device_model=None,
            serial_number=None,
            location_name=work_site.name,
            imported_from_excel=False,
            result=entry["result_value"],
            notes=entry["notes"],
            issue_description=entry["issue_description"] or None,
            recommendations=entry["recommendations"] or None,
        )
        item.photos = [
            GeneralMaintenancePhoto(
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


@router.post("/general-maintenance/submit")
async def submit_record(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    form = await request.form()
    errors: dict[str, str] = {}
    project_raw = str(form.get("project_id") or "").strip()
    sub_project_raw = str(form.get("sub_project_id") or "").strip()
    device_import_token = str(form.get("device_import_token") or "").strip()
    confirm_asset_overwrites = str(form.get("confirm_asset_overwrites") or "") == "1"
    work_site_raw = str(form.get("work_site_id") or "").strip()
    installed_ids = [str(value).strip() for value in form.getlist("installed_device_id")]
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
        errors["form"] = "This maintenance record was already submitted. Check your records."

    scopes, scope_errors = validate_entry_scopes(form, db, require_quotation=False)
    errors.update(scope_errors)
    data_rows, data_row_errors = parse_entry_data_rows(
        form, scopes, installation=False
    )
    errors.update(data_row_errors)
    project = scopes[0].project if scopes else None
    sub_project = scopes[0].sub_project if scopes else None
    work_site = scopes[0].site if scopes else None

    item_count = max(len(service_ids), len(notes_values), 1)
    if item_count > MAX_DEVICES_PER_RECORD:
        errors["form"] = f"Add at most {MAX_DEVICES_PER_RECORD} devices to one record."
        item_count = MAX_DEVICES_PER_RECORD
    for values in (
        installed_ids,
        service_ids,
        notes_values,
        issue_values,
        recommendation_values,
    ):
        values.extend([""] * (item_count - len(values)))
    scope_count = max(len(form.getlist("project_id")), 1)
    item_scopes, item_scope_errors = item_scope_indexes(form, item_count, scope_count)
    errors.update(item_scope_errors)

    entries: list[dict] = []
    seen_items: set[tuple[str, int]] = set()
    for index in range(item_count):
        suffix = f"_{index}"
        assigned_scope = scopes[item_scopes[index]] if len(scopes) == scope_count else None
        installed_raw = ""
        service_raw = service_ids[index]
        result_raw = str(form.get(f"result_{index}") or "").strip()
        service_id = entity_id(service_raw)
        selected_item = None
        service = db.get(ServiceType, service_id) if service_id is not None else None

        if not service_raw:
            errors[f"service_type_id{suffix}"] = "Select the service performed."
        elif service is None:
            errors[f"service_type_id{suffix}"] = "That service no longer exists."
        elif not service.is_active:
            errors[f"service_type_id{suffix}"] = "That service is deactivated."

        result = None
        try:
            result = MaintenanceResult(result_raw)
        except ValueError:
            errors[f"result{suffix}"] = "Select the maintenance result."
        if result in NEEDS_ISSUE_DETAIL and not issue_values[index]:
            errors[f"issue_description_{index}"] = (
                "Describe the issue or observation for this result."
            )
        notes = notes_values[index]
        if len(notes) > MAX_NOTE_LENGTH:
            errors[f"notes{suffix}"] = f"Keep notes under {MAX_NOTE_LENGTH} characters."

        entries.append(
            {
                "installed_device_id": installed_raw,
                "service_type_id": service_raw,
                "result": result_raw,
                "notes": notes,
                "issue_description": issue_values[index],
                "recommendations": recommendation_values[index],
                "selected_item": selected_item,
                "service": service,
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
            entry_kind="maintenance",
            project_id=scope.project.id,
            sub_project_id=scope.sub_project.id if scope.sub_project else None,
            site_id=scope.site.id,
        )
        error_key = "device_import_token" if scope.index == 0 else f"device_import_token_scope_{scope.index}"
        current_error = "" if import_error else validate_current_import_rows(
            db, scope_rows, entry_kind="maintenance", project_id=scope.project.id, site_id=scope.site.id
        )
        indexes = [index for index, entry in enumerate(entries) if entry["scope_index"] == scope.index]
        if import_error:
            errors[error_key] = import_error
        elif current_error:
            errors[error_key] = current_error
        elif len(scope_rows) != len(indexes):
            errors[error_key] = "The Excel preview and maintenance item count do not match. Preview the file again."
        else:
            for index, imported in zip(indexes, scope_rows):
                entry_item = entries[index]
                imported_by_item[index] = imported
                if entry_item["selected_item"] is None or entry_item["selected_item"].device_id != imported.get("device_id"):
                    errors[f"installed_device_id_{index}"] = "This item no longer matches the Excel preview. Preview the file again."
            if any(row.get("asset_conflicts") for row in scope_rows) and not confirm_asset_overwrites:
                errors[error_key] = "Confirm replacement of the existing Installed Asset values shown in the Excel preview."
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
            upload for upload in form.getlist(f"photos_{index}")
            if isinstance(upload, UploadFile) and upload.filename
        ]
        before_descriptions = [str(value).strip() for value in form.getlist(f"before_photo_descriptions_{index}")]
        after_descriptions = [str(value).strip() for value in form.getlist(f"after_photo_descriptions_{index}")]
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
            errors[f"photos_{index}"] = "Attach at least one proof photo."
        elif len(before_uploads) > settings.max_photos_per_record:
            errors[f"before_photos_{index}"] = "Attach at most 10 before photos."
        elif len(after_uploads) > settings.max_photos_per_record:
            errors[f"after_photos_{index}"] = "Attach at most 10 after photos."
        elif len(legacy_uploads) > settings.max_photos_per_record:
            errors[f"photos_{index}"] = "Attach at most 10 photos."
        elif any(len(description) > MAX_NOTE_LENGTH for description in before_descriptions + after_descriptions):
            errors[f"photos_{index}"] = f"Keep each photo description under {MAX_NOTE_LENGTH} characters."

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
                    *[s.storage_key for group in stored_by_item for _, s, _, _ in group],
                    *[s.thumbnail_key for group in stored_by_item for _, s, _, _ in group],
                )
                stored_by_item = [[] for _ in range(item_count)]
                break

    payload = {
        "project_id": project_raw,
        "sub_project_id": sub_project_raw,
        "device_import_token": device_import_token,
        "work_site_id": work_site_raw,
        "devices": [
            {
                key: entry[key]
                for key in (
                    "installed_device_id",
                    "service_type_id",
                    "result",
                    "notes",
                    "issue_description",
                    "recommendations",
                )
            }
            for entry in entries
        ],
        "participants": participant_ids,
    }
    if errors:
        token = issue_form_token(request)
        if _is_ajax(request):
            return localized_json(request,
                {"ok": False, "errors": errors, "form_token": token}, status_code=422
            )
        return render(
            request,
            "general_maintenance_entry.html",
            _form_context(request, db, payload, errors, token),
            status_code=422,
        )

    if not consume_form_token(request, form.get("form_token")):
        delete_stored(
            *[s.storage_key for group in stored_by_item for _, s, _, _ in group],
            *[s.thumbnail_key for group in stored_by_item for _, s, _, _ in group],
        )
        message = "This maintenance record was already submitted. Check your records."
        token = issue_form_token(request)
        if _is_ajax(request):
            return localized_json(request,
                {"ok": False, "errors": {"form": message}, "form_token": token},
                status_code=422,
            )
        return render(
            request,
            "general_maintenance_entry.html",
            _form_context(request, db, payload, {"form": message}, token),
            status_code=422,
        )

    assert project and work_site
    assert all(e["service"] and e["result_value"] for e in entries)
    all_entries = entries
    all_stored_by_item = stored_by_item
    first_indexes = [index for index, entry in enumerate(all_entries) if entry["scope_index"] == 0]
    entries = [all_entries[index] for index in first_indexes]
    stored_by_item = [all_stored_by_item[index] for index in first_indexes]
    imported_rows = [imported_by_item[index] for index in first_indexes] if device_import_token else []
    first = entries[0]
    for imported in (row for row in imported_by_item if row):
        apply_asset_metadata(db, imported, allow_overwrite=confirm_asset_overwrites)
    now = utcnow()
    record = GeneralMaintenanceRecord(
        record_number=next_general_maintenance_record_number(db, now),
        site_id=project.id,
        sub_project_id=sub_project.id if sub_project else None,
        sub_project_name=sub_project.name if sub_project else "General",
        work_site_id=work_site.id,
        service_type_id=first["service"].id,
        submitted_by_id=user.id,
        quotation_id=None,
        quotation_number=None,
        project_name=project.name,
        site_name=work_site.name,
        project_address=project.address,
        service_name=first["service"].name,
        team_leader_name=user.full_name,
        result=first["result_value"],
        notes=first["notes"],
        submitted_at=now,
        created_at=now,
    )
    record.participants = [
        GeneralMaintenanceParticipant(user_id=int(user_id), name=name)
        for user_id, name in zip(participant_ids, participants)
    ]
    for index, entry in enumerate(entries):
        service: ServiceType = entry["service"]
        item = GeneralMaintenanceItem(
            installed_device_id=None,
            service_type_id=service.id,
            position=index,
            service_name=service.name,
            device_id=None,
            device_name=service.name,
            manufacturer=None,
            device_model=None,
            serial_number=None,
            location_name=work_site.name,
            imported_from_excel=False,
            result=entry["result_value"],
            notes=entry["notes"],
            issue_description=entry["issue_description"] or None,
            recommendations=entry["recommendations"] or None,
        )
        item.photos = [
            GeneralMaintenancePhoto(
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
        indexes = [index for index, entry in enumerate(all_entries) if entry["scope_index"] == scope.index]
        additional = _new_general_maintenance_record(
            db,
            scope=scope,
            entries=[all_entries[index] for index in indexes],
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
        additional.work_items = []
        for scoped_item in scoped_items:
            scoped_item.position = len(record.work_items)
            apply_scope_snapshot(scoped_item, scope)
            record.work_items.append(scoped_item)
    record.device_data_rows = [
        GeneralMaintenanceDataRow(**row_model_values(row, scopes[row["scope_index"]]))
        for row in data_rows
    ]
    try:
        db.commit()
    except Exception:
        db.rollback()
        delete_stored(
            *[s.storage_key for group in all_stored_by_item for _, s, _, _ in group],
            *[s.thumbnail_key for group in all_stored_by_item for _, s, _, _ in group],
        )
        message = "The maintenance record could not be saved. Try again."
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
            "general_maintenance_entry.html",
            _form_context(request, db, payload, {"form": message}),
            status_code=500,
        )
    db.refresh(record)
    record_numbers = [record.record_number]
    flash(request, f"Maintenance record {record.record_number} saved.")
    target = f"/general-maintenance/records/{record.id}"
    if _is_ajax(request):
        return localized_json(request,
            {"ok": True, "redirect": target, "record_number": record.record_number, "record_numbers": record_numbers},
            status_code=201,
        )
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/general-maintenance/records")
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

    conditions = []
    if user.is_customer:
        conditions.append(
            GeneralMaintenanceRecord.site_id.in_(user.assigned_project_ids)
        )
    if q:
        like = f"%{q}%"
        conditions.append(
            or_(
                GeneralMaintenanceRecord.record_number.ilike(like),
                GeneralMaintenanceRecord.project_name.ilike(like),
                GeneralMaintenanceRecord.site_name.ilike(like),
                GeneralMaintenanceRecord.team_leader_name.ilike(like),
                GeneralMaintenanceRecord.work_items.any(
                    or_(
                        GeneralMaintenanceItem.service_name.ilike(like),
                        GeneralMaintenanceItem.device_name.ilike(like),
                        GeneralMaintenanceItem.manufacturer.ilike(like),
                        GeneralMaintenanceItem.device_model.ilike(like),
                        GeneralMaintenanceItem.serial_number.ilike(like),
                        GeneralMaintenanceItem.notes.ilike(like),
                        GeneralMaintenanceItem.issue_description.ilike(like),
                        GeneralMaintenanceItem.recommendations.ilike(like),
                    )
                ),
            )
        )
    if (project_value := entity_id(project_id)) is not None:
        conditions.append(GeneralMaintenanceRecord.site_id == project_value)
    if (work_site_value := entity_id(work_site_id)) is not None:
        conditions.append(GeneralMaintenanceRecord.work_site_id == work_site_value)
    if (service_value := entity_id(service_id)) is not None:
        conditions.append(
            GeneralMaintenanceRecord.work_items.any(
                GeneralMaintenanceItem.service_type_id == service_value
            )
        )
    selected_item = (
        db.get(PricingItem, entity_id(device_id)) if entity_id(device_id) is not None else None
    )
    if selected_item is not None and selected_item.device_catalog_id is not None:
        device_value = selected_item.device_catalog_id
        conditions.append(
            GeneralMaintenanceRecord.work_items.any(
                GeneralMaintenanceItem.device_id == device_value
            )
        )
    if user.can_view_all_records and (
        leader_value := entity_id(leader_id)
    ) is not None:
        conditions.append(GeneralMaintenanceRecord.submitted_by_id == leader_value)
    if result:
        try:
            selected = MaintenanceResult(result)
            conditions.append(
                GeneralMaintenanceRecord.work_items.any(
                    GeneralMaintenanceItem.result == selected
                )
            )
        except ValueError:
            result = ""
    if date_from:
        conditions.append(
            GeneralMaintenanceRecord.submitted_at
            >= to_utc_from_display(dt.combine(date_from, dt_time.min))
        )
    if date_to:
        conditions.append(
            GeneralMaintenanceRecord.submitted_at
            < to_utc_from_display(dt.combine(date_to, dt_time.min) + timedelta(days=1))
        )

    stmt = select(GeneralMaintenanceRecord).where(*conditions)
    count_stmt = select(func.count(GeneralMaintenanceRecord.id)).where(*conditions)
    total = int(db.scalar(count_stmt) or 0)
    page_info = paginate(total, page, settings.page_size)
    records = list(
        db.scalars(
            stmt.options(selectinload(GeneralMaintenanceRecord.work_items))
            .order_by(
                GeneralMaintenanceRecord.submitted_at.desc(),
                GeneralMaintenanceRecord.id.desc(),
            )
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
        "general_maintenance_records.html",
        {
            "active_nav": "general_maintenance_records",
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
            "services": list(db.scalars(select(ServiceType).order_by(ServiceType.name))),
            "devices": list(
                db.scalars(select(PricingItem).order_by(PricingItem.name, PricingItem.model))
            ),
            "leaders": (
                list(db.scalars(select(User).order_by(User.full_name)))
                if user.can_view_all_records
                else []
            ),
        },
    )


def _load_record(
    db: Session, record_id: int, user: User
) -> GeneralMaintenanceRecord:
    record = db.get(
        GeneralMaintenanceRecord,
        record_id,
        options=[
            selectinload(GeneralMaintenanceRecord.participants),
            selectinload(GeneralMaintenanceRecord.work_items).selectinload(
                GeneralMaintenanceItem.photos
            ),
        ],
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Maintenance record not found")
    project_ids = {item.project_id or record.site_id for item in record.work_items} or {record.site_id}
    if not all(user.can_access_project(project_id) for project_id in project_ids):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "This record is outside your assigned Projects",
        )
    return record


@router.get("/general-maintenance/records/{record_id}")
def record_details(
    record_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = _load_record(db, record_id, user)
    return render(
        request,
        "general_maintenance_detail.html",
        {
            "active_nav": "general_maintenance_records",
            "record": record,
            "revisions": revisions_for(db, "maintenance", record.id),
            "linked_reports": linked_reports(
                db, ServiceReportRecord.maintenance_record_id, record.id
            ),
        },
    )


def _edit_items(record: GeneralMaintenanceRecord) -> list[dict]:
    return [
        {
            "data": item,
            "photos": item.photos,
            "photo_groups": grouped_photos(item.photos),
            "photo_media_path": "/media/general-maintenance-photo",
            "device_label": f"{item.device_name} — {item.device_model}",
            "service_label": item.service_name,
            "serial_number": item.serial_number,
        }
        for item in record.work_items
    ]


def _edit_context(
    request: Request,
    db: Session,
    record: GeneralMaintenanceRecord,
    error: str = "",
    selected_participant_ids: list[str] | None = None,
) -> dict:
    choices = technical_user_choices(db, request.state.user)
    if selected_participant_ids is None:
        selected_participant_ids = selected_ids_for_names(
            choices, (participant.name for participant in record.participants)
        )
    return {
        "active_nav": "general_maintenance_records",
        "record": record,
        "record_kind": "maintenance",
        "record_label": "Maintenance record",
        "project_name": record.project_name,
        "edit_items": _edit_items(record),
        "technical_users": choices,
        "selected_participant_ids": selected_participant_ids,
        "participant_error": error if "Technical user" in error else "",
        "results": list(MaintenanceResult),
        "detail_url": f"/general-maintenance/records/{record.id}",
        "edit_url": f"/general-maintenance/records/{record.id}/edit",
        "error": error,
    }


@router.get("/general-maintenance/records/{record_id}/edit")
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


@router.post("/general-maintenance/records/{record_id}/edit")
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
        description_updates, description_error = existing_photo_descriptions(
            form, wrapper["photos"], maximum=MAX_NOTE_LENGTH
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
            maximum=MAX_NOTE_LENGTH,
        )
        after_descriptions, description_error = new_photo_descriptions(
            form,
            f"add_after_photo_descriptions_{index}",
            len(after_uploads),
            maximum=MAX_NOTE_LENGTH,
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
        before_count = sum(photo.stage == EvidencePhotoStage.BEFORE for photo in kept)
        after_count = sum(photo.stage == EvidencePhotoStage.AFTER for photo in kept)
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
        photo_note_changes = []
        for photo in wrapper["photos"]:
            if photo.id in removals[index]:
                continue
            value = description_updates_by_item[index][photo.id] or None
            delta = changed(photo.description, value)
            if delta:
                photo_note_changes.append({"photo_id": photo.id, **delta})
                photo.description = value
        for photo in removed:
            removed_keys.update(
                key for key in (photo.storage_key, photo.thumbnail_key) if key
            )
            item.photos.remove(photo)
        for stage, stored, description in stored_by_item[index]:
            position = sum(photo.stage == stage for photo in wrapper["photos"])
            item.photos.append(
                GeneralMaintenancePhoto(
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

    old_names = [p.name for p in record.participants]
    old_user_ids = [p.user_id for p in record.participants]
    new_user_ids = [int(value) for value in selected_participant_ids]
    if old_names != names or old_user_ids != new_user_ids:
        changes["participants"] = {"before": old_names, "after": names}
        record.participants = [
            GeneralMaintenanceParticipant(user_id=user_id, name=name)
            for user_id, name in zip(new_user_ids, names)
        ]
    if not changes:
        delete_stored(
            *[stored.storage_key for group in stored_by_item for _, stored, _ in group],
            *[stored.thumbnail_key for group in stored_by_item for _, stored, _ in group],
        )
        flash(request, "No changes were made.")
        return RedirectResponse(
            f"/general-maintenance/records/{record.id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    add_revision(
        db,
        record_type="maintenance",
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
        f"/general-maintenance/records/{record.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post(
    "/general-maintenance/records/{record_id}/delete",
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
        for photo in [p for item in record.work_items for p in item.photos]
        for key in (photo.storage_key, photo.thumbnail_key)
        if key
    }
    record_number = record.record_number
    deleted_reports = delete_linked_reports(
        db, ServiceReportRecord.maintenance_record_id, record.id
    )
    add_revision(
        db,
        record_type="maintenance",
        record_id=record.id,
        record_number=record_number,
        action="deleted",
        user=user,
        changes={"record": "Permanently deleted by Administrator"},
    )
    db.delete(record)
    db.commit()
    delete_stored(*keys)
    report_note = (
        f" {len(deleted_reports)} linked generated report(s) were also deleted."
        if deleted_reports
        else ""
    )
    flash(request, f"{record_number} permanently deleted.{report_note}")
    return RedirectResponse(
        "/general-maintenance/records",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/media/general-maintenance-photo/{photo_id}")
def photo(
    photo_id: int,
    request: Request,
    size: str = "full",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    photo_row = db.get(GeneralMaintenancePhoto, photo_id)
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
