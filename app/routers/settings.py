"""Administrator-only read-only machine status and legacy settings audit."""
from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from ..config import ENV_FILE, settings
from ..database import get_db
from ..deployment_config import (
    default_profile,
    profile_dict,
)
from ..deps import require_admin
from ..helpers import render
from ..machine_config.profile_store import MachineProfileError, load_profile
from ..models import (
    DeploymentSettings,
    DeploymentSettingsAudit,
    User,
)

router = APIRouter(prefix="/settings", dependencies=[Depends(require_admin)])

BACKUP_STATUS_GRACE = timedelta(hours=6)


def _detected_ipv4() -> list[str]:
    try:
        addresses = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return []
    return sorted({address for address in addresses if address != "127.0.0.1"})


def _runtime_database() -> dict[str, object]:
    database = make_url(settings.database_url)
    return {
        "host": database.host or "",
        "port": database.port or 5432,
        "database": database.database or "",
        "username": database.username or "",
    }


def _history(db: Session) -> list[DeploymentSettingsAudit]:
    return list(
        db.scalars(
            select(DeploymentSettingsAudit)
            .order_by(
                DeploymentSettingsAudit.created_at.desc(),
                DeploymentSettingsAudit.id.desc(),
            )
            .limit(20)
        )
    )


def _status_time(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_text(moment: datetime, *, now: datetime) -> str:
    seconds = max(0, int((now - moment).total_seconds()))
    if seconds < 90:
        return "just now"
    hours = seconds // 3600
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _backup_status(
    profile: dict[str, object],
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    if not profile.get("backup_enabled"):
        return {
            "state": "info",
            "message": "Automatic backups are disabled.",
            "completion_age": "",
            "last_success_age": "",
            "backup_file": "",
            "uploads_snapshot": "",
            "uploads_summary": "No scheduled backup will run until it is enabled.",
        }
    program_data = os.getenv("PROGRAMDATA")
    if not program_data:
        return {
            "state": "error",
            "message": "No backup status is available. Verify the scheduled task.",
            "completion_age": "",
            "last_success_age": "",
            "backup_file": "",
            "uploads_snapshot": "",
            "uploads_summary": "",
        }
    path = (
        Path(program_data)
        / "ServiceManagementSystem"
        / "database-backup-status.json"
    )
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return {
            "state": "error",
            "message": (
                "The backup status is missing or unreadable. "
                "Verify the scheduled task."
            ),
            "completion_age": "",
            "last_success_age": "",
            "backup_file": "",
            "uploads_snapshot": "",
            "uploads_summary": "",
        }
    if not isinstance(value, dict):
        return {
            "state": "error",
            "message": "The backup status is malformed. Verify the scheduled task.",
            "completion_age": "",
            "last_success_age": "",
            "backup_file": "",
            "uploads_snapshot": "",
            "uploads_summary": "",
        }

    current = now or datetime.now(timezone.utc)
    completed = _status_time(value.get("completed_utc"))
    last_success = _status_time(value.get("last_success_utc"))
    try:
        interval_days = int(value.get("interval_days"))
        if not 1 <= interval_days <= 365:
            raise ValueError
    except (TypeError, ValueError):
        interval_days = int(profile.get("backup_interval_days") or 1)

    failed = value.get("ok") is not True
    stale = (
        completed is None
        or current - completed > timedelta(days=interval_days) + BACKUP_STATUS_GRACE
    )
    if failed:
        state = "error"
        message = str(value.get("message") or "The latest backup attempt failed.")
    elif stale:
        state = "error"
        message = (
            "The latest backup is stale. Verify that the scheduled task is running."
        )
    else:
        state = "success"
        message = str(value.get("message") or "Backup completed.")

    uploads_mode = str(value.get("uploads_mode") or "skipped").lower()
    uploads_snapshot = str(value.get("uploads_snapshot") or "")
    include_uploads = bool(profile.get("backup_include_uploads"))
    if uploads_mode == "skipped" or not uploads_snapshot:
        uploads_summary = (
            "Upload snapshots are disabled. This backup is database-only and "
            "a restore will not include photos."
        )
        if state == "success" and not include_uploads:
            state = "info"
    else:
        uploads_summary = (
            f"Complete upload snapshot ({uploads_mode} mode): {uploads_snapshot}"
        )

    return {
        "state": state,
        "message": message,
        "completion_age": (
            f"Last completed {_age_text(completed, now=current)}."
            if completed and not failed
            else (
                f"Last attempt {_age_text(completed, now=current)}."
                if completed
                else ""
            )
        ),
        "last_success_age": (
            f"Last successful backup {_age_text(last_success, now=current)}."
            if failed and last_success
            else ""
        ),
        "backup_file": str(value.get("backup_file") or ""),
        "uploads_snapshot": uploads_snapshot,
        "uploads_summary": uploads_summary,
    }


def _context(
    db: Session,
) -> dict:
    saved = db.get(DeploymentSettings, 1)
    machine_path = ENV_FILE.parent / "machine-settings.json"
    try:
        values = (
            load_profile(machine_path)
            if machine_path.exists()
            else profile_dict(saved) if saved else default_profile()
        )
        profile_error_key = ""
    except MachineProfileError:
        values = profile_dict(saved) if saved else default_profile()
        profile_error_key = "ui.local.machine.settings.file.is.unreadable.open.the.service.console"
    return {
        "active_nav": "settings",
        "profile": values,
        "saved_profile": saved,
        "history": _history(db),
        "detected_ipv4": _detected_ipv4(),
        "runtime_app_host": settings.app_host,
        "runtime_app_port": settings.app_port,
        "runtime_database": _runtime_database(),
        "backup_status": _backup_status(values),
        "profile_error_key": profile_error_key,
    }


@router.get("")
def settings_page(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return render(request, "settings.html", _context(db))
