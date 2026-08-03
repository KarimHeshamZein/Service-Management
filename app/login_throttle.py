"""Database-backed throttling for failed login attempts."""
from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import LoginAttempt, utcnow

LOGIN_THROTTLE_WINDOW = timedelta(minutes=15)
LOGIN_IDENTIFIER_LIMIT = 10
LOGIN_IP_LIMIT = 50


def _digest(value: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _attempt_hashes(identifier: str, ip_address: str) -> tuple[str, str]:
    return _digest(identifier.strip().lower()), _digest(ip_address)


def login_is_throttled(
    db: Session,
    identifier: str,
    ip_address: str,
) -> bool:
    now = utcnow()
    since = now - LOGIN_THROTTLE_WINDOW
    identifier_hash, ip_hash = _attempt_hashes(identifier, ip_address)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < since))
    identifier_count = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.identifier_hash == identifier_hash,
            LoginAttempt.created_at >= since,
        )
    )
    ip_count = db.scalar(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.ip_hash == ip_hash,
            LoginAttempt.created_at >= since,
        )
    )
    return int(identifier_count or 0) >= LOGIN_IDENTIFIER_LIMIT or int(
        ip_count or 0
    ) >= LOGIN_IP_LIMIT


def record_failed_login(
    db: Session,
    identifier: str,
    ip_address: str,
) -> None:
    identifier_hash, ip_hash = _attempt_hashes(identifier, ip_address)
    db.add(
        LoginAttempt(
            identifier_hash=identifier_hash,
            ip_hash=ip_hash,
            created_at=utcnow(),
        )
    )
    db.commit()


def clear_failed_logins(db: Session, identifier: str) -> None:
    identifier_hash = _digest(identifier.strip().lower())
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.identifier_hash == identifier_hash
        )
    )
    db.commit()
