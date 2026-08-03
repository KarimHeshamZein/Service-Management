import io

from pypdf import PdfReader

from app.models import (
    InstallationRecord,
    MaintenanceRecord,
    RecordRevision,
    utcnow,
)
from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    LEADER_A,
    LEADER_B,
    login,
    logout,
    submit_installation,
    submit_record,
)


def _pdf_text(response) -> str:
    reader = PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_technician_activity_is_administrator_only_and_hidden(client):
    login(client, *LEADER_A)
    technical_reports = client.get("/reports")
    assert "/reports/technician-audit" not in technical_reports.text
    assert client.get("/reports/technician-audit").status_code == 403
    assert client.get("/reports/technician-audit/pdf?technician_id=2").status_code == 403

    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get("/reports/technician-audit").status_code == 403

    logout(client)
    login(client, *ADMIN)
    reports = client.get("/reports")
    assert "/reports/technician-audit" in reports.text
    assert client.get("/reports/technician-audit").status_code == 200


def test_activity_counts_led_assisted_devices_photos_and_edits(client, db):
    login(client, *LEADER_A)
    submit_installation(
        client,
        serial_number="AUDIT-INSTALL-001",
        participants=["3"],
        notes="Technician audit installation evidence.",
    )
    installation = db.query(InstallationRecord).one()
    assert installation.participants[0].user_id == 3

    submit_record(
        client,
        participants=["3"],
        notes="Technician audit preventive evidence.",
    )
    preventive = db.query(MaintenanceRecord).one()
    db.add(
        RecordRevision(
            record_type="installation",
            record_id=installation.id,
            record_number=installation.record_number,
            action="edited",
            edited_by_id=2,
            editor_name="Leader One",
            changes_json='{"notes": {"before": "Old", "after": "New"}}',
            created_at=utcnow(),
        )
    )
    db.add(
        RecordRevision(
            record_type="preventive_maintenance",
            record_id=preventive.id,
            record_number=preventive.record_number,
            action="edited",
            edited_by_id=2,
            editor_name="Leader One",
            changes_json='{"recommendations": {"before": "", "after": "Review"}}',
            created_at=utcnow(),
        )
    )
    db.commit()

    logout(client)
    login(client, *ADMIN)
    leader_page = client.get("/reports/technician-audit?technician_id=2")
    assert leader_page.status_code == 200
    assert "Technician audit installation evidence." in leader_page.text
    assert "Technician audit preventive evidence." in leader_page.text
    assert "Visits led</span><strong>2</strong>" in leader_page.text
    assert "Visits assisted</span><strong>0</strong>" in leader_page.text
    assert "Devices handled</span><strong>2</strong>" in leader_page.text
    assert "Evidence photos</span><strong>2</strong>" in leader_page.text
    assert "Record edits</span><strong>2</strong>" in leader_page.text
    assert "Notes" in leader_page.text

    preventive_page = client.get(
        "/reports/technician-audit?technician_id=2&type=maintenance"
    )
    assert "Record edits</span><strong>1</strong>" in preventive_page.text
    assert preventive.record_number in preventive_page.text
    assert installation.record_number not in preventive_page.text

    assistant_page = client.get("/reports/technician-audit?technician_id=3")
    assert assistant_page.status_code == 200
    assert "Visits led</span><strong>0</strong>" in assistant_page.text
    assert "Visits assisted</span><strong>2</strong>" in assistant_page.text
    assert "AUDIT-INSTALL-001" in assistant_page.text


def test_activity_filters_and_pdf_include_full_history_and_optional_photos(client):
    login(client, *LEADER_A)
    submit_installation(
        client,
        serial_number="AUDIT-PDF-INSTALL",
        notes="Installation notes in technician PDF.",
        participants=["3"],
    )
    submit_record(
        client,
        notes="Preventive notes excluded by installation filter.",
        participants=["3"],
    )
    logout(client)
    login(client, *ADMIN)

    page = client.get(
        "/reports/technician-audit"
        "?technician_id=2&type=installation&project_id=1"
    )
    assert page.status_code == 200
    assert "AUDIT-PDF-INSTALL" in page.text
    assert "Preventive notes excluded" not in page.text

    response = client.get(
        "/reports/technician-audit/pdf"
        "?technician_id=2&type=installation&project_id=1&include_photos=1"
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert "attachment;" in response.headers["content-disposition"]
    text = _pdf_text(response)
    assert "Technician activity report" in text
    assert "Leader One" in text
    assert "AUDIT-PDF-INSTALL" in text
    assert "Installation notes in technician PDF." in text
    assert "Preventive notes excluded" not in text
    reader = PdfReader(io.BytesIO(response.content))
    assert sum(len(page.images) for page in reader.pages) >= 1


def test_technician_pdf_rejects_missing_or_non_technical_user(client):
    login(client, *ADMIN)
    assert client.get("/reports/technician-audit/pdf").status_code == 404
    assert (
        client.get("/reports/technician-audit/pdf?technician_id=1").status_code
        == 404
    )
