"""Request dependencies. Every protected route goes through one of these."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserNotification, UserRole
from .account_recovery import auth_version
from .access_control import (
    allowed_permission_keys,
    permission_allowed,
    permission_scopes,
    resolve_department,
    visible_project_ids,
)
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
    if not user.is_customer:
        department_context = resolve_department(request, db, user)
        permissions = allowed_permission_keys(db, user, department_context.active.id)
        user._allowed_permissions = permissions
        scopes = permission_scopes(db, user, department_context.active.id)
        user._permission_scopes = scopes
        user._active_department_id = department_context.active.id
        user._scoped_project_ids = visible_project_ids(
            db, user, department_context.active.id, module_key="records"
        ) or set()
        request.state.permission_scopes = scopes
        request.state.project_ids = {
            module_key: visible_project_ids(
                db, user, department_context.active.id, module_key=module_key
            ) or set()
            for module_key in ("projects", "records", "reports", "quotations", "tasks")
        }
        request.state.can = permissions.__contains__
        db.info["can_manage_pricing_items"] = "pricing_items.manage" in permissions
        db.info["project_ids"] = request.state.project_ids["records"]
        db.info["project_ids_by_module"] = request.state.project_ids
        db.info["module_scopes"] = {
            key: value.value for key, value in scopes.items()
        }
        request.state.unread_notifications = int(
            db.scalar(
                select(func.count(UserNotification.id)).where(
                    UserNotification.user_id == user.id,
                    UserNotification.is_read.is_(False),
                )
            )
            or 0
        )
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return user


def _has_any(request: Request, db: Session, user: User, *keys: str) -> bool:
    department = resolve_department(request, db, user).active
    return any(permission_allowed(db, user, department.id, key) for key in keys)


def require_catalog_manager(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if not _has_any(request, db, user, "projects.view", "projects.edit"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access required")
    return user


def require_dashboard_access(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if user.is_customer or not _has_any(request, db, user, "dashboard.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dashboard access is unavailable")
    return user


def require_record_submitter(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Administrators and Technical users may enter field-service evidence."""
    if not _has_any(
        request, db, user,
        "records.create_installation", "records.create_preventive", "records.create_maintenance",
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Technical access required")
    return user


def require_product_evaluations_access(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if user.is_customer or not _has_any(request, db, user, "product_evaluations.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Product evaluations access required")
    return user


def require_pricing_access(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Administrators and explicitly permitted Technical users may use Pricing."""
    if not _has_any(request, db, user, "pricing_items.view", "quotations.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Pricing access required")
    return user


def require_purchase_documents_access(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not _has_any(request, db, user, "purchase_documents.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Purchase documents access required")
    return user


def require_technical_documents_access(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not _has_any(request, db, user, "technical_documents.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Technical information access required")
    return user


def require_technical_documents_manager(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not _has_any(request, db, user, "technical_documents.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Technical information management required")
    return user


def require_wiring_diagrams_access(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not _has_any(request, db, user, "wiring.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wiring diagrams access required")
    return user


def require_wiring_diagrams_manager(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not _has_any(request, db, user, "wiring.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Wiring diagrams management required")
    return user


def require_store_access(
    request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    if not _has_any(request, db, user, "store.view"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Store access required")
    return user


def login_redirect(next_url: str) -> RedirectResponse:
    target = "/login"
    if next_url and next_url not in {"/", "/login"}:
        target = f"/login?next={quote(next_url, safe='')}"
    return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
