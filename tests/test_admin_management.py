"""Administrator management of projects, service types, devices and users."""
from __future__ import annotations

from app.models import DeviceCatalog, ServiceType, Site, User, WorkSite
from tests.conftest import ADMIN, LEADER_A, csrf_of, login, logout


def test_admin_can_add_and_edit_a_project(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/projects")

    created = client.post(
        "/projects",
        data={
            "name": "Nakheel Retail",
            "address": "Al Thumamah Road",
            "city": "Riyadh",
            "contact_person": "Lina Saad",
            "contact_number": "+966 11 355 9021",
            "csrf_token": token,
        },
    )
    assert created.status_code == 303

    site = db.query(Site).filter(Site.name == "Nakheel Retail").one()
    assert site.is_active is True
    assert site.customer_name == "Nakheel Retail"

    edited = client.post(
        f"/projects/{site.id}/edit",
        data={
            "name": "Nakheel Retail North",
            "address": "Al Thumamah Road",
            "csrf_token": token,
        },
    )
    assert edited.status_code == 303
    db.expire_all()
    assert db.get(Site, site.id).name == "Nakheel Retail North"
    assert db.get(Site, site.id).customer_name == "Nakheel Retail North"


def test_legacy_site_write_endpoint_is_removed_for_technical_users(client, db):
    login(client, *LEADER_A)
    token = csrf_of(client, "/projects")
    before = db.query(Site).count()

    response = client.post(
        "/_legacy/sites",
        data={
            "name": "Legacy Site",
            "customer_name": "Different Customer",
            "csrf_token": token,
        },
    )

    assert response.status_code in {404, 405}
    assert db.query(Site).count() == before
    assert db.query(Site).filter(Site.name == "Legacy Site").count() == 0


def test_admin_can_deactivate_a_project_and_it_leaves_the_form(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/projects")
    site = db.query(Site).filter(Site.name == "Tower A").one()

    client.post(f"/projects/{site.id}/toggle", data={"csrf_token": token})
    db.expire_all()
    assert db.get(Site, site.id).is_active is False

    logout(client)
    login(client, *LEADER_A)
    assert "Tower A" not in client.get("/maintenance/submit").text


def test_project_search_filters_the_list(client):
    login(client, *ADMIN)
    assert "Tower A" in client.get("/projects?q=Tower").text
    assert "Tower A" not in client.get("/projects?q=zzzznothing").text


def test_admin_can_manage_one_field_sites_catalog(client, db):
    from app.models import WorkSite

    login(client, *ADMIN)
    token = csrf_of(client, "/sites")
    response = client.post("/sites", data={"name": "Gate 4", "csrf_token": token})
    assert response.status_code == 303
    site = db.query(WorkSite).filter(WorkSite.name == "Gate 4").one()
    assert "Gate 4" in client.get("/sites?q=Gate%204").text

    client.post(
        f"/sites/{site.id}/edit",
        data={"name": "Gate 04", "csrf_token": token},
    )
    db.expire_all()
    assert db.get(WorkSite, site.id).name == "Gate 04"


def test_admin_can_add_and_deactivate_a_service_type(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/service-types")

    response = client.post(
        "/service-types",
        data={"name": "Gate Service", "description": "Barriers and motors", "csrf_token": token},
    )
    assert response.status_code == 303

    service = db.query(ServiceType).filter(ServiceType.name == "Gate Service").one()
    assert service.is_active is True

    client.post(f"/service-types/{service.id}/toggle", data={"csrf_token": token})
    db.expire_all()
    assert db.get(ServiceType, service.id).is_active is False


def test_legacy_device_catalog_redirects_to_unified_pricing_items(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    response = client.post(
        "/pricing/items",
        data={
            "name": "Network Router",
            "model": "RUT956",
            "unit_price": "0",
            "currency": "SAR",
            "service_enabled": "1",
            "csrf_token": token,
        },
    )
    assert response.status_code == 303
    device = db.query(DeviceCatalog).filter(DeviceCatalog.model == "RUT956").one()
    assert "Network Router" in client.get("/pricing/items?q=Network+Router").text
    assert client.get("/devices").headers["location"] == "/pricing/items"

    client.cookies.clear()
    login(client, *LEADER_A)
    assert "RUT956" in client.get("/installations").text


def test_duplicate_service_name_is_rejected(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/service-types")
    client.post("/service-types", data={"name": "camera service", "csrf_token": token})
    assert db.query(ServiceType).filter(ServiceType.name.ilike("camera service")).count() == 1


def test_inactive_service_is_not_offered_in_the_form(client):
    login(client, *LEADER_A)
    page = client.get("/maintenance/submit").text
    assert "Camera Service" in page
    assert "Retired Service" not in page


def test_admin_can_create_a_technical_user_who_can_then_log_in(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/users")

    response = client.post(
        "/users",
        data={
            "full_name": "Omar Al-Rashid",
            "username": "omar@test.local",
            "password": "Onsite@2026",
            "role": "technical",
            "phone": "+966 55 402 8811",
            "csrf_token": token,
        },
    )
    assert response.status_code == 303

    created = db.query(User).filter(User.username == "omar@test.local").one()
    assert created.password_hash != "Onsite@2026"
    assert created.password_hash.startswith("$2")

    logout(client)
    assert login(client, "omar@test.local", "Onsite@2026").status_code == 303


def test_admin_assigns_customer_projects_on_create_and_edit(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    created = client.post(
        "/users",
        data={
            "full_name": "Customer Viewer",
            "username": "viewer@test.local",
            "password": "Viewer@2026",
            "role": "customer",
            "project_ids": ["1"],
            "csrf_token": token,
        },
    )
    assert created.status_code == 303

    customer = db.query(User).filter(User.username == "viewer@test.local").one()
    assert customer.role.value == "customer"
    assert customer.assigned_project_ids == {1}

    edited = client.post(
        f"/users/{customer.id}/edit",
        data={
            "full_name": "Customer Viewer",
            "username": "viewer@test.local",
            "phone": "",
            "role": "customer",
            "project_ids": ["3"],
            "csrf_token": token,
        },
    )
    assert edited.status_code == 303
    db.expire_all()
    customer = db.query(User).filter(User.username == "viewer@test.local").one()
    assert customer.assigned_project_ids == {3}


def test_customer_creation_requires_an_assigned_project(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    client.post(
        "/users",
        data={
            "full_name": "Unassigned Customer",
            "username": "unassigned@test.local",
            "password": "Viewer@2026",
            "role": "customer",
            "csrf_token": token,
        },
    )
    assert (
        db.query(User).filter(User.username == "unassigned@test.local").count()
        == 0
    )


def test_short_passwords_are_rejected(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    client.post(
        "/users",
        data={"full_name": "Weak", "username": "weak@test.local", "password": "short",
              "role": "technical", "csrf_token": token},
    )
    assert db.query(User).filter(User.username == "weak@test.local").count() == 0


def test_password_reset_replaces_the_old_password(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    leader = db.query(User).filter(User.username == LEADER_A[0]).one()

    client.post(f"/users/{leader.id}/reset-password",
                data={"password": "BrandNew@2026", "csrf_token": token})
    logout(client)

    assert login(client, LEADER_A[0], LEADER_A[1]).status_code == 401
    assert login(client, LEADER_A[0], "BrandNew@2026").status_code == 303


def test_admin_cannot_deactivate_their_own_account(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    admin = db.query(User).filter(User.username == ADMIN[0]).one()

    client.post(f"/users/{admin.id}/toggle", data={"csrf_token": token})
    db.expire_all()
    assert db.get(User, admin.id).is_active is True


def test_write_actions_require_a_valid_csrf_token(client, db):
    login(client, *ADMIN)
    before = db.query(Site).count()
    response = client.post(
        "/projects",
        data={"name": "Forged", "address": "Y", "csrf_token": "wrong"},
    )
    assert response.status_code == 303
    assert db.query(Site).count() == before


def test_admin_deletes_unused_catalog_rows_and_users(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/projects")
    project = Site(name="Disposable Project", customer_name="Disposable Project", address="Test")
    site = WorkSite(name="Disposable Gate")
    service = ServiceType(name="Disposable Service")
    db.add_all([project, site, service])
    db.commit()
    ids = project.id, site.id, service.id

    assert client.post(
        f"/projects/{project.id}/delete", data={"csrf_token": token}
    ).status_code == 303
    assert client.post(
        f"/sites/{site.id}/delete", data={"csrf_token": token}
    ).status_code == 303
    assert client.post(
        f"/service-types/{service.id}/delete", data={"csrf_token": token}
    ).status_code == 303
    db.expire_all()
    assert db.get(Site, ids[0]) is None
    assert db.get(WorkSite, ids[1]) is None
    assert db.get(ServiceType, ids[2]) is None

    client.post(
        "/users",
        data={
            "full_name": "Disposable User",
            "username": "disposable@test.local",
            "password": "Disposable@2026",
            "role": "technical",
            "csrf_token": token,
        },
    )
    disposable = db.query(User).filter(User.username == "disposable@test.local").one()
    user_id = disposable.id
    assert client.post(
        f"/users/{user_id}/delete", data={"csrf_token": token}
    ).status_code == 303
    db.expire_all()
    assert db.get(User, user_id) is None


def test_referenced_catalog_rows_are_deactivated_instead_of_deleted(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/projects")

    assert client.post("/projects/1/delete", data={"csrf_token": token}).status_code == 303
    assert client.post("/sites/1/delete", data={"csrf_token": token}).status_code == 303
    db.expire_all()
    assert db.get(Site, 1).is_active is False
    assert db.get(WorkSite, 1).is_active is False


def test_technical_users_have_edit_but_not_delete_catalog_controls(client, db):
    login(client, *LEADER_A)
    for path in ("/projects", "/sites", "/service-types"):
        page = client.get(path)
        assert page.status_code == 200
        assert ">Edit<" in page.text
        assert "/delete" not in page.text

    token = csrf_of(client, "/projects")
    for path in (
        "/projects/1/delete",
        "/sites/1/delete",
        "/service-types/1/delete",
    ):
        assert client.post(path, data={"csrf_token": token}).status_code == 403
    assert client.get("/users").status_code == 403
