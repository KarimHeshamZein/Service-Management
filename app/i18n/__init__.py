"""Small dependency-free translation catalog for the HTML interface."""
from __future__ import annotations

import re
from typing import Any

from .ar import MESSAGES as AR_MESSAGES
from .en import MESSAGES as EN_MESSAGES

DEFAULT_LANGUAGE = "en"

LANGUAGES = {
    "en": {"code": "en", "name": "English", "direction": "ltr"},
    "ar": {"code": "ar", "name": "العربية", "direction": "rtl"},
}

CATALOGS = {
    "en": EN_MESSAGES,
    "ar": AR_MESSAGES,
}


def supported_language(raw: object) -> str:
    code = str(raw or "").strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


class _Placeholders(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def translate(key: str, lang: str = DEFAULT_LANGUAGE, **params: Any) -> str:
    language = supported_language(lang)
    message = CATALOGS[language].get(key)
    if message is None:
        message = EN_MESSAGES.get(key, key)
    return message.format_map(_Placeholders(params)) if params else message


_SERVER_KEYS = tuple(
    key
    for key in EN_MESSAGES
    if key.startswith("server.") and key != "server.fallback"
)
_SERVER_EXACT = {
    EN_MESSAGES[key]: key
    for key in _SERVER_KEYS
    if "{" not in EN_MESSAGES[key]
}


def _server_pattern(template: str) -> re.Pattern[str]:
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", template):
        parts.append(re.escape(template[cursor : match.start()]))
        parts.append(f"(?P<{match.group(1)}>.+?)")
        cursor = match.end()
    parts.append(re.escape(template[cursor:]))
    return re.compile("^" + "".join(parts) + "$")


_SERVER_PATTERNS = tuple(
    (key, _server_pattern(EN_MESSAGES[key]))
    for key in _SERVER_KEYS
    if "{" in EN_MESSAGES[key]
)


def server_message_reference(text: object) -> tuple[str, dict[str, str]]:
    """Return a stable catalog reference for an English server message."""
    raw = str(text)
    key = _SERVER_EXACT.get(raw)
    if key is not None:
        return key, {}
    for candidate, pattern in _SERVER_PATTERNS:
        match = pattern.fullmatch(raw)
        if match:
            return candidate, match.groupdict()
    # Preserve exact English while preventing untranslated server copy in Arabic.
    return "server.fallback", {"message": raw}


def localize_server_text(text: object, lang: str) -> str:
    key, params = server_message_reference(text)
    return translate(key, lang, **params)


def localize_server_payload(value: Any, lang: str) -> Any:
    """Translate server-owned text in validation/JSON payloads recursively."""
    if isinstance(value, str):
        return localize_server_text(value, lang)
    if isinstance(value, dict):
        return {key: localize_server_payload(item, lang) for key, item in value.items()}
    if isinstance(value, list):
        return [localize_server_payload(item, lang) for item in value]
    if isinstance(value, tuple):
        return tuple(localize_server_payload(item, lang) for item in value)
    return value


def language_direction(lang: object) -> str:
    return LANGUAGES[supported_language(lang)]["direction"]


def language_choices() -> tuple[dict[str, str], ...]:
    return tuple(LANGUAGES.values())
