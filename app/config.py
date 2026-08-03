"""Application configuration, sourced from environment variables."""
from __future__ import annotations

import os
from datetime import timedelta
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_environment() -> Path:
    """Load development config locally or an explicit production env file."""
    configured_path = os.getenv("SMS_ENV_FILE", "").strip()
    if configured_path:
        env_path = Path(configured_path)
        if not env_path.is_absolute():
            raise RuntimeError("SMS_ENV_FILE must be an absolute path")
        if not env_path.is_file():
            raise RuntimeError(f"SMS_ENV_FILE does not exist: {env_path}")
        # An explicit production file is the protected source of truth. Service
        # wrappers can retain an older inherited APP_PORT across restarts, so
        # values in this file must replace inherited copies.
        load_dotenv(env_path, override=True)
        return env_path

    env_path = BASE_DIR / ".env"
    load_dotenv(env_path)
    if os.getenv("ENVIRONMENT", "development").strip().lower() == "production":
        raise RuntimeError("SMS_ENV_FILE must point to the shared .env in production")
    return env_path


ENV_FILE = _load_environment()


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime settings. Secrets never have a hard-coded production default."""

    def __init__(self) -> None:
        self.app_name: str = os.getenv("APP_NAME", "Service Management System")
        self.environment: str = os.getenv("ENVIRONMENT", "development")
        self.app_host: str = os.getenv("APP_HOST", "0.0.0.0")
        self.app_port: int = int(os.getenv("APP_PORT", "8993"))
        self.app_reload: bool = _bool(
            "APP_RELOAD",
            self.environment != "production",
        )

        secret = os.getenv("SECRET_KEY")
        if not secret:
            if self.environment == "production":
                raise RuntimeError("SECRET_KEY must be set in production")
            secret = "dev-only-insecure-secret-change-me"
        self.secret_key: str = secret

        default_db = (
            "postgresql://postgres:postgres@localhost:5432/service_management"
        )
        self.database_url: str = os.getenv("DATABASE_URL", default_db)

        self.upload_dir: Path = Path(
            os.getenv("UPLOAD_DIR", str(BASE_DIR / "data" / "uploads"))
        ).resolve()

        self.max_upload_mb: float = float(os.getenv("MAX_UPLOAD_MB", "8"))
        self.max_photos_per_record: int = int(os.getenv("MAX_PHOTOS_PER_RECORD", "10"))
        self.session_max_age: int = int(os.getenv("SESSION_MAX_AGE_SECONDS", "43200"))
        self.session_https_only: bool = _bool("SESSION_HTTPS_ONLY", False)
        self.page_size: int = int(os.getenv("PAGE_SIZE", "10"))
        self.max_pdf_records: int = int(os.getenv("MAX_PDF_RECORDS", "250"))
        self.public_base_url: str = os.getenv(
            "PUBLIC_BASE_URL", "http://127.0.0.1:8993"
        ).rstrip("/")
        self.smtp_host: str = os.getenv("SMTP_HOST", "").strip()
        self.smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username: str = os.getenv("SMTP_USERNAME", "").strip()
        self.smtp_password: str = os.getenv("SMTP_PASSWORD", "")
        self.smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "").strip()
        self.smtp_starttls: bool = _bool("SMTP_STARTTLS", True)

        # Display timezone offset in minutes (Riyadh = +180). Storage is always UTC.
        self.display_tz_offset: timedelta = timedelta(
            minutes=int(os.getenv("DISPLAY_TZ_OFFSET_MINUTES", "180"))
        )
        self.display_tz_label: str = os.getenv("DISPLAY_TZ_LABEL", "UTC+03:00")

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def email_delivery_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)


ALLOWED_IMAGE_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".webp"}

THUMBNAIL_MAX_EDGE = 480


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
