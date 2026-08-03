"""Unified record pagination, bounds, and Customer scoping tests."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

from pypdf import PdfReader
from sqlalchemy import event

from app.config import settings
from app.database import engine
from app.models import (
    GeneralMaintenanceRecord,
    InstallationRecord,
    InstallationParticipant,
    MaintenanceRecord,
    MaintenanceResult,
    User,
)
from app.report_pdf import PDF_PHOTOS_PER_RECORD, build_records_pdf
from app.technician_audit import load_technician_audit, normalize_audit_filters
from tests.conftest import ADMIN, CUSTOMER_A, login


def _record(model, *, index: int, project_id: int, submitted_at: datetime):
    common = {
        "record_number": f"PAGE-{model.__tablename__[:2].upper()}-{index:03d}",
        "site_id": project_id,
        "service_type_id": 1,
        "submitted_by_id": 2,
        "quotation_number": None,
        "service_name": "Camera Service",
        "team_leader_name": "Leader One",
        "result": MaintenanceResult.COMPLETED_SUCCESSFULLY,
        "notes": f"Pagination record {index}.",
        "submitted_at": submitted_at,
        "created_at": submitted_at,
    }
    if model is MaintenanceRecord:
        return model(
            **common,
            site_name=f"Project {project_id}",
            customer_name=f"Customer {project_id}",
            site_address="Riyadh",
        )
    if model is InstallationRecord:
        return model(
            **common,
            site_name=f"Project {project_id}",
            customer_name=f"Customer {project_id}",
            site_address="Riyadh",
            equipment_model="Camera",
            serial_number=f"SERIAL-{index:03d}",
        )
    return model(
        **common,
        work_site_id=1,
        project_name=f"Project {project_id}",
        site_name="Gate 1",
        project_address="Riyadh",
    )


def seed_mixed_records(db, *, assigned: int, other: int):
    models = (MaintenanceRecord, InstallationRecord, GeneralMaintenanceRecord)
    start = datetime(2035, 1, 1, 8, 0)
    assigned_rows = [
        _record(
            models[index % len(models)],
            index=index,
            project_id=1,
            submitted_at=start + timedelta(minutes=index * 2),
        )
        for index in range(assigned)
    ]
    other_rows = [
        _record(
            models[index % len(models)],
            index=100 + index,
            project_id=3,
            submitted_at=start + timedelta(minutes=index * 2 + 1),
        )
        for index in range(other)
    ]
    db.add_all([*assigned_rows, *other_rows])
    db.commit()
    return assigned_rows, other_rows


def _pdf_text(response) -> str:
    reader = PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_customer_project_scope_survives_multiple_unified_pages(client, db):
    assigned, other = seed_mixed_records(db, assigned=12, other=12)
    login(client, *CUSTOMER_A)

    records_html = client.get("/records?page=1").text + client.get(
        "/records?page=2"
    ).text
    reports_html = client.get("/reports?page=1").text + client.get(
        "/reports?page=2"
    ).text
    pdf = client.get("/reports/pdf")

    assert pdf.status_code == 200
    pdf_text = _pdf_text(pdf)
    for record in assigned:
        assert record.record_number in records_html
        assert record.record_number in reports_html
        assert record.record_number in pdf_text
    for record in other:
        assert record.record_number not in records_html
        assert record.record_number not in reports_html
        assert record.record_number not in pdf_text


def test_unified_page_has_global_order_count_and_bounded_hydration(client, db):
    assigned, other = seed_mixed_records(db, assigned=7, other=6)
    expected = sorted(
        [*assigned, *other],
        key=lambda row: (row.submitted_at, row.id),
        reverse=True,
    )
    statements: list[tuple[str, int]] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append((statement, _cursor.rowcount))

    login(client, *ADMIN)
    event.listen(engine, "after_cursor_execute", capture)
    try:
        first = client.get("/records?page=1")
        last = client.get("/records?page=2")
    finally:
        event.remove(engine, "after_cursor_execute", capture)

    assert "13 records" in first.text
    assert "Page 1 of 2" in first.text
    assert "Page 2 of 2" in last.text
    for left, right in zip(expected[:10], expected[1:10]):
        assert first.text.index(left.record_number) < first.text.index(
            right.record_number
        )
    for record in expected[10:]:
        assert record.record_number in last.text

    hydration = [
        rowcount
        for statement, rowcount in statements
        if " IN (" in statement
        and any(
            f"FROM {table}" in statement
            for table in (
                "maintenance_records",
                "installation_records",
                "general_maintenance_records",
            )
        )
    ]
    assert hydration
    assert max(hydration) <= settings.page_size


def test_reports_pdf_refuses_over_cap_without_truncating(client, db, monkeypatch):
    seed_mixed_records(db, assigned=4, other=0)
    monkeypatch.setattr(settings, "max_pdf_records", 3)
    login(client, *ADMIN)

    oversized = client.get("/reports/pdf")
    bounded = client.get("/reports/pdf?type=installation")

    assert oversized.status_code == 422
    assert oversized.headers["content-type"].startswith("text/html")
    assert "exceeds the 3-record export limit" in oversized.text
    assert bounded.status_code == 200
    assert bounded.headers["content-type"] == "application/pdf"
    assert bounded.content.startswith(b"%PDF-")


def test_technician_filters_are_applied_in_sql_before_evidence_load(db):
    assigned, other = seed_mixed_records(db, assigned=3, other=3)
    assisted = assigned[1]
    assisted.submitted_by_id = 3
    db.add(
        InstallationParticipant(
            record_id=assisted.id,
            user_id=2,
            name="Leader One",
        )
    )
    db.commit()
    admin = db.get(User, 1)
    technician = db.get(User, 2)
    filters = normalize_audit_filters(
        start="2035-01-01",
        end="2035-01-02",
        project_id="1",
    )
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        audit = load_technician_audit(db, admin, technician, filters)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert {row["record_number"] for row in audit["records"]} == {
        row.record_number for row in assigned
    }
    assert audit["summary"]["led_visits"] == 2
    assert audit["summary"]["assisted_visits"] == 1
    assert not {
        row.record_number for row in other
    } & {row["record_number"] for row in audit["records"]}
    record_selects = [
        statement
        for statement in statements
        if "SELECT" in statement
        and any(
            f"FROM {table}" in statement
            for table in (
                "maintenance_records",
                "installation_records",
                "general_maintenance_records",
            )
        )
    ]
    assert record_selects
    assert all("submitted_at" in statement and "site_id" in statement for statement in record_selects)


def test_technician_pdf_refuses_audit_over_cap(client, db, monkeypatch):
    seed_mixed_records(db, assigned=3, other=0)
    monkeypatch.setattr(settings, "max_pdf_records", 2)
    login(client, *ADMIN)

    response = client.get(
        "/reports/technician-audit/pdf?technician_id=2"
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("text/html")
    assert "exceeds the 2-record export limit" in response.text


def test_standard_pdf_marks_photos_omitted_by_per_record_cap():
    photos = [
        {
            "storage_key": f"missing-{index}.jpg",
            "thumbnail_key": None,
            "original_filename": f"photo-{index}.jpg",
            "stage": "before",
        }
        for index in range(PDF_PHOTOS_PER_RECORD + 2)
    ]
    item = {
        "service_name": "Camera Service",
        "device_name": "Camera",
        "device_model": "P3265",
        "serial_number": "CAP-001",
        "result": MaintenanceResult.COMPLETED_SUCCESSFULLY,
        "notes": "Photo cap check.",
        "issue_description": None,
        "recommendations": None,
        "handover_notes": None,
        "warranty_start": None,
        "photos": photos,
    }
    record = {
        "record_number": "CAP-TEST-001",
        "record_type": "Installation",
        "site_name": "Tower A",
        "work_site_name": "Gate 1",
        "customer_name": "Tower A",
        "address": "Riyadh",
        "service_name": "Camera Service",
        "result": MaintenanceResult.COMPLETED_SUCCESSFULLY,
        "team_leader_name": "Leader One",
        "submitted_at": datetime(2035, 1, 1, 8, 0),
        "device": "Camera",
        "participants": [],
        "items": [item],
        "quotation_number": None,
    }

    content = build_records_pdf(
        [record],
        {"q": "", "type": ""},
        "Test Admin",
    )
    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(content)).pages
    )

    assert "2 additional evidence photos omitted from this PDF." in text
