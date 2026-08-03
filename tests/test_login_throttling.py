"""Login-throttling and anti-enumeration regression tests."""
from app.models import LoginAttempt
from tests.conftest import ADMIN, login


def test_eleventh_failed_login_is_throttled_with_generic_error(client, db):
    for _ in range(10):
        response = login(client, ADMIN[0], "wrong-password")
        assert response.status_code == 401

    response = login(client, ADMIN[0], "wrong-password")

    assert response.status_code == 429
    assert "match an account" in response.text
    assert db.query(LoginAttempt).count() == 10


def test_valid_login_before_limit_succeeds_and_clears_failures(client, db):
    for _ in range(3):
        assert login(client, ADMIN[0], "wrong-password").status_code == 401

    response = login(client, *ADMIN)

    assert response.status_code == 303
    assert db.query(LoginAttempt).count() == 0


def test_login_attempts_store_only_hashed_identity_and_ip(client, db):
    raw_username = "unknown-person@example.test"
    assert login(client, raw_username, "wrong-password").status_code == 401

    attempt = db.query(LoginAttempt).one()
    assert raw_username not in attempt.identifier_hash
    assert "testclient" not in attempt.ip_hash
    assert len(attempt.identifier_hash) == 64
    assert len(attempt.ip_hash) == 64


def test_unknown_user_and_wrong_password_remain_indistinguishable(client):
    wrong_password = login(client, ADMIN[0], "wrong-password")
    unknown_user = login(client, "unknown@example.test", "wrong-password")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert "match an account" in wrong_password.text
    assert "match an account" in unknown_user.text
