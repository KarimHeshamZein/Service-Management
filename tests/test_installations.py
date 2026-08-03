"""New Installation submission, visibility, evidence, and unified records."""
from __future__ import annotations

import re
from datetime import date

import pytest

from app.models import (
    EvidencePhotoStage,
    InstalledDevice,
    InstallationRecord,
    RecordRevision,
)
from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    CUSTOMER_B,
    LEADER_A,
    LEADER_B,
    csrf_of,
    ensure_service_quotation,
    installation_tokens,
    login,
    logout,
    make_image,
    submit_installation,
    submit_record,
)


def test_team_leader_can_submit_installation(client, db):
    login(client, *LEADER_A)
    response = submit_installation(
        client,
        participants=["3"],
        handover_notes="Customer representative received the system.",
        record_number="FAKE",
        submitted_by_id="999",
        submitted_at="1900-01-01",
    )

    assert response.status_code == 303
    record = db.query(InstallationRecord).one()
    assert re.fullmatch(r"NI-\d{4}-00001", record.record_number)
    assert response.headers["location"] == f"/installations/records/{record.id}"
    assert record.team_leader_name == "Leader One"
    assert record.equipment_model == "IP Camera — Axis P3265-LV"
    assert record.installed_device.device_name == "IP Camera"
    assert record.serial_number == "SN-2026-0001"
    assert record.warranty_start == date(2026, 7, 28)
    assert [person.name for person in record.participants] == ["Leader Two"]
    assert len(record.photos) == 1
    assert record.submitted_at.year != 1900


def test_installation_keeps_before_and_after_photos_separate(client, db):
    login(client, *LEADER_A)
    response = submit_installation(
        client,
        photos=[
            ("before_photos_0", ("before.jpg", make_image((80, 20, 20)), "image/jpeg")),
            ("after_photos_0", ("after.jpg", make_image((20, 80, 20)), "image/jpeg")),
        ],
    )

    assert response.status_code == 303
    record = db.query(InstallationRecord).one()
    assert [photo.stage for photo in record.work_items[0].photos] == [
        EvidencePhotoStage.BEFORE,
        EvidencePhotoStage.AFTER,
    ]
    detail = client.get(response.headers["location"])
    assert "Before photos" in detail.text
    assert "After photos" in detail.text


def test_installation_allows_ten_photos_in_each_stage_but_not_eleven(client):
    login(client, *LEADER_A)
    staged_files = [
        ("before_photos_0", (f"before-{index}.jpg", make_image(), "image/jpeg"))
        for index in range(10)
    ] + [
        ("after_photos_0", (f"after-{index}.jpg", make_image(), "image/jpeg"))
        for index in range(10)
    ]
    assert submit_installation(client, photos=staged_files).status_code == 303

    csrf, form_token = installation_tokens(client)
    too_many = [
        ("before_photos_0", (f"before-{index}.jpg", make_image(), "image/jpeg"))
        for index in range(11)
    ]
    response = submit_installation(
        client,
        serial_number="STAGE-LIMIT-11",
        photos=too_many,
        tokens=(csrf, form_token),
    )
    assert response.status_code == 422
    assert "Attach at most 10 before photos." in response.text


def test_quotation_id_is_required_and_must_match_the_project(client):
    login(client, *LEADER_A)
    missing = submit_installation(client, quotation_number="")
    assert missing.status_code == 422
    assert "Enter the quotation ID." in missing.text

    mismatch = submit_installation(
        client,
        site_id="3",
        quotation_number=ensure_service_quotation("1"),
    )
    assert mismatch.status_code == 422
    assert "belonging to the selected Project" in mismatch.text


def test_quotation_id_is_hidden_without_pricing_access_but_visible_to_admin(
    client,
    db,
):
    login(client, *LEADER_A)
    response = submit_installation(client)
    record = db.query(InstallationRecord).one()
    assert record.quotation_number == "TEST-QUO-P1"
    assert record.quotation_number not in client.get(response.headers["location"]).text

    logout(client)
    login(client, *ADMIN)
    assert record.quotation_number in client.get(response.headers["location"]).text


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"site_id": None}, "Select the project"),
        ({"work_site_id": ""}, "Select the site"),
        ({"service_id": None}, "Select the installation type"),
        ({"device_id": ""}, "Select the device being installed"),
        ({"serial_number": ""}, "Enter the equipment serial number"),
        ({"warranty_start": ""}, "Select the warranty start date"),
        ({"warranty_start": "not-a-date"}, "valid warranty start date"),
        ({"result": ""}, "Select the installation result"),
        ({"notes": ""}, "Describe the installation"),
        ({"photos": []}, "Attach at least one installation photo"),
    ],
)
def test_installation_validation(client, overrides, message):
    login(client, *LEADER_A)
    response = submit_installation(client, **overrides)
    assert response.status_code == 422
    assert message in response.text


def test_inactive_master_data_cannot_be_used(client):
    login(client, *LEADER_A)
    assert submit_installation(client, site_id="2").status_code == 422
    assert submit_installation(client, service_id="2").status_code == 422


def test_technical_can_edit_but_cannot_delete_installation(client, db):
    login(client, *LEADER_A)
    submit_installation(client)
    record = db.query(InstallationRecord).one()
    detail = client.get(f"/installations/records/{record.id}")
    assert "Edit record" in detail.text
    assert "Delete record" not in detail.text
    assert client.get(f"/installations/records/{record.id}/edit").status_code == 200
    assert client.post(f"/installations/records/{record.id}/delete").status_code == 403
    assert client.put(f"/installations/records/{record.id}").status_code == 405
    assert client.delete(f"/installations/records/{record.id}").status_code == 405


def test_installation_edit_is_saved_and_audited(client, db):
    login(client, *LEADER_A)
    submit_installation(client, participants=["3"])
    record = db.query(InstallationRecord).one()
    original_number = record.record_number
    original_project = record.site_id
    token = csrf_of(client, f"/installations/records/{record.id}/edit")

    response = client.post(
        f"/installations/records/{record.id}/edit",
        data={
            "csrf_token": token,
            "result_0": "completed_with_observations",
            "notes_0": "Corrected installation notes after supervisor review.",
            "handover_notes_0": "Handover confirmed by the project contact.",
            "participant_ids": ["3"],
        },
    )

    assert response.status_code == 303
    db.expire_all()
    record = db.get(InstallationRecord, record.id)
    assert record.record_number == original_number
    assert record.site_id == original_project
    assert record.notes == "Corrected installation notes after supervisor review."
    assert [person.name for person in record.participants] == ["Leader Two"]
    revision = db.query(RecordRevision).one()
    assert revision.record_type == "installation"
    assert revision.editor_name == "Leader One"
    assert "item_1_notes" in revision.changes


def test_customer_cannot_edit_or_delete_assigned_installation(client, db):
    login(client, *LEADER_A)
    submit_installation(client)
    record = db.query(InstallationRecord).one()
    client.cookies.clear()
    login(client, *CUSTOMER_A)

    detail = client.get(f"/installations/records/{record.id}")
    assert detail.status_code == 200
    assert "Edit record" not in detail.text
    assert "Delete record" not in detail.text
    assert client.get(f"/installations/records/{record.id}/edit").status_code == 403
    assert client.post(f"/installations/records/{record.id}/edit").status_code == 403
    assert client.post(f"/installations/records/{record.id}/delete").status_code == 403


def test_admin_can_delete_unreferenced_installation(client, db):
    login(client, *LEADER_A)
    submit_installation(client)
    record = db.query(InstallationRecord).one()
    record_id = record.id
    installed_id = record.installed_device.id
    client.cookies.clear()
    login(client, *ADMIN)
    token = csrf_of(client, f"/installations/records/{record_id}")

    response = client.post(
        f"/installations/records/{record_id}/delete",
        data={"csrf_token": token},
    )

    assert response.status_code == 303
    db.expire_all()
    assert db.get(InstallationRecord, record_id) is None
    assert db.get(InstalledDevice, installed_id) is None
    revision = db.query(RecordRevision).one()
    assert revision.action == "deleted"


def test_admin_cannot_delete_installation_used_by_maintenance(client, db):
    login(client, *LEADER_A)
    submit_installation(client, serial_number="REFERENCED-INSTALLATION")
    record = db.query(InstallationRecord).one()
    record_id = record.id
    installed_id = record.installed_device.id
    submit_record(client, installed_device_id=str(installed_id))
    client.cookies.clear()
    login(client, *ADMIN)
    token = csrf_of(client, f"/installations/records/{record_id}")

    response = client.post(
        f"/installations/records/{record_id}/delete",
        data={"csrf_token": token},
    )

    assert response.status_code == 303
    db.expire_all()
    assert db.get(InstallationRecord, record_id) is not None
    detail = client.get(response.headers["location"])
    assert "referenced by a maintenance record" in detail.text


def test_customer_can_only_view_assigned_project_installations_and_photos(client, db):
    login(client, *LEADER_A)
    submit_installation(client)
    record = db.query(InstallationRecord).one()
    photo_id = record.photos[0].id

    client.cookies.clear()
    login(client, *CUSTOMER_A)
    assert client.get(f"/installations/records/{record.id}").status_code == 200
    assert client.get(f"/media/installation-photo/{photo_id}").status_code == 200
    logout(client)
    login(client, *CUSTOMER_B)
    assert client.get(f"/installations/records/{record.id}").status_code == 403
    assert client.get(f"/media/installation-photo/{photo_id}").status_code == 403


def test_customer_record_lists_only_include_assigned_projects(client, db):
    login(client, *LEADER_A)
    submit_installation(client, serial_number="CUSTOMER-SCOPE-A")
    logout(client)
    login(client, *LEADER_B)
    submit_installation(
        client,
        site_id="3",
        serial_number="CUSTOMER-SCOPE-B",
    )
    records = {
        record.serial_number: record
        for record in db.query(InstallationRecord).all()
    }
    logout(client)

    login(client, *CUSTOMER_A)
    assigned_list = client.get("/installations/records").text
    assigned_all = client.get("/records").text
    assert "CUSTOMER-SCOPE-A" in assigned_list
    assert "CUSTOMER-SCOPE-A" in assigned_all
    assert "CUSTOMER-SCOPE-B" not in assigned_list
    assert "CUSTOMER-SCOPE-B" not in assigned_all
    assert client.get(
        f"/installations/records/{records['CUSTOMER-SCOPE-B'].id}"
    ).status_code == 403

    logout(client)
    login(client, *CUSTOMER_B)
    other_list = client.get("/installations/records").text
    assert "CUSTOMER-SCOPE-B" in other_list
    assert "CUSTOMER-SCOPE-A" not in other_list


def test_admin_can_view_and_open_installation_entry(client, db):
    login(client, *LEADER_A)
    submit_installation(client)
    record = db.query(InstallationRecord).one()

    client.cookies.clear()
    login(client, *ADMIN)
    assert record.record_number in client.get("/installations/records").text
    assert client.get(f"/installations/records/{record.id}").status_code == 200
    assert client.get("/installations/submit").status_code == 200


def test_installation_snapshots_survive_master_data_changes(client, db):
    from app.models import ServiceType, Site, User, WorkSite

    login(client, *LEADER_A)
    submit_installation(client)
    record = db.query(InstallationRecord).one()

    db.get(Site, record.site_id).name = "Renamed Site"
    db.get(ServiceType, record.service_type_id).name = "Renamed Type"
    db.get(WorkSite, record.work_site_evidence.site_id).name = "Renamed Gate"
    db.get(User, record.submitted_by_id).full_name = "Renamed Leader"
    db.commit()

    detail = client.get(f"/installations/records/{record.id}").text
    assert "Tower A" in detail
    assert "Gate 1" in detail
    assert "Camera Service" in detail
    assert "Leader One" in detail
    assert "Renamed Site" not in detail
    assert "Renamed Gate" not in detail


def test_all_records_combines_specific_record_tables(client, db):
    login(client, *LEADER_A)
    submit_record(client)
    submit_installation(client)

    records = client.get("/records")
    assert records.status_code == 200
    assert db.query(InstallationRecord).one().record_number in records.text
    assert "PM-" in records.text
    assert "Maintenance" in records.text
    assert "Installation" in records.text

    installation_only = client.get("/records?type=installation").text
    assert "NI-" in installation_only
    assert "PM-" not in installation_only


def test_installation_records_search_customer_device_model_and_serial(client, db):
    login(client, *LEADER_A)
    submit_installation(client, serial_number="SEARCHABLE-SERIAL-77")

    assert "NI-" in client.get("/installations/records?q=P3265-LV").text
    assert "NI-" in client.get("/installations/records?q=SEARCHABLE-SERIAL-77").text
    assert "NI-" in client.get("/installations/records?project_id=1").text
    assert "NI-" in client.get("/installations/records?work_site_id=1").text
    assert "NI-" in client.get("/installations/records?device_id=1").text
    assert "NI-" in client.get("/records?q=SEARCHABLE-SERIAL-77").text


def test_installation_entry_orders_project_site_service_device(client):
    login(client, *LEADER_A)
    page = client.get("/installations").text
    positions = [
        page.index('name="project_id"'),
        page.index('name="work_site_id"'),
        page.index('name="service_type_id"'),
        page.index('name="device_id"'),
    ]
    assert positions == sorted(positions)
    assert "Gate 1" in page and "Gate 2" in page and "Gate 3" in page


def test_people_picker_only_lists_other_active_technical_users(client):
    login(client, *LEADER_A)
    for path in ("/installations", "/maintenance", "/general-maintenance"):
        page = client.get(path)
        assert page.status_code == 200
        participant_ids = re.findall(
            r'name="participant_ids" value="(\d+)"', page.text
        )
        assert participant_ids == ["3"]
        assert "Leader Two" in page.text
        assert "Select Technical users" in page.text


def test_participant_submission_rejects_nontechnical_inactive_self_and_unknown_users(
    client, db
):
    login(client, *LEADER_A)
    response = submit_installation(
        client,
        participants=["1", "2", "4", "5", "999999"],
    )
    assert response.status_code == 422
    assert "no longer an active Technical user" in response.text
    assert db.query(InstallationRecord).count() == 0


def test_one_installation_record_can_contain_multiple_devices(client, db):
    login(client, *LEADER_A)
    response = submit_installation(
        client,
        service_id=["1", "1"],
        device_id=["1", "1"],
        serial_number=["GROUPED-CAMERA-001", "GROUPED-CAMERA-002"],
        warranty_start=["2026-07-28", "2026-07-29"],
        notes=["Camera installation notes.", "Recorder installation notes."],
        result_0="completed_successfully",
        result_1="completed_with_observations",
        photos=[
            ("photos_0", ("camera.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("recorder.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert response.status_code == 303

    record = db.query(InstallationRecord).one()
    assert record.installed_device.serial_number == "GROUPED-CAMERA-001"
    assert len(record.additional_devices) == 1
    assert record.additional_devices[0].installed_device.serial_number == "GROUPED-CAMERA-002"
    assert [item.notes for item in record.work_items] == [
        "Camera installation notes.",
        "Recorder installation notes.",
    ]
    assert [item.result.value for item in record.work_items] == [
        "completed_successfully",
        "completed_with_observations",
    ]
    assert [len(item.photos) for item in record.work_items] == [1, 1]
    assert db.query(InstalledDevice).count() == 3

    detail = client.get(response.headers["location"]).text
    assert "GROUPED-CAMERA-001" in detail
    assert "GROUPED-CAMERA-002" in detail
    assert "Camera installation notes." in detail
    assert "Recorder installation notes." in detail
    assert record.record_number in client.get(
        "/installations/records?q=GROUPED-CAMERA-002"
    ).text
    assert record.record_number in client.get(
        "/installations/records?q=Recorder+installation+notes"
    ).text
    assert record.record_number in client.get("/records?q=GROUPED-CAMERA-002").text
    item_photo_id = record.work_items[1].photos[0].id
    assert client.get(f"/media/installation-item-photo/{item_photo_id}").status_code == 200
    logout(client)
    login(client, *CUSTOMER_B)
    assert client.get(f"/media/installation-item-photo/{item_photo_id}").status_code == 403


def test_grouped_installation_rejects_duplicate_serials(client, db):
    login(client, *LEADER_A)
    response = submit_installation(
        client,
        service_id=["1", "1"],
        device_id=["1", "1"],
        serial_number=["SAME-SERIAL", "same-serial"],
        warranty_start=["2026-07-28", "2026-07-28"],
        notes=["First device.", "Second device."],
    )
    assert response.status_code == 422
    assert "Serial numbers must be unique" in response.text
    assert db.query(InstallationRecord).count() == 0


def test_invalid_multi_installation_can_retry_with_the_same_form_token(client, db):
    login(client, *LEADER_A)
    tokens = installation_tokens(client)
    common = {
        "tokens": tokens,
        "service_id": ["1", "1"],
        "device_id": ["1", "1"],
        "serial_number": ["RETRY-SERIAL-001", "RETRY-SERIAL-002"],
        "warranty_start": ["2026-07-28", "2026-07-28"],
        "notes": ["First installation.", "Second installation."],
        "result_1": "completed_successfully",
    }
    invalid = submit_installation(
        client,
        **common,
        photos=[("photos_0", ("first.jpg", make_image(), "image/jpeg"))],
    )
    assert invalid.status_code == 422
    assert "Attach at least one installation photo" in invalid.text
    assert "already submitted" not in invalid.text

    corrected = submit_installation(
        client,
        **common,
        photos=[
            ("photos_0", ("first.jpg", make_image(), "image/jpeg")),
            ("photos_1", ("second.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert corrected.status_code == 303
    assert db.query(InstallationRecord).count() == 1
    csrf_of,
