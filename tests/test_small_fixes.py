from pathlib import Path

import seed

from app.models import InstallationRecord, MaintenanceRecord
from tests.conftest import (
    LEADER_A,
    login,
    submit_installation,
    submit_record,
)


def test_seed_reset_guard_refuses_production_without_prompting(monkeypatch):
    monkeypatch.setattr(seed.settings, "environment", "production")

    def unexpected_prompt(_prompt):
        raise AssertionError("production reset must not prompt or touch the database")

    assert seed.confirm_reset(unexpected_prompt) is False


def test_seed_reset_guard_requires_the_exact_database_name(monkeypatch):
    monkeypatch.setattr(seed.settings, "environment", "development")
    expected = seed.make_url(seed.settings.database_url).database
    assert seed.confirm_reset(lambda _prompt: "wrong-database") is False
    assert seed.confirm_reset(lambda _prompt: expected) is True


def test_production_service_documentation_uses_settings_driven_launcher():
    documentation = Path("docs/PRODUCTION_UPDATES.md").read_text(encoding="utf-8")
    assert "Arguments:         serve.py" in documentation
    assert "SMS_ENV_FILE=C:\\ServiceManagement\\shared\\.env" in documentation
    assert "listens on `0.0.0.0`" in documentation
    assert "port-proxy" not in documentation.lower()


def test_live_entry_forms_and_participant_selection_still_work(client, db):
    login(client, *LEADER_A)

    installation_form = client.get("/installations/submit")
    maintenance_form = client.get("/maintenance/submit")
    assert installation_form.status_code == 200
    assert maintenance_form.status_code == 200
    assert 'name="participant_ids"' in installation_form.text
    assert 'name="participant_ids"' in maintenance_form.text
    assert "data-chips" not in installation_form.text
    assert "data-chips" not in maintenance_form.text

    installation = submit_installation(
        client,
        participants=["3"],
        serial_number="DEAD-CODE-CHECK-001",
    )
    maintenance = submit_record(client, participants=["3"])
    assert installation.status_code == 303
    assert maintenance.status_code == 303

    db.expire_all()
    installation_record = db.query(InstallationRecord).one()
    maintenance_record = db.query(MaintenanceRecord).one()
    assert [row.user_id for row in installation_record.participants] == [3]
    assert [row.user_id for row in maintenance_record.participants] == [3]
