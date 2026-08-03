"""Candidate database testing and transactional production connection changes."""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import URL

from app.machine_config.env_file import read_env_file, update_env_file
from app.machine_config.validation import validate_database
from bootstrap_cli import test_database_command

from .config_store import load_profile, save_profile
from .paths import InstallPaths
from .service_core import ServiceController


class DatabaseOperationError(RuntimeError):
    """A database setting could not be tested, saved or rolled back."""


class DatabaseController:
    def __init__(
        self,
        paths: InstallPaths,
        service: ServiceController,
        *,
        env_writer=update_env_file,
        connection_tester=test_database_command,
    ) -> None:
        self.paths = paths
        self.service = service
        self.env_writer = env_writer
        self.connection_tester = connection_tester

    def current(self) -> dict[str, Any]:
        from sqlalchemy.engine import make_url

        url = make_url(read_env_file(self.paths.env_file)["DATABASE_URL"])
        return {
            "host": url.host or "",
            "port": url.port or 5432,
            "database": url.database or "",
            "username": url.username or "",
            "password": url.password or "",
        }

    def test(self, values: Mapping[str, Any]) -> dict[str, Any]:
        return self.connection_tester(dict(values))

    def save(self, values: Mapping[str, Any]) -> None:
        candidate, errors = validate_database(values)
        if errors:
            raise DatabaseOperationError(next(iter(errors.values())))
        result = self.connection_tester(candidate)
        if not result["ok"]:
            raise DatabaseOperationError("The database connection failed; nothing was changed.")
        old_url = read_env_file(self.paths.env_file).get("DATABASE_URL", "")
        old_profile = load_profile(self.paths.machine_settings)
        new_profile = {
            **old_profile,
            "postgres_host": candidate["host"],
            "postgres_port": candidate["port"],
        }
        new_url = URL.create(
            "postgresql",
            username=candidate["username"],
            password=candidate["password"],
            host=candidate["host"],
            port=candidate["port"],
            database=candidate["database"],
        ).render_as_string(hide_password=False)
        try:
            save_profile(self.paths.machine_settings, new_profile)
            self.env_writer(self.paths.env_file, {"DATABASE_URL": new_url})
            self.service.restart()
            if not self.service.health_checker(None):
                raise DatabaseOperationError("The application health check failed.")
        except Exception:
            self._restore(old_url, old_profile)
            raise DatabaseOperationError(
                "The database change failed; the previous connection was restored."
            ) from None

    def _restore(self, database_url: str, profile: Mapping[str, Any]) -> None:
        try:
            save_profile(self.paths.machine_settings, profile)
            self.env_writer(self.paths.env_file, {"DATABASE_URL": database_url})
            self.service.restart()
        except Exception:
            raise DatabaseOperationError(
                "Database rollback failed. Restore shared\\.env.bak and restart the service."
            ) from None
