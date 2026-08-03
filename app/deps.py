"""Request dependencies. Every protected route goes through one of these."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserRole
from .account_recovery import auth_version
from .security import current_user_id, logout_session


class RedirectToLogin(Exception):
    def __init__(self, next_url: str) -> None:
        self.next_url = next_url


def _wants_json(request: Request) -> bool:
    return request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    user_id = current_user_id(request)
    if user_id is None:
        raise RedirectToLogin(request.url.path)

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        # Account removed or deactivated mid-session: the session dies with it.
        logout_session(request)
        raise RedirectToLogin(request.url.path)

    if request.session.get("auth_version") != auth_version(db, user.id):
        logout_session(request)
        raise RedirectToLogin(request.url.path)

    request.state.user = user
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user


def require_catalog_manager(user: User = Depends(get_current_user)) -> User:
    if not user.can_manage_catalogs:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Technical access required")
    return user


def require_dashboard_access(user: User = Depends(get_current_user)) -> User:
    if user.is_customer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dashboard access is unavailable")
    return user


def require_record_submitter(user: User = Depends(get_current_user)) -> User:
    """Administrators and Technical users may enter field-service evidence."""
    if not user.can_submit_records:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Technical access required")
    return user


def require_pricing_access(user: User = Depends(get_current_user)) -> User:
    """Administrators and explicitly permitted Technical users may use Pricing."""
    if not user.can_access_pricing:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Pricing access required")
    return user


def login_redirect(next_url: str) -> RedirectResponse:
    target = "/login"
    if next_url and next_url not in {"/", "/login"}:
        target = f"/login?next={quote(next_url, safe='')}"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
