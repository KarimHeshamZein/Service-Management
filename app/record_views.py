"""Shared filtered record views for the Records and Reports modules."""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.orm import Session, selectinload

from .helpers import paginate
from .models import (
    GeneralMaintenanceItem,
    GeneralMaintenanceParticipant,
    GeneralMaintenanceRecord,
    InstalledDevice,
    InstallationParticipant,
    InstallationRecord,
    InstallationRecordAdditionalDevice,
    InstallationRecordItem,
    MaintenanceRecord,
    MaintenanceRecordAdditionalDevice,
    MaintenanceRecordDevice,
    MaintenanceRecordItem,
    MaintenanceParticipant,
    User,
)

VALID_RECORD_TYPES = {"", "maintenance", "general_maintenance", "installation"}
RECORD_TYPE_ORDER = {
    "maintenance": 0,
    "installation": 1,
    "general_maintenance": 2,
}


def normalize_record_filters(q: str = "", record_type: str = "") -> dict[str, str]:
    normalized_type = record_type.strip()
    if normalized_type not in VALID_RECORD_TYPES:
        normalized_type = ""
    return {
        "q": q.strip(),
        "type": normalized_type,
    }


def _photo_view(photo: Any) -> dict[str, str | None]:
    stage = getattr(photo, "stage", None)
    return {
        "storage_key": photo.storage_key,
        "thumbnail_key": photo.thumbnail_key,
        "original_filename": photo.original_filename,
        "stage": stage.value if stage is not None else "legacy",
    }


def _device_label(name: str, model: str, serial: str) -> str:
    return f"{name} - {model} | {serial}"


def _maintenance_items(record: MaintenanceRecord) -> list[dict[str, Any]]:
    if record.work_items:
        return [
            {
                "service_name": item.service_name,
                "device_name": item.device_name,
                "device_model": item.device_model,
                "serial_number": item.serial_number,
                "result": item.result,
                "notes": item.notes,
                "issue_description": item.issue_description,
                "recommendations": item.recommendations,
                "handover_notes": None,
                "warranty_start": None,
                "photos": [_photo_view(photo) for photo in item.photos],
            }
            for item in record.work_items
        ]

    device = record.device_evidence
    return [
        {
            "service_name": record.service_name,
            "device_name": device.device_name if device else "Legacy device",
            "device_model": device.device_model if device else "",
            "serial_number": device.serial_number if device else "",
            "result": record.result,
            "notes": record.notes,
            "issue_description": record.issue_description,
            "recommendations": record.recommendations,
            "handover_notes": None,
            "warranty_start": None,
            "photos": [_photo_view(photo) for photo in record.photos],
        }
    ]


def _installation_items(record: InstallationRecord) -> list[dict[str, Any]]:
    if record.work_items:
        return [
            {
                "service_name": item.service_name,
                "device_name": item.device_name,
                "device_model": item.device_model,
                "serial_number": item.serial_number,
                "result": item.result,
                "notes": item.notes,
                "issue_description": None,
                "recommendations": None,
                "handover_notes": item.handover_notes,
                "warranty_start": item.warranty_start,
                "photos": [_photo_view(photo) for photo in item.photos],
            }
            for item in record.work_items
        ]

    device = record.installed_device
    return [
        {
            "service_name": record.service_name,
            "device_name": device.device_name if device else record.equipment_model,
            "device_model": device.device_model if device else record.equipment_model,
            "serial_number": (
                device.serial_number if device else record.serial_number
            ),
            "result": record.result,
            "notes": record.notes,
            "issue_description": None,
            "recommendations": None,
            "handover_notes": record.handover_notes,
            "warranty_start": record.warranty_start,
            "photos": [_photo_view(photo) for photo in record.photos],
        }
    ]


def _general_maintenance_items(
    record: GeneralMaintenanceRecord,
) -> list[dict[str, Any]]:
    return [
        {
            "service_name": item.service_name,
            "device_name": item.device_name,
            "device_model": item.device_model,
            "serial_number": item.serial_number,
            "result": item.result,
            "notes": item.notes,
            "issue_description": item.issue_description,
            "recommendations": item.recommendations,
            "handover_notes": None,
            "warranty_start": None,
            "photos": [_photo_view(photo) for photo in item.photos],
        }
        for item in record.work_items
    ]


def _common_conditions(
    model,
    participant_model,
    user: User,
    *,
    technician_id: int | None = None,
    start_at=None,
    end_before=None,
    project_id: int | None = None,
) -> list[Any]:
    conditions: list[Any] = []
    if user.is_customer:
        conditions.append(model.site_id.in_(user.assigned_project_ids))
    if technician_id is not None:
        conditions.append(
            or_(
                model.submitted_by_id == technician_id,
                model.participants.any(participant_model.user_id == technician_id),
            )
        )
    if start_at is not None:
        conditions.append(model.submitted_at >= start_at)
    if end_before is not None:
        conditions.append(model.submitted_at < end_before)
    if project_id is not None:
        conditions.append(model.site_id == project_id)
    return conditions


def _maintenance_conditions(user: User, q: str, **extra) -> list[Any]:
    conditions = _common_conditions(
        MaintenanceRecord,
        MaintenanceParticipant,
        user,
        **extra,
    )
    if not q:
        return conditions
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
                    MaintenanceRecordDevice.device_model.ilike(like),
                    MaintenanceRecordDevice.serial_number.ilike(like),
                )
            ),
            MaintenanceRecord.additional_device_evidence.any(
                or_(
                    MaintenanceRecordAdditionalDevice.service_name.ilike(like),
                    MaintenanceRecordAdditionalDevice.device_name.ilike(like),
                    MaintenanceRecordAdditionalDevice.device_model.ilike(like),
                    MaintenanceRecordAdditionalDevice.serial_number.ilike(like),
                )
            ),
            MaintenanceRecord.work_items.any(
                or_(
                    MaintenanceRecordItem.service_name.ilike(like),
                    MaintenanceRecordItem.device_name.ilike(like),
                    MaintenanceRecordItem.device_model.ilike(like),
                    MaintenanceRecordItem.serial_number.ilike(like),
                    MaintenanceRecordItem.notes.ilike(like),
                    MaintenanceRecordItem.issue_description.ilike(like),
                    MaintenanceRecordItem.recommendations.ilike(like),
                )
            ),
        )
    )
    return conditions


def _installation_conditions(user: User, q: str, **extra) -> list[Any]:
    conditions = _common_conditions(
        InstallationRecord,
        InstallationParticipant,
        user,
        **extra,
    )
    if not q:
        return conditions
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
                    InstallationRecordItem.device_model.ilike(like),
                    InstallationRecordItem.serial_number.ilike(like),
                    InstallationRecordItem.notes.ilike(like),
                    InstallationRecordItem.handover_notes.ilike(like),
                )
            ),
        )
    )
    return conditions


def _general_conditions(user: User, q: str, **extra) -> list[Any]:
    conditions = _common_conditions(
        GeneralMaintenanceRecord,
        GeneralMaintenanceParticipant,
        user,
        **extra,
    )
    if not q:
        return conditions
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
                    GeneralMaintenanceItem.device_model.ilike(like),
                    GeneralMaintenanceItem.serial_number.ilike(like),
                    GeneralMaintenanceItem.notes.ilike(like),
                    GeneralMaintenanceItem.issue_description.ilike(like),
                    GeneralMaintenanceItem.recommendations.ilike(like),
                )
            ),
        )
    )
    return conditions


def _sources(user: User, q: str, record_type: str, **extra):
    available = (
        ("maintenance", MaintenanceRecord, _maintenance_conditions),
        ("installation", InstallationRecord, _installation_conditions),
        ("general_maintenance", GeneralMaintenanceRecord, _general_conditions),
    )
    return [
        (key, model, conditions(user, q, **extra))
        for key, model, conditions in available
        if record_type in {"", key}
    ]


def count_record_views(
    db: Session,
    user: User,
    *,
    q: str = "",
    record_type: str = "",
    **extra,
) -> int:
    filters = normalize_record_filters(q, record_type)
    sources = _sources(
        user,
        filters["q"],
        filters["type"],
        **extra,
    )
    selects = [
        select(model.id.label("record_id")).where(*conditions)
        for _, model, conditions in sources
    ]
    combined = union_all(*selects).subquery()
    return int(db.scalar(select(func.count()).select_from(combined)) or 0)


def load_record_page(
    db: Session,
    user: User,
    *,
    q: str = "",
    record_type: str = "",
    page: int,
    per_page: int,
    include_evidence: bool = False,
    **extra,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    filters = normalize_record_filters(q, record_type)
    sources = _sources(
        user,
        filters["q"],
        filters["type"],
        **extra,
    )
    selections = [
        select(
            literal(key).label("record_key"),
            literal(RECORD_TYPE_ORDER[key]).label("type_order"),
            model.id.label("record_id"),
            model.submitted_at.label("submitted_at"),
        ).where(*conditions)
        for key, model, conditions in sources
    ]
    combined = union_all(*selections).subquery()
    total = int(db.scalar(select(func.count()).select_from(combined)) or 0)
    page_info = paginate(total, page, per_page)
    page_rows = db.execute(
        select(combined)
        .order_by(
            combined.c.submitted_at.desc(),
            combined.c.record_id.desc(),
            combined.c.type_order.asc(),
        )
        .offset(page_info["offset"])
        .limit(page_info["per_page"])
    )
    selected: dict[str, list[int]] = {key: [] for key, _, _ in sources}
    for row in page_rows:
        selected[row.record_key].append(row.record_id)
    records = load_record_views(
        db,
        user,
        q=filters["q"],
        record_type=filters["type"],
        include_evidence=include_evidence,
        selected_ids=selected,
        **extra,
    )
    return records, page_info


def load_record_views(
    db: Session,
    user: User,
    *,
    q: str = "",
    record_type: str = "",
    include_evidence: bool = False,
    selected_ids: dict[str, list[int]] | None = None,
    technician_id: int | None = None,
    start_at=None,
    end_before=None,
    project_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return one normalized, permission-scoped set used by Records and Reports."""
    filters = normalize_record_filters(q, record_type)
    q = filters["q"]
    record_type = filters["type"]
    records: list[dict[str, Any]] = []
    extra = {
        "technician_id": technician_id,
        "start_at": start_at,
        "end_before": end_before,
        "project_id": project_id,
    }

    maintenance_ids = (
        selected_ids.get("maintenance", []) if selected_ids is not None else None
    )
    if record_type in {"", "maintenance"} and maintenance_ids != []:
        options = [
            selectinload(MaintenanceRecord.device_evidence),
            selectinload(MaintenanceRecord.additional_device_evidence),
            selectinload(MaintenanceRecord.work_items),
        ]
        if include_evidence:
            options.extend(
                [
                    selectinload(MaintenanceRecord.photos),
                    selectinload(MaintenanceRecord.participants),
                    selectinload(MaintenanceRecord.work_site_evidence),
                    selectinload(MaintenanceRecord.work_items).selectinload(
                        MaintenanceRecordItem.photos
                    ),
                ]
            )
        stmt = select(MaintenanceRecord).options(*options)
        conditions = _maintenance_conditions(user, q, **extra)
        if maintenance_ids is not None:
            conditions.append(MaintenanceRecord.id.in_(maintenance_ids))
        if conditions:
            stmt = stmt.where(*conditions)
        for record in db.scalars(stmt):
            device = record.device_evidence
            first_item = record.work_items[0] if record.work_items else None
            device_total = (
                len(record.work_items)
                if record.work_items
                else ((1 if device else 0) + len(record.additional_device_evidence))
            )
            records.append(
                {
                    "id": record.id,
                    "project_id": record.site_id,
                    "submitted_by_id": record.submitted_by_id,
                    "record_number": record.record_number,
                    "quotation_number": record.quotation_number,
                    "record_key": "maintenance",
                    "record_type": "Preventive maintenance",
                    "site_name": record.site_name,
                    "work_site_name": (
                        record.work_site_evidence.site_name
                        if include_evidence and record.work_site_evidence
                        else ""
                    ),
                    "customer_name": record.customer_name,
                    "address": record.site_address,
                    "service_name": record.service_name,
                    "result": record.result,
                    "team_leader_name": record.team_leader_name,
                    "submitted_at": record.submitted_at,
                    "device": (
                        _device_label(
                            first_item.device_name,
                            first_item.device_model,
                            first_item.serial_number,
                        )
                        if first_item
                        else (
                            _device_label(
                                device.device_name,
                                device.device_model,
                                device.serial_number,
                            )
                            if device
                            else "-"
                        )
                    ),
                    "device_total": device_total,
                    "href": f"/maintenance/records/{record.id}",
                    "participants": (
                        [person.name for person in record.participants]
                        if include_evidence
                        else []
                    ),
                    "participant_user_ids": (
                        [
                            person.user_id
                            for person in record.participants
                            if person.user_id is not None
                        ]
                        if include_evidence
                        else []
                    ),
                    "items": (
                        _maintenance_items(record) if include_evidence else []
                    ),
                }
            )

    installation_ids = (
        selected_ids.get("installation", []) if selected_ids is not None else None
    )
    if record_type in {"", "installation"} and installation_ids != []:
        options = [
            selectinload(InstallationRecord.installed_device),
            selectinload(InstallationRecord.additional_devices).selectinload(
                InstallationRecordAdditionalDevice.installed_device
            ),
            selectinload(InstallationRecord.work_items),
        ]
        if include_evidence:
            options.extend(
                [
                    selectinload(InstallationRecord.photos),
                    selectinload(InstallationRecord.participants),
                    selectinload(InstallationRecord.work_site_evidence),
                    selectinload(InstallationRecord.work_items).selectinload(
                        InstallationRecordItem.photos
                    ),
                ]
            )
        stmt = select(InstallationRecord).options(*options)
        conditions = _installation_conditions(user, q, **extra)
        if installation_ids is not None:
            conditions.append(InstallationRecord.id.in_(installation_ids))
        if conditions:
            stmt = stmt.where(*conditions)
        for record in db.scalars(stmt):
            device = record.installed_device
            first_item = record.work_items[0] if record.work_items else None
            device_total = (
                len(record.work_items)
                if record.work_items
                else ((1 if device else 0) + len(record.additional_devices))
            )
            records.append(
                {
                    "id": record.id,
                    "project_id": record.site_id,
                    "submitted_by_id": record.submitted_by_id,
                    "record_number": record.record_number,
                    "quotation_number": record.quotation_number,
                    "record_key": "installation",
                    "record_type": "Installation",
                    "site_name": record.site_name,
                    "work_site_name": (
                        record.work_site_evidence.site_name
                        if include_evidence and record.work_site_evidence
                        else ""
                    ),
                    "customer_name": record.customer_name,
                    "address": record.site_address,
                    "service_name": record.service_name,
                    "result": record.result,
                    "team_leader_name": record.team_leader_name,
                    "submitted_at": record.submitted_at,
                    "device": (
                        _device_label(
                            first_item.device_name,
                            first_item.device_model,
                            first_item.serial_number,
                        )
                        if first_item
                        else (
                            _device_label(
                                device.device_name,
                                device.device_model,
                                device.serial_number,
                            )
                            if device
                            else f"{record.equipment_model} | {record.serial_number}"
                        )
                    ),
                    "device_total": device_total,
                    "href": f"/installations/records/{record.id}",
                    "participants": (
                        [person.name for person in record.participants]
                        if include_evidence
                        else []
                    ),
                    "participant_user_ids": (
                        [
                            person.user_id
                            for person in record.participants
                            if person.user_id is not None
                        ]
                        if include_evidence
                        else []
                    ),
                    "items": (
                        _installation_items(record) if include_evidence else []
                    ),
                }
            )

    general_ids = (
        selected_ids.get("general_maintenance", [])
        if selected_ids is not None
        else None
    )
    if record_type in {"", "general_maintenance"} and general_ids != []:
        options = [selectinload(GeneralMaintenanceRecord.work_items)]
        if include_evidence:
            options.extend(
                [
                    selectinload(GeneralMaintenanceRecord.participants),
                    selectinload(GeneralMaintenanceRecord.work_items).selectinload(
                        GeneralMaintenanceItem.photos
                    ),
                ]
            )
        stmt = select(GeneralMaintenanceRecord).options(*options)
        conditions = _general_conditions(user, q, **extra)
        if general_ids is not None:
            conditions.append(GeneralMaintenanceRecord.id.in_(general_ids))
        if conditions:
            stmt = stmt.where(*conditions)
        for record in db.scalars(stmt):
            first_item = record.work_items[0] if record.work_items else None
            device = (
                _device_label(
                    first_item.device_name,
                    first_item.device_model,
                    first_item.serial_number,
                )
                if first_item
                else "-"
            )
            records.append(
                {
                    "id": record.id,
                    "project_id": record.site_id,
                    "submitted_by_id": record.submitted_by_id,
                    "record_number": record.record_number,
                    "quotation_number": record.quotation_number,
                    "record_key": "general_maintenance",
                    "record_type": "Maintenance",
                    "site_name": record.site_name,
                    "work_site_name": record.site_name,
                    "customer_name": record.project_name,
                    "address": record.project_address,
                    "service_name": record.service_name,
                    "result": record.result,
                    "team_leader_name": record.team_leader_name,
                    "submitted_at": record.submitted_at,
                    "device": device,
                    "device_total": len(record.work_items),
                    "href": f"/general-maintenance/records/{record.id}",
                    "participants": (
                        [person.name for person in record.participants]
                        if include_evidence
                        else []
                    ),
                    "participant_user_ids": (
                        [
                            person.user_id
                            for person in record.participants
                            if person.user_id is not None
                        ]
                        if include_evidence
                        else []
                    ),
                    "items": (
                        _general_maintenance_items(record)
                        if include_evidence
                        else []
                    ),
                }
            )

    records.sort(
        key=lambda record: (record["submitted_at"], record["id"]),
        reverse=True,
    )
    return records
