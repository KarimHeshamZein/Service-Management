"""Login, session and role enforcement."""
from __future__ import annotations

import pytest

from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    INACTIVE,
    LEADER_A,
    csrf_of,
    login,
    logout,
    submit_installation,
    submit_record,
)


def test_login_succeeds_with_valid_credentials(client):
    response = login(client, *ADMIN)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert client.get("/dashboard").status_code == 200


def test_login_fails_with_wrong_password(client):
    response = login(client, ADMIN[0], "not-the-password")
    assert response.status_code == 401
    assert "match an account" in response.text
    assert client.get("/dashboard").status_code == 303  # still anonymous


def test_login_fails_for_unknown_user(client):
    response = login(client, "nobody@test.local", "whatever12345")
    assert response.status_code == 401
    # The same message for a bad user and a bad password: no account enumeration.
    assert "match an account" in response.text


def test_inactive_user_cannot_log_in(client):
    response = login(client, *INACTIVE)
    assert response.status_code == 401
    assert "deactivated" in response.text
    assert client.get("/dashboard").status_code == 303


def test_login_requires_both_fields(client):
    token = csrf_of(client)
    response = client.post("/login", data={"username": "", "password": "", "csrf_token": token})
    assert response.status_code == 401
    assert "Enter your email or username." in response.text
    assert "Enter your password." in response.text


def test_login_enables_browser_password_manager(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert 'name="username" type="text" autocomplete="username"' in response.text
    assert 'name="password" type="password" autocomplete="current-password"' in response.text
    assert "Your browser can securely save and fill this password." in response.text


def test_password_hash_is_never_rendered(client, db):
    from app.models import User

    login(client, *ADMIN)
    page = client.get("/users")
    stored = db.query(User).filter(User.username == ADMIN[0]).one()
    assert stored.password_hash.startswith("$2")
    assert stored.password_hash not in page.text
    assert "password_hash" not in page.text


@pytest.mark.parametrize(
    "path",
    ["/dashboard", "/records", "/maintenance", "/maintenance/records", "/maintenance/submit",
     "/installations", "/installations/records", "/installations/submit",
     "/projects", "/sites", "/service-types", "/devices", "/users", "/reports"],
)
def test_pages_require_authentication(client, path):
    response = client.get(path)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")


@pytest.mark.parametrize("path", ["/projects", "/sites", "/service-types"])
def test_technical_user_can_open_catalog_pages(client, path):
    login(client, *LEADER_A)
    assert client.get(path).status_code == 200


def test_technical_user_can_create_but_cannot_deactivate_catalog_data(client):
    login(client, *LEADER_A)
    token = csrf_of(client, "/dashboard")
    created = client.post(
        "/projects",
        data={"name": "Technical Project", "address": "Y", "csrf_token": token},
    )
    assert created.status_code == 303
    assert client.post(
        "/projects/1/toggle", data={"csrf_token": token}
    ).status_code == 403
    assert client.get("/users").status_code == 403


def test_admin_can_open_and_submit_maintenance(client):
    login(client, *ADMIN)
    assert client.get("/maintenance").status_code == 200
    assert client.get("/maintenance/submit").status_code == 200
    assert submit_record(client).status_code == 303


def test_admin_can_open_and_submit_installation(client):
    login(client, *ADMIN)
    assert client.get("/installations").status_code == 200
    assert client.get("/installations/submit").status_code == 200
    assert submit_installation(client).status_code == 303


def test_data_entry_modules_open_their_forms(client):
    login(client, *LEADER_A)

    installations = client.get("/installations")
    assert installations.status_code == 200
    assert 'action="/installations/submit"' in installations.text
    assert "Submit installation" in installations.text

    maintenance = client.get("/maintenance")
    assert maintenance.status_code == 200
    assert 'action="/maintenance/submit"' in maintenance.text
    assert "Submit preventive maintenance" in maintenance.text


def test_navigation_separates_data_entry_from_records(client):
    login(client, *LEADER_A)
    page = client.get("/dashboard").text

    assert 'href="/installations"' in page
    assert 'href="/maintenance"' in page
    assert 'href="/records"' in page
    assert 'href="/installations/records"' in page
    assert 'href="/maintenance/records"' in page


def test_administrator_navigation_has_all_collapsible_groups(client):
    login(client, *ADMIN)
    page = client.get("/dashboard").text

    for section in ("data-entry", "records", "reports", "management"):
        assert f'data-nav-section="{section}"' in page
        assert f'aria-controls="nav-{section}"' in page
        assert f'id="nav-{section}"' in page

    assert 'href="/reports/technician-audit"' in page
    assert 'href="/users"' in page
    assert 'href="/settings"' in page


def test_collapsible_navigation_preserves_role_visibility(client):
    login(client, *LEADER_A)
    technical_page = client.get("/dashboard").text
    assert 'data-nav-section="data-entry"' in technical_page
    assert 'data-nav-section="records"' in technical_page
    assert 'data-nav-section="reports"' in technical_page
    assert 'data-nav-section="management"' in technical_page
    assert 'href="/reports/technician-audit"' not in technical_page
    assert 'href="/users"' not in technical_page
    assert 'href="/settings"' not in technical_page

    logout(client)
    login(client, *CUSTOMER_A)
    customer_page = client.get("/records").text
    assert 'data-nav-section="records"' in customer_page
    assert 'data-nav-section="reports"' in customer_page
    assert 'data-nav-section="data-entry"' not in customer_page
    assert 'data-nav-section="management"' not in customer_page


def test_active_navigation_group_is_marked_for_automatic_opening(client):
    login(client, *ADMIN)

    installation_page = client.get("/installations").text
    assert 'data-nav-section="data-entry" data-active="true"' in installation_page

    records_page = client.get("/installations/records").text
    assert 'data-nav-section="records" data-active="true"' in records_page

    reports_page = client.get("/reports").text
    assert 'data-nav-section="reports" data-active="true"' in reports_page

    settings_page = client.get("/settings").text
    assert 'data-nav-section="management" data-active="true"' in settings_page


def test_logout_ends_the_session(client):
    login(client, *ADMIN)
    get_response = client.get("/logout")
    assert get_response.status_code in {404, 405}
    assert client.get("/dashboard").status_code == 200

    token = csrf_of(client, "/dashboard")
    response = client.post("/logout", data={"csrf_token": token})
    assert response.status_code == 303
    assert client.get("/dashboard").status_code == 303


def test_session_dies_when_account_is_deactivated_mid_session(client, db):
    from app.models import User

    login(client, *LEADER_A)
    assert client.get("/dashboard").status_code == 200

    user = db.query(User).filter(User.username == LEADER_A[0]).one()
    user.is_active = False
    db.commit()

    assert client.get("/dashboard").status_code == 303


def test_technical_navigation_shows_catalogs_but_hides_users(client):
    login(client, *LEADER_A)
    page = client.get("/dashboard").text
    assert 'href="/projects"' in page
    assert 'href="/sites"' in page
    assert 'href="/devices"' not in page
    assert 'href="/users"' not in page

    logout(client)
    login(client, *ADMIN)
    assert 'href="/projects"' in client.get("/dashboard").text
    assert 'href="/sites"' in client.get("/dashboard").text
    assert 'href="/devices"' not in client.get("/dashboard").text
    assert 'href="/users"' in client.get("/dashboard").text


def test_customer_only_reaches_records_reports_and_assigned_navigation(client):
    login(client, *CUSTOMER_A)
    assert client.get("/").headers["location"] == "/records"
    assert client.get("/records").status_code == 200
    assert client.get("/reports").status_code == 200
    for path in (
        "/dashboard",
        "/installations",
        "/maintenance",
        "/general-maintenance",
        "/projects",
        "/sites",
        "/service-types",
        "/devices",
        "/users",
    ):
        assert client.get(path).status_code == 403

    page = client.get("/records").text
    assert 'href="/records"' in page
    assert 'href="/reports"' in page
    assert 'href="/dashboard"' not in page
    assert 'href="/installations"' not in page
    assert 'href="/projects"' not in page


def test_unknown_url_renders_the_styled_error_page(client):
    """A route that doesn't exist must not fall through to raw framework JSON."""
    anonymous = client.get("/no-such-page")
    assert anonymous.status_code == 404
    assert "ERROR 404" in anonymous.text
    assert '{"detail"' not in anonymous.text

    login(client, *ADMIN)
    signed_in = client.get("/no-such-page")
    assert signed_in.status_code == 404
    assert "ERROR 404" in signed_in.text
    assert "Go to dashboard" in signed_in.text


def test_wrong_method_renders_the_styled_error_page(client):
    login(client, *ADMIN)
    response = client.post("/dashboard")
    assert response.status_code == 405
    assert "ERROR 405" in response.text
