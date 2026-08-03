import io

from pypdf import PdfReader

from app.models import InstallationRecord, MaintenanceRecord
from tests.conftest import (
    CUSTOMER_A,
    ADMIN,
    LEADER_A,
    LEADER_B,
    login,
    logout,
    make_image,
    submit_installation,
    submit_record,
)


def _pdf_text(response) -> str:
    reader = PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_reports_and_records_share_search_and_type_filters(client, db):
    login(client, *LEADER_A)
    submit_installation(client, serial_number="REPORT-SERIAL-100")
    installation_number = db.query(InstallationRecord).one().record_number
    submit_record(client, notes="Preventive evidence outside the installation filter.")
    maintenance_number = db.query(MaintenanceRecord).one().record_number
    client.get("/dashboard")  # consume the record-submission flash

    records_page = client.get("/records?type=installation&q=REPORT-SERIAL-100")
    reports_page = client.get("/reports?type=installation&q=REPORT-SERIAL-100")

    assert records_page.status_code == reports_page.status_code == 200
    assert installation_number in records_page.text
    assert installation_number in reports_page.text
    assert maintenance_number not in records_page.text
    assert maintenance_number not in reports_page.text
    assert 'action="/reports/pdf"' in reports_page.text
    assert 'name="q" value="REPORT-SERIAL-100"' in reports_page.text
    assert 'name="type" value="installation"' in reports_page.text


def test_filtered_pdf_contains_record_details_and_photo(client, db):
    login(client, *LEADER_A)
    submit_installation(
        client,
        serial_number="PDF-EVIDENCE-200",
        notes="PDF installation notes for visual evidence.",
        handover_notes="PDF handover completed with the customer.",
    )
    record = db.query(InstallationRecord).one()

    response = client.get(
        "/reports/pdf?type=installation&q=PDF-EVIDENCE-200"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert "attachment;" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")

    reader = PdfReader(io.BytesIO(response.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert record.record_number in text
    assert "PDF-EVIDENCE-200" in text
    assert "PDF installation notes for visual evidence." in text
    assert "PDF handover completed with the customer." in text
    assert sum(len(page.images) for page in reader.pages) >= 1


def test_pdf_labels_before_and_after_evidence(client):
    login(client, *LEADER_A)
    submit_installation(
        client,
        serial_number="PDF-STAGED-EVIDENCE",
        photos=[
            ("before_photos_0", ("before.jpg", make_image((80, 20, 20)), "image/jpeg")),
            ("after_photos_0", ("after.jpg", make_image((20, 80, 20)), "image/jpeg")),
        ],
    )
    response = client.get("/reports/pdf?type=installation&q=PDF-STAGED-EVIDENCE")
    assert response.status_code == 200
    text = _pdf_text(response)
    assert "Before:" in text
    assert "After:" in text


def test_quotation_id_is_only_in_pdf_when_authorized_and_selected(client, db):
    login(client, *LEADER_A)
    submit_installation(client, serial_number="QUOTATION-PDF-CHECK")
    quotation_number = db.query(InstallationRecord).one().quotation_number

    reports_page = client.get("/reports")
    assert "Include quotation ID" not in reports_page.text
    unauthorized = _pdf_text(
        client.get("/reports/pdf?include_quotation=1&q=QUOTATION-PDF-CHECK")
    )
    assert quotation_number not in unauthorized

    logout(client)
    login(client, *ADMIN)
    assert "Include quotation ID" in client.get("/reports").text
    default_pdf = _pdf_text(
        client.get("/reports/pdf?q=QUOTATION-PDF-CHECK")
    )
    selected_pdf = _pdf_text(
        client.get(
            "/reports/pdf?include_quotation=1&q=QUOTATION-PDF-CHECK"
        )
    )
    assert quotation_number not in default_pdf
    assert quotation_number in selected_pdf


def test_customer_pdf_only_contains_assigned_project_records(client, db):
    login(client, *LEADER_A)
    submit_installation(client, serial_number="CUSTOMER-REPORT-A")
    assigned_number = db.query(InstallationRecord).one().record_number

    logout(client)
    login(client, *LEADER_B)
    submit_installation(
        client,
        site_id="3",
        serial_number="CUSTOMER-REPORT-B",
    )
    other_number = (
        db.query(InstallationRecord)
        .filter(InstallationRecord.serial_number == "CUSTOMER-REPORT-B")
        .one()
        .record_number
    )

    logout(client)
    login(client, *CUSTOMER_A)
    reports_page = client.get("/reports")
    response = client.get("/reports/pdf")
    text = _pdf_text(response)

    assert reports_page.status_code == 200
    assert assigned_number in reports_page.text
    assert other_number not in reports_page.text
    assert response.status_code == 200
    assert assigned_number in text
    assert other_number not in text


def test_pdf_export_requires_authentication(client):
    response = client.get("/reports/pdf")

    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
