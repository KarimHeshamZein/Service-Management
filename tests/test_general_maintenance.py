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


def test_edit_flow_can_append_a_complete_site_service_to_same_maintenance_record(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    first = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": "1",
            "result_0": "completed_successfully",
            "notes": "Original maintenance work",
        },
        files=[("photos_0", ("first.jpg", make_image(), "image/jpeg"))],
    )
    record = db.query(GeneralMaintenanceRecord).one()
    page = client.get(f"/general-maintenance/records/{record.id}/edit")
    assert "data-add-to-existing-site" in page.text
    assert f"/general-maintenance/submit?append_to={record.id}" not in page.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    item_id = record.work_items[0].id
    response = client.post(
        f"/general-maintenance/records/{record.id}/edit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "append_record_id": str(record.id),
            "existing_item_id": str(item_id),
            f"existing_result_{item_id}": "completed_successfully",
            f"existing_notes_{item_id}": record.work_items[0].notes,
            "append_scope_position": "0",
            "project_id": "1",
            "work_site_id": "1",
            "item_scope_index": "0",
            "service_type_id": "1",
            "result_0": "completed_successfully",
            "notes": "Added maintenance work",
        },
        files=[("photos_0", ("second.jpg", make_image(), "image/jpeg"))],
    )

    assert response.status_code == 303
    assert response.headers["location"] == first.headers["location"]
    db.expire_all()
    record = db.get(GeneralMaintenanceRecord, record.id)
    assert db.query(GeneralMaintenanceRecord).count() == 1
    assert [item.notes for item in record.work_items] == [
        "Original maintenance work",
        "Added maintenance work",
    ]
    assert [item.scope_position for item in record.work_items] == [0, 0]
    assert db.query(RecordRevision).filter_by(
        record_type="maintenance", action="items_added"
    ).count() == 1
    detail = client.get(f"/general-maintenance/records/{record.id}")
    assert detail.status_code == 200
    assert "Change history" not in detail.text


def test_edit_new_maintenance_site_without_service_returns_actionable_error(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    assert client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf, "form_token": form_token, "project_id": "1",
            "work_site_id": "1", "service_type_id": "1",
            "result_0": "completed_successfully",
        },
        files=[("photos_0", ("first.jpg", make_image(), "image/jpeg"))],
    ).status_code == 303
    record = db.query(GeneralMaintenanceRecord).one()
    original_item = record.work_items[0]
    page = client.get(f"/general-maintenance/records/{record.id}/edit")

    response = client.post(
        f"/general-maintenance/records/{record.id}/edit",
        data={
            "csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1),
            "form_token": re.search(r'name="form_token" value="([^"]+)"', page.text).group(1),
            "append_record_id": str(record.id),
            "existing_item_id": str(original_item.id),
            f"existing_result_{original_item.id}": original_item.result.value,
            f"existing_notes_{original_item.id}": original_item.notes,
            "append_scope_position": "", "project_id": "1", "work_site_id": "2",
            "item_scope_index": "0", "service_type_id": "",
            "result_0": "completed_successfully",
        },
        files=[("photos_0", ("unsaved.jpg", make_image(), "image/jpeg"))],
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 422
    assert response.json()["errors"]["service_type_id_0"] == "Select the service performed."
    assert "No changes were made" not in response.text
    db.expire_all()
    assert len(db.get(GeneralMaintenanceRecord, record.id).work_items) == 1


def test_maintenance_module_is_separate_and_uses_the_grouped_layout(client):
    assert client.get("/general-maintenance").status_code == 303
    login(client, *LEADER_A)
    page = client.get("/general-maintenance")
    assert page.status_code == 200
    assert 'action="/general-maintenance/submit"' in page.text
    assert "Add another service" in page.text
    assert "Maintenance result" in page.text
    assert 'href="/maintenance"' in page.text
    assert 'href="/general-maintenance"' in page.text
    assert "Before photos" in page.text
    assert "After photos" in page.text
    assert 'name="quotation_number"' not in page.text


def test_normal_maintenance_stores_before_and_after_photos(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "quotation_number": "FORGED-QUOTATION",
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "completed_successfully",
            "notes": "Completed normal maintenance.",
            "before_photo_descriptions_0": "General site view",
            "after_photo_descriptions_0": "Loose solar panel connection",
            "after_photo_issue_found_0_0": "1",
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
    assert [photo.is_issue_found for photo in record.work_items[0].photos] == [False, True]
    assert record.work_items[0].photos[1].description == "Loose solar panel connection"
    assert record.quotation_id is None
    assert record.quotation_number is None
    assert record.work_items[0].quotation_id is None
    assert record.work_items[0].quotation_number is None


def test_normal_maintenance_stores_direct_site_table_without_asset_link(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": "1",
            "result_0": "completed_successfully",
            "notes": "Serviced gate",
            "data_scope_index": "0",
            "data_item_name": "Barrier service",
            "data_quantity": "2",
            "data_notes": "Lubricated mechanisms",
        },
        files=[("photos_0", ("proof.jpg", make_image(), "image/jpeg"))],
    )
    assert response.status_code == 303
    record = db.query(GeneralMaintenanceRecord).one()
    assert record.work_items[0].installed_device_id is None
    assert record.device_data_rows[0].quantity == 2


def test_normal_maintenance_allows_blank_notes(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "completed_successfully",
            "notes": "",
        },
        files=[("photos_0", ("proof.jpg", make_image(), "image/jpeg"))],
    )

    assert response.status_code == 303
    assert db.query(GeneralMaintenanceRecord).one().notes == ""


def test_normal_maintenance_has_no_item_selector_and_ignores_forged_item(client, db):
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
    assert 'name="installed_device_id"' not in page.text
    assert f'value="catalog:{item.id}"' not in page.text
    assert "BASE-SN-001" not in page.text
    assert "Installed items" not in page.text
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
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
    assert record.work_items[0].device_name == "Camera Service"
    assert record.work_items[0].installed_device_id is None


def test_one_maintenance_record_contains_independent_services(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": ["1", "1"],
            "item_scope_index": ["0", "0"],
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
    assert all(item.installed_device_id is None for item in record.work_items)

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


def test_each_maintenance_item_requires_its_own_result_and_photo(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
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
    assert "Attach at least one proof photo" in response.text


def test_maintenance_entry_does_not_show_workflow_notes_field(client, db):
    login(client, *LEADER_A)
    entry = client.get("/general-maintenance")
    assert entry.status_code == 200
    assert '<textarea name="notes"' not in entry.text

    csrf, form_token = _tokens(client)
    created = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": "1",
            "result_0": "completed_successfully",
        },
        files=[("photos_0", ("proof.jpg", make_image(), "image/jpeg"))],
    )
    assert created.status_code == 303
    record = db.query(GeneralMaintenanceRecord).one()
    edit = client.get(f"/general-maintenance/records/{record.id}/edit")
    assert f'name="existing_notes_{record.work_items[0].id}"' in edit.text
    assert f'<textarea name="existing_notes_{record.work_items[0].id}"' not in edit.text


def test_normal_maintenance_allows_blank_issue_detail_for_unable_result(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "unable_to_complete",
            "notes": "Unable to complete the repair.",
            "issue_description": "",
        },
        files=[("photos_0", ("normal.jpg", make_image(), "image/jpeg"))],
    )
    assert response.status_code == 303
    record = db.query(GeneralMaintenanceRecord).one()
    assert not record.work_items[0].issue_description


def test_normal_maintenance_can_be_edited_and_deleted_by_the_right_roles(client, db):
    login(client, *LEADER_A)
    csrf, form_token = _tokens(client)
    client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
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
            "add_after_photo_descriptions_0": "Alignment after correction.",
            "add_after_photo_issue_found_0_0": "1",
        },
        files=[
            ("add_after_photos_0", ("after-edit.jpg", make_image(), "image/jpeg"))
        ],
    )
    assert edited.status_code == 303
    db.expire_all()
    assert db.get(GeneralMaintenanceRecord, record.id).work_items[0].notes == (
        "Updated normal maintenance notes."
    )
    assert any(
        photo.description == "Alignment after correction."
        and photo.stage == EvidencePhotoStage.AFTER
        and photo.is_issue_found
        for photo in db.get(GeneralMaintenanceRecord, record.id).work_items[0].photos
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
