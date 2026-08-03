"""Administrator-only account recovery primitives and SMTP delivery."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from email.utils import parseaddr

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .models import (
    AccountRecoveryAttempt,
    AccountRecoveryToken,
    AdminRecoveryContact,
    User,
    UserAuthState,
    UserRole,
    utcnow,
)

RESET_PURPOSE = "reset_password"
VERIFY_PURPOSE = "verify_email"
RESET_LIFETIME = timedelta(minutes=15)
VERIFY_LIFETIME = timedelta(hours=24)
THROTTLE_WINDOW = timedelta(minutes=15)


class MailDeliveryError(RuntimeError):
    pass


def valid_email(value: str) -> bool:
    _, address = parseaddr(value.strip())
    return (
        address == value.strip()
        and 3 <= len(address) <= 254
        and "@" in address
        and "." in address.rsplit("@", 1)[-1]
    )


def _digest(value: str) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_token(
    db: Session,
    user_id: int,
    purpose: str,
    lifetime: timedelta,
) -> str:
    now = utcnow()
    existing = list(
        db.scalars(
            select(AccountRecoveryToken).where(
                AccountRecoveryToken.user_id == user_id,
                AccountRecoveryToken.purpose == purpose,
                AccountRecoveryToken.used_at.is_(None),
            )
        )
    )
    for row in existing:
        row.used_at = now
    raw = secrets.token_urlsafe(32)
    db.add(
        AccountRecoveryToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=token_digest(raw),
            expires_at=now + lifetime,
            created_at=now,
        )
    )
    return raw


def valid_token(
    db: Session, raw_token: str, purpose: str
) -> tuple[AccountRecoveryToken, User] | None:
    row = db.scalar(
        select(AccountRecoveryToken).where(
            AccountRecoveryToken.token_hash == token_digest(raw_token),
            AccountRecoveryToken.purpose == purpose,
            AccountRecoveryToken.used_at.is_(None),
            AccountRecoveryToken.expires_at > utcnow(),
        )
    )
    if row is None:
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active or user.role != UserRole.ADMIN:
        return None
    return row, user


def bump_auth_version(db: Session, user_id: int) -> int:
    state = db.get(UserAuthState, user_id)
    if state is None:
        state = UserAuthState(user_id=user_id, version=1, updated_at=utcnow())
        db.add(state)
    else:
        state.version += 1
        state.updated_at = utcnow()
    return state.version


def auth_version(db: Session, user_id: int) -> int:
    state = db.get(UserAuthState, user_id)
    return state.version if state else 0


def record_attempt_and_check_limit(
    db: Session, identifier: str, ip_address: str
) -> bool:
    now = utcnow()
    since = now - THROTTLE_WINDOW
    identifier_hash = _digest(identifier.strip().lower())
    ip_hash = _digest(ip_address)
    identifier_count = int(
        db.scalar(
            select(func.count(AccountRecoveryAttempt.id)).where(
                AccountRecoveryAttempt.identifier_hash == identifier_hash,
                AccountRecoveryAttempt.created_at >= since,
            )
        )
        or 0
    )
    ip_count = int(
        db.scalar(
            select(func.count(AccountRecoveryAttempt.id)).where(
                AccountRecoveryAttempt.ip_hash == ip_hash,
                AccountRecoveryAttempt.created_at >= since,
            )
        )
        or 0
    )
    db.add(
        AccountRecoveryAttempt(
            identifier_hash=identifier_hash,
            ip_hash=ip_hash,
            created_at=now,
        )
    )
    return identifier_count < 5 and ip_count < 20


def find_verified_admin(
    db: Session, identifier: str
) -> tuple[User, AdminRecoveryContact] | None:
    row = db.execute(
        select(User, AdminRecoveryContact)
        .join(AdminRecoveryContact, AdminRecoveryContact.user_id == User.id)
        .where(
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
            AdminRecoveryContact.verified_at.is_not(None),
            or_(
                func.lower(User.username) == identifier.strip().lower(),
                func.lower(AdminRecoveryContact.email) == identifier.strip().lower(),
            ),
        )
    ).first()
    return (row[0], row[1]) if row else None


def send_email(recipient: str, subject: str, body: str) -> None:
    if not settings.email_delivery_configured:
        raise MailDeliveryError("Email delivery is not configured.")
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_starttls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError("Email delivery failed.") from exc


def send_reset_email(recipient: str, token: str) -> None:
    link = f"{settings.public_base_url}/forgot-password/reset?token={token}"
    send_email(
        recipient,
        f"Reset your {settings.app_name} Administrator password",
        "A password reset was requested for your Administrator account.\n\n"
        f"Open this single-use link within 15 minutes:\n{link}\n\n"
        "If you did not request this, ignore this email.",
    )


def send_verification_email(recipient: str, token: str) -> None:
    link = f"{settings.public_base_url}/recovery-email/verify?token={token}"
    send_email(
        recipient,
        f"Verify your {settings.app_name} recovery email",
        "Verify this email for Administrator password recovery.\n\n"
        f"Open this single-use link within 24 hours:\n{link}\n\n"
        "If you did not configure this address, ignore this email.",
    )
