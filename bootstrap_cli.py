"""Structured, secret-safe bootstrap operations for the Windows setup wizard.

Passwords are accepted only inside one JSON document on standard input. They
are never accepted through command-line arguments, environment variables or
temporary files.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable, Sequence
from typing import Any, TextIO

import psycopg2
from psycopg2 import sql
from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.machine_config.validation import validate_database, validate_network

MAX_INPUT_BYTES = 64 * 1024


def validate_network_command(payload: dict[str, Any]) -> dict[str, Any]:
    profile, errors = validate_network(payload)
    return _result(not errors, errors=errors, data=profile if not errors else None)


def test_database_command(
    payload: dict[str, Any],
    *,
    engine_factory: Callable[..., Any] = create_engine,
) -> dict[str, Any]:
    candidate, errors = validate_database(payload)
    if errors:
        return _result(False, errors=errors)
    engine = None
    try:
        engine = engine_factory(
            _database_url(candidate),
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return _result(True, message="PostgreSQL connection succeeded.")
    except (SQLAlchemyError, OSError, ValueError):
        return _result(
            False,
            errors={"form": "PostgreSQL connection failed. Check the supplied settings."},
        )
    finally:
        if engine is not None:
            engine.dispose()


def create_role_database_command(
    payload: dict[str, Any],
    *,
    connector: Callable[..., Any] = psycopg2.connect,
) -> dict[str, Any]:
    admin, application, errors = _role_database_values(payload)
    if errors:
        return _result(False, errors=errors)
    connection = None
    role_created = False
    try:
        connection = connector(
            host=admin["host"],
            port=admin["port"],
            dbname=admin["database"],
            user=admin["username"],
            password=admin["password"],
            connect_timeout=5,
        )
        connection.autocommit = True
        existing_errors = _existing_database_errors(connection, application)
        if existing_errors:
            return _result(False, errors=existing_errors)
        _create_role(connection, application)
        role_created = True
        _create_database(connection, application)
        return _result(True, message="The application role and database were created.")
    except (psycopg2.Error, OSError):
        if connection is not None and role_created:
            _drop_created_role(connection, application["username"])
        return _result(
            False,
            errors={
                "form": (
                    "Database initialization failed. Check PostgreSQL for a partially "
                    "created role or database before retrying."
                )
            },
        )
    finally:
        if connection is not None:
            connection.close()


def create_admin_command(payload: dict[str, Any]) -> dict[str, Any]:
    full_name = str(payload.get("full_name") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    errors = _admin_errors(full_name, username, password)
    if errors:
        return _result(False, errors=errors)

    from create_admin import AdminBootstrapError, create_admin
    from app.database import SessionLocal, engine
    from app.models import User

    try:
        if not inspect(engine).has_table(User.__tablename__):
            return _result(
                False,
                errors={"form": "The schema is missing. Run the database migrations first."},
            )
    except SQLAlchemyError:
        return _result(False, errors={"form": "The application schema could not be verified."})
    database = SessionLocal()
    try:
        administrator = create_admin(database, full_name, username, password)
        return _result(
            True,
            message="The first Administrator was created.",
            data={"username": administrator.username},
        )
    except AdminBootstrapError as exc:
        database.rollback()
        field = "username" if "username" in str(exc).lower() else "form"
        return _result(False, errors={field: str(exc)})
    except SQLAlchemyError:
        database.rollback()
        return _result(False, errors={"form": "The Administrator could not be created."})
    finally:
        database.close()


COMMANDS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "validate-network": validate_network_command,
    "test-database": test_database_command,
    "create-role-database": create_role_database_command,
    "create-admin": create_admin_command,
}


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1 or arguments[0] not in COMMANDS:
        _emit(stdout, _result(False, errors={"command": "Choose a supported bootstrap command."}))
        return 2
    try:
        raw = stdin.read(MAX_INPUT_BYTES + 1)
        if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError
    except (UnicodeError, ValueError, json.JSONDecodeError):
        _emit(stdout, _result(False, errors={"input": "Enter one valid JSON object."}))
        return 2
    try:
        result = COMMANDS[arguments[0]](payload)
    except Exception:
        result = _result(False, errors={"form": "The bootstrap operation could not be completed."})
    _emit(stdout, result)
    return 0 if result["ok"] else 1


def _role_database_values(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    raw_admin = payload.get("admin") if isinstance(payload.get("admin"), dict) else {}
    raw_application = (
        payload.get("application") if isinstance(payload.get("application"), dict) else {}
    )
    admin, admin_errors = validate_database(raw_admin)
    application_input = {**raw_application, "host": admin["host"], "port": admin["port"]}
    application, application_errors = validate_database(application_input)
    errors = {f"admin.{key}": value for key, value in admin_errors.items()}
    errors.update({
        f"application.{key}": value
        for key, value in application_errors.items()
        if key in {"database", "username", "password"}
    })
    return admin, application, errors


def _existing_database_errors(
    connection: Any,
    application: dict[str, Any],
) -> dict[str, str]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s",
            (application["username"],),
        )
        role_exists = cursor.fetchone() is not None
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (application["database"],),
        )
        database_exists = cursor.fetchone() is not None
    errors: dict[str, str] = {}
    if role_exists:
        errors["application.username"] = "That PostgreSQL role already exists."
    if database_exists:
        errors["application.database"] = "That PostgreSQL database already exists."
    return errors


def _create_role(connection: Any, application: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(
                sql.Identifier(application["username"])
            ),
            (application["password"],),
        )


def _create_database(connection: Any, application: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(application["database"]),
                sql.Identifier(application["username"]),
            )
        )


def _database_url(values: dict[str, Any]) -> URL:
    return URL.create(
        "postgresql+psycopg2",
        username=values["username"],
        password=values["password"],
        host=values["host"],
        port=values["port"],
        database=values["database"],
    )


def _admin_errors(full_name: str, username: str, password: str) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not full_name:
        errors["full_name"] = "Enter the Administrator full name."
    if not username:
        errors["username"] = "Enter the Administrator username."
    if len(password) < 8:
        errors["password"] = "The password must contain at least 8 characters."
    return errors


def _drop_created_role(connection: Any, username: str) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(username)))
    except psycopg2.Error:
        pass


def _result(
    ok: bool,
    *,
    errors: dict[str, str] | None = None,
    message: str = "",
    data: Any = None,
) -> dict[str, Any]:
    return {"ok": ok, "errors": errors or {}, "message": message, "data": data}


def _emit(stream: TextIO, value: dict[str, Any]) -> None:
    stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


if __name__ == "__main__":
    raise SystemExit(main())
