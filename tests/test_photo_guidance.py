"""Independent project-scoped photo guidance profiles."""

import re

from app.models import (
    ProjectPhotoGuidanceRule,
    ProjectPhotoGuidanceSetting,
    GeneralMaintenanceRecord,
    InstallationRecord,
    MaintenanceRecord,
    SubProject,
    SubProjectSite,
)
from tests.conftest import (
    ADMIN,
    LEADER_A,
    csrf_of,
    login,
    logout,
    make_image,
    submit_installation,
    submit_record,
)


def assign_project_sites(db, *site_ids: int) -> None:
    sub_project = SubProject(project_id=1, name="Photo guidance scope")
    sub_project.site_assignments = [SubProjectSite(site_id=site_id) for site_id in site_ids]
    db.add(sub_project)
    db.commit()


def save_rule(client, token: str, *, before: str = ""):
    return client.post(
        "/projects/1/photo-guidance/rules",
        data={
            "csrf_token": token,
            "profile_name": "Solar Solution",
            "before_alert": before or "Show the complete mounting surface.",
            "after_alert": "Include the final camera direction.",
            "before_descriptions": "Mounting point before work\nExisting cable route",
            "after_descriptions": "Camera mounted and aligned\nArea cleaned after work",
            "guidance_enabled": "on",
        },
    )


def test_admin_manages_project_photo_guidance_and_technical_user_cannot(client, db):
    assign_project_sites(db, 1, 2)
    login(client, *LEADER_A)
    assert client.get("/projects/1/photo-guidance").status_code == 403

    logout(client)
    login(client, *ADMIN)
    page = client.get("/projects/1/photo-guidance")
    assert page.status_code == 200
    assert "Photo Guidance" in page.text
    assert "Guidance scope" not in page.text
    assert "Profile name" in page.text
    assert 'data-description-editor' in page.text
    assert 'data-add-description' in page.text
    assert 'data-guidance-preview="before"' in page.text
    projects_page = client.get("/projects?project_id=1")
    assert 'class="card project-photo-guidance-card"' in projects_page.text
    assert "Manage Photo Guidance" in projects_page.text
    token = csrf_of(client, "/projects/1/photo-guidance")

    enabled = client.post(
        "/projects/1/photo-guidance/settings",
        data={"csrf_token": token, "enabled": "on"},
    )
    assert enabled.status_code == 303
    assert db.query(ProjectPhotoGuidanceSetting).filter_by(project_id=1).one().enabled

    created = save_rule(client, token)
    assert created.status_code == 303
    rule = db.query(ProjectPhotoGuidanceRule).filter_by(project_id=1).one()
    assert rule.name == "Solar Solution"
    assert [(entry.stage, entry.description) for entry in rule.descriptions] == [
        ("after", "Camera mounted and aligned"),
        ("after", "Area cleaned after work"),
        ("before", "Mounting point before work"),
        ("before", "Existing cable route"),
    ]


def test_installation_lookup_applies_project_rule_to_every_site_and_respects_toggle(client, db):
    assign_project_sites(db, 1, 2)
    login(client, *ADMIN)
    token = csrf_of(client, "/projects/1/photo-guidance")
    client.post(
        "/projects/1/photo-guidance/settings",
        data={"csrf_token": token, "enabled": "on"},
    )
    save_rule(client, token)

    logout(client)
    login(client, *LEADER_A)
    rule = db.query(ProjectPhotoGuidanceRule).filter_by(project_id=1).one()
    first_site = client.get(
        f"/photo-guidance?project_id=1&profile_id={rule.id}&work_site_id=1"
    )
    assert first_site.status_code == 200
    assert first_site.json()["scope"] == "project"
    assert first_site.json()["before"]["alert"] == "Show the complete mounting surface."

    project_default = client.get(
        f"/photo-guidance?project_id=1&profile_id={rule.id}&work_site_id=2"
    ).json()
    assert project_default["scope"] == "project"
    assert project_default["before"]["descriptions"] == [
        "Mounting point before work",
        "Existing cable route",
    ]

    setting = db.query(ProjectPhotoGuidanceSetting).filter_by(project_id=1).one()
    setting.enabled = False
    db.commit()
    assert client.get(
        f"/photo-guidance?project_id=1&profile_id={rule.id}&work_site_id=1"
    ).json() == {"enabled": False}


def test_admin_can_edit_alerts_descriptions_and_enable_state(client, db):
    assign_project_sites(db, 1)
    login(client, *ADMIN)
    token = csrf_of(client, "/projects/1/photo-guidance")
    save_rule(client, token)
    rule = db.query(ProjectPhotoGuidanceRule).filter_by(project_id=1).one()

    response = client.post(
        "/projects/1/photo-guidance/rules",
        data={
            "csrf_token": token,
            "rule_id": str(rule.id),
            "profile_name": "Solar Solution",
            "guidance_enabled": "on",
            "before_alert": "Updated Before guidance",
            "after_alert": "Updated After guidance",
            "before_descriptions": ["Updated before one", "Updated before two"],
            "after_descriptions": ["Updated after one"],
        },
    )

    assert response.status_code == 303
    db.expire_all()
    updated = db.get(ProjectPhotoGuidanceRule, rule.id)
    assert updated.before_alert == "Updated Before guidance"
    assert updated.after_alert == "Updated After guidance"
    assert [(entry.stage, entry.position, entry.description) for entry in updated.descriptions] == [
        ("after", 0, "Updated after one"),
        ("before", 0, "Updated before one"),
        ("before", 1, "Updated before two"),
    ]
    assert db.query(ProjectPhotoGuidanceSetting).filter_by(project_id=1).one().enabled

    page = client.get("/projects/1/photo-guidance")
    assert "Updated Before guidance" in page.text
    assert "Updated before one" in page.text
    assert "Updated after one" in page.text
    assert "2 Before" in page.text
    assert "1 After" in page.text


def test_duplicate_is_rejected_and_admin_can_delete_rule(client, db):
    assign_project_sites(db, 1)
    login(client, *ADMIN)
    token = csrf_of(client, "/projects/1/photo-guidance")
    save_rule(client, token)
    rule = db.query(ProjectPhotoGuidanceRule).filter_by(project_id=1).one()

    duplicate = save_rule(client, token, before="Duplicate should not replace the rule")
    assert duplicate.status_code == 303
    db.expire_all()
    assert db.query(ProjectPhotoGuidanceRule).filter_by(project_id=1).count() == 1
    assert db.get(ProjectPhotoGuidanceRule, rule.id).before_alert == "Show the complete mounting surface."

    deleted = client.post(
        f"/projects/1/photo-guidance/rules/{rule.id}/delete",
        data={"csrf_token": token},
    )
    assert deleted.status_code == 303
    assert db.query(ProjectPhotoGuidanceRule).filter_by(project_id=1).count() == 0
    assert db.query(ProjectPhotoGuidanceSetting).filter_by(project_id=1).one().enabled


def test_existing_rule_without_setting_is_enabled_for_backward_compatibility(client, db):
    assign_project_sites(db, 1)
    rule = ProjectPhotoGuidanceRule(
        project_id=1,
        name="Existing profile",
        before_alert="Existing rule alert",
    )
    db.add(rule)
    db.commit()

    login(client, *LEADER_A)
    payload = client.get(
        f"/photo-guidance?project_id=1&profile_id={rule.id}&work_site_id=1"
    ).json()
    assert payload["enabled"] is True
    assert payload["before"]["alert"] == "Existing rule alert"


def test_photo_guidance_hooks_are_available_in_all_data_entry_forms(client):
    login(client, *LEADER_A)
    installation = client.get("/installations")
    assert installation.status_code == 200
    assert "data-photo-guidance" in installation.text
    assert "photo_guidance_profile_id" in installation.text
    assert 'data-photo-stage="before"' in installation.text
    assert 'data-photo-stage="after"' in installation.text
    preventive = client.get("/maintenance").text
    maintenance = client.get("/general-maintenance").text
    assert "data-photo-guidance" in preventive
    assert "photo_guidance_profile_id" in preventive
    assert "data-photo-guidance" in maintenance
    assert "photo_guidance_profile_id" in maintenance


def test_lookup_rejects_site_outside_project(client, db):
    assign_project_sites(db, 1)
    login(client, *ADMIN)
    token = csrf_of(client, "/projects/1/photo-guidance")
    save_rule(client, token)
    rule = db.query(ProjectPhotoGuidanceRule).filter_by(project_id=1).one()
    logout(client)
    login(client, *LEADER_A)
    response = client.get(
        f"/photo-guidance?project_id=1&profile_id={rule.id}&work_site_id=2"
    )
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_selected_profile_is_saved_for_every_data_entry_type(client, db):
    assign_project_sites(db, 1)
    profile = ProjectPhotoGuidanceRule(project_id=1, name="Solar Solution")
    db.add(profile)
    db.commit()

    login(client, *LEADER_A)
    assert submit_installation(
        client,
        serial_number="GUIDANCE-INSTALL-1",
        photo_guidance_profile_id=str(profile.id),
    ).status_code == 303
    assert submit_record(
        client,
        photo_guidance_profile_id=str(profile.id),
    ).status_code == 303

    page = client.get("/general-maintenance")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    response = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": csrf,
            "form_token": form_token,
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": "1",
            "photo_guidance_profile_id": str(profile.id),
            "result_0": "completed_successfully",
        },
        files=[("photos_0", ("proof.jpg", make_image(), "image/jpeg"))],
    )
    assert response.status_code == 303

    assert db.query(InstallationRecord).one().work_items[0].photo_guidance_profile_id == profile.id
    assert db.query(MaintenanceRecord).one().work_items[0].photo_guidance_profile_id == profile.id
    assert db.query(GeneralMaintenanceRecord).one().work_items[0].photo_guidance_profile_id == profile.id


def test_admin_can_select_profile_while_editing_every_record_type(client, db):
    assign_project_sites(db, 1)
    profile = ProjectPhotoGuidanceRule(project_id=1, name="Maintenance Checklist")
    db.add(profile)
    db.commit()
    login(client, *ADMIN)

    assert submit_installation(client, serial_number="GUIDANCE-EDIT-1").status_code == 303
    assert submit_record(client).status_code == 303
    page = client.get("/general-maintenance")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    assert client.post(
        "/general-maintenance/submit",
        data={"csrf_token": csrf, "form_token": form_token, "project_id": "1", "work_site_id": "1", "service_type_id": "1", "result_0": "completed_successfully"},
        files=[("photos_0", ("proof.jpg", make_image(), "image/jpeg"))],
    ).status_code == 303

    cases = [
        ("/installations/records/{id}/edit", db.query(InstallationRecord).one()),
        ("/maintenance/records/{id}/edit", db.query(MaintenanceRecord).one()),
        ("/general-maintenance/records/{id}/edit", db.query(GeneralMaintenanceRecord).one()),
    ]
    for route, record in cases:
        item = record.work_items[0]
        edit_url = route.format(id=record.id)
        edit_page = client.get(edit_url)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', edit_page.text).group(1)
        form_token = re.search(r'name="form_token" value="([^"]+)"', edit_page.text).group(1)
        response = client.post(
            edit_url,
            data={
                "csrf_token": csrf,
                "form_token": form_token,
                "existing_item_id": str(item.id),
                f"existing_result_{item.id}": item.result.value,
                f"existing_notes_{item.id}": item.notes or "",
                f"existing_issue_description_{item.id}": getattr(item, "issue_description", "") or "",
                f"existing_recommendations_{item.id}": getattr(item, "recommendations", "") or "",
                f"existing_handover_notes_{item.id}": getattr(item, "handover_notes", "") or "",
                f"existing_photo_guidance_profile_id_{item.id}": str(profile.id),
            },
        )
        assert response.status_code == 303
        db.expire_all()
        assert db.get(type(item), item.id).photo_guidance_profile_id == profile.id


def test_profile_from_another_project_is_rejected(client, db):
    profile = ProjectPhotoGuidanceRule(project_id=2, name="Other Project Profile")
    db.add(profile)
    db.commit()
    login(client, *LEADER_A)

    response = submit_installation(
        client,
        serial_number="GUIDANCE-WRONG-PROJECT",
        photo_guidance_profile_id=str(profile.id),
    )

    assert response.status_code == 422
    assert "belonging to the selected Main Project" in response.text
    assert db.query(InstallationRecord).count() == 0
