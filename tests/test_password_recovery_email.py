"""Administrator-only verified-email password recovery."""
from __future__ import annotations

from app.config import settings
from app.models import (
    AccountRecoveryToken,
    AdminRecoveryContact,
    User,
    UserAuthState,
)
from tests.conftest import ADMIN, LEADER_A, csrf_of, login, logout


def _configure_mail(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from_email", "service@test.local")


def _verify_admin_recovery_email(client, db, monkeypatch) -> str:
    import app.routers.admin as admin_router

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        admin_router,
        "send_verification_email",
        lambda email, token: sent.append((email, token)),
    )
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    response = client.post(
        "/users/1/recovery-email",
        data={"recovery_email": "owner@example.com", "csrf_token": token},
    )
    assert response.status_code == 303
    assert sent and sent[0][0] == "owner@example.com"
    verification_token = sent[0][1]
    assert client.get(
        f"/recovery-email/verify?token={verification_token}"
    ).status_code == 303
    db.expire_all()
    assert db.get(AdminRecoveryContact, 1).verified_at is not None
    return verification_token


def test_login_page_exposes_administrator_forgot_password(client):
    page = client.get("/login")
    assert page.status_code == 200
    assert 'href="/forgot-password"' in page.text
    forgot = client.get("/forgot-password")
    assert "Administrator password recovery" in forgot.text
    assert "Technical and Customer passwords" in forgot.text


def test_verified_admin_can_reset_by_single_use_email_link(
    client, db, monkeypatch
):
    import app.routers.auth as auth_router

    _configure_mail(monkeypatch)
    _verify_admin_recovery_email(client, db, monkeypatch)
    logout(client)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        auth_router,
        "send_reset_email",
        lambda email, token: sent.append((email, token)),
    )

    request_token = csrf_of(client, "/forgot-password")
    response = client.post(
        "/forgot-password",
        data={"identifier": "admin", "csrf_token": request_token},
    )
    assert response.status_code == 200
    assert "If that matches a verified Administrator account" in response.text
    assert sent and sent[0][0] == "owner@example.com"
    raw_token = sent[0][1]
    stored = db.query(AccountRecoveryToken).filter(
        AccountRecoveryToken.purpose == "reset_password"
    ).one()
    assert raw_token != stored.token_hash

    reset_path = f"/forgot-password/reset?token={raw_token}"
    reset_token = csrf_of(client, reset_path)
    reset = client.post(
        "/forgot-password/reset",
        data={
            "token": raw_token,
            "password": "Recovered@2026",
            "password_confirmation": "Recovered@2026",
            "csrf_token": reset_token,
        },
    )
    assert reset.status_code == 303
    assert reset.headers["location"] == "/login"
    assert client.get(reset_path).status_code == 400
    db.expire_all()
    assert db.get(UserAuthState, 1).version == 1
    assert login(client, ADMIN[0], ADMIN[1]).status_code == 401
    assert login(client, ADMIN[0], "Recovered@2026").status_code == 303


def test_forgot_password_never_sends_for_technical_unknown_or_unverified(
    client, db, monkeypatch
):
    import app.routers.auth as auth_router

    _configure_mail(monkeypatch)
    db.add(
        AdminRecoveryContact(
            user_id=2,
            email="technical@example.com",
            verified_at=None,
        )
    )
    db.commit()
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        auth_router,
        "send_reset_email",
        lambda email, token: sent.append((email, token)),
    )
    for identifier in (LEADER_A[0], "technical@example.com", "unknown@example.com"):
        token = csrf_of(client, "/forgot-password")
        response = client.post(
            "/forgot-password",
            data={"identifier": identifier, "csrf_token": token},
        )
        assert response.status_code == 200
        assert "If that matches a verified Administrator account" in response.text
    assert sent == []


def test_recovery_email_cannot_be_configured_for_technical_user(
    client, db, monkeypatch
):
    import app.routers.admin as admin_router

    _configure_mail(monkeypatch)
    monkeypatch.setattr(admin_router, "send_verification_email", lambda *_: None)
    login(client, *ADMIN)
    token = csrf_of(client, "/users")
    response = client.post(
        "/users/2/recovery-email",
        data={"recovery_email": "technical@example.com", "csrf_token": token},
    )
    assert response.status_code == 303
    assert db.get(AdminRecoveryContact, 2) is None
