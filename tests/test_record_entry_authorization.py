"""Permission and Project boundaries shared by the three service-entry forms."""
from __future__ import annotations

import re

import pytest

from app.config import settings
from app.models import (
    AccessScope,
    GeneralMaintenanceRecord,
    InstallationRecord,
    MaintenanceRecord,
    ProjectTeamMember,
    User,
    UserDepartmentPermission,
    UserDepartmentScope,
)
from tests.conftest import (
    ADMIN,
    LEADER_A,
    ensure_service_quotation,
    login,
    logout,
    make_image,
    submit_installation,
    submit_record,
)


KINDS = (
    ("installation", "/installations/submit", InstallationRecord, "records.create_installation"),
    ("preventive", "/maintenance/submit", MaintenanceRecord, "records.create_preventive"),
    ("maintenance", "/general-maintenance/submit", GeneralMaintenanceRecord, "records.create_maintenance"),
)


def _tokens(page):
    assert page.status_code == 200, page.text
    return {
        key: re.search(rf'name="{key}" value="([^"]+)"', page.text).group(1)
        for key in ("csrf_token", "form_token")
    }


def _post_entry(client, kind, path, tokens, *, project_ids, append_record_id=None):
    count = len(project_ids)
    data = {
        **tokens,
        "project_id": [str(value) for value in project_ids],
        "work_site_id": [str(value) for value in project_ids],
        "item_scope_index": [str(index) for index in range(count)],
        "service_type_id": ["1"] * count,
        "result_0": "completed_successfully",
        "notes": ["Authorization test"] * count,
    }
    if append_record_id is not None:
        data["append_record_id"] = str(append_record_id)
    if kind == "installation":
        data.update({
            "device_id": ["1"] * count,
            "serial_number": [
                f"P14-SN-{append_record_id or 'NEW'}-{index}"
                for index in range(count)
            ],
            "quotation_number": [ensure_service_quotation(value) for value in project_ids],
        })
    elif kind == "preventive":
        data["installed_device_id"] = ["1"] * count
    files = [
        (f"photos_{index}", (f"proof-{index}.jpg", make_image(), "image/jpeg"))
        for index in range(count)
    ]
    return client.post(path, data=data, files=files)


def _create_saved_record(client, db, kind, path, model):
    login(client, *ADMIN)
    if kind == "installation":
        response = submit_installation(client, serial_number="P14-ORIGINAL")
    elif kind == "preventive":
        response = submit_record(client, notes="Original preventive work")
    else:
        page = client.get(path)
        response = _post_entry(
            client, kind, path, _tokens(page), project_ids=(1,)
        )
    assert response.status_code == 303, response.text
    record = db.query(model).one()
    record_id = record.id
    original_count = len(record.work_items)
    logout(client)
    return record_id, original_count


@pytest.mark.parametrize("kind,path,model,create_key", KINDS)
def test_append_requires_edit_but_edit_only_can_add_to_saved_record(
    client, db, kind, path, model, create_key
):
    record_id, original_count = _create_saved_record(client, db, kind, path, model)
    user = db.query(User).filter_by(username=LEADER_A[0]).one()
    db.get(UserDepartmentPermission, (user.id, 1, "records.edit")).allowed = False
    db.commit()

    login(client, *LEADER_A)
    assert client.get(f"{path}?append_to={record_id}").status_code == 403
    response = client.post(path, data={"append_record_id": str(record_id)})
    assert response.status_code == 403
    db.expire_all()
    assert len(db.get(model, record_id).work_items) == original_count
    logout(client)

    db.get(UserDepartmentPermission, (user.id, 1, "records.edit")).allowed = True
    db.get(UserDepartmentPermission, (user.id, 1, create_key)).allowed = False
    db.commit()
    login(client, *LEADER_A)
    assert client.get(path).status_code == 403
    page = client.get(f"{path}?append_to={record_id}")
    response = _post_entry(
        client, kind, path, _tokens(page), project_ids=(1,),
        append_record_id=record_id,
    )
    assert response.status_code == 303, response.text
    db.expire_all()
    assert db.query(model).count() == 1
    assert len(db.get(model, record_id).work_items) == original_count + 1


@pytest.mark.parametrize("kind,path,model,create_key", KINDS)
def test_mixed_project_submission_rejects_hidden_project_atomically(
    client, db, kind, path, model, create_key
):
    user = db.query(User).filter_by(username=LEADER_A[0]).one()
    db.get(UserDepartmentScope, (user.id, 1, "records")).scope = AccessScope.SELECTED
    db.query(ProjectTeamMember).filter(
        ProjectTeamMember.user_id == user.id,
        ProjectTeamMember.project_id == 3,
    ).delete(synchronize_session=False)
    if kind == "installation":
        db.get(UserDepartmentPermission, (user.id, 1, "quotations.view")).allowed = False
    db.commit()

    if kind == "installation":
        ensure_service_quotation(1)
        ensure_service_quotation(3)
    login(client, *LEADER_A)
    page = client.get(path)
    assert page.status_code == 200
    if kind == "installation":
        assert '<option value="TEST-QUO-P1">' in page.text
        assert '<option value="TEST-QUO-P3">' not in page.text
    response = _post_entry(
        client, kind, path, _tokens(page), project_ids=(1, 3)
    )
    assert response.status_code == 422, response.text
    assert "You do not have access to this Project." in response.text
    db.expire_all()
    assert db.query(model).count() == 0
    assert not any(path.is_file() for path in settings.upload_dir.rglob("*"))

    allowed_page = client.get(path)
    allowed = _post_entry(
        client, kind, path, _tokens(allowed_page), project_ids=(1,)
    )
    assert allowed.status_code == 303, allowed.text
    db.expire_all()
    record = db.query(model).one()
    assert len(record.work_items) == 1
    assert record.work_items[0].project_id == 1

    before_files = {path for path in settings.upload_dir.rglob("*") if path.is_file()}
    append_page = client.get(f"{path}?append_to={record.id}")
    denied_append = _post_entry(
        client, kind, path, _tokens(append_page),
        project_ids=(3,), append_record_id=record.id,
    )
    assert denied_append.status_code == 422, denied_append.text
    assert "You do not have access to this Project." in denied_append.text
    db.expire_all()
    assert len(db.get(model, record.id).work_items) == 1
    assert {path for path in settings.upload_dir.rglob("*") if path.is_file()} == before_files
