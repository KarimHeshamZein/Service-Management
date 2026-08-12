"""Saved, hierarchy-aware customer reports assembled from service records."""
from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin, require_record_submitter
from ..helpers import entity_id, flash, parse_date, render, to_display, to_utc_from_display
from ..models import (
    CustomerProjectAssignment,
    InstalledDevice,
    ServiceReport,
    ServiceReportCounter,
    ServiceReportRecord,
    ServiceReportTechnician,
    ServiceReportType,
    Site,
    User,
    UserRole,
    utcnow,
)
from ..participant_selection import technical_user_choices, validate_participant_ids
from ..record_views import load_record_views
from ..security import csrf_valid
from ..structured_report_pdf import build_structured_report_pdf


router = APIRouter()

MAX_REPORT_NAME = 200
MAX_REPORT_NOTES = 5000
MAX_REPORT_TECHNICIANS = 20

REPORT_CONFIG: dict[str, dict[str, Any]] = {
    "installation": {
        "type": ServiceReportType.INSTALLATION,
        "record_key": "installation",
        "title": "Installation Reports",
        "singular": "Installation Report",
        "title_key": "ui.installation.reports.title",
        "singular_key": "ui.installation.report.title",
        "prefix": "IR",
        "active_nav": "installation_reports",
        "link_field": "installation_record_id",
    },
    "maintenance": {
        "type": ServiceReportType.MAINTENANCE,
        "record_key": "general_maintenance",
        "title": "Maintenance Reports",
        "singular": "Maintenance Report",
        "title_key": "ui.maintenance.reports.title",
        "singular_key": "ui.maintenance.report.title",
        "prefix": "MR",
        "active_nav": "maintenance_reports",
        "link_field": "maintenance_record_id",
    },
    "preventive-maintenance": {
        "type": ServiceReportType.PREVENTIVE_MAINTENANCE,
        "record_key": "maintenance",
        "title": "Preventive Maintenance Reports",
        "singular": "Preventive Maintenance Report",
        "title_key": "ui.preventive.maintenance.reports.title",
        "singular_key": "ui.preventive.maintenance.report.title",
        "prefix": "PMR",
        "active_nav": "preventive_maintenance_reports",
        "link_field": "preventive_record_id",
    },
}


def _config(report_slug: str) -> dict[str, Any]:
    config = REPORT_CONFIG.get(report_slug)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report type not found.")
    return config


def _team_leader_choices(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.is_active.is_(True),
                User.role.in_((UserRole.ADMIN, UserRole.TECHNICAL)),
            )
            .order_by(User.full_name, User.username)
        )
    )


def _available_record_views(
    db: Session,
    user: User,
    config: dict[str, Any],
    *,
    record_number: str = "",
    start_at: datetime | None = None,
    end_before: datetime | None = None,
) -> list[dict[str, Any]]:
    records = load_record_views(
        db,
        user,
        q=record_number,
        record_type=config["record_key"],
        include_evidence=False,
        start_at=start_at,
        end_before=end_before,
    )
    return sorted(
        records,
        key=lambda record: (
            record["customer_name"].casefold(),
            record["sub_project_name"].casefold(),
            record["work_site_name"].casefold(),
            record["submitted_at"],
            record["id"],
        ),
    )


def _report_time_filter(request: Request) -> tuple[dict[str, str], dict[str, str], datetime | None, datetime | None]:
    values = {
        "record_number": str(request.query_params.get("record_number") or "").strip(),
        "from_at": str(request.query_params.get("from_at") or "").strip(),
        "to_at": str(request.query_params.get("to_at") or "").strip(),
    }
    errors: dict[str, str] = {}

    def parse(name: str) -> datetime | None:
        raw = values[name]
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            errors[name] = "Enter a valid date and time including seconds."
            return None

    start_local = parse("from_at")
    end_local = parse("to_at")
    if start_local and end_local and end_local < start_local:
        errors["to_at"] = "To must be the same as or later than From."
    if errors:
        return values, errors, None, None
    start_at = to_utc_from_display(start_local) if start_local else None
    # The query helper uses an exclusive upper boundary. Advancing one second
    # makes a user-entered second inclusive without broadening later times.
    end_before = (
        to_utc_from_display(end_local) + timedelta(seconds=1)
        if end_local
        else None
    )
    return values, errors, start_at, end_before


def _project_lookup(db: Session, project_ids: set[int]) -> dict[int, Site]:
    if not project_ids:
        return {}
    projects = db.scalars(
        select(Site)
        .options(
            selectinload(Site.customer_assignments).selectinload(
                CustomerProjectAssignment.user
            )
        )
        .where(Site.id.in_(project_ids))
    )
    return {project.id: project for project in projects}


def _customer_names(project: Site | None) -> str:
    if project is None:
        return ""
    return ", ".join(
        assignment.user.full_name for assignment in project.customer_assignments
    )


def _record_project_ids(records: list[dict[str, Any]]) -> set[int]:
    ids: set[int] = set()
    for record in records:
        ids.add(int(record["project_id"]))
        ids.update(
            int(section["project_id"])
            for section in record.get("site_sections", [])
            if section.get("project_id") is not None
        )
    return ids


def _record_tree(records: list[dict[str, Any]], projects: dict[int, Site]) -> list[dict[str, Any]]:
    mains: OrderedDict[int, dict[str, Any]] = OrderedDict()
    for record in records:
        sections = record.get("site_sections") or [
            {
                "project_id": record["project_id"],
                "project_name": record["customer_name"],
                "sub_project_id": record["sub_project_id"],
                "sub_project_name": record["sub_project_name"],
                "work_site_id": record["work_site_id"],
                "work_site_name": record["work_site_name"] or record["site_name"],
            }
        ]
        for section in sections:
            project_id = int(section.get("project_id") or record["project_id"])
            project_name = section.get("project_name") or record["customer_name"]
            sub_project_id = section.get("sub_project_id") or record["sub_project_id"]
            sub_project_name = section.get("sub_project_name") or record["sub_project_name"]
            site_id = section.get("work_site_id") or record["work_site_id"]
            site_name = section.get("work_site_name") or record["work_site_name"] or record["site_name"]
            main = mains.setdefault(
                project_id,
                {
                    "id": project_id,
                    "name": project_name,
                    "customer_names": _customer_names(projects.get(project_id)),
                    "sub_projects": OrderedDict(),
                    "record_ids": set(),
                },
            )
            sub_key = sub_project_id or f"legacy-{sub_project_name}"
            sub = main["sub_projects"].setdefault(
                sub_key,
                {
                    "id": sub_project_id,
                    "name": sub_project_name,
                    "sites": OrderedDict(),
                    "record_ids": set(),
                },
            )
            site = sub["sites"].setdefault(
                site_id,
                {
                    "id": site_id,
                    "name": site_name,
                    "records": [],
                },
            )
            site["records"].append(
                {
                    **record,
                    "project_id": project_id,
                    "customer_name": project_name,
                    "sub_project_id": sub_project_id,
                    "sub_project_name": sub_project_name,
                    "work_site_id": site_id,
                    "work_site_name": site_name,
                }
            )
            sub["record_ids"].add(record["id"])
            main["record_ids"].add(record["id"])
    result = []
    for main in mains.values():
        main["record_count"] = len(main.pop("record_ids"))
        main["sub_projects"] = list(main["sub_projects"].values())
        for sub in main["sub_projects"]:
            sub["record_count"] = len(sub.pop("record_ids"))
            sub["sites"] = list(sub["sites"].values())
        result.append(main)
    return result


def _report_form_context(
    request: Request,
    db: Session,
    user: User,
    report_slug: str,
    *,
    form: dict[str, Any] | None = None,
    errors: dict[str, str] | None = None,
    import_rows: list[Any] | None = None,
    import_token: str = "",
    structural_errors: list[str] | None = None,
) -> dict[str, Any]:
    config = _config(report_slug)
    time_filter, time_filter_errors, start_at, end_before = _report_time_filter(request)
    records = _available_record_views(
        db,
        user,
        config,
        record_number=time_filter["record_number"],
        start_at=start_at,
        end_before=end_before,
    )
    projects = _project_lookup(db, _record_project_ids(records))
    selected = [str(value) for value in (form or {}).get("record_ids", [])]
    return {
        "active_nav": config["active_nav"],
        "report_slug": report_slug,
        "report_config": config,
        "record_tree": _record_tree(records, projects),
        "available_record_count": len(records),
        "time_filter": time_filter,
        "time_filter_errors": time_filter_errors,
        "form": form or {
            "name": "",
            "report_date": utcnow().date().isoformat(),
            "team_leader_id": str(user.id),
            "technician_ids": [],
            "record_ids": [],
            "notes": "",
            "include_device_data": False,
        },
        "selected_record_ids": selected,
        "team_leaders": _team_leader_choices(db),
        "technical_users": technical_user_choices(db, user),
        "errors": errors or {},
        "import_rows": import_rows or [],
        "import_token": import_token,
        "import_structural_errors": structural_errors or [],
        "import_valid_count": sum(not row.errors for row in (import_rows or [])),
        "import_warning_count": sum(bool(row.warnings) for row in (import_rows or [])),
        "import_error_count": sum(bool(row.errors) for row in (import_rows or [])),
    }


def _parse_report_form(form: Any) -> dict[str, Any]:
    return {
        "name": str(form.get("name") or "").strip(),
        "report_date": str(form.get("report_date") or "").strip(),
        "team_leader_id": str(form.get("team_leader_id") or "").strip(),
        "technician_ids": [str(value).strip() for value in form.getlist("technician_ids")],
        "record_ids": [str(value).strip() for value in form.getlist("record_ids")],
        "notes": str(form.get("notes") or "").strip(),
        "include_device_data": str(form.get("include_device_data") or "").lower()
        in {"1", "true", "on", "yes"},
    }


def _validate_report_form(
    request: Request,
    db: Session,
    user: User,
    config: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, str], User | None, list[str], list[str], list[dict[str, Any]]]:
    errors: dict[str, str] = {}
    if not csrf_valid(request, request.state.submitted_form.get("csrf_token")):
        errors["form"] = "Your session expired. Reload the page and try again."
    if not payload["name"]:
        errors["name"] = "Enter a report name."
    elif len(payload["name"]) > MAX_REPORT_NAME:
        errors["name"] = f"Keep the report name under {MAX_REPORT_NAME} characters."
    report_date = parse_date(payload["report_date"])
    if report_date is None:
        errors["report_date"] = "Select a valid report date."
    if len(payload["notes"]) > MAX_REPORT_NOTES:
        errors["notes"] = f"Keep notes under {MAX_REPORT_NOTES} characters."

    team_leader_id = entity_id(payload["team_leader_id"])
    team_leader = db.get(User, team_leader_id) if team_leader_id else None
    if team_leader is None or not team_leader.is_active or not team_leader.can_submit_records:
        errors["team_leader_id"] = "Select an active Team Leader."

    technician_names, technician_ids, technician_error = validate_participant_ids(
        db,
        user,
        payload["technician_ids"],
        maximum=MAX_REPORT_TECHNICIANS,
    )
    if technician_error:
        errors["technician_ids"] = technician_error

    submitted_ids = list(dict.fromkeys(payload["record_ids"]))
    if not submitted_ids:
        errors["record_ids"] = "Select at least one service record."
        return errors, team_leader, technician_names, technician_ids, []
    if len(submitted_ids) > settings.max_pdf_records:
        errors["record_ids"] = f"Select at most {settings.max_pdf_records} records."
        return errors, team_leader, technician_names, technician_ids, []
    if any(entity_id(value) is None for value in submitted_ids):
        errors["record_ids"] = "One selected record is invalid. Review the selection."
        return errors, team_leader, technician_names, technician_ids, []
    record_ids = [int(value) for value in submitted_ids]
    selected = {config["record_key"]: record_ids}
    records = load_record_views(
        db,
        user,
        record_type=config["record_key"],
        include_evidence=False,
        selected_ids=selected,
    )
    if {record["id"] for record in records} != set(record_ids):
        errors["record_ids"] = (
            "One selected record is unavailable or outside your authorized Projects. "
            "Review the selection."
        )
        return errors, team_leader, technician_names, technician_ids, []
    if any(record["work_site_id"] is None for record in records):
        errors["record_ids"] = "One selected legacy record has no Site assignment. Update that record first."
    records.sort(
        key=lambda record: (
            record["customer_name"].casefold(),
            record["sub_project_name"].casefold(),
            record["work_site_name"].casefold(),
            record["submitted_at"],
            record["id"],
        )
    )
    payload["record_ids"] = [str(record["id"]) for record in records]
    payload["report_date_value"] = report_date
    return errors, team_leader, technician_names, technician_ids, records


def _next_report_number(db: Session, config: dict[str, Any], when: datetime) -> str:
    year = to_display(when).year
    report_type = config["type"]
    db.execute(
        insert(ServiceReportCounter)
        .values(report_type=report_type, year=year, last_sequence=0)
        .on_conflict_do_nothing(
            index_elements=[ServiceReportCounter.report_type, ServiceReportCounter.year]
        )
    )
    counter = db.execute(
        select(ServiceReportCounter)
        .where(
            ServiceReportCounter.report_type == report_type,
            ServiceReportCounter.year == year,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    counter.last_sequence += 1
    db.flush()
    return f"{config['prefix']}-{year}-{counter.last_sequence:05d}"


def _reports_for_user(db: Session, user: User, report_type: ServiceReportType) -> list[ServiceReport]:
    reports = list(
        db.scalars(
            select(ServiceReport)
            .options(
                selectinload(ServiceReport.record_links),
                selectinload(ServiceReport.technicians),
            )
            .where(ServiceReport.report_type == report_type)
            .order_by(ServiceReport.created_at.desc(), ServiceReport.id.desc())
        )
    )
    if user.is_customer:
        allowed = user.assigned_project_ids
        reports = [
            report
            for report in reports
            if report.record_links
            and {link.main_project_id for link in report.record_links} <= allowed
        ]
    return reports


def _load_report(db: Session, user: User, report_id: int, config: dict[str, Any]) -> ServiceReport:
    report = db.scalar(
        select(ServiceReport)
        .options(
            selectinload(ServiceReport.record_links).selectinload(ServiceReportRecord.installation_record),
            selectinload(ServiceReport.record_links).selectinload(ServiceReportRecord.maintenance_record),
            selectinload(ServiceReport.record_links).selectinload(ServiceReportRecord.preventive_record),
            selectinload(ServiceReport.technicians),
            selectinload(ServiceReport.imported_devices).selectinload(InstalledDevice.work_site_evidence),
        )
        .where(ServiceReport.id == report_id, ServiceReport.report_type == config["type"])
    )
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    if user.is_customer and not {
        link.main_project_id for link in report.record_links
    } <= user.assigned_project_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    if user.is_customer:
        linked_ids = {
            value
            for link in report.record_links
            if (value := getattr(link, config["link_field"])) is not None
        }
        authorized = load_record_views(
            db,
            user,
            record_type=config["record_key"],
            selected_ids={config["record_key"]: list(linked_ids)},
        )
        if {record["id"] for record in authorized} != linked_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    return report


def _report_record_views(db: Session, user: User, report: ServiceReport, config: dict[str, Any]) -> list[dict[str, Any]]:
    ids = []
    for link in report.record_links:
        value = getattr(link, config["link_field"])
        if value is not None:
            ids.append(value)
    views = load_record_views(
        db,
        user,
        record_type=config["record_key"],
        include_evidence=True,
        selected_ids={config["record_key"]: ids},
    )
    by_id = {view["id"]: view for view in views}
    ordered = []
    for link in report.record_links:
        record_id = getattr(link, config["link_field"])
        view = by_id.get(record_id)
        if view is not None:
            ordered.append({"link": link, "record": view})
    return ordered


@router.get("/reports/{report_slug}")
def report_list(
    report_slug: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _config(report_slug)
    return render(
        request,
        "structured_reports_list.html",
        {
            "active_nav": config["active_nav"],
            "report_slug": report_slug,
            "report_config": config,
            "reports": _reports_for_user(db, user, config["type"]),
        },
    )


@router.get("/reports/{report_slug}/new")
def new_report(
    report_slug: str,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "structured_report_form.html",
        _report_form_context(request, db, user, report_slug),
    )


@router.post("/reports/{report_slug}")
async def create_report(
    report_slug: str,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    config = _config(report_slug)
    form = await request.form()
    request.state.submitted_form = form
    payload = _parse_report_form(form)
    errors, team_leader, technician_names, technician_ids, records = _validate_report_form(
        request, db, user, config, payload
    )
    if errors:
        return render(
            request,
            "structured_report_form.html",
            _report_form_context(request, db, user, report_slug, form=payload, errors=errors),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    assert team_leader is not None and payload["report_date_value"] is not None
    now = utcnow()
    projects = _project_lookup(db, {int(record["project_id"]) for record in records})
    report = ServiceReport(
        report_number=_next_report_number(db, config, now),
        report_type=config["type"],
        name=payload["name"],
        created_by_id=user.id,
        created_by_name=user.full_name,
        team_leader_id=team_leader.id,
        team_leader_name=team_leader.full_name,
        report_date=payload["report_date_value"],
        notes=payload["notes"] or None,
        include_device_data=payload["include_device_data"],
        created_at=now,
        updated_at=now,
    )
    report.technicians = [
        ServiceReportTechnician(user_id=int(user_id), name=name)
        for user_id, name in zip(technician_ids, technician_names)
    ]
    for position, record in enumerate(records):
        link = ServiceReportRecord(
            main_project_id=record["project_id"],
            main_project_name=record["customer_name"],
            customer_names=_customer_names(projects.get(int(record["project_id"]))),
            sub_project_id=record["sub_project_id"],
            sub_project_name=record["sub_project_name"],
            site_id=record["work_site_id"],
            site_name=record["work_site_name"],
            position=position,
        )
        setattr(link, config["link_field"], record["id"])
        report.record_links.append(link)

    db.add(report)
    try:
        db.commit()
    except Exception:
        db.rollback()
        return render(
            request,
            "structured_report_form.html",
            _report_form_context(
                request,
                db,
                user,
                report_slug,
                form=payload,
                errors={"form": "The report could not be saved. Review the selections and try again."},
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    flash(request, f"{config['singular']} {report.report_number} saved.")
    return RedirectResponse(
        f"/reports/{report_slug}/{report.id}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/reports/{report_slug}/{report_id}")
def report_detail(
    report_slug: str,
    report_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _config(report_slug)
    report = _load_report(db, user, report_id, config)
    report_records = [
        entry["record"] for entry in _report_record_views(db, user, report, config)
    ]
    report_tree = _record_tree(
        report_records,
        _project_lookup(db, _record_project_ids(report_records)),
    )
    for main in report_tree:
        link = next(
            (
                candidate
                for candidate in report.record_links
                if candidate.main_project_id == main["id"]
            ),
            None,
        )
        if link:
            main["customer_names"] = link.customer_names or ""
    return render(
        request,
        "structured_report_detail.html",
        {
            "active_nav": config["active_nav"],
            "report_slug": report_slug,
            "report_config": config,
            "report": report,
            "report_tree": report_tree,
        },
    )


@router.post(
    "/reports/{report_slug}/{report_id}/delete",
    dependencies=[Depends(require_admin)],
)
async def delete_report(
    report_slug: str,
    report_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    config = _config(report_slug)
    form = await request.form()
    if not csrf_valid(request, form.get("csrf_token")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
    report = _load_report(db, user, report_id, config)
    report_number = report.report_number
    db.delete(report)
    db.commit()
    flash(
        request,
        f"{report_number} permanently deleted. Its source service records were kept.",
    )
    return RedirectResponse(
        f"/reports/{report_slug}", status_code=status.HTTP_303_SEE_OTHER
    )


def _pdf_response(
    db: Session,
    user: User,
    report: ServiceReport,
    config: dict[str, Any],
    *,
    include_device_data: bool,
    inline: bool,
) -> Response:
    entries = _report_record_views(db, user, report, config)
    content = build_structured_report_pdf(
        report,
        entries,
        include_device_data=include_device_data,
    )
    disposition = "inline" if inline else "attachment"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{report.report_number}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/reports/{report_slug}/{report_id}/preview")
def report_preview(
    report_slug: str,
    report_id: int,
    request: Request,
    include_device_data: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _config(report_slug)
    report = _load_report(db, user, report_id, config)
    return _pdf_response(
        db,
        user,
        report,
        config,
        include_device_data=include_device_data,
        inline=True,
    )


@router.get("/reports/{report_slug}/{report_id}/pdf")
def report_pdf(
    report_slug: str,
    report_id: int,
    request: Request,
    include_device_data: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    config = _config(report_slug)
    report = _load_report(db, user, report_id, config)
    return _pdf_response(
        db,
        user,
        report,
        config,
        include_device_data=include_device_data,
        inline=False,
    )
