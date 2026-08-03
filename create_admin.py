"""Interactively create the first Administrator on a migrated installation.

The password is intentionally never accepted as a command-line argument, where
it could be retained in shell history or exposed in a process listing.
"""
from __future__ import annotations

import getpass
import sys

from sqlalchemy import func, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, init_db
from app.models import User, UserRole
from app.security import hash_password

MIN_PASSWORD_LENGTH = 8


class AdminBootstrapError(ValueError):
    """The requested first-Administrator bootstrap is not safe or valid."""


def _reject_existing_active_admin(db: Session) -> None:
    active_admin_id = db.scalar(
        select(User.id)
        .where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        .limit(1)
    )
    if active_admin_id is not None:
        raise AdminBootstrapError(
            "An active Administrator already exists. Use the Users page to manage "
            "accounts or reset_admin_password.py to recover its password."
        )


def create_admin(db: Session, full_name: str, username: str, password: str) -> User:
    """Create and commit the first active Administrator account."""
    _reject_existing_active_admin(db)

    normalized_name = full_name.strip()
    normalized_username = username.strip()
    if not normalized_name:
        raise AdminBootstrapError("Enter the Administrator full name.")
    if not normalized_username:
        raise AdminBootstrapError("Enter the Administrator username.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminBootstrapError(
            f"The password must contain at least {MIN_PASSWORD_LENGTH} characters."
        )
    duplicate = db.scalar(
        select(User.id).where(
            func.lower(User.username) == normalized_username.lower()
        )
    )
    if duplicate is not None:
        raise AdminBootstrapError(
            f"The username '{normalized_username}' is already in use. Choose another."
        )

    administrator = User(
        full_name=normalized_name,
        username=normalized_username,
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(administrator)
    db.commit()
    db.refresh(administrator)
    return administrator


def _schema_is_ready() -> bool:
    init_db()
    return inspect(engine).has_table(User.__tablename__)


def main() -> int:
    try:
        if not _schema_is_ready():
            raise AdminBootstrapError(
                "The application schema is not installed. Run "
                "'python -m alembic upgrade head' and try again."
            )
    except SQLAlchemyError:
        print(
            "The application schema could not be verified. Run "
            "'python -m alembic upgrade head' and try again.",
            file=sys.stderr,
        )
        return 1
    except AdminBootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        _reject_existing_active_admin(db)
    except AdminBootstrapError as exc:
        db.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db.close()

    try:
        full_name = input("Administrator full name: ").strip()
        username = input("Administrator username: ").strip()
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
    except (EOFError, KeyboardInterrupt):
        print("\nAdministrator creation cancelled.", file=sys.stderr)
        return 1

    if password != confirmation:
        print("Passwords do not match. Nothing was changed.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        administrator = create_admin(db, full_name, username, password)
    except AdminBootstrapError as exc:
        db.rollback()
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Administrator account '{administrator.username}' created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
