"""Password hashing, session state, CSRF and single-use form tokens."""
from __future__ import annotations

import os
import secrets

import bcrypt
from fastapi import Request

MAX_TRACKED_FORM_TOKENS = 25
# 12 is the production default; tests lower it so the suite is not bcrypt-bound.
_BCRYPT_ROUNDS = max(4, int(os.getenv("BCRYPT_ROUNDS", "12")))


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --- session -------------------------------------------------------------


def login_session(
    request: Request, user_id: int, role: str, auth_version: int = 0
) -> None:
    request.session.clear()
    request.session["user_id"] = user_id
    request.session["role"] = role
    request.session["auth_version"] = auth_version
    request.session["csrf_token"] = secrets.token_urlsafe(32)


def logout_session(request: Request) -> None:
    request.session.clear()


def current_user_id(request: Request) -> int | None:
    value = request.session.get("user_id")
    return int(value) if value is not None else None


# --- CSRF ----------------------------------------------------------------


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def csrf_valid(request: Request, submitted: str | None) -> bool:
    expected = request.session.get("csrf_token")
    return bool(expected and submitted and secrets.compare_digest(expected, submitted))


# --- single-use form tokens (duplicate submission guard) -----------------


def issue_form_token(request: Request) -> str:
    return secrets.token_urlsafe(24)


def form_token_available(request: Request, token: str | None) -> bool:
    """Return whether a token exists and has not completed a submission."""
    if not token:
        return False
    used: list[str] = list(request.session.get("used_form_tokens", []))
    return token not in used


def consume_form_token(request: Request, token: str | None) -> bool:
    """Return True the first time a token is seen, False on any replay."""
    if not form_token_available(request, token):
        return False
    used: list[str] = list(request.session.get("used_form_tokens", []))
    if token in used:
        return False
    used.append(token)
    request.session["used_form_tokens"] = used[-MAX_TRACKED_FORM_TOKENS:]
    return True
