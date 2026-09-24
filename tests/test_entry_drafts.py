from __future__ import annotations

from datetime import timedelta

from app.models import EntryDraft, utcnow
from tests.conftest import ADMIN, CUSTOMER_A, LEADER_A, csrf_of, login, logout


def test_record_entry_pages_enable_autosave(client):
    login(client, *LEADER_A)
    for path in ("/installations", "/maintenance", "/general-maintenance"):
        response = client.get(path)
        assert response.status_code == 200
        assert "data-record-autosave" in response.text


def test_autosave_is_private_refreshes_and_can_be_discarded(client, db):
    login(client, *LEADER_A)
    csrf = csrf_of(client, "/maintenance")
    payload = {
        "version": 1,
        "fields": [{"name": "project_id", "ordinal": 0, "value": "1"}],
        "structure": [],
    }
    saved = client.post(
        "/drafts/autosave",
        json={
            "csrf_token": csrf,
            "draft_key": "/maintenance",
            "page_url": "/maintenance",
            "payload": payload,
        },
    )
    assert saved.status_code == 200
    assert db.query(EntryDraft).count() == 1

    loaded = client.get("/drafts/current", params={"draft_key": "/maintenance"})
    assert loaded.status_code == 200
    assert loaded.json()["draft"]["payload"] == payload
    listed = client.get("/drafts")
    assert listed.status_code == 200
    assert "/maintenance" in listed.text
    assert "Continue draft" in listed.text

    logout(client)
    login(client, *ADMIN)
    other_user = client.get("/drafts/current", params={"draft_key": "/maintenance"})
    assert other_user.status_code == 200
    assert other_user.json()["draft"] is None

    logout(client)
    login(client, *LEADER_A)
    csrf = csrf_of(client, "/maintenance")
    discarded = client.delete(
        "/drafts/current",
        params={"draft_key": "/maintenance", "csrf_token": csrf},
    )
    assert discarded.status_code == 200
    assert db.query(EntryDraft).count() == 0


def test_autosave_rejects_customers_and_bad_csrf(client):
    login(client, *CUSTOMER_A)
    assert client.get("/drafts/keepalive").status_code == 403
    logout(client)

    login(client, *LEADER_A)
    response = client.post(
        "/drafts/autosave",
        json={
            "csrf_token": "wrong",
            "draft_key": "/maintenance",
            "page_url": "/maintenance",
            "payload": {},
        },
    )
    assert response.status_code == 403


def test_keepalive_refreshes_the_authenticated_session_cookie(client):
    login(client, *LEADER_A)
    response = client.get("/drafts/keepalive")
    assert response.status_code == 200
    cookie = response.headers.get("set-cookie", "").lower()
    assert "sms_session=" in cookie
    assert "max-age=" in cookie


def test_loading_a_draft_prunes_expired_entries(client, db):
    login(client, *LEADER_A)
    current = client.get("/drafts/keepalive").json()
    db.add(
        EntryDraft(
            user_id=current["user_id"],
            draft_key="/expired",
            page_url="/maintenance",
            payload={},
            expires_at=utcnow() - timedelta(seconds=1),
        )
    )
    db.commit()
    response = client.get("/drafts/current", params={"draft_key": "/expired"})
    assert response.status_code == 200
    assert response.json()["draft"] is None
    assert db.query(EntryDraft).count() == 0


def test_edit_table_rows_retain_their_saved_site_position_marker(client, db):
    login(client, *LEADER_A)
    # Existing focused edit tests create the records themselves; this assertion
    # protects the client-side clone marker shared by all three edit workflows.
    template = open("app/templates/record_edit.html", encoding="utf-8").read()
    script = open("app/static/js/app.js", encoding="utf-8").read()
    assert 'name="existing_data_scope_position"' in template
    assert "data-existing-data-scope" in template
    assert 'field.hasAttribute("data-existing-data-scope")' in script
    assert 'field.name === "existing_data_quantity"' in script
