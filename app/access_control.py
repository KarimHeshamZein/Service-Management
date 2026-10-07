"""Department workspace resolution and centralized authorization checks."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AccessScope,
    CustomerProjectAssignment,
    Department,
    ProjectTeamMember,
    Site,
    User,
    UserDepartment,
    UserDepartmentPermission,
    UserDepartmentScope,
)
from .permissions import PERMISSION_BY_KEY, PERMISSION_IMPLICATIONS


@dataclass(frozen=True)
class DepartmentContext:
    active: Department
    choices: tuple[Department, ...]


def available_departments(db: Session, user: User) -> tuple[Department, ...]:
    statement = select(Department).where(Department.is_active.is_(True)).order_by(Department.name)
    if not user.is_admin:
        statement = statement.join(UserDepartment).where(UserDepartment.user_id == user.id)
    return tuple(db.scalars(statement).unique())


def resolve_department(request: Request, db: Session, user: User) -> DepartmentContext:
    choices = available_departments(db, user)
    if not choices:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Your account is not assigned to an active Department.",
        )

    allowed = {department.id: department for department in choices}
    raw_id = request.session.get("department_id")
    active = allowed.get(raw_id) if isinstance(raw_id, int) else None
    if active is None:
        primary_id = db.scalar(
            select(UserDepartment.department_id).where(
                UserDepartment.user_id == user.id,
                UserDepartment.is_primary.is_(True),
            )
        )
        active = allowed.get(primary_id) or choices[0]
        request.session["department_id"] = active.id

    request.state.department = active
    request.state.department_choices = choices
    db.info["department_id"] = active.id
    db.info["user_id"] = user.id
    db.info["is_admin"] = user.is_admin
    return DepartmentContext(active=active, choices=choices)


def set_active_department(request: Request, db: Session, user: User, department_id: int) -> Department:
    allowed = {department.id: department for department in available_departments(db, user)}
    department = allowed.get(department_id)
    if department is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Department access denied")
    request.session["department_id"] = department.id
    db.info["department_id"] = department.id
    db.info["user_id"] = user.id
    db.info["is_admin"] = user.is_admin
    request.state.department = department
    request.state.department_choices = tuple(allowed.values())
    return department


def permission_allowed(db: Session, user: User, department_id: int, permission_key: str) -> bool:
    if permission_key not in PERMISSION_BY_KEY:
        raise ValueError(f"Unknown permission key: {permission_key}")
    if user.is_admin:
        return True

    membership_exists = db.scalar(
        select(UserDepartment.user_id).where(
            UserDepartment.user_id == user.id,
            UserDepartment.department_id == department_id,
        )
    )
    if membership_exists is None:
        return False

    override = db.scalar(
        select(UserDepartmentPermission.allowed).where(
            UserDepartmentPermission.user_id == user.id,
            UserDepartmentPermission.department_id == department_id,
            UserDepartmentPermission.permission_key == permission_key,
        )
    )
    if override is not None:
        return bool(override)

    implied_by = PERMISSION_IMPLICATIONS.get(permission_key, frozenset())
    if implied_by:
        return bool(db.scalar(select(UserDepartmentPermission.permission_key).where(
            UserDepartmentPermission.user_id == user.id,
            UserDepartmentPermission.department_id == department_id,
            UserDepartmentPermission.permission_key.in_(implied_by),
            UserDepartmentPermission.allowed.is_(True),
        ).limit(1)))

    return False


def allowed_permission_keys(
    db: Session,
    user: User,
    department_id: int,
) -> frozenset[str]:
    """Resolve one immutable permission snapshot for the current request."""
    if user.is_admin:
        return frozenset(PERMISSION_BY_KEY)

    membership_exists = db.scalar(
        select(UserDepartment.user_id).where(
            UserDepartment.user_id == user.id,
            UserDepartment.department_id == department_id,
        )
    )
    if membership_exists is None:
        return frozenset()

    allowed: set[str] = set()
    denied: set[str] = set()
    for key, value in db.execute(
        select(
            UserDepartmentPermission.permission_key,
            UserDepartmentPermission.allowed,
        ).where(
            UserDepartmentPermission.user_id == user.id,
            UserDepartmentPermission.department_id == department_id,
        )
    ):
        if key not in PERMISSION_BY_KEY:
            continue
        if value:
            allowed.add(key)
            denied.discard(key)
        else:
            allowed.discard(key)
            denied.add(key)
    for implied, sources in PERMISSION_IMPLICATIONS.items():
        if implied not in denied and sources & allowed:
            allowed.add(implied)
    return frozenset(allowed)


def permission_scopes(db: Session, user: User, department_id: int) -> dict[str, AccessScope]:
    if user.is_admin:
        return {}
    return {
        module_key: scope
        for module_key, scope in db.execute(
            select(UserDepartmentScope.module_key, UserDepartmentScope.scope).where(
                UserDepartmentScope.user_id == user.id,
                UserDepartmentScope.department_id == department_id,
            )
        )
    }


def module_scope(user: User, module_key: str) -> AccessScope:
    if user.is_admin:
        return AccessScope.DEPARTMENT
    scope = getattr(user, "_permission_scopes", {}).get(module_key, AccessScope.NONE)
    if scope == AccessScope.NONE and any(
        key.startswith(f"{module_key}.") and not key.endswith(".view")
        for key in getattr(user, "_allowed_permissions", frozenset())
    ):
        return AccessScope.OWN
    return scope


def visible_project_ids(
    db: Session,
    user: User,
    department_id: int,
    *,
    module_key: str = "projects",
) -> set[int] | None:
    """Resolve the shared selected Project list for one module view scope."""
    if user.is_admin:
        return None
    if user.is_customer:
        return set(db.scalars(select(CustomerProjectAssignment.project_id).where(
            CustomerProjectAssignment.user_id == user.id
        )))
    scope = module_scope(user, module_key)
    if scope == AccessScope.DEPARTMENT:
        return set(db.scalars(select(ProjectTeamMember.project_id).where(
            ProjectTeamMember.department_id == department_id
        ).distinct()))
    if scope == AccessScope.SELECTED:
        return set(db.scalars(select(ProjectTeamMember.project_id).where(
            ProjectTeamMember.user_id == user.id,
            ProjectTeamMember.department_id == department_id,
        )))
    if scope == AccessScope.OWN:
        return set(db.scalars(select(ProjectTeamMember.project_id).where(
            ProjectTeamMember.user_id == user.id,
            ProjectTeamMember.department_id == department_id,
            ProjectTeamMember.project_role == "Project creator",
        )))
    return set()


def owns_or_can_view_project_record(user: User, *, project_ids: set[int], submitted_by_id: int) -> bool:
    return user.is_admin or submitted_by_id == user.id or project_ids.issubset(user.assigned_project_ids)


def require_permission(
    request: Request,
    db: Session,
    user: User,
    permission_key: str,
) -> Department:
    context = resolve_department(request, db, user)
    if not permission_allowed(db, user, context.active.id, permission_key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Permission denied")
    return context.active


def project_access_allowed(
    db: Session,
    user: User,
    project_id: int,
    *,
    capability: str = "can_view_records",
    module_key: str | None = None,
) -> bool:
    if user.is_admin:
        return True
    if capability not in {
        "can_view_records", "can_create_records", "can_view_reports",
        "can_view_quotations", "can_manage_tasks",
    }:
        raise ValueError(f"Unknown Project capability: {capability}")
    if user.is_customer:
        return bool(db.scalar(select(CustomerProjectAssignment.project_id).where(
            CustomerProjectAssignment.project_id == project_id,
            CustomerProjectAssignment.user_id == user.id,
        )))
    department_id = db.info.get("department_id")
    if department_id is None:
        return False
    module_key = module_key or {
        "can_view_records": "records",
        "can_create_records": "records",
        "can_view_reports": "reports",
        "can_view_quotations": "quotations",
        "can_manage_tasks": "tasks",
    }[capability]
    return project_id in (visible_project_ids(db, user, department_id, module_key=module_key) or set())


def accessible_project_ids(db: Session, user: User, *, capability: str) -> set[int] | None:
    """Return None for the Administrator's unrestricted scope; otherwise explicit IDs."""
    if user.is_admin:
        return None
    if capability not in {
        "can_view_records", "can_create_records", "can_view_reports",
        "can_view_quotations", "can_manage_tasks",
    }:
        raise ValueError(f"Unknown Project capability: {capability}")
    if user.is_customer:
        return set(db.scalars(select(CustomerProjectAssignment.project_id).where(
            CustomerProjectAssignment.user_id == user.id
        )))
    department_id = db.info.get("department_id")
    if department_id is None:
        return set()
    module_key = {
        "can_view_records": "records",
        "can_create_records": "records",
        "can_view_reports": "reports",
        "can_view_quotations": "quotations",
        "can_manage_tasks": "tasks",
    }[capability]
    return visible_project_ids(db, user, department_id, module_key=module_key) or set()
