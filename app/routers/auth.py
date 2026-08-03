"""Login and logout."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..account_recovery import (
    RESET_LIFETIME,
    RESET_PURPOSE,
    VERIFY_PURPOSE,
    MailDeliveryError,
    auth_version,
    bump_auth_version,
    find_verified_admin,
    issue_token,
    record_attempt_and_check_limit,
    send_reset_email,
    valid_token,
)
from ..config import settings
from ..helpers import flash, render
from ..i18n import LANGUAGES, supported_language
from ..login_throttle import (
    clear_failed_logins,
    login_is_throttled,
    record_failed_login,
)
from ..models import AccountRecoveryToken, AdminRecoveryContact, User, utcnow
from ..security import (
    csrf_valid,
    current_user_id,
    hash_password,
    login_session,
    logout_session,
    verify_password,
)

router = APIRouter()

GENERIC_LOGIN_ERROR = "Those details don't match an account. Check the username and password."
GENERIC_RECOVERY_MESSAGE = (
    "If that matches a verified Administrator account, a password reset link "
    "will be sent."
)
MIN_PASSWORD_LENGTH = 8


def _deliver_reset_safely(email: str, token: str) -> None:
    try:
        send_reset_email(email, token)
    except MailDeliveryError:
        # Public responses stay generic; server mail configuration is private.
        return


def _safe_next(raw: str | None) -> str:
    """Only same-origin absolute paths are accepted as redirect targets."""
    if raw and raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/dashboard"


def _login_error_response(
    request: Request,
    *,
    next_path: str,
    username: str,
    errors: dict[str, str],
    status_code: int,
):
    return render(
        request,
        "login.html",
        {
            "next": _safe_next(next_path),
            "form": {"username": username},
            "errors": errors,
            "layout": "bare",
        },
        status_code=status_code,
    )


@router.get("/login")
def login_page(request: Request, next: str | None = None):
    if current_user_id(request):
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return render(
        request,
        "login.html",
        {"next": _safe_next(next), "form": {}, "errors": {}, "layout": "bare"},
    )


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/dashboard"),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    username = (username or "").strip()
    errors: dict[str, str] = {}
    response_status = status.HTTP_401_UNAUTHORIZED

    if not csrf_valid(request, csrf_token):
        errors["form"] = "Your session expired. Please try again."
    if not username:
        errors["username"] = "Enter your email or username."
    if not password:
        errors["password"] = "Enter your password."

    user: User | None = None
    if not errors:
        client_ip = request.client.host if request.client else "unknown"
        if login_is_throttled(db, username, client_ip):
            errors["form"] = GENERIC_LOGIN_ERROR
            response_status = status.HTTP_429_TOO_MANY_REQUESTS
            db.commit()
        else:
            user = db.scalar(
                select(User).where(func.lower(User.username) == username.lower())
            )
            if user is None or not verify_password(password, user.password_hash):
                errors["form"] = GENERIC_LOGIN_ERROR
                record_failed_login(db, username, client_ip)
            elif not user.is_active:
                errors["form"] = (
                    "This account is deactivated. Contact your administrator."
                )

    if errors or user is None:
        return _login_error_response(
            request,
            next_path=next,
            username=username,
            errors=errors,
            status_code=response_status,
        )

    anonymous_language = request.session.get("language")
    clear_failed_logins(db, username)
    if anonymous_language in LANGUAGES:
        user.language = str(anonymous_language)
        db.commit()
    login_session(
        request,
        user.id,
        user.role.value if hasattr(user.role, "value") else user.role,
        auth_version(db, user.id),
    )
    request.session["language"] = supported_language(user.language)
    flash(request, f"Signed in as {user.full_name}.")
    return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/language")
def change_language(
    request: Request,
    language: str = Form(""),
    next: str = Form("/dashboard"),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if not csrf_valid(request, csrf_token):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your session expired. Reload the page and try again.",
        )
    code = language.strip().lower()
    if code not in LANGUAGES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported language.")

    user_id = current_user_id(request)
    user = db.get(User, user_id) if user_id is not None else None
    if user is not None:
        user.language = code
        db.commit()
        request.session["language"] = code
    else:
        request.session["language"] = code
    return RedirectResponse(_safe_next(next), status_code=status.HTTP_303_SEE_OTHER)


@router.get("/forgot-password")
def forgot_password_page(request: Request):
    if current_user_id(request):
        return RedirectResponse("/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return render(
        request,
        "forgot_password.html",
        {"errors": {}, "form": {}, "submitted": False, "layout": "bare"},
    )


@router.post("/forgot-password")
def forgot_password_request(
    request: Request,
    background_tasks: BackgroundTasks,
    identifier: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    identifier = identifier.strip()
    errors: dict[str, str] = {}
    if not csrf_valid(request, csrf_token):
        errors["form"] = "Your session expired. Reload and try again."
    elif not identifier:
        errors["identifier"] = "Enter the Administrator username or recovery email."
    if errors:
        return render(
            request,
            "forgot_password.html",
            {
                "errors": errors,
                "form": {"identifier": identifier},
                "submitted": False,
                "layout": "bare",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    ip_address = request.client.host if request.client else "unknown"
    allowed = record_attempt_and_check_limit(db, identifier, ip_address)
    match = find_verified_admin(db, identifier) if allowed else None
    if match and settings.email_delivery_configured:
        admin, contact = match
        token = issue_token(db, admin.id, RESET_PURPOSE, RESET_LIFETIME)
        db.commit()
        background_tasks.add_task(_deliver_reset_safely, contact.email, token)
    else:
        db.commit()

    return render(
        request,
        "forgot_password.html",
        {
            "errors": {},
            "form": {},
            "submitted": True,
            "message": GENERIC_RECOVERY_MESSAGE,
            "layout": "bare",
        },
    )


@router.get("/forgot-password/reset")
def reset_password_page(request: Request, token: str = "", db: Session = Depends(get_db)):
    token_match = valid_token(db, token, RESET_PURPOSE) if token else None
    return render(
        request,
        "forgot_password_reset.html",
        {
            "token": token,
            "valid": token_match is not None,
            "errors": {},
            "layout": "bare",
        },
        status_code=200 if token_match else status.HTTP_400_BAD_REQUEST,
    )


@router.post("/forgot-password/reset")
def reset_password_submit(
    request: Request,
    token: str = Form(""),
    password: str = Form(""),
    password_confirmation: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    errors: dict[str, str] = {}
    if not csrf_valid(request, csrf_token):
        errors["form"] = "Your session expired. Reload the link and try again."
    match = valid_token(db, token, RESET_PURPOSE) if token else None
    if match is None:
        errors["form"] = "This password reset link is invalid or has expired."
    if len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = (
            f"The new password must contain at least {MIN_PASSWORD_LENGTH} characters."
        )
    if password != password_confirmation:
        errors["password_confirmation"] = "The passwords do not match."
    if errors or match is None:
        return render(
            request,
            "forgot_password_reset.html",
            {
                "token": token,
                "valid": match is not None,
                "errors": errors,
                "layout": "bare",
            },
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    row, admin = match
    now = utcnow()
    admin.password_hash = hash_password(password)
    admin.updated_at = now
    row.used_at = now
    for other in db.scalars(
        select(AccountRecoveryToken).where(
            AccountRecoveryToken.user_id == admin.id,
            AccountRecoveryToken.purpose == RESET_PURPOSE,
            AccountRecoveryToken.used_at.is_(None),
        )
    ):
        other.used_at = now
    bump_auth_version(db, admin.id)
    db.commit()
    logout_session(request)
    flash(request, "Administrator password reset. Log in with the new password.")
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/recovery-email/verify")
def verify_recovery_email(
    request: Request, token: str = "", db: Session = Depends(get_db)
):
    match = valid_token(db, token, VERIFY_PURPOSE) if token else None
    if match is None:
        return render(
            request,
            "recovery_link_invalid.html",
            {"layout": "bare"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    row, admin = match
    contact = db.get(AdminRecoveryContact, admin.id)
    if contact is None:
        return render(
            request,
            "recovery_link_invalid.html",
            {"layout": "bare"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    now = utcnow()
    contact.verified_at = now
    contact.updated_at = now
    row.used_at = now
    db.commit()
    flash(request, "Administrator recovery email verified.")
    return RedirectResponse(
        "/dashboard" if current_user_id(request) else "/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form("")):
    if csrf_valid(request, csrf_token):
        logout_session(request)
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
