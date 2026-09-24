"""The Periodic Maintenance workflow: submission, validation and visibility."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.config import settings
from app.models import (
    EvidencePhotoStage,
    DeviceCatalog,
    GeneralMaintenanceRecord,
    InstalledDevice,
    InstalledDeviceSite,
    InstallationRecord,
    MaintenancePhoto,
    MaintenanceRecord,
    MaintenanceResult,
    PricingItem,
    RecordRevision,
    ServiceType,
    Site,
    SubProject,
    SubProjectSite,
    WorkSite,
)
from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    CUSTOMER_B,
    LEADER_A,
    LEADER_B,
    csrf_of,
    login,
    logout,
    make_image,
    make_large_image,
    submit_record,
    submit_tokens,
)


def _record(db) -> MaintenanceRecord:
    return db.query(MaintenanceRecord).order_by(MaintenanceRecord.id.desc()).first()


def test_edit_flow_can_append_a_complete_site_service_to_same_preventive_record(client, db):
    login(client, *LEADER_A)
    original = submit_record(client, notes="Original preventive work")
    record = _record(db)
    page = client.get(f"/maintenance/records/{record.id}/edit")
    assert "data-add-to-existing-site" in page.text
    script = client.get("/static/js/app.js")
    assert script.status_code == 200
    assert 'scope.querySelector("select[name=project_id]")' in script.text
    assert 'scope.querySelector("select[name=sub_project_id]")' in script.text
    assert 'scope.querySelector("select[name=work_site_id]")' in script.text
    assert 'scope.querySelectorAll("[data-entry-data-scope]")' in script.text
    assert "prepareNestedEditSubmission(submitForm)" in script.text
    assert 'field.name.indexOf("existing_remove_photo_") !== 0' in script.text
    assert 'new DOMParser().parseFromString(xhr.responseText, "text/html")' in script.text
    assert f"/maintenance/submit?append_to={record.id}" not in page.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    item_id = record.work_items[0].id
    response = client.post(
        f"/maintenance/records/{record.id}/edit",
        data={
            "csrf_token": csrf, "form_token": form_token, "append_record_id": str(record.id),
            "existing_item_id": str(item_id), f"existing_result_{item_id}": "completed_successfully",
            f"existing_notes_{item_id}": record.work_items[0].notes,
            "append_scope_position": "0", "project_id": "1", "work_site_id": "1",
            "item_scope_index": "0", "service_type_id": "1",
            "result_0": "completed_successfully", "notes": "Added preventive work",
            "existing_data_scope_position": "0", "existing_data_item_name": "Camera cleaning",
            "existing_data_quantity": "2", "existing_data_notes": "Edited online table",
        },
        files=[("photos_0", ("added.jpg", make_image(), "image/jpeg"))],
    )

    assert response.status_code == 303
    assert response.headers["location"] == original.headers["location"]
    db.expire_all()
    record = db.get(MaintenanceRecord, record.id)
    assert db.query(MaintenanceRecord).count() == 1
    assert [item.notes for item in record.work_items] == [
        "Original preventive work",
        "Added preventive work",
    ]
    assert [item.scope_position for item in record.work_items] == [0, 0]
    assert [(row.item_name, row.quantity, row.scope_position) for row in record.device_data_rows] == [
        ("Camera cleaning", 2, 0)
    ]
    assert db.query(RecordRevision).filter_by(
        record_type="preventive_maintenance", action="items_added"
    ).count() == 1
    detail = client.get(f"/maintenance/records/{record.id}")
    assert detail.status_code == 200
    assert "Change history" not in detail.text


def test_edit_flow_can_add_two_new_sites_to_same_preventive_record(client, db):
    login(client, *LEADER_A)
    submit_record(client, notes="Gate 1 service")
    record = _record(db)
    page = client.get(f"/maintenance/records/{record.id}/edit")
    assert "data-async-form" in page.text
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    item = record.work_items[0]

    response = client.post(
        f"/maintenance/records/{record.id}/edit",
        data={
            "csrf_token": csrf, "form_token": form_token, "append_record_id": str(record.id),
            "existing_item_id": str(item.id), f"existing_result_{item.id}": item.result.value,
            f"existing_notes_{item.id}": item.notes,
            "append_scope_position": ["", ""],
            "project_id": ["1", "1"],
            "work_site_id": ["2", "3"],
            "item_scope_index": ["0", "1"],
            "service_type_id": ["1", "1"],
            "result_0": "completed_successfully", "notes": "Gate 2 service",
            "result_1": "completed_with_observations",
            "data_scope_index": ["0", "1"],
            "data_item_name": ["Gate 2 checklist", "Gate 3 checklist"],
            "data_quantity": ["2", "3"],
            "data_notes": ["Gate 2 rows", "Gate 3 rows"],
        },
        files=[
            ("photos_0", ("gate-2.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("gate-3.jpg", make_image(), "image/jpeg")),
        ],
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 201
    assert response.json()["redirect"] == f"/maintenance/records/{record.id}"
    db.expire_all()
    record = db.get(MaintenanceRecord, record.id)
    assert [(item.scope_position, item.work_site_name) for item in record.work_items] == [
        (0, "Gate 1"), (1, "Gate 2"), (2, "Gate 3")
    ]
    assert [(row.scope_position, row.work_site_name, row.item_name) for row in record.device_data_rows] == [
        (1, "Gate 2", "Gate 2 checklist"),
        (2, "Gate 3", "Gate 3 checklist"),
    ]


def test_edit_append_validation_stays_in_edit_and_preserves_saved_record(client, db):
    login(client, *LEADER_A)
    submit_record(client, notes="Saved preventive work")
    record = _record(db)
    page = client.get(f"/maintenance/records/{record.id}/edit")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    item = record.work_items[0]

    response = client.post(
        f"/maintenance/records/{record.id}/edit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "append_record_id": str(record.id),
            "existing_item_id": str(item.id),
            f"existing_result_{item.id}": item.result.value,
            f"existing_notes_{item.id}": item.notes,
            "append_scope_position": "",
            "project_id": "1",
            "work_site_id": "2",
            "item_scope_index": "0",
            "service_type_id": "1",
            "result_0": "completed_successfully",
            "notes": "Unsaved Gate 2 service",
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["ok"] is False
    assert "new Site or service was not saved" in payload["errors"]["form"]
    assert "Attach at least one proof photo" in payload["errors"]["form"]
    assert "preventive_maintenance_entry" not in response.text
    db.expire_all()
    saved = db.get(MaintenanceRecord, record.id)
    assert db.query(MaintenanceRecord).count() == 1
    assert [(entry.work_site_name, entry.notes) for entry in saved.work_items] == [
        ("Gate 1", "Saved preventive work")
    ]


def test_edit_new_site_without_service_returns_exact_error_instead_of_no_changes(client, db):
    login(client, *LEADER_A)
    submit_record(client, notes="Saved preventive work")
    record = _record(db)
    original_item = record.work_items[0]
    page = client.get(f"/maintenance/records/{record.id}/edit")

    response = client.post(
        f"/maintenance/records/{record.id}/edit",
        data={
            "csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1),
            "form_token": re.search(r'name="form_token" value="([^"]+)"', page.text).group(1),
            "append_record_id": str(record.id),
            "existing_item_id": str(original_item.id),
            f"existing_result_{original_item.id}": original_item.result.value,
            f"existing_notes_{original_item.id}": original_item.notes,
            "append_scope_position": "",
            "project_id": "1",
            "work_site_id": "2",
            "item_scope_index": "0",
            "service_type_id": "",
            "result_0": "completed_successfully",
        },
        files=[("photos_0", ("unsaved.jpg", make_image(), "image/jpeg"))],
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["errors"]["service_type_id_0"] == "Select the service performed."
    assert "No changes were made" not in response.text
    db.expire_all()
    saved = db.get(MaintenanceRecord, record.id)
    assert [(item.work_site_name, item.notes) for item in saved.work_items] == [
        ("Gate 1", "Saved preventive work")
    ]


def test_admin_can_append_then_remove_a_cross_project_site_from_same_preventive_record(client, db):
    """Clean Edit flow: keep the old Site, add another Main/Sub/Site, then remove it."""
    added_sub = SubProject(project_id=3, name="Added preventive Sub Project")
    added_sub.site_assignments = [SubProjectSite(site_id=2)]
    db.add(added_sub)
    db.commit()

    login(client, *ADMIN)
    submit_record(client, notes="Original Site remains")
    record = _record(db)
    original_item = record.work_items[0]
    page = client.get(f"/maintenance/records/{record.id}/edit")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)

    appended = client.post(
        f"/maintenance/records/{record.id}/edit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "append_record_id": str(record.id),
            "existing_item_id": str(original_item.id),
            f"existing_result_{original_item.id}": original_item.result.value,
            f"existing_notes_{original_item.id}": original_item.notes,
            "append_scope_position": "",
            "project_id": "3",
            "sub_project_id": str(added_sub.id),
            "work_site_id": "2",
            "item_scope_index": "0",
            "service_type_id": "1",
            "result_0": "completed_successfully",
            "issue_description": "Added Site test",
            "data_scope_index": "0",
            "data_item_name": "Added Site table",
            "data_quantity": "1",
            "data_notes": "Remove this Site next",
        },
        files=[("photos_0", ("added-site.jpg", make_image(), "image/jpeg"))],
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert appended.status_code == 201, appended.text

    db.expire_all()
    record = db.get(MaintenanceRecord, record.id)
    assert db.query(MaintenanceRecord).count() == 1
    assert [(item.project_id, item.sub_project_id, item.work_site_id) for item in record.work_items] == [
        (1, original_item.sub_project_id, 1),
        (3, added_sub.id, 2),
    ]
    added_item_id = record.work_items[1].id

    page = client.get(f"/maintenance/records/{record.id}/edit")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    original_item = record.work_items[0]
    removed = client.post(
        f"/maintenance/records/{record.id}/edit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "append_record_id": str(record.id),
            "existing_item_id": str(original_item.id),
            f"existing_result_{original_item.id}": original_item.result.value,
            f"existing_notes_{original_item.id}": original_item.notes,
        },
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["redirect"] == f"/maintenance/records/{record.id}"

    db.expire_all()
    record = db.get(MaintenanceRecord, record.id)
    assert db.query(MaintenanceRecord).count() == 1
    assert record.record_number.startswith("PM-")
    assert [(item.project_id, item.work_site_id, item.notes) for item in record.work_items] == [
        (1, 1, "Original Site remains")
    ]
    assert db.get(type(original_item), added_item_id) is None
    assert not record.device_data_rows


def test_preventive_maintenance_stores_before_and_after_photos(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client,
        before_photo_descriptions_0="General site view",
        after_photo_descriptions_0="Battery terminal corrosion",
        after_photo_issue_found_0_0="1",
        photos=[
            ("before_photos_0", ("before.jpg", make_image((80, 20, 20)), "image/jpeg")),
            ("after_photos_0", ("after.jpg", make_image((20, 80, 20)), "image/jpeg")),
        ],
    )
    assert response.status_code == 303
    photos = _record(db).work_items[0].photos
    stages = [photo.stage for photo in photos]
    assert stages == [EvidencePhotoStage.BEFORE, EvidencePhotoStage.AFTER]
    assert [photo.is_issue_found for photo in photos] == [False, True]
    assert photos[1].description == "Battery terminal corrosion"


def test_preventive_maintenance_stores_direct_site_table_without_asset_link(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client,
        data_scope_index="0",
        data_item_name="Camera cleaning",
        data_quantity="3",
        data_notes="All housings cleaned",
    )
    assert response.status_code == 303
    record = _record(db)
    assert record.device_evidence is None
    assert record.work_items[0].installed_device_id is None
    assert record.device_data_rows[0].item_name == "Camera cleaning"
    assert record.device_data_rows[0].quantity == 3


def test_preventive_maintenance_has_no_item_selector_and_ignores_forged_item(client, db):
    device = DeviceCatalog(name="Solar Panel", model="SP-500")
    item = PricingItem(
        name="Solar Panel",
        model="SP-500",
        unit_price=Decimal("750.00"),
        currency="SAR",
        service_enabled=True,
        legacy_device=device,
    )
    db.add(item)
    db.commit()

    login(client, *LEADER_A)
    page = client.get("/maintenance")
    assert page.status_code == 200
    assert 'name="installed_device_id"' not in page.text
    assert f'value="catalog:{item.id}"' not in page.text
    assert "BASE-SN-001" not in page.text
    assert "Installed items" not in page.text

    response = submit_record(client, installed_device_id=f"catalog:{item.id}")
    assert response.status_code == 303
    record = _record(db)
    assert record.work_items[0].device_name == "Camera Service"
    assert record.work_items[0].installed_device_id is None
    assert record.device_evidence is None


# ------------------------------------------------------------ happy path


def test_team_leader_can_submit_a_complete_record(client, db):
    login(client, *LEADER_A)
    assert 'name="quotation_number"' not in client.get("/maintenance").text
    response = submit_record(
        client,
        participants=["3"],
        quotation_number="FORGED-QUOTATION",
        issue_description="Loose connector on camera 3.",
        recommendations="Replace the connector next visit.",
    )
    assert response.status_code == 303

    record = _record(db)
    assert response.headers["location"] == f"/maintenance/records/{record.id}"
    assert record.notes == "Cleaned and tested every camera on site."
    assert record.issue_description == "Loose connector on camera 3."
    assert record.recommendations == "Replace the connector next visit."
    assert record.participant_names == ["Leader Two"]
    assert len(record.photos) == 1
    assert record.result == MaintenanceResult.COMPLETED_SUCCESSFULLY
    assert record.quotation_id is None
    assert record.quotation_number is None
    assert record.work_items[0].quotation_id is None
    assert record.work_items[0].quotation_number is None


def test_backend_records_the_user_and_its_own_timestamp(client, db):
    login(client, *LEADER_A)
    before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=5)

    # A browser-supplied timestamp and user id must both be ignored.
    submit_record(
        client,
        submitted_at="1999-01-01T00:00:00",
        submitted_by_id="999",
        team_leader_name="Somebody Else",
        record_number="PM-1999-00001",
    )
    after = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=5)

    record = _record(db)
    assert before <= record.submitted_at <= after
    assert record.submitted_at.year != 1999
    assert record.team_leader_name == "Leader One"
    assert record.submitted_by.username == LEADER_A[0]
    assert record.record_number.startswith(f"PM-{datetime.now(timezone.utc).replace(tzinfo=None).year}-")


def test_record_numbers_are_sequential_and_formatted(client, db):
    login(client, *LEADER_A)
    for _ in range(3):
        assert submit_record(client).status_code == 303

    numbers = [r.record_number for r in db.query(MaintenanceRecord).order_by(MaintenanceRecord.id)]
    assert all(re.fullmatch(r"PM-\d{4}-\d{5}", n) for n in numbers)
    assert numbers[-1].endswith("00003")
    assert len(set(numbers)) == 3


def test_multiple_photos_are_all_stored_on_disk(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client,
        photos=[
            ("photos", ("one.jpg", make_image(), "image/jpeg")),
            ("photos", ("two.png", make_image(fmt="PNG"), "image/png")),
        ],
    )
    assert response.status_code == 303

    record = _record(db)
    assert len(record.photos) == 2
    for photo in record.photos:
        assert (settings.upload_dir / photo.storage_key).is_file()
        # The stored name is a generated UUID, never the uploaded filename.
        assert "one" not in photo.storage_key and "two" not in photo.storage_key


# ------------------------------------------------------------ validation


def test_submission_fails_without_a_project(client, db):
    login(client, *LEADER_A)
    response = submit_record(client, site_id=None)
    assert response.status_code == 422
    assert "Select the project" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_submission_fails_without_a_work_site(client, db):
    login(client, *LEADER_A)
    response = submit_record(client, work_site_id=None)
    assert response.status_code == 422
    assert "Select the site" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_submission_fails_without_a_service(client, db):
    login(client, *LEADER_A)
    response = submit_record(client, service_id=None)
    assert response.status_code == 422
    assert "Select the service" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_submission_fails_without_a_result(client, db):
    login(client, *LEADER_A)
    response = submit_record(client, result="")
    assert response.status_code == 422
    assert "Select the maintenance result" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_preventive_entry_does_not_show_workflow_notes_field(client, db):
    login(client, *LEADER_A)
    entry = client.get("/maintenance")
    assert entry.status_code == 200
    assert '<textarea name="notes"' not in entry.text

    created = submit_record(client, notes="")
    assert created.status_code == 303
    record = _record(db)
    assert record.notes == ""
    edit = client.get(f"/maintenance/records/{record.id}/edit")
    assert f'name="existing_notes_{record.work_items[0].id}"' in edit.text
    assert f'<textarea name="existing_notes_{record.work_items[0].id}"' not in edit.text


def test_submission_fails_with_an_invalid_result(client, db):
    login(client, *LEADER_A)
    assert submit_record(client, result="completed_perfectly").status_code == 422
    assert db.query(MaintenanceRecord).count() == 0


def test_issue_detail_is_optional_for_any_result(client, db):
    login(client, *LEADER_A)
    created = submit_record(
        client,
        result="unable_to_complete",
        issue_description="",
    )
    assert created.status_code == 303
    assert not _record(db).work_items[0].issue_description


def test_grouped_services_allow_blank_issue_detail(client, db):
    second = InstalledDevice(
        site_id=1,
        device_id=1,
        customer_name="Tower A",
        site_name="Gate 1",
        device_name="IP Camera",
        manufacturer="Axis",
        device_model="P3265-LV",
        serial_number="ISSUE-INDEX-002",
    )
    second.work_site_evidence = InstalledDeviceSite(site_id=1, site_name="Gate 1")
    db.add(second)
    db.commit()

    login(client, *LEADER_A)
    response = submit_record(
        client,
        service_type_id=["1", "1"],
        installed_device_id=["1", str(second.id)],
        notes=["Completed first device.", "Could not complete second device."],
        result_0="completed_successfully",
        result_1="unable_to_complete",
        issue_description=["", ""],
        recommendations=["", ""],
        photos=[
            ("photos_0", ("first.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("second.jpg", make_image(), "image/jpeg")),
        ],
    )

    assert response.status_code == 303
    record = _record(db)
    assert len(record.work_items) == 2
    assert all(not item.issue_description for item in record.work_items)


def test_out_of_range_project_id_returns_field_error(client, db):
    login(client, *LEADER_A)
    response = submit_record(client, site_id="99999999999999999999")
    assert response.status_code == 422
    assert 'data-error-for="project_id"' in response.text
    assert "That project no longer exists." in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_submission_allows_blank_notes(client, db):
    login(client, *LEADER_A)
    response = submit_record(client, notes="   ")
    assert response.status_code == 303
    assert db.query(MaintenanceRecord).one().notes == ""


def test_submission_fails_without_a_photo(client, db):
    login(client, *LEADER_A)
    response = submit_record(client, photos=[])
    assert response.status_code == 422
    assert "at least one proof photo" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_inactive_site_is_rejected(client, db):
    login(client, *LEADER_A)
    inactive = db.query(Site).filter(Site.is_active.is_(False)).one()
    response = submit_record(client, site_id=str(inactive.id))
    assert response.status_code == 422
    assert "deactivated" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_inactive_service_is_rejected(client, db):
    login(client, *LEADER_A)
    inactive = db.query(ServiceType).filter(ServiceType.is_active.is_(False)).one()
    response = submit_record(client, service_id=str(inactive.id))
    assert response.status_code == 422
    assert "deactivated" in response.text
    assert db.query(MaintenanceRecord).count() == 0


# --------------------------------------------------------------- uploads


def test_unsupported_file_type_is_rejected(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client, photos=[("photos", ("payload.pdf", b"%PDF-1.7 not an image", "application/pdf"))]
    )
    assert response.status_code == 422
    assert "not a JPEG, PNG or WebP" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_executable_disguised_as_an_image_is_rejected(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client, photos=[("photos", ("shell.jpg", b"#!/bin/sh\nrm -rf /\n", "image/jpeg"))]
    )
    assert response.status_code == 422
    assert "not a real image" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_oversized_file_is_rejected(client, db):
    login(client, *LEADER_A)
    huge = make_large_image()
    assert len(huge) > settings.max_upload_bytes

    response = submit_record(client, photos=[("photos", ("huge.png", huge, "image/png"))])
    assert response.status_code == 422
    assert "limit is" in response.text
    assert db.query(MaintenanceRecord).count() == 0


def test_rejected_upload_leaves_no_files_behind(client, db):
    login(client, *LEADER_A)
    submit_record(
        client,
        photos=[
            ("photos", ("good.jpg", make_image(), "image/jpeg")),
            ("photos", ("bad.jpg", b"definitely not an image", "image/jpeg")),
        ],
    )
    assert db.query(MaintenancePhoto).count() == 0
    written = [p for p in settings.upload_dir.rglob("*") if p.is_file()]
    assert written == []


def test_directory_traversal_in_the_filename_is_neutralised(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client, photos=[("photos", ("../../../../etc/passwd.jpg", make_image(), "image/jpeg"))]
    )
    assert response.status_code == 303

    photo = db.query(MaintenancePhoto).one()
    assert ".." not in photo.storage_key
    assert ".." not in photo.original_filename
    assert (settings.upload_dir / photo.storage_key).is_file()


# ------------------------------------------------------------ duplicates


def test_duplicate_submission_is_prevented(client, db):
    login(client, *LEADER_A)
    tokens = submit_tokens(client)

    first = submit_record(client, tokens=tokens)
    second = submit_record(client, tokens=tokens)

    assert first.status_code == 303
    assert second.status_code == 422
    assert "already submitted" in second.text
    assert db.query(MaintenanceRecord).count() == 1


# ------------------------------------------------------------ visibility


def test_technical_user_sees_records_for_assigned_projects(client, db):
    login(client, *LEADER_A)
    submit_record(client, notes="Leader One was here and cleaned the cameras.")
    mine_record = _record(db)
    mine, mine_number = mine_record.id, mine_record.record_number
    logout(client)

    login(client, *LEADER_B)
    submit_record(client, notes="Leader Two was here and checked the recordings.")
    their_record = _record(db)
    theirs, their_number = their_record.id, their_record.record_number

    listing_response = client.get("/maintenance/records")
    assert listing_response.status_code == 200
    listing = listing_response.text
    assert mine_number in listing
    assert their_number in listing
    assert client.get(f"/maintenance/records/{theirs}").status_code == 200
    assert client.get(f"/maintenance/records/{mine}").status_code == 200


def test_customer_record_and_photo_access_is_scoped_by_project(client, db):
    login(client, *LEADER_A)
    submit_record(client)
    photo_id = db.query(MaintenancePhoto).one().id
    logout(client)

    login(client, *CUSTOMER_A)
    assert client.get(f"/media/photo/{photo_id}").status_code == 200
    logout(client)
    login(client, *CUSTOMER_B)
    assert client.get(f"/media/photo/{photo_id}").status_code == 403


def test_admin_sees_every_record_and_photo(client, db):
    login(client, *LEADER_A)
    submit_record(client)
    logout(client)
    login(client, *LEADER_B)
    submit_record(client)
    logout(client)

    login(client, *ADMIN)
    listing = client.get("/maintenance/records")
    assert listing.status_code == 200
    assert "Leader One" in listing.text and "Leader Two" in listing.text

    for record in db.query(MaintenanceRecord):
        assert client.get(f"/maintenance/records/{record.id}").status_code == 200
    for photo in db.query(MaintenancePhoto):
        assert client.get(f"/media/photo/{photo.id}").status_code == 200


def test_technical_can_edit_but_cannot_delete_records(client, db):
    login(client, *LEADER_A)
    submit_record(client)
    record = _record(db)

    detail = client.get(f"/maintenance/records/{record.id}")
    assert detail.status_code == 200
    assert "Edit record" in detail.text
    assert "Delete record" not in detail.text
    assert client.get(f"/maintenance/records/{record.id}/edit").status_code == 200
    assert client.post(f"/maintenance/records/{record.id}/delete").status_code == 403
    assert client.put(f"/maintenance/records/{record.id}").status_code == 405
    assert client.delete(f"/maintenance/records/{record.id}").status_code == 405


def test_preventive_maintenance_edit_is_saved_and_audited(client, db):
    login(client, *LEADER_A)
    submit_record(client, participants=["3"])
    record = _record(db)
    original_number = record.record_number
    original_project = record.site_id
    token = csrf_of(client, f"/maintenance/records/{record.id}/edit")

    response = client.post(
        f"/maintenance/records/{record.id}/edit",
        data={
            "csrf_token": token,
            "result_0": "completed_with_observations",
            "notes_0": "Updated preventive maintenance notes.",
            "issue_description_0": "Minor dust remained inside the enclosure.",
            "recommendations_0": "Inspect the enclosure during the next visit.",
            "participant_ids": ["3"],
            "add_after_photo_descriptions_0": "Enclosure after cleaning.",
            "add_after_photo_issue_found_0_0": "1",
        },
        files=[
            ("add_after_photos_0", ("after-edit.jpg", make_image(), "image/jpeg"))
        ],
    )

    assert response.status_code == 303
    db.expire_all()
    record = db.get(MaintenanceRecord, record.id)
    assert record.record_number == original_number
    assert record.site_id == original_project
    assert record.notes == "Updated preventive maintenance notes."
    assert [person.name for person in record.participants] == ["Leader Two"]
    assert any(
        photo.description == "Enclosure after cleaning."
        and photo.stage == EvidencePhotoStage.AFTER
        and photo.is_issue_found
        for photo in record.work_items[0].photos
    )
    revision = db.query(RecordRevision).one()
    assert revision.record_type == "preventive_maintenance"
    assert revision.editor_name == "Leader One"
    assert "item_1_notes" in revision.changes


def test_customer_record_mutation_controls_are_hidden_and_forbidden(client, db):
    login(client, *LEADER_A)
    submit_record(client)
    record = _record(db)
    client.cookies.clear()
    login(client, *CUSTOMER_A)

    detail = client.get(f"/maintenance/records/{record.id}")
    assert "Edit record" not in detail.text
    assert "Delete record" not in detail.text
    assert client.get(f"/maintenance/records/{record.id}/edit").status_code == 403
    assert client.post(f"/maintenance/records/{record.id}/edit").status_code == 403
    assert client.post(f"/maintenance/records/{record.id}/delete").status_code == 403


def test_admin_can_permanently_delete_preventive_record(client, db):
    login(client, *LEADER_A)
    submit_record(client)
    record_id = _record(db).id
    client.cookies.clear()
    login(client, *ADMIN)
    token = csrf_of(client, f"/maintenance/records/{record_id}")
    response = client.post(
        f"/maintenance/records/{record_id}/delete",
        data={"csrf_token": token},
    )
    assert response.status_code == 303
    db.expire_all()
    assert db.get(MaintenanceRecord, record_id) is None
    assert db.query(RecordRevision).one().action == "deleted"


def test_filters_narrow_the_record_list(client, db):
    login(client, *LEADER_A)
    submit_record(client, result=MaintenanceResult.COMPLETED_SUCCESSFULLY.value)
    submit_record(
        client,
        result=MaintenanceResult.FURTHER_ACTION_REQUIRED.value,
        issue_description="The camera mount needs replacement.",
    )

    listing = client.get("/maintenance/records?result=further_action_required").text
    assert "Further action required" in listing
    assert listing.count("PM-") >= 1

    number = db.query(MaintenanceRecord).first().record_number
    assert number in client.get(f"/maintenance/records?q={number}").text
    assert "No records match those filters" in client.get(
        "/maintenance/records?q=PM-1900-99999"
    ).text


# ------------------------------------------------------------- snapshots


def test_history_survives_a_site_and_service_rename(client, db):
    login(client, *LEADER_A)
    submit_record(client)
    record_id = _record(db).id
    logout(client)

    site = db.query(Site).filter(Site.name == "Tower A").one()
    work_site = db.query(WorkSite).filter(WorkSite.name == "Gate 1").one()
    service = db.query(ServiceType).filter(ServiceType.name == "Camera Service").one()
    site.name, site.customer_name = "Tower A — Renamed", "New Owner LLC"
    work_site.name = "Gate 1 — Renamed"
    service.name = "CCTV Maintenance"
    site.is_active = False
    service.is_active = False
    db.commit()

    db.expire_all()
    record = db.get(MaintenanceRecord, record_id)
    assert record.site_name == "Gate 1"
    assert record.customer_name == "Tower A"
    assert record.work_site_evidence.site_name == "Gate 1"
    assert record.service_name == "Camera Service"

    login(client, *ADMIN)
    detail = client.get(f"/maintenance/records/{record_id}").text
    assert "Tower A" in detail and "Gate 1" in detail
    assert "New Owner LLC" not in detail
    assert "Gate 1 — Renamed" not in detail


def test_history_keeps_the_leader_name_after_rename_and_deactivation(client, db):
    from app.models import User

    login(client, *LEADER_A)
    submit_record(client)
    record_id = _record(db).id
    logout(client)

    leader = db.query(User).filter(User.username == LEADER_A[0]).one()
    leader.full_name = "Leader One (left the company)"
    leader.is_active = False
    db.commit()

    login(client, *ADMIN)
    detail = client.get(f"/maintenance/records/{record_id}").text
    assert "Leader One" in detail
    assert "left the company" not in detail


# ------------------------------------------------------------- dashboard


def test_dashboard_statistics_update_after_a_submission(client, db):
    login(client, *ADMIN)
    assert ">0<" in client.get("/dashboard").text
    logout(client)

    login(client, *LEADER_A)
    submit_record(
        client,
        result=MaintenanceResult.FURTHER_ACTION_REQUIRED.value,
        issue_description="The camera mount needs replacement.",
    )
    technical_dashboard = client.get("/dashboard").text
    assert "Your records" in technical_dashboard
    assert ">1<" in technical_dashboard
    logout(client)

    login(client, *ADMIN)
    admin_dashboard = client.get("/dashboard").text
    assert "Camera Service" in admin_dashboard
    assert "Leader One" in admin_dashboard


def test_dashboard_combines_all_record_types_and_uses_correct_recent_links(client, db):
    db.add_all(
        [
            InstallationRecord(
                record_number="NI-2026-90001",
                site_id=1,
                service_type_id=1,
                submitted_by_id=2,
                site_name="Tower A",
                customer_name="Acme Holding",
                site_address="Riyadh",
                service_name="Camera installation",
                team_leader_name="Leader One",
                equipment_model="P3265-LV",
                result=MaintenanceResult.COMPLETED_SUCCESSFULLY,
                notes="Installed.",
            ),
            GeneralMaintenanceRecord(
                record_number="GM-2026-90001",
                site_id=1,
                work_site_id=1,
                service_type_id=1,
                submitted_by_id=2,
                project_name="Tower A",
                site_name="Gate 1",
                project_address="Riyadh",
                service_name="Camera repair",
                team_leader_name="Leader One",
                result=MaintenanceResult.FURTHER_ACTION_REQUIRED,
                notes="Repair pending.",
            ),
        ]
    )
    db.commit()

    login(client, *ADMIN)
    page = client.get("/dashboard").text

    assert re.search(
        r'<div class="label">Total records</div>\s*<div class="value">2</div>',
        page,
    )
    assert 'href="/installations/records/1"' in page
    assert 'href="/general-maintenance/records/1"' in page
    assert "Camera installation" in page
    assert "Camera repair" in page
    assert 'class="topbar-dashboard-link"' in page
    assert ">Dashboard</span>" in page


def test_technical_dashboard_includes_other_technical_users_work(client, db):
    login(client, *LEADER_B)
    submit_record(client)
    record_number = _record(db).record_number
    logout(client)

    login(client, *LEADER_A)
    dashboard = client.get("/dashboard").text
    assert record_number in dashboard


def test_preventive_records_search_service_project_and_site_without_device_link(client, db):
    login(client, *LEADER_A)
    response = submit_record(client)
    assert response.status_code == 303

    record = _record(db)
    assert record.device_evidence is None
    assert record.work_items[0].installed_device_id is None

    assert record.record_number in client.get("/maintenance/records?q=Camera+Service").text
    assert record.record_number in client.get("/maintenance/records?q=Tower+A").text
    assert record.record_number in client.get("/maintenance/records?q=Gate+1").text
    assert record.record_number in client.get("/maintenance/records?project_id=1").text
    assert record.record_number in client.get("/maintenance/records?work_site_id=1").text
    assert record.record_number in client.get("/records?q=Camera+Service").text


def test_one_preventive_record_can_contain_multiple_services(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client,
        service_type_id=["1", "1"],
        item_scope_index=["0", "0"],
        notes=["Cleaned the first camera.", "Adjusted the second camera."],
        result_0="completed_successfully",
        result_1="further_action_required",
        issue_description=["", "The second camera mount is loose."],
        recommendations=["", "Replace the mounting bracket."],
        photos=[
            ("photos_0", ("first.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("second.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert response.status_code == 303

    record = _record(db)
    assert record.device_evidence is None
    assert all(item.installed_device_id is None for item in record.work_items)
    assert [item.notes for item in record.work_items] == [
        "Cleaned the first camera.",
        "Adjusted the second camera.",
    ]
    assert [item.result.value for item in record.work_items] == [
        "completed_successfully",
        "further_action_required",
    ]
    assert [len(item.photos) for item in record.work_items] == [1, 1]

    detail = client.get(response.headers["location"]).text
    assert "Cleaned the first camera." in detail
    assert "The second camera mount is loose." in detail
    assert record.record_number in client.get(
        "/maintenance/records?q=mounting+bracket"
    ).text
    item_photo_id = record.work_items[1].photos[0].id
    assert client.get(f"/media/maintenance-item-photo/{item_photo_id}").status_code == 200
    logout(client)
    login(client, *CUSTOMER_B)
    assert client.get(f"/media/maintenance-item-photo/{item_photo_id}").status_code == 403


def test_grouped_preventive_allows_the_same_service_more_than_once(client, db):
    login(client, *LEADER_A)
    response = submit_record(
        client,
        service_type_id=["1", "1"],
        item_scope_index=["0", "0"],
        result_1="completed_successfully",
        notes=["First unit", "Second unit"],
        photos=[
            ("photos_0", ("first.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("second.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert response.status_code == 303
    assert [item.notes for item in _record(db).work_items] == ["First unit", "Second unit"]
