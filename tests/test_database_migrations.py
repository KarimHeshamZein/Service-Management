"""Alembic chain, round-trip, and ORM metadata drift tests."""
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401 - register every ORM mapper
from app.config import settings
from app.database import Base

DEFAULT_MIGRATION_DATABASE_URL = (
    "postgresql://postgres:postgres@localhost:5432/"
    "service_management_migrations_test"
)
PROTECTED_DATABASES = {
    "postgres",
    "service_management",
    "service_management_test",
}


def _scratch_database_url() -> str:
    return os.getenv(
        "MIGRATION_TEST_DATABASE_URL",
        DEFAULT_MIGRATION_DATABASE_URL,
    )


def _scratch_engine():
    url = _scratch_database_url()
    database = make_url(url).database
    if database in PROTECTED_DATABASES:
        pytest.fail(
            "MIGRATION_TEST_DATABASE_URL must identify a dedicated scratch database."
        )
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError as exc:
        engine.dispose()
        pytest.skip(f"Migration scratch database is unavailable: {exc}")
    return engine


def _empty_public_schema(engine) -> None:
    with engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")


def test_alembic_chain_round_trip_and_metadata_drift(monkeypatch):
    engine = _scratch_engine()
    config = Config("alembic.ini")
    monkeypatch.setattr(settings, "database_url", _scratch_database_url())
    try:
        _empty_public_schema(engine)
        command.upgrade(config, "head")

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert compare_metadata(context, Base.metadata) == []

        command.downgrade(config, "base")
        command.upgrade(config, "head")

        script = ScriptDirectory.from_config(config)
        assert len(script.get_heads()) == 1
    finally:
        engine.dispose()


def test_alembic_accepts_percent_encoded_database_url(monkeypatch):
    engine = _scratch_engine()
    separator = "&" if "?" in _scratch_database_url() else "?"
    encoded_url = (
        f"{_scratch_database_url()}{separator}"
        "application_name=service%20management"
    )
    config = Config("alembic.ini")
    monkeypatch.setattr(settings, "database_url", encoded_url)
    try:
        command.current(config)
    finally:
        engine.dispose()


def test_upload_backup_settings_migration_upgrades_and_downgrades(monkeypatch):
    engine = _scratch_engine()
    config = Config("alembic.ini")
    monkeypatch.setattr(settings, "database_url", _scratch_database_url())
    try:
        _empty_public_schema(engine)
        command.upgrade(config, "e017fa3d1f83")
        before = {column["name"] for column in inspect(engine).get_columns(
            "deployment_settings"
        )}
        assert "backup_include_uploads" not in before
        assert "backup_upload_retention_count" not in before

        command.upgrade(config, "head")
        upgraded = {column["name"] for column in inspect(engine).get_columns(
            "deployment_settings"
        )}
        assert "backup_include_uploads" in upgraded
        assert "backup_upload_retention_count" in upgraded
        checks = {
            constraint["name"]
            for constraint in inspect(engine).get_check_constraints(
                "deployment_settings"
            )
        }
        assert "ck_deployment_backup_upload_retention" in checks

        command.downgrade(config, "e017fa3d1f83")
        downgraded = {column["name"] for column in inspect(engine).get_columns(
            "deployment_settings"
        )}
        assert "backup_include_uploads" not in downgraded
        assert "backup_upload_retention_count" not in downgraded
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_user_language_migration_upgrades_and_downgrades(monkeypatch):
    engine = _scratch_engine()
    config = Config("alembic.ini")
    monkeypatch.setattr(settings, "database_url", _scratch_database_url())
    try:
        _empty_public_schema(engine)
        command.upgrade(config, "f4c2a91d7e63")
        before = {
            column["name"] for column in inspect(engine).get_columns("users")
        }
        assert "language" not in before

        command.upgrade(config, "head")
        upgraded = {
            column["name"] for column in inspect(engine).get_columns("users")
        }
        assert "language" in upgraded

        command.downgrade(config, "f4c2a91d7e63")
        downgraded = {
            column["name"] for column in inspect(engine).get_columns("users")
        }
        assert "language" not in downgraded
        command.upgrade(config, "head")
    finally:
        engine.dispose()


def test_item_unification_migrates_devices_and_currency_snapshots(monkeypatch):
    engine = _scratch_engine()
    config = Config("alembic.ini")
    monkeypatch.setattr(settings, "database_url", _scratch_database_url())
    try:
        _empty_public_schema(engine)
        command.upgrade(config, "a6d1e7c93b52")
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO device_catalog
                        (name, manufacturer, model, description, is_active,
                         created_at, updated_at)
                    VALUES
                        ('Migration Camera', 'Afaqy', 'MC-1', NULL, true,
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO pricing_items
                        (name, model, unit_price, is_active, created_at, updated_at)
                    VALUES
                        ('Migration Camera', 'MC-1', 20, true,
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
                        ('Quotation Only Item', 'QO-1', 30, true,
                         CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                )
            )

        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT name, currency, service_enabled, device_catalog_id
                    FROM pricing_items ORDER BY name
                    """
                )
            ).mappings().all()
            assert len(rows) == 2
            assert {row["currency"] for row in rows} == {"SAR"}
            assert all(row["service_enabled"] for row in rows)
            assert all(row["device_catalog_id"] is not None for row in rows)
            assert connection.execute(
                text("SELECT count(*) FROM device_catalog")
            ).scalar_one() == 2
    finally:
        engine.dispose()
