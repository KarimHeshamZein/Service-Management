"""Redaction helpers for local console displays and diagnostic exports."""
from __future__ import annotations

import re

SECRET_LINE_RE = re.compile(
    r"(?im)^\s*(SECRET_KEY|DATABASE_URL|SMTP_PASSWORD|PGPASSWORD)\s*=.*$"
)
POSTGRES_URL_RE = re.compile(r"postgresql(?:\+[^:]+)?://[^\s@]+@", re.IGNORECASE)
PASSWORD_FIELD_RE = re.compile(
    r'(?i)("?(?:password|secret_key|smtp_password)"?\s*[:=]\s*)[^,\s}\r\n]+|'
    r"(--password(?:=|\s+))\S+"
)


def redact(text: str) -> str:
    """Remove known secret forms without changing ordinary diagnostic text."""
    value = SECRET_LINE_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    value = POSTGRES_URL_RE.sub("postgresql://<redacted>@", value)
    return PASSWORD_FIELD_RE.sub(lambda match: (match.group(1) or match.group(2)) + "<redacted>", value)
