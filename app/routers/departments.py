"""Administrator Department workspaces and granular access management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from ..access_control import set_active_department
from ..audit import set_audit_context
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..helpers import entity_id, flash, render, request_language
from ..models import (
    AccessScope,
    Department,
    DepartmentPermission,
    PricingCategoryUserAccess,
    PricingItem,
    PricingItemCategory,
    PricingItemUserAccess,
    ProjectTeamMember,
    Site,
    StoreUserWarehouse,
    StoreWarehouse,
    TaskStatus,
    User,
    UserDepartment,
    UserDepartmentPermission,
    UserDepartmentScope,
    UserRole,
    WorkTask,
    utcnow,
)
from ..permissions import (
    PERMISSION_BY_KEY,
    PROJECT_SCOPED_GROUPS,
    SCOPED_PERMISSION_GROUPS,
    SCOPE_CHOICES,
    grouped_permissions,
)
from ..security import csrf_valid


router = APIRouter()


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _csrf_or_redirect(request: Request, token: str, path: str) -> RedirectResponse | None:
    if csrf_valid(request, token):
        return None
    flash(request, "Your form expired. Try again.", "error")
    return _redirect(path)


def _clean_code(value: str) -> str:
    return "-".join(value.strip().upper().split())


@router.post("/workspace")
def switch_workspace(
    request: Request,
    department_id: str = Form(""),
    next_url: str = Form("/dashboard"),
    csrf_token: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if (bad := _csrf_or_redirect(request, csrf_token, "/dashboard")):
        return bad
    parsed = entity_id(department_id)
    if parsed is None:
        flash(request, "Choose a valid Department.", "error")
        return _redirect("/dashboard")
    department = set_active_department(request, db, user, parsed)
    flash(request, f"Workspace changed to {department.name}.")
    safe_next = next_url if next_url.startswith("/") and not next_url.startswith("//") else "/dashboard"
    return _redirect(safe_next)


@router.get("/departments", dependencies=[Depends(require_admin)])
def department_list(request: Request, db: Session = Depends(get_db)):
    departments = list(
        db.scalars(
            select(Department)
            .options(selectinload(Department.memberships).selectinload(UserDepartment.user))
            .order_by(Department.is_general.desc(), Department.name)
        ).unique()
    )
    return render(
        request,
        "departments.html",
        {
            "active_nav": "departments",
            "departments": departments,
        },
    )


@router.post("/departments", dependencies=[Depends(require_admin)])
def create_department(
    request: Request,
    name: str = Form(""),
    code: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _csrf_or_redirect(request, csrf_token, "/departments")):
        return bad
    clean_name, clean_code = name.strip(), _clean_code(code)
    if not clean_name or not clean_code:
        flash(request, "Department name and code are required.", "error")
        return _redirect("/departments")
    clash = db.scalar(
        select(Department.id).where(
            (func.lower(Department.name) == clean_name.lower())
            | (func.lower(Department.code) == clean_code.lower())
        )
    )
    if clash:
        flash(request, "Department name or code is already in use.", "error")
        return _redirect("/departments")
    department = Department(
        name=clean_name,
        code=clean_code,
        description=description.strip() or None,
    )
    db.add(department)
    db.flush()
    set_audit_context(
        request,
        action="department_created",
        entity_type="department",
        entity_id=department.id,
        entity_label=department.name,
        changes={"code": department.code},
    )
    db.commit()
    flash(request, f"Department {clean_name} created.")
    return _redirect(f"/departments/{department.id}")


@router.get("/departments/{department_id}", dependencies=[Depends(require_admin)])
def department_detail(department_id: int, request: Request, db: Session = Depends(get_db)):
    department = db.scalar(
        select(Department)
        .where(Department.id == department_id)
        .options(
            selectinload(Department.memberships).selectinload(UserDepartment.user),
            selectinload(Department.default_permissions),
        )
    )
    if department is None:
        flash(request, "That Department no longer exists.", "error")
        return _redirect("/departments")
    defaults = {row.permission_key: row.allowed for row in department.default_permissions}
    return render(
        request,
        "department_detail.html",
        {
            "active_nav": "departments",
            "department": department,
            "defaults": defaults,
            "permission_groups": grouped_permissions(request_language(request)),
            "users": list(
                db.scalars(
                    select(User)
                    .where(User.is_active.is_(True), User.role != UserRole.CUSTOMER)
                    .order_by(User.full_name)
                )
            ),
        },
    )


@router.post("/departments/{department_id}/details", dependencies=[Depends(require_admin)])
def update_department(
    department_id: int,
    request: Request,
    name: str = Form(""),
    code: str = Form(""),
    description: str = Form(""),
    is_active: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    back = f"/departments/{department_id}"
    if (bad := _csrf_or_redirect(request, csrf_token, back)):
        return bad
    department = db.get(Department, department_id)
    if department is None:
        return _redirect("/departments")
    clean_name, clean_code = name.strip(), _clean_code(code)
    if not clean_name or not clean_code:
        flash(request, "Department name and code are required.", "error")
        return _redirect(back)
    clash = db.scalar(
        select(Department.id).where(
            Department.id != department.id,
            (func.lower(Department.name) == clean_name.lower())
            | (func.lower(Department.code) == clean_code.lower()),
        )
    )
    if clash:
        flash(request, "Department name or code is already in use.", "error")
        return _redirect(back)
    before = {
        "name": department.name,
        "code": department.code,
        "description": department.description,
        "is_active": department.is_active,
    }
    department.name = clean_name
    department.code = clean_code
    department.description = description.strip() or None
    department.is_active = True if department.is_general else is_active == "1"
    department.updated_at = utcnow()
    set_audit_context(
        request,
        action="department_updated",
        entity_type="department",
        entity_id=department.id,
        entity_label=department.name,
        changes={
            "before": before,
            "after": {
                "name": department.name,
                "code": department.code,
                "description": department.description,
                "is_active": department.is_active,
            },
        },
    )
    db.commit()
    flash(request, "Department details saved.")
    return _redirect(back)


@router.post("/departments/{department_id}/permissions", dependencies=[Depends(require_admin)])
async def update_department_permissions(
    department_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    back = f"/departments/{department_id}"
    form = await request.form()
    if (bad := _csrf_or_redirect(request, str(form.get("csrf_token") or ""), back)):
        return bad
    department = db.get(Department, department_id)
    if department is None:
        return _redirect("/departments")
    selected = set(form.getlist("permission_key")) & set(PERMISSION_BY_KEY)
    existing = {
        row.permission_key: row
        for row in db.scalars(
            select(DepartmentPermission).where(DepartmentPermission.department_id == department.id)
        )
    }
    before_selected = sorted(key for key, row in existing.items() if row.allowed)
    for key in PERMISSION_BY_KEY:
        row = existing.get(key)
        if row is None:
            db.add(DepartmentPermission(department_id=department.id, permission_key=key, allowed=key in selected))
        else:
            row.allowed = key in selected
            row.updated_at = utcnow()
    set_audit_context(
        request,
        action="department_permissions_updated",
        entity_type="department",
        entity_id=department.id,
        entity_label=department.name,
        changes={
            "before": before_selected,
            "after": sorted(selected),
        },
    )
    db.commit()
    flash(request, "Department permission defaults saved.")
    return _redirect(back)


@router.post("/departments/{department_id}/members", dependencies=[Depends(require_admin)])
def add_department_member(
    department_id: int,
    request: Request,
    user_id: str = Form(""),
    job_title: str = Form(""),
    is_primary: str = Form(""),
    csrf_token: str = Form(""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    back = f"/departments/{department_id}"
    if (bad := _csrf_or_redirect(request, csrf_token, back)):
        return bad
    parsed = entity_id(user_id)
    department, target = db.get(Department, department_id), db.get(User, parsed) if parsed else None
    if department is None or target is None or target.is_customer:
        flash(request, "Choose a valid internal user.", "error")
        return _redirect(back)
    membership = db.get(UserDepartment, (target.id, department.id))
    if membership is None:
        membership = UserDepartment(
            user_id=target.id,
            department_id=department.id,
            added_by_id=admin.id,
        )
        db.add(membership)
    membership.job_title = job_title.strip() or None
    if is_primary == "1":
        db.execute(
            UserDepartment.__table__.update()
            .where(UserDepartment.user_id == target.id)
            .values(is_primary=False)
        )
        membership.is_primary = True
    set_audit_context(
        request,
        action="department_member_added" if membership in db.new else "department_member_updated",
        entity_type="user_department",
        entity_id=f"{target.id}:{department.id}",
        entity_label=f"{target.full_name} — {department.name}",
        changes={"job_title": membership.job_title, "is_primary": membership.is_primary},
    )
    db.commit()
    flash(request, f"{target.full_name} added to {department.name}.")
    return _redirect(back)


@router.get("/users/{user_id}/access", dependencies=[Depends(require_admin)])
def user_access_page(user_id: int, request: Request, db: Session = Depends(get_db)):
    target = db.scalar(
        select(User)
        .where(User.id == user_id)
        .options(
            selectinload(User.department_memberships).selectinload(UserDepartment.department),
            selectinload(User.department_memberships).selectinload(UserDepartment.permissions),
            selectinload(User.department_memberships).selectinload(UserDepartment.scopes),
        )
    )
    if target is None:
        return _redirect("/users")
    direct_permissions = {
        (row.department_id, row.permission_key)
        for membership in target.department_memberships
        for row in membership.permissions
        if row.allowed
    }
    scopes = {
        (row.department_id, row.module_key): row.scope.value
        for membership in target.department_memberships
        for row in membership.scopes
    }
    catalog_categories = list(db.scalars(
        select(PricingItemCategory)
        .where(PricingItemCategory.parent_id.is_(None))
        .order_by(PricingItemCategory.name)
        .execution_options(include_all_departments=True)
    ))
    catalog_items = list(db.scalars(
        select(PricingItem)
        .options(selectinload(PricingItem.category).selectinload(PricingItemCategory.parent))
        .order_by(PricingItem.name, PricingItem.model)
        .execution_options(include_all_departments=True)
    ))
    warehouses = list(db.scalars(
        select(StoreWarehouse)
        .order_by(StoreWarehouse.name)
        .execution_options(include_all_departments=True)
    ))
    return render(
        request,
        "user_access.html",
        {
            "active_nav": "users",
            "target": target,
            "departments": list(db.scalars(select(Department).order_by(Department.name))),
            "permission_groups": grouped_permissions(request_language(request)),
            "direct_permissions": direct_permissions,
            "scopes": scopes,
            "scope_choices": SCOPE_CHOICES,
            "scoped_permission_groups": SCOPED_PERMISSION_GROUPS,
            "project_scoped_groups": PROJECT_SCOPED_GROUPS,
            "projects": list(db.scalars(select(Site).where(Site.is_active.is_(True)).order_by(Site.name))),
            "selected_projects": {
                (membership.department_id, membership.project_id)
                for membership in target.project_team_memberships
            },
            "catalog_categories": catalog_categories,
            "catalog_items": catalog_items,
            "warehouses": warehouses,
            "selected_warehouse_ids": set(db.scalars(
                select(StoreUserWarehouse.warehouse_id).where(
                    StoreUserWarehouse.user_id == target.id
                )
            )),
            "selected_category_ids": set(db.scalars(
                select(PricingCategoryUserAccess.category_id).where(
                    PricingCategoryUserAccess.user_id == target.id
                )
            )),
            "selected_item_ids": set(db.scalars(
                select(PricingItemUserAccess.item_id).where(
                    PricingItemUserAccess.user_id == target.id
                )
            )),
        },
    )


@router.post("/users/{user_id}/access", dependencies=[Depends(require_admin)])
async def save_user_access(user_id: int, request: Request, db: Session = Depends(get_db)):
    back = f"/users/{user_id}/access"
    form = await request.form()
    if (bad := _csrf_or_redirect(request, str(form.get("csrf_token") or ""), back)):
        return bad
    target = db.get(User, user_id)
    if target is None or target.is_customer:
        flash(request, "That internal user no longer exists.", "error")
        return _redirect("/users")
    selected_ids = {
        parsed for value in form.getlist("department_id") if (parsed := entity_id(str(value)))
    }
    valid_ids = set(db.scalars(select(Department.id).where(Department.id.in_(selected_ids))))
    if not valid_ids:
        flash(request, "Assign at least one Department to an internal user.", "error")
        return _redirect(back)
    primary_id = entity_id(str(form.get("primary_department_id") or ""))
    if primary_id not in valid_ids and len(valid_ids) == 1:
        primary_id = next(iter(valid_ids))
    if valid_ids and primary_id not in valid_ids:
        flash(request, "Choose a primary Department from the user's memberships.", "error")
        return _redirect(back)

    existing = {row.department_id: row for row in target.department_memberships}
    removed_ids = set(existing) - valid_ids
    blocked_task = db.scalar(
        select(WorkTask.id).where(
            WorkTask.assigned_to_id == target.id,
            WorkTask.department_id.in_(removed_ids),
            WorkTask.status.not_in((TaskStatus.COMPLETED, TaskStatus.CANCELLED)),
        ).limit(1)
    ) if removed_ids else None
    if blocked_task is not None:
        flash(
            request,
            "Reassign or close the user's active Tasks in that Department before removing the Department membership.",
            "error",
        )
        return _redirect(back)
    # Clear the old primary first. PostgreSQL checks the partial unique index
    # row-by-row, so changing the new membership to primary in the same flush
    # can otherwise collide with the previous primary membership.
    for membership in existing.values():
        membership.is_primary = False
    db.flush()
    carried_project_ids = {
        row.project_id
        for row in target.project_team_memberships
        if row.department_id in removed_ids
    }
    for department_id in valid_ids:
        membership = existing.get(department_id)
        if membership is None:
            membership = UserDepartment(user_id=target.id, department_id=department_id)
            db.add(membership)
        membership.is_primary = department_id == primary_id
        membership.job_title = str(form.get(f"job_title:{department_id}") or "").strip() or None
    db.flush()
    # Project selection belongs to the user.  When their old Department is
    # removed, carry those selections into the new primary Department instead
    # of forcing the Administrator to delete and recreate every assignment.
    for team_member in db.scalars(
        select(ProjectTeamMember).where(
            ProjectTeamMember.user_id == target.id,
            ProjectTeamMember.department_id.in_(removed_ids),
        )
    ):
        team_member.department_id = primary_id
    for department_id, membership in existing.items():
        if department_id not in valid_ids:
            db.delete(membership)
    db.flush()

    db.execute(delete(UserDepartmentPermission).where(UserDepartmentPermission.user_id == target.id))
    db.execute(delete(UserDepartmentScope).where(UserDepartmentScope.user_id == target.id))
    for department_id in valid_ids:
        for key in PERMISSION_BY_KEY:
            if str(form.get(f"permission:{department_id}:{key}") or "") == "1":
                db.add(
                    UserDepartmentPermission(
                        user_id=target.id,
                        department_id=department_id,
                        permission_key=key,
                        allowed=True,
                    )
                )
        for module_key in SCOPED_PERMISSION_GROUPS:
            try:
                scope = AccessScope(str(form.get(f"scope:{department_id}:{module_key}") or "none"))
            except ValueError:
                scope = AccessScope.NONE
            db.add(UserDepartmentScope(
                user_id=target.id,
                department_id=department_id,
                module_key=module_key,
                scope=scope,
            ))

    requested_projects: dict[int, set[int]] = {
        department_id: {
            parsed
            for raw in form.getlist(f"project:{department_id}")
            if (parsed := entity_id(str(raw))) is not None
        }
        for department_id in valid_ids
    }
    # A removed Department is not a request to forget the user's selected
    # Projects. Keep those selections under the new primary Department; the
    # Administrator can explicitly remove them on a later save.
    if carried_project_ids:
        requested_projects.setdefault(primary_id, set()).update(carried_project_ids)
    valid_project_ids = set(db.scalars(select(Site.id).where(
        Site.id.in_(set().union(*requested_projects.values()) if requested_projects else set())
    )))
    for team_member in list(target.project_team_memberships):
        if team_member.project_role == "Project creator":
            continue
        expected = requested_projects.get(team_member.department_id, set())
        if team_member.project_id not in expected:
            db.delete(team_member)
    db.flush()
    existing_project_ids = {row.project_id for row in target.project_team_memberships}
    for department_id, project_ids in requested_projects.items():
        for project_id in project_ids & valid_project_ids:
            if project_id in existing_project_ids:
                team_member = db.get(ProjectTeamMember, (project_id, target.id))
                team_member.department_id = department_id
                continue
            db.add(ProjectTeamMember(
                project_id=project_id,
                user_id=target.id,
                department_id=department_id,
                project_role="Selected access",
                can_view_records=True,
                can_create_records=True,
                can_view_reports=True,
                can_view_quotations=True,
                can_manage_tasks=True,
                added_by_id=request.state.user.id,
            ))
            existing_project_ids.add(project_id)

    db.execute(delete(PricingCategoryUserAccess).where(
        PricingCategoryUserAccess.user_id == target.id
    ))
    db.execute(delete(PricingItemUserAccess).where(
        PricingItemUserAccess.user_id == target.id
    ))
    for department_id in valid_ids:
        requested_category_ids = {
            parsed for raw in form.getlist(f"category:{department_id}")
            if (parsed := entity_id(str(raw))) is not None
        }
        valid_category_ids = set(db.scalars(
            select(PricingItemCategory.id).where(
                PricingItemCategory.department_id == department_id,
                PricingItemCategory.id.in_(requested_category_ids),
            ).execution_options(include_all_departments=True)
        ))
        for category_id in valid_category_ids:
            db.add(PricingCategoryUserAccess(
                category_id=category_id,
                user_id=target.id,
                granted_by_id=request.state.user.id,
            ))
        requested_item_ids = {
            parsed for raw in form.getlist(f"item:{department_id}")
            if (parsed := entity_id(str(raw))) is not None
        }
        valid_item_ids = set(db.scalars(
            select(PricingItem.id).where(
                PricingItem.department_id == department_id,
                PricingItem.id.in_(requested_item_ids),
            ).execution_options(include_all_departments=True)
        ))
        for item_id in valid_item_ids:
            db.add(PricingItemUserAccess(
                item_id=item_id,
                user_id=target.id,
                granted_by_id=request.state.user.id,
            ))
    db.execute(delete(StoreUserWarehouse).where(StoreUserWarehouse.user_id == target.id))
    requested_warehouse_ids = {
        parsed
        for department_id in valid_ids
        for raw in form.getlist(f"warehouse:{department_id}")
        if (parsed := entity_id(str(raw))) is not None
    }
    valid_warehouse_ids = set(db.scalars(
        select(StoreWarehouse.id).where(
            StoreWarehouse.department_id.in_(valid_ids),
            StoreWarehouse.id.in_(requested_warehouse_ids),
        ).execution_options(include_all_departments=True)
    ))
    for warehouse_id in valid_warehouse_ids:
        db.add(StoreUserWarehouse(user_id=target.id, warehouse_id=warehouse_id))
    set_audit_context(
        request,
        action="user_department_access_updated",
        entity_type="user",
        entity_id=target.id,
        entity_label=target.full_name,
        changes={
            "departments": {"before": sorted(existing), "after": sorted(valid_ids)},
            "primary_department_id": primary_id,
            "direct_permissions": sum(
                1
                for department_id in valid_ids
                for key in PERMISSION_BY_KEY
                if str(form.get(f"permission:{department_id}:{key}") or "") == "1"
            ),
            "project_access": {str(key): sorted(value) for key, value in requested_projects.items()},
            "warehouses": sorted(valid_warehouse_ids),
        },
    )
    db.commit()
    flash(request, f"Department access saved for {target.full_name}.")
    return _redirect(back)
