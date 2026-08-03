"""First-Administrator bootstrap for a migrated production database."""
from __future__ import annotations

import pytest

from app.models import CustomerProjectAssignment, User, UserRole
from app.security import verify_password
from create_admin import AdminBootstrapError, create_admin
from tests.conftest import ADMIN, LEADER_A, login


def _remove_all_users(db) -> None:
    db.query(CustomerProjectAssignment).delete()
    db.query(User).delete()
    db.commit()


def _remove_active_admin(db) -> None:
    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    db.delete(admin)
    db.commit()


def test_bootstrap_creates_one_active_administrator_with_a_bcrypt_hash(db):
    _remove_all_users(db)

    administrator = create_admin(
        db,
        "First Administrator",
        "first.admin",
        "Bootstrap@2026",
    )

    assert db.query(User).count() == 1
    assert administrator.role == UserRole.ADMIN
    assert administrator.is_active is True
    assert administrator.password_hash != "Bootstrap@2026"
    assert verify_password("Bootstrap@2026", administrator.password_hash)


def test_bootstrap_refuses_when_an_active_administrator_exists(db):
    before = db.query(User).count()

    with pytest.raises(AdminBootstrapError, match="active Administrator"):
        create_admin(db, "Second Admin", "second.admin", "Bootstrap@2026")

    assert db.query(User).count() == before
    assert db.query(User).filter(User.username == "second.admin").count() == 0


def test_bootstrap_succeeds_when_the_only_administrator_is_inactive(db):
    existing = db.query(User).filter(User.username == ADMIN[0]).one()
    existing.is_active = False
    db.commit()

    administrator = create_admin(
        db,
        "Recovery Administrator",
        "recovery.admin",
        "Bootstrap@2026",
    )

    assert administrator.role == UserRole.ADMIN
    assert administrator.is_active is True
    assert db.query(User).filter(
        User.role == UserRole.ADMIN,
        User.is_active.is_(True),
    ).count() == 1


@pytest.mark.parametrize(
    ("full_name", "username", "password", "message"),
    [
        ("", "new.admin", "Bootstrap@2026", "full name"),
        ("New Admin", "", "Bootstrap@2026", "username"),
        ("New Admin", "new.admin", "short", "at least 8"),
        ("New Admin", "LEADER.A@TEST.LOCAL", "Bootstrap@2026", "already in use"),
    ],
)
def test_bootstrap_rejects_invalid_or_duplicate_values_without_creating_a_user(
    db, full_name, username, password, message
):
    _remove_active_admin(db)
    before = db.query(User).count()

    with pytest.raises(AdminBootstrapError, match=message):
        create_admin(db, full_name, username, password)

    assert db.query(User).count() == before


def test_bootstrapped_administrator_can_log_in_and_reach_dashboard(client, db):
    _remove_all_users(db)
    create_admin(db, "Production Admin", "production.admin", "Bootstrap@2026")

    response = login(client, "PRODUCTION.ADMIN", "Bootstrap@2026")
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "Production Admin" in dashboard.text
