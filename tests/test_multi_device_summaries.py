import io

from pypdf import PdfReader

from app.models import InstallationRecord, MaintenanceRecord
from tests.conftest import (
    LEADER_A,
    csrf_of,
    login,
    make_image,
    submit_installation,
    submit_record,
)


def _pdf_text(response) -> str:
    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(response.content)).pages
    )
    return " ".join(text.split())


def _switch_to_arabic(client, next_path: str = "/records") -> None:
    response = client.post(
        "/language",
        data={
            "language": "ar",
            "next": next_path,
            "csrf_token": csrf_of(client, next_path),
        },
    )
    assert response.status_code == 303


def _submit_three_device_records(client, db):
    installation_serials = ["INST-SN-1", "INST-SN-2", "INST-SN-3"]
    response = submit_installation(
        client,
        service_id=["1", "1", "1"],
        device_id=["1", "1", "1"],
        serial_number=installation_serials,
        warranty_start=["2026-07-28", "2026-07-28", "2026-07-28"],
        notes=["Installed camera one.", "Installed camera two.", "Installed camera three."],
        result_0="completed_successfully",
        result_1="completed_successfully",
        result_2="completed_successfully",
        photos=[
            ("photos_0", ("installation-1.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("installation-2.jpg", make_image(), "image/jpeg")),
            ("photos_2", ("installation-3.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert response.status_code == 303
    db.expire_all()
    installation = db.query(InstallationRecord).one()
    installed_ids = [str(item.installed_device_id) for item in installation.work_items]

    response = submit_record(
        client,
        service_type_id=["1", "1", "1"],
        installed_device_id=installed_ids,
        notes=["Maintained camera one.", "Maintained camera two.", "Maintained camera three."],
        issue_description=["", "", ""],
        recommendations=["", "", ""],
        result_0="completed_successfully",
        result_1="completed_successfully",
        result_2="completed_successfully",
        photos=[
            ("photos_0", ("maintenance-1.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("maintenance-2.jpg", make_image(), "image/jpeg")),
            ("photos_2", ("maintenance-3.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert response.status_code == 303
    db.expire_all()
    maintenance = db.query(MaintenanceRecord).one()
    return installation, maintenance, installation_serials


def test_three_device_summaries_are_exact_and_localized_in_html_but_english_in_pdf(
    client, db
):
    assert login(client, *LEADER_A).status_code == 303
    installation, maintenance, serials = _submit_three_device_records(client, db)
    english_cell = "IP Camera - P3265-LV | INST-SN-1 | +2 more"

    for path in ("/records", "/reports"):
        for record in (installation, maintenance):
            page = client.get(f"{path}?q={record.record_number}")
            assert page.status_code == 200
            assert f"<td>{english_cell}</td>" in page.text

    installation_list = client.get(
        f"/installations/records?q={installation.record_number}"
    )
    maintenance_list = client.get(
        f"/maintenance/records?q={maintenance.record_number}"
    )
    assert installation_list.text.count("+2 more") == 2
    assert maintenance_list.text.count("+2 more") == 1

    for record_type, record in (
        ("installation", installation),
        ("maintenance", maintenance),
    ):
        pdf = client.get(
            f"/reports/pdf?type={record_type}&q={record.record_number}"
        )
        assert pdf.status_code == 200
        text = _pdf_text(pdf)
        assert english_cell in text
        for serial in serials:
            assert serial in text

    _switch_to_arabic(client)
    arabic_cell = "IP Camera - P3265-LV | INST-SN-1 | +2 أخرى"
    for path in ("/records", "/reports"):
        page = client.get(f"{path}?q={installation.record_number}")
        assert page.status_code == 200
        assert f"<td>{arabic_cell}</td>" in page.text
        assert english_cell not in page.text

    pdf = client.get(
        f"/reports/pdf?type=installation&q={installation.record_number}"
    )
    assert pdf.status_code == 200
    text = _pdf_text(pdf)
    assert english_cell in text
    assert "+2 أخرى" not in text


def test_single_device_summary_keeps_the_existing_markup_without_a_suffix(client):
    assert login(client, *LEADER_A).status_code == 303
    response = submit_installation(client, serial_number="SINGLE-SN-1")
    assert response.status_code == 303

    expected_cell = "<td>IP Camera - P3265-LV | SINGLE-SN-1</td>"
    for path in ("/records?q=SINGLE-SN-1", "/reports?q=SINGLE-SN-1"):
        page = client.get(path)
        assert page.status_code == 200
        assert expected_cell in page.text
        assert "+1 more" not in page.text


def test_legacy_grouped_record_without_work_items_uses_relationship_fallback(client, db):
    assert login(client, *LEADER_A).status_code == 303
    installation, _, _ = _submit_three_device_records(client, db)
    installation_number = installation.record_number
    installation.work_items.clear()
    db.commit()

    expected_cell = "<td>IP Camera - P3265-LV | INST-SN-1 | +2 more</td>"
    page = client.get(f"/records?type=installation&q={installation_number}")
    assert page.status_code == 200
    assert expected_cell in page.text

    pdf = client.get(f"/reports/pdf?type=installation&q={installation_number}")
    assert pdf.status_code == 200
    assert "IP Camera - P3265-LV | INST-SN-1 | +2 more" in _pdf_text(pdf)
