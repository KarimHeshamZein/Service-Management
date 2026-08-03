"""Interactively reset an active Administrator password from the local server.

The password is intentionally never accepted as a command-line argument, where
it could be retained in shell history or exposed in a process listing.
"""
from __future__ import annotations

import getpass
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import SessionLocal, init_db
from app.account_recovery import bump_auth_version
from app.models import User, UserRole, utcnow
from app.security import hash_password

MIN_PASSWORD_LENGTH = 8


class AdminPasswordResetError(ValueError):
    """The requested recovery reset is not safe or valid."""


def reset_admin_password(db: Session, username: str, password: str) -> User:
    """Reset one active Administrator account and commit the change."""
    normalized_username = username.strip()
    if not normalized_username:
        raise AdminPasswordResetError("Enter the Administrator username.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminPasswordResetError(
            f"The new password must contain at least {MIN_PASSWORD_LENGTH} characters."
        )

    target = db.scalar(
        select(User).where(func.lower(User.username) == normalized_username.lower())
    )
    if target is None or target.role != UserRole.ADMIN or not target.is_active:
        raise AdminPasswordResetError(
            "No active Administrator account matches that username."
        )

    target.password_hash = hash_password(password)
    target.updated_at = utcnow()
    bump_auth_version(db, target.id)
    db.commit()
    return target


def main() -> int:
    init_db()
    try:
        username = input("Administrator username [admin]: ").strip() or "admin"
        password = getpass.getpass("New password: ")
        confirmation = getpass.getpass("Confirm new password: ")
    except (EOFError, KeyboardInterrupt):
        print("\nPassword reset cancelled.", file=sys.stderr)
        return 1

    if password != confirmation:
        print("Passwords do not match. Nothing was changed.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        target = reset_admin_password(db, username, password)
    except AdminPasswordResetError as exc:
        db.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Password reset for Administrator account '{target.username}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
