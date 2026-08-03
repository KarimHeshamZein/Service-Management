"""Shared helpers: record numbering, timezone display and template setup."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import BASE_DIR, settings
from .counters import allocate_year_sequence
from .i18n import (
    DEFAULT_LANGUAGE,
    language_choices,
    language_direction,
    localize_server_payload,
    server_message_reference,
    supported_language,
    translate,
)
from .models import (
    GeneralMaintenanceRecordCounter,
    InstallationRecordCounter,
    MaintenanceResult,
    RecordCounter,
    UserRole,
    utcnow,
)

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


# --- record numbers ------------------------------------------------------


def next_record_number(db: Session, when: datetime | None = None) -> str:
    """PM-YYYY-NNNNN, allocated from a per-year counter row."""
    moment = when or utcnow()
    year = to_display(moment).year
    sequence = allocate_year_sequence(db, RecordCounter, year)
    return f"PM-{year}-{sequence:05d}"


def next_installation_record_number(
    db: Session, when: datetime | None = None
) -> str:
    """NI-YYYY-NNNNN, allocated independently from maintenance records."""
    moment = when or utcnow()
    year = to_display(moment).year
    sequence = allocate_year_sequence(db, InstallationRecordCounter, year)
    return f"NI-{year}-{sequence:05d}"


def next_general_maintenance_record_number(
    db: Session, when: datetime | None = None
) -> str:
    """MA-YYYY-NNNNN, allocated independently from preventive maintenance."""
    moment = when or utcnow()
    year = to_display(moment).year
    sequence = allocate_year_sequence(db, GeneralMaintenanceRecordCounter, year)
    return f"MA-{year}-{sequence:05d}"


# --- time ----------------------------------------------------------------


def entity_id(raw: str) -> int | None:
    """Return a PostgreSQL INTEGER identity, or None for invalid input."""
    if not raw.isdigit():
        return None
    value = int(raw)
    return value if 0 < value <= 2**31 - 1 else None


def to_display(value: datetime) -> datetime:
    return value + settings.display_tz_offset


def to_utc_from_display(value: datetime) -> datetime:
    return value - settings.display_tz_offset


def display_today_bounds() -> tuple[datetime, datetime]:
    """UTC window covering 'today' in the configured display timezone."""
    local_now = to_display(utcnow())
    start_local = datetime.combine(local_now.date(), datetime.min.time())
    return to_utc_from_display(start_local), to_utc_from_display(start_local + timedelta(days=1))


def _localized_month(value: date | datetime, lang: str) -> str:
    return translate(f"date.month.{value.strftime('%b').lower()}", lang)


def fmt_datetime(value: datetime | None, lang: str = DEFAULT_LANGUAGE) -> str:
    if value is None:
        return "—"
    displayed = to_display(value)
    return (
        f"{displayed.day:02d} {_localized_month(displayed, lang)} "
        f"{displayed.year}, {displayed:%H:%M}"
    )


def fmt_date(
    value: datetime | date | None, lang: str = DEFAULT_LANGUAGE
) -> str:
    if value is None:
        return "—"
    if isinstance(value, datetime):
        value = to_display(value).date()
    return f"{value.day:02d} {_localized_month(value, lang)} {value.year}"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def fmt_filesize(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes / 1024 / 1024:.1f} MB"


def fmt_money(value: object) -> str:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    return f"{amount:,.2f}"


# --- rendering -----------------------------------------------------------


def request_language(request: Request) -> str:
    user = getattr(request.state, "user", None)
    requested = user.language if user is not None else request.session.get("language")
    return supported_language(requested or DEFAULT_LANGUAGE)


def flash(request: Request, message: str, level: str = "success") -> None:
    queue = list(request.session.get("flash", []))
    key, params = server_message_reference(message)
    queue.append({"key": key, "params": params, "level": level})
    request.session["flash"] = queue[-5:]


def pop_flash(request: Request, lang: str) -> list[dict]:
    queue = request.session.get("flash", [])
    if queue:
        request.session["flash"] = []
    rendered: list[dict] = []
    for entry in queue:
        # Temporary compatibility for cookies issued before Phase C. Those entries
        # may be a plain string or the old {message, level} mapping.
        if isinstance(entry, str):
            rendered.append({"message": entry, "level": "success"})
        elif isinstance(entry, dict) and "key" in entry:
            rendered.append(
                {
                    "message": translate(
                        str(entry["key"]), lang, **dict(entry.get("params") or {})
                    ),
                    "level": str(entry.get("level") or "success"),
                }
            )
        elif isinstance(entry, dict) and "message" in entry:
            rendered.append(
                {
                    "message": str(entry["message"]),
                    "level": str(entry.get("level") or "success"),
                }
            )
    return rendered


def localized_json(
    request: Request,
    payload: dict,
    *,
    status_code: int = 200,
) -> JSONResponse:
    localized = dict(payload)
    if "errors" in localized:
        localized["errors"] = localize_server_payload(
            localized["errors"], request_language(request)
        )
    if "message" in localized:
        localized["message"] = localize_server_payload(
            localized["message"], request_language(request)
        )
    return JSONResponse(
        localized,
        status_code=status_code,
    )


def render(request: Request, template: str, context: dict | None = None, status_code: int = 200):
    from .security import csrf_token

    user = getattr(request.state, "user", None)
    lang = request_language(request)
    language_next = request.url.path
    if request.url.query:
        language_next += f"?{request.url.query}"

    payload = {
        "request": request,
        "settings": settings,
        "user": user,
        "csrf_token": csrf_token(request),
        "flashes": pop_flash(request, lang),
        "MaintenanceResult": MaintenanceResult,
        "UserRole": UserRole,
        "results": list(MaintenanceResult),
        "active_nav": "",
        "t": lambda key, **params: translate(key, lang, **params),
        "lang": lang,
        "dir": language_direction(lang),
        "languages": language_choices(),
        "language_next": language_next,
    }
    supplied = dict(context or {})
    for key, value in list(supplied.items()):
        if (
            key in {"errors", "error", "message", "title", "detail"}
            or key.endswith("_error")
            or key.endswith("_message")
        ):
            supplied[key] = localize_server_payload(value, lang)
    if isinstance(supplied.get("backup_status"), dict):
        backup_status = dict(supplied["backup_status"])
        for key in (
            "message",
            "uploads_summary",
            "completion_age",
            "last_success_age",
        ):
            if backup_status.get(key):
                backup_status[key] = localize_server_payload(
                    backup_status[key], lang
                )
        supplied["backup_status"] = backup_status
    payload.update(supplied)
    return templates.TemplateResponse(request, template, payload, status_code=status_code)


def _register_filters() -> None:
    env = templates.env

    @pass_context
    def localized_datetime(context, value):
        return fmt_datetime(value, context.get("lang", DEFAULT_LANGUAGE))

    @pass_context
    def localized_date(context, value):
        return fmt_date(value, context.get("lang", DEFAULT_LANGUAGE))

    env.filters["datetime"] = localized_datetime
    env.filters["date"] = localized_date
    env.filters["filesize"] = fmt_filesize
    env.filters["money"] = fmt_money
    env.globals["display_tz_label"] = settings.display_tz_label


_register_filters()


def paginate(total: int, page: int, per_page: int) -> dict:
    pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, page), pages)
    return {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": per_page,
        "offset": (page - 1) * per_page,
        "has_prev": page > 1,
        "has_next": page < pages,
    }


def all_results() -> list[MaintenanceResult]:
    return list(MaintenanceResult)


def query_string(params: dict, **overrides) -> str:
    merged = {k: v for k, v in {**params, **overrides}.items() if v not in (None, "", [])}
    if not merged:
        return ""
    from urllib.parse import urlencode

    return "?" + urlencode(merged)


templates.env.globals["query_string"] = query_string
