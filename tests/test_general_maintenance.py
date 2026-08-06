"""Normal Maintenance is independent from Preventive Maintenance."""
from __future__ import annotations

import re
from decimal import Decimal

from app.models import (
    EvidencePhotoStage,
    DeviceCatalog,
    GeneralMaintenanceRecord,
    InstalledDevice,
    InstalledDeviceSite,
    PricingItem,
    RecordRevision,
)
from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    CUSTOMER_B,
    LEADER_A,
    csrf_of,
    ensure_service_quotation,
    login,
    logout,
    make_image,
)


def _tokens(client) -> tuple[str, str]:
    page = client.get("/general-maintenance")
    assert page.status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    return csrf, form_token


def test_maintenance_module_is_separate_and_uses_the_grouped_layout(client):
    assert client.get("/general-maintenance").status_code == 303
    login(client, *LEADER_A)
    page = client.get("/general-maintenance")
    assert page.status_code == 200
    assert 'action="/general-maintenance/submit"' in page.text
    assert "Add another item" in page.text
    assert "Maintenance result" in page.text
    assert 'href="/maintenance"' in page.text
    assert 'href="/general-maintenance"' in page.text
    assert "Before photos" in page.text
    assert "After photos" in page.text


def test_normal_maintenance_stores_before_and_after_photos(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "quotation_number": ensure_service_quotation("1"),
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "completed_successfully",
            "notes": "Completed normal maintenance.",
        },
        files=[
            ("before_photos_0", ("before.jpg", make_image((80, 20, 20)), "image/jpeg")),
            ("after_photos_0", ("after.jpg", make_image((20, 80, 20)), "image/jpeg")),
        ],
    )
    assert response.status_code == 303
    record = db.query(GeneralMaintenanceRecord).one()
    assert [photo.stage for photo in record.work_items[0].photos] == [
        EvidencePhotoStage.BEFORE,
        EvidencePhotoStage.AFTER,
    ]


def test_normal_maintenance_lists_and_accepts_uninstalled_catalog_item(client, db):
    device = DeviceCatalog(name="Generator", model="GEN-20")
    item = PricingItem(
        name="Generator",
        model="GEN-20",
        unit_price=Decimal("2500.00"),
        currency="SAR",
        service_enabled=True,
        legacy_device=device,
    )
    db.add(item)
    db.commit()

    login(client, *LEADER_A)
    page = client.get("/general-maintenance")
    assert page.status_code == 200
    assert f'value="catalog:{item.id}"' in page.text
    assert "Generator" in page.text
    assert "BASE-SN-001" not in page.text
    assert "Installed items" not in page.text
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "quotation_number": ensure_service_quotation("1"),
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": f"catalog:{item.id}",
            "result_0": "completed_successfully",
            "notes": "Serviced the generator.",
        },
        files=[("photos_0", ("proof.jpg", make_image(), "image/jpeg"))],
    )
    assert response.status_code == 303
    record = db.query(GeneralMaintenanceRecord).one()
    assert record.work_items[0].device_name == "Generator"
    assert record.work_items[0].installed_device_id is None


def test_one_maintenance_record_contains_independent_device_evidence(client, db):
    second = InstalledDevice(
        site_id=1,
        device_id=1,
        customer_name="Tower A",
        site_name="Gate 1",
        device_name="IP Camera",
        manufacturer="Axis",
        device_model="P3265-LV",
        serial_number="NORMAL-MAINT-SN-002",
    )
    second.work_site_evidence = InstalledDeviceSite(site_id=1, site_name="Gate 1")
    db.add(second)
    db.commit()

    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "quotation_number": ensure_service_quotation("1"),
            "work_site_id": "1",
            "service_type_id": ["1", "1"],
            "installed_device_id": ["1", str(second.id)],
            "result_0": "completed_successfully",
            "result_1": "further_action_required",
            "notes": ["Repaired camera one.", "Repaired camera two."],
            "issue_description": ["", "Damaged mounting bracket."],
            "recommendations": ["", "Replace the bracket."],
            "participant_ids": ["3"],
        },
        files=[
            ("photos_0", ("first.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("second.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert response.status_code == 303

    record = db.query(GeneralMaintenanceRecord).one()
    assert re.fullmatch(r"MA-\d{4}-\d{5}", record.record_number)
    assert record.project_name == "Tower A"
    assert record.site_name == "Gate 1"
    assert [item.notes for item in record.work_items] == [
        "Repaired camera one.",
        "Repaired camera two.",
    ]
    assert [item.result.value for item in record.work_items] == [
        "completed_successfully",
        "further_action_required",
    ]
    assert [len(item.photos) for item in record.work_items] == [1, 1]

    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "Repaired camera one." in detail.text
    assert "Damaged mounting bracket." in detail.text
    assert record.record_number in client.get(
        "/general-maintenance/records?q=Damaged+mounting+bracket"
    ).text
    assert record.record_number in client.get(
        "/general-maintenance/records?result=further_action_required"
    ).text
    assert record.record_number in client.get(
        "/records?type=general_maintenance"
    ).text
    assert record.record_number in client.get("/records?q=NORMAL-MAINT-SN-002").text

    photo_id = record.work_items[1].photos[0].id
    assert client.get(f"/media/general-maintenance-photo/{photo_id}").status_code == 200
    logout(client)
    login(client, *CUSTOMER_B)
    assert client.get(f"/general-maintenance/records/{record.id}").status_code == 403
    assert client.get(f"/media/general-maintenance-photo/{photo_id}").status_code == 403
    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get(f"/general-maintenance/records/{record.id}").status_code == 200
    assert client.get(f"/media/general-maintenance-photo/{photo_id}").status_code == 200


def test_each_maintenance_item_requires_its_own_result_notes_and_photo(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "quotation_number": ensure_service_quotation("1"),
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "",
            "notes": "",
        },
        files=[],
    )
    assert response.status_code == 422
    assert "Select the maintenance result" in response.text
    assert "Describe the maintenance" in response.text
    assert "Attach at least one proof photo" in response.text


def test_normal_maintenance_requires_issue_detail_for_unable_result(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "quotation_number": ensure_service_quotation("1"),
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "unable_to_complete",
            "notes": "Unable to complete the repair.",
            "issue_description": "",
        },
        files=[("photos_0", ("normal.jpg", make_image(), "image/jpeg"))],
    )
    assert response.status_code == 422
    assert 'data-error-for="issue_description_0"' in response.text
    assert "Describe the issue or observation for this result." in response.text
    assert db.query(GeneralMaintenanceRecord).count() == 0


def test_normal_maintenance_can_be_edited_and_deleted_by_the_right_roles(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "quotation_number": ensure_service_quotation("1"),
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "completed_successfully",
            "notes": "Original normal maintenance notes.",
        },
        files=[("photos_0", ("normal.jpg", make_image(), "image/jpeg"))],
    )
    record = db.query(GeneralMaintenanceRecord).one()
    token = csrf_of(client, f"/general-maintenance/records/{record.id}/edit")
    edited = client.post(
        f"/general-maintenance/records/{record.id}/edit",
        data={
            "csrf_token": token,
            "result_0": "completed_with_observations",
            "notes_0": "Updated normal maintenance notes.",
            "issue_description_0": "Small alignment issue observed.",
            "recommendations_0": "Check alignment next month.",
            "participant_ids": ["3"],
        },
    )
    assert edited.status_code == 303
    db.expire_all()
    assert db.get(GeneralMaintenanceRecord, record.id).work_items[0].notes == (
        "Updated normal maintenance notes."
    )
    assert db.query(RecordRevision).one().record_type == "maintenance"
    assert client.post(
        f"/general-maintenance/records/{record.id}/delete"
    ).status_code == 403

    record_id = record.id
    client.cookies.clear()
    login(client, *ADMIN)
    token = csrf_of(client, f"/general-maintenance/records/{record_id}")
    deleted = client.post(
        f"/general-maintenance/records/{record_id}/delete",
        data={"csrf_token": token},
    )
    assert deleted.status_code == 303
    db.expire_all()
    assert db.get(GeneralMaintenanceRecord, record_id) is None
    assert db.query(GeneralMaintenanceRecord).count() == 0
