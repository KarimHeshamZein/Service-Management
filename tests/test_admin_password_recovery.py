"""Local recovery for a forgotten Administrator password."""
from __future__ import annotations

import pytest

from app.models import User
from app.security import verify_password
from reset_admin_password import AdminPasswordResetError, reset_admin_password
from tests.conftest import ADMIN, LEADER_A


def test_local_recovery_resets_an_active_admin_password(db):
    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    old_hash = admin.password_hash

    reset_admin_password(db, "ADMIN", "Recovered@2026")

    db.expire_all()
    admin = db.get(User, admin.id)
    assert admin.password_hash != old_hash
    assert verify_password("Recovered@2026", admin.password_hash)
    assert not verify_password(ADMIN[1], admin.password_hash)


def test_local_recovery_rejects_a_technical_account(db):
    technical = db.query(User).filter(User.username == LEADER_A[0]).one()
    old_hash = technical.password_hash

    with pytest.raises(AdminPasswordResetError, match="Administrator"):
        reset_admin_password(db, technical.username, "Recovered@2026")

    db.expire_all()
    assert db.get(User, technical.id).password_hash == old_hash


def test_local_recovery_rejects_inactive_admin_and_short_password(db):
    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    with pytest.raises(AdminPasswordResetError, match="at least 8"):
        reset_admin_password(db, admin.username, "short")

    admin.is_active = False
    db.commit()
    with pytest.raises(AdminPasswordResetError, match="active Administrator"):
        reset_admin_password(db, admin.username, "Recovered@2026")
