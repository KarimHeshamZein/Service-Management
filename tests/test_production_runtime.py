"""Production configuration and launcher regression tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import serve


ROOT = Path(__file__).resolve().parents[1]


def _run_config(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    process_env = os.environ.copy()
    process_env.pop("SMS_ENV_FILE", None)
    process_env.pop("ENVIRONMENT", None)
    process_env.pop("APP_NAME", None)
    process_env.update(env)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.config import ENV_FILE, settings; "
            "print(ENV_FILE); print(settings.app_name); print(settings.app_port)",
        ],
        cwd=ROOT,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_explicit_absolute_environment_file_is_loaded(tmp_path):
    env_path = tmp_path / "production.env"
    env_path.write_text(
        "ENVIRONMENT=production\n"
        "SECRET_KEY=test-production-secret\n"
        "APP_NAME=Shared production config\n",
        encoding="utf-8",
    )

    result = _run_config({"SMS_ENV_FILE": str(env_path)})

    assert result.returncode == 0, result.stderr
    assert str(env_path) in result.stdout
    assert "Shared production config" in result.stdout


def test_explicit_production_file_overrides_an_inherited_stale_port(tmp_path):
    env_path = tmp_path / "production.env"
    env_path.write_text(
        "ENVIRONMENT=production\n"
        "SECRET_KEY=test-production-secret\n"
        "APP_PORT=8995\n",
        encoding="utf-8",
    )

    result = _run_config(
        {
            "SMS_ENV_FILE": str(env_path),
            "APP_PORT": "8997",
        }
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "8995"


def test_explicit_environment_file_must_be_absolute_and_exist(tmp_path):
    relative = _run_config({"SMS_ENV_FILE": "shared/.env"})
    missing = _run_config({"SMS_ENV_FILE": str(tmp_path / "missing.env")})

    assert relative.returncode != 0
    assert "SMS_ENV_FILE must be an absolute path" in relative.stderr
    assert missing.returncode != 0
    assert "SMS_ENV_FILE does not exist" in missing.stderr


def test_production_refuses_implicit_release_local_environment_file():
    result = _run_config({"ENVIRONMENT": "production"})

    assert result.returncode != 0
    assert "SMS_ENV_FILE must point to the shared .env in production" in result.stderr


def test_production_launcher_uses_configured_host_and_port(monkeypatch):
    calls = []
    monkeypatch.setattr(serve.settings, "app_host", "0.0.0.0")
    monkeypatch.setattr(serve.settings, "app_port", 8123)
    monkeypatch.setattr(serve.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs)))

    assert serve.main() == 0
    assert calls == [
        (("app.main:app",), {"host": "0.0.0.0", "port": 8123, "reload": False})
    ]
