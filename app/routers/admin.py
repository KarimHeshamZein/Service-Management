"""Administrator pages: sites, service types and users.

Nothing here is reachable without require_admin — hiding nav links is cosmetic,
the dependency is the actual control.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..account_recovery import (
    VERIFY_LIFETIME,
    VERIFY_PURPOSE,
    MailDeliveryError,
    bump_auth_version,
    issue_token,
    send_verification_email,
    valid_email,
)
from ..access_control import permission_allowed, project_access_allowed, require_permission
from ..audit import set_audit_context
from ..database import get_db
from ..deps import require_admin, require_catalog_manager
from ..helpers import entity_id, flash, render
from ..notifications import create_notification, deliver_notification_email
from ..models import (
    CustomerProjectAssignment,
    AdminRecoveryContact,
    DeviceCatalog,
    Department,
    GeneralMaintenanceRecord,
    InstalledDevice,
    InstallationRecord,
    InstallationRecordSite,
    MaintenanceRecord,
    ProjectTeamMember,
    ServiceType,
    Site,
    SubProject,
    SubProjectSite,
    User,
    UserDepartment,
    UserRole,
    WorkSite,
    utcnow,
)
from ..security import csrf_valid, hash_password

router = APIRouter()

MIN_PASSWORD_LENGTH = 8
MAX_DESCRIPTION_LENGTH = 5000


def _guard(request: Request, csrf: str, back: str) -> RedirectResponse | None:
    if not csrf_valid(request, csrf):
        flash(request, "Your session expired. Please try again.", "error")
        return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)
    return None


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def _usage_count(db: Session, column, value: int) -> int:
    return int(db.scalar(select(func.count(MaintenanceRecord.id)).where(column == value)) or 0)


def _delete_or_deactivate(db: Session, model, row_id: int) -> str:
    """Hard-delete unused catalog data; deactivate rows protected by history."""
    try:
        db.execute(
            delete(model)
            .where(model.id == row_id)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        return "deleted"
    except IntegrityError:
        db.rollback()
        row = db.get(model, row_id)
        if row is None:
            return "missing"
        row.is_active = False
        if hasattr(row, "updated_at"):
            row.updated_at = utcnow()
        db.commit()
        return "deactivated"


def _optional_date_range(
    start_raw: str,
    end_raw: str,
) -> tuple[date | None, date | None, str | None]:
    try:
        start = date.fromisoformat(start_raw) if start_raw.strip() else None
        end = date.fromisoformat(end_raw) if end_raw.strip() else None
    except ValueError:
        return None, None, "Enter valid project dates."
    if start and end and end < start:
        return None, None, "End date must be on or after start date."
    return start, end, None


def _project_record_usage(db: Session) -> dict[int, int]:
    usage: dict[int, int] = {}
    for model in (MaintenanceRecord, InstallationRecord, GeneralMaintenanceRecord):
        for project_id, count in db.execute(
            select(model.site_id, func.count()).group_by(model.site_id)
        ).all():
            usage[project_id] = usage.get(project_id, 0) + int(count)
    return usage


# ------------------------------------------------------------------ sites


@router.get("/_legacy/sites")
def sites_page(
    request: Request,
    q: str = "",
    user: User = Depends(require_catalog_manager),
):
    return _redirect("/projects")


# --------------------------------------------------------------- projects


@router.get("/projects")
def projects_page(
    request: Request,
    q: str = "",
    project_id: str = "",
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "projects.view")
    stmt = (
        select(Site)
        .options(
            selectinload(Site.customer_assignments).selectinload(
                CustomerProjectAssignment.user
            ),
            selectinload(Site.sub_projects)
            .selectinload(SubProject.site_assignments)
            .selectinload(SubProjectSite.site),
            selectinload(Site.photo_guidance_setting),
            selectinload(Site.photo_guidance_profiles),
            selectinload(Site.team_memberships).selectinload(ProjectTeamMember.user),
            selectinload(Site.team_memberships).selectinload(ProjectTeamMember.department),
        )
        .order_by(Site.is_active.desc(), Site.name)
    )
    term = q.strip()
    if not user.is_admin:
        stmt = stmt.where(Site.id.in_(request.state.project_ids["projects"]))
    projects = list(db.scalars(stmt).unique())
    if term:
        needle = term.casefold()
        projects = [
            project
            for project in projects
            if needle
            in " ".join(
                filter(
                    None,
                    (
                        project.name,
                        project.city,
                        project.address,
                        project.contact_person,
                        project.contact_number,
                        project.description,
                        *(assignment.user.full_name for assignment in project.customer_assignments),
                        *(sub_project.name for sub_project in project.sub_projects),
                        *(
                            assignment.site.name
                            for sub_project in project.sub_projects
                            for assignment in sub_project.site_assignments
                        ),
                    ),
                )
            ).casefold()
        ]
    selected_id = entity_id(project_id)
    selected_project = next(
        (project for project in projects if project.id == selected_id),
        projects[0] if projects else None,
    )
    return render(
        request,
        "projects.html",
        {
            "active_nav": "projects",
            "projects": projects,
            "selected_project": selected_project,
            "available_sites": list(
                db.scalars(
                    select(WorkSite).order_by(WorkSite.is_active.desc(), WorkSite.name)
                )
            ),
            "q": term,
            "usage": _project_record_usage(db),
            "project_member_choices": list(
                db.scalars(
                    select(UserDepartment)
                    .options(selectinload(UserDepartment.user), selectinload(UserDepartment.department))
                    .join(User, User.id == UserDepartment.user_id)
                    .where(User.is_active.is_(True))
                    .order_by(User.full_name, UserDepartment.department_id)
                )
            ) if permission_allowed(
                db, user, db.info["department_id"], "projects.manage_team"
            ) else [],
        },
    )


@router.post("/projects")
def create_project(
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    contact_person: str = Form(""),
    contact_number: str = Form(""),
    description: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    csrf_token: str = Form(""),
    creator: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, creator, "projects.create")
    if (bad := _guard(request, csrf_token, "/projects")):
        return bad
    name, address = name.strip(), address.strip()
    if not name or not address:
        flash(request, "Project name and address or location are required.", "error")
        return _redirect("/projects")
    description = description.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        flash(request, f"Keep the project description under {MAX_DESCRIPTION_LENGTH} characters.", "error")
        return _redirect("/projects")
    starts_on, ends_on, date_error = _optional_date_range(start_date, end_date)
    if date_error:
        flash(request, date_error, "error")
        return _redirect("/projects")
    if db.scalar(select(Site).where(func.lower(Site.name) == name.lower())):
        flash(request, f"“{name}” already exists.", "error")
        return _redirect("/projects")
    project = Site(
        name=name,
        customer_name=name,
        address=address,
        city=city.strip() or None,
        contact_person=contact_person.strip() or None,
        contact_number=contact_number.strip() or None,
        description=description or None,
        start_date=starts_on,
        end_date=ends_on,
    )
    general = SubProject(name="General")
    project.sub_projects.append(general)
    db.add(project)
    db.flush()
    active_department = getattr(request.state, "department", None)
    if active_department is not None and db.get(UserDepartment, (creator.id, active_department.id)):
        project.team_memberships.append(
            ProjectTeamMember(
                user_id=creator.id,
                department_id=active_department.id,
                project_role="Project creator",
                can_view_records=True,
                can_create_records=True,
                can_view_reports=True,
                can_view_quotations=True,
                can_manage_tasks=True,
                added_by_id=creator.id,
            )
        )
    db.commit()
    flash(request, f"Project “{name}” added.")
    return _redirect("/projects")


@router.post("/projects/{project_id}/team")
def add_project_team_member(
    project_id: int,
    request: Request,
    membership: str = Form(""),
    project_role: str = Form(""),
    csrf_token: str = Form(""),
    admin: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, admin, "projects.manage_team")
    back = f"/projects?project_id={project_id}"
    if (bad := _guard(request, csrf_token, back)):
        return bad
    try:
        user_raw, department_raw = membership.split(":", 1)
    except ValueError:
        user_raw = department_raw = ""
    user_id, department_id = entity_id(user_raw), entity_id(department_raw)
    project = db.get(Site, project_id)
    target_membership = db.get(UserDepartment, (user_id, department_id)) if user_id and department_id else None
    if project is None or target_membership is None:
        flash(request, "Choose a valid user and Department membership.", "error")
        return _redirect(back)
    team_member = db.get(ProjectTeamMember, (project.id, target_membership.user_id))
    is_new_member = team_member is None
    if team_member is None:
        team_member = ProjectTeamMember(project_id=project.id, user_id=target_membership.user_id)
        db.add(team_member)
    team_member.department_id = target_membership.department_id
    team_member.project_role = project_role.strip() or None
    team_member.can_view_records = True
    # Project membership is only the selected-resource list.  What the user
    # may actually do is controlled by their direct permissions and module
    # scope on the User Roles page.
    team_member.can_create_records = True
    team_member.can_view_reports = True
    team_member.can_view_quotations = True
    team_member.can_manage_tasks = True
    team_member.added_by_id = admin.id
    target_user = db.get(User, target_membership.user_id)
    notification = None
    if is_new_member and target_user is not None and target_user.id != admin.id:
        notification = create_notification(
            db,
            user=target_user,
            kind="project_team_added",
            title=f"Added to Project {project.name}",
            message=f"{admin.full_name} added you to the Project team.",
            target_url=f"/projects?project_id={project.id}",
            department_id=target_membership.department_id,
        )
    set_audit_context(
        request,
        action="project_team_member_added" if is_new_member else "project_team_member_updated",
        entity_type="project_team_member",
        entity_id=f"{project.id}:{target_membership.user_id}",
        entity_label=f"{project.name} — {target_user.full_name if target_user else target_membership.user_id}",
        changes={
            "department_id": target_membership.department_id,
            "project_role": team_member.project_role,
            "selection_only": True,
        },
    )
    db.commit()
    if notification is not None and target_user is not None:
        deliver_notification_email(db, notification, target_user)
    flash(request, "Project team member saved.")
    return _redirect(back)


@router.post("/projects/{project_id}/team/{user_id}/remove")
def remove_project_team_member(
    project_id: int,
    user_id: int,
    request: Request,
    csrf_token: str = Form(""),
    admin: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, admin, "projects.manage_team")
    back = f"/projects?project_id={project_id}"
    if (bad := _guard(request, csrf_token, back)):
        return bad
    member = db.get(ProjectTeamMember, (project_id, user_id))
    if member is not None:
        project = db.get(Site, project_id)
        target = db.get(User, user_id)
        set_audit_context(
            request,
            action="project_team_member_removed",
            entity_type="project_team_member",
            entity_id=f"{project_id}:{user_id}",
            entity_label=f"{project.name if project else project_id} — {target.full_name if target else user_id}",
            changes={"removed": True, "department_id": member.department_id},
        )
        db.delete(member)
        db.commit()
        flash(request, "Project team member removed.")
    return _redirect(back)


@router.post("/projects/{project_id}/edit")
def edit_project(
    project_id: int,
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    contact_person: str = Form(""),
    contact_number: str = Form(""),
    description: str = Form(""),
    start_date: str = Form(""),
    end_date: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "projects.edit")
    if not project_access_allowed(db, user, project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    if (bad := _guard(request, csrf_token, "/projects")):
        return bad
    project = db.get(Site, project_id)
    name, address = name.strip(), address.strip()
    if project is None:
        flash(request, "That project no longer exists.", "error")
        return _redirect("/projects")
    if not name or not address:
        flash(request, "Project name and address or location are required.", "error")
        return _redirect("/projects")
    description = description.strip()
    if len(description) > MAX_DESCRIPTION_LENGTH:
        flash(request, f"Keep the project description under {MAX_DESCRIPTION_LENGTH} characters.", "error")
        return _redirect(f"/projects?project_id={project.id}")
    starts_on, ends_on, date_error = _optional_date_range(start_date, end_date)
    if date_error:
        flash(request, date_error, "error")
        return _redirect(f"/projects?project_id={project.id}")
    duplicate = db.scalar(
        select(Site).where(
            Site.id != project.id,
            func.lower(Site.name) == name.lower(),
        )
    )
    if duplicate:
        flash(request, f"“{name}” already exists.", "error")
        return _redirect("/projects")
    project.name = name
    project.customer_name = name
    project.address = address
    project.city = city.strip() or None
    project.contact_person = contact_person.strip() or None
    project.contact_number = contact_number.strip() or None
    project.description = description or None
    project.start_date = starts_on
    project.end_date = ends_on
    project.updated_at = utcnow()
    db.commit()
    flash(request, f"Project “{project.name}” updated. Existing records keep their original details.")
    return _redirect("/projects")


@router.post("/projects/{project_id}/sub-projects")
def create_sub_project(
    project_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "projects.edit")
    if not project_access_allowed(db, user, project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    back = f"/projects?project_id={project_id}"
    if (bad := _guard(request, csrf_token, back)):
        return bad
    project = db.get(Site, project_id)
    name, description = name.strip(), description.strip()
    if project is None:
        flash(request, "That Main Project no longer exists.", "error")
        return _redirect("/projects")
    if not name:
        flash(request, "Enter a Sub Project name.", "error")
        return _redirect(back)
    if len(name) > 160 or len(description) > MAX_DESCRIPTION_LENGTH:
        flash(request, "Keep the Sub Project name and description within their limits.", "error")
        return _redirect(back)
    duplicate = db.scalar(
        select(SubProject).where(
            SubProject.project_id == project.id,
            func.lower(SubProject.name) == name.lower(),
        )
    )
    if duplicate:
        flash(request, f"Sub Project “{name}” already exists under this Main Project.", "error")
        return _redirect(back)
    db.add(SubProject(project_id=project.id, name=name, description=description or None))
    db.commit()
    flash(request, f"Sub Project “{name}” added.")
    return _redirect(back)


@router.post("/sub-projects/{sub_project_id}/edit")
def edit_sub_project(
    sub_project_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    sub_project = db.get(SubProject, sub_project_id)
    require_permission(request, db, user, "projects.edit")
    if sub_project and not project_access_allowed(db, user, sub_project.project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    back = f"/projects?project_id={sub_project.project_id}" if sub_project else "/projects"
    if (bad := _guard(request, csrf_token, back)):
        return bad
    name, description = name.strip(), description.strip()
    if sub_project is None:
        flash(request, "That Sub Project no longer exists.", "error")
        return _redirect("/projects")
    if not name or len(name) > 160 or len(description) > MAX_DESCRIPTION_LENGTH:
        flash(request, "Enter a valid Sub Project name and description.", "error")
        return _redirect(back)
    duplicate = db.scalar(
        select(SubProject).where(
            SubProject.project_id == sub_project.project_id,
            SubProject.id != sub_project.id,
            func.lower(SubProject.name) == name.lower(),
        )
    )
    if duplicate:
        flash(request, f"Sub Project “{name}” already exists under this Main Project.", "error")
        return _redirect(back)
    sub_project.name = name
    sub_project.description = description or None
    sub_project.updated_at = utcnow()
    db.commit()
    flash(request, f"Sub Project “{name}” updated.")
    return _redirect(back)


@router.post("/sub-projects/{sub_project_id}/toggle")
def toggle_sub_project(
    sub_project_id: int,
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    sub_project = db.get(SubProject, sub_project_id)
    require_permission(request, db, user, "projects.edit")
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    if sub_project and not project_access_allowed(db, user, sub_project.project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    back = f"/projects?project_id={sub_project.project_id}" if sub_project else "/projects"
    if (bad := _guard(request, csrf_token, back)):
        return bad
    if sub_project is None:
        flash(request, "That Sub Project no longer exists.", "error")
        return _redirect("/projects")
    sub_project.is_active = not sub_project.is_active
    sub_project.updated_at = utcnow()
    db.commit()
    flash(request, f"Sub Project “{sub_project.name}” {'activated' if sub_project.is_active else 'deactivated'}.")
    return _redirect(back)


@router.post("/sub-projects/{sub_project_id}/delete")
def delete_sub_project(
    sub_project_id: int,
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    sub_project = db.get(SubProject, sub_project_id)
    require_permission(request, db, user, "projects.edit")
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    if sub_project and not project_access_allowed(db, user, sub_project.project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    back = f"/projects?project_id={sub_project.project_id}" if sub_project else "/projects"
    if (bad := _guard(request, csrf_token, back)):
        return bad
    if sub_project is None:
        flash(request, "That Sub Project no longer exists.", "error")
        return _redirect("/projects")
    name = sub_project.name
    outcome = _delete_or_deactivate(db, SubProject, sub_project_id)
    flash(
        request,
        f"Sub Project “{name}” {'permanently deleted' if outcome == 'deleted' else 'deactivated because it is referenced by history'}.",
    )
    return _redirect(back)


@router.post("/sub-projects/{sub_project_id}/sites")
async def assign_sub_project_sites(
    sub_project_id: int,
    request: Request,
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    sub_project = db.get(SubProject, sub_project_id)
    require_permission(request, db, user, "projects.edit")
    if sub_project and not project_access_allowed(db, user, sub_project.project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    back = f"/projects?project_id={sub_project.project_id}" if sub_project else "/projects"
    form = await request.form()
    if (bad := _guard(request, str(form.get("csrf_token") or ""), back)):
        return bad
    if sub_project is None:
        flash(request, "That Sub Project no longer exists.", "error")
        return _redirect("/projects")
    submitted_ids = {entity_id(value) for value in form.getlist("site_ids")}
    if None in submitted_ids:
        flash(request, "Choose valid Sites.", "error")
        return _redirect(back)
    site_ids = {int(value) for value in submitted_ids}
    valid_ids = set(db.scalars(select(WorkSite.id).where(WorkSite.id.in_(site_ids)))) if site_ids else set()
    if valid_ids != site_ids:
        flash(request, "One or more selected Sites no longer exist.", "error")
        return _redirect(back)
    sub_project.site_assignments = [
        SubProjectSite(site_id=site_id) for site_id in sorted(site_ids)
    ]
    sub_project.updated_at = utcnow()
    db.commit()
    flash(request, f"Sites assigned to Sub Project “{sub_project.name}”.")
    return _redirect(back)


@router.post("/projects/{project_id}/toggle")
def toggle_project(
    project_id: int,
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "projects.edit")
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    if not project_access_allowed(db, user, project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    if (bad := _guard(request, csrf_token, "/projects")):
        return bad
    project = db.get(Site, project_id)
    if project is None:
        flash(request, "That project no longer exists.", "error")
        return _redirect("/projects")
    project.is_active = not project.is_active
    project.updated_at = utcnow()
    db.commit()
    flash(
        request,
        f"Project “{project.name}” {'activated' if project.is_active else 'deactivated'}.",
    )
    return _redirect("/projects")


@router.post("/projects/{project_id}/delete")
def delete_project(
    project_id: int,
    request: Request,
    csrf_token: str = Form(""),
    user: User = Depends(require_catalog_manager),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "projects.edit")
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    if not project_access_allowed(db, user, project_id, module_key="projects"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Project access denied")
    if (bad := _guard(request, csrf_token, "/projects")):
        return bad
    project = db.get(Site, project_id)
    if project is None:
        flash(request, "That Project no longer exists.", "error")
        return _redirect("/projects")
    name = project.name
    outcome = _delete_or_deactivate(db, Site, project_id)
    if outcome == "deleted":
        flash(request, f"Project “{name}” permanently deleted.")
    else:
        flash(
            request,
            f"Project “{name}” is referenced by history and was deactivated instead.",
        )
    return _redirect("/projects")


# ------------------------------------------------------------------ sites


@router.get("/sites", dependencies=[Depends(require_admin)])
def work_sites_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    stmt = select(WorkSite).order_by(WorkSite.is_active.desc(), WorkSite.name)
    term = q.strip()
    if term:
        stmt = stmt.where(WorkSite.name.ilike(f"%{term}%"))
    sites = list(db.scalars(stmt))
    usage = {
        row[0]: int(row[1])
        for row in db.execute(
            select(InstallationRecordSite.site_id, func.count()).group_by(
                InstallationRecordSite.site_id
            )
        ).all()
    }
    return render(
        request,
        "work_sites.html",
        {
            "active_nav": "sites",
            "sites": sites,
            "q": term,
            "usage": usage,
        },
    )


@router.post("/sites", dependencies=[Depends(require_admin)])
def create_work_site(
    request: Request,
    name: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/sites")):
        return bad
    name = name.strip()
    if not name:
        flash(request, "Enter a site name.", "error")
        return _redirect("/sites")
    if db.scalar(select(WorkSite).where(func.lower(WorkSite.name) == name.lower())):
        flash(request, f"“{name}” already exists.", "error")
        return _redirect("/sites")
    db.add(WorkSite(name=name))
    db.commit()
    flash(request, f"Site “{name}” added.")
    return _redirect("/sites")


@router.post("/sites/{site_id}/edit", dependencies=[Depends(require_admin)])
def edit_work_site(
    site_id: int,
    request: Request,
    name: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/sites")):
        return bad
    site = db.get(WorkSite, site_id)
    name = name.strip()
    if site is None or not name:
        flash(request, "Enter a valid site name.", "error")
        return _redirect("/sites")
    duplicate = db.scalar(
        select(WorkSite).where(
            WorkSite.id != site.id,
            func.lower(WorkSite.name) == name.lower(),
        )
    )
    if duplicate:
        flash(request, f"“{name}” already exists.", "error")
        return _redirect("/sites")
    site.name = name
    site.updated_at = utcnow()
    db.commit()
    flash(request, f"Site “{site.name}” updated. Existing records keep their original name.")
    return _redirect("/sites")


@router.post(
    "/sites/{site_id}/toggle",
    dependencies=[Depends(require_admin)],
)
def toggle_work_site(
    site_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/sites")):
        return bad
    site = db.get(WorkSite, site_id)
    if site is None:
        flash(request, "That site no longer exists.", "error")
        return _redirect("/sites")
    site.is_active = not site.is_active
    site.updated_at = utcnow()
    db.commit()
    flash(request, f"Site “{site.name}” {'activated' if site.is_active else 'deactivated'}.")
    return _redirect("/sites")


@router.post(
    "/sites/{site_id}/delete",
    dependencies=[Depends(require_admin)],
)
def delete_work_site(
    site_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/sites")):
        return bad
    site = db.get(WorkSite, site_id)
    if site is None:
        flash(request, "That Site no longer exists.", "error")
        return _redirect("/sites")
    name = site.name
    outcome = _delete_or_deactivate(db, WorkSite, site_id)
    if outcome == "deleted":
        flash(request, f"Site “{name}” permanently deleted.")
    else:
        flash(
            request,
            f"Site “{name}” is referenced by history and was deactivated instead.",
        )
    return _redirect("/sites")


# ---------------------------------------------------------- service types


@router.get("/service-types", dependencies=[Depends(require_admin)])
def services_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    stmt = select(ServiceType).order_by(ServiceType.is_active.desc(), ServiceType.name)
    term = q.strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(or_(ServiceType.name.ilike(like), ServiceType.description.ilike(like)))
    services = list(db.scalars(stmt))
    usage = {
        row[0]: int(row[1])
        for row in db.execute(
            select(MaintenanceRecord.service_type_id, func.count()).group_by(
                MaintenanceRecord.service_type_id
            )
        ).all()
    }
    return render(
        request,
        "service_types.html",
        {"active_nav": "services", "services": services, "q": term, "usage": usage},
    )


@router.post("/service-types", dependencies=[Depends(require_admin)])
def create_service(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/service-types")):
        return bad

    name = name.strip()
    if not name:
        flash(request, "Enter a service name.", "error")
        return _redirect("/service-types")

    if db.scalar(select(ServiceType).where(func.lower(ServiceType.name) == name.lower())):
        flash(request, f"“{name}” already exists.", "error")
        return _redirect("/service-types")

    db.add(ServiceType(name=name, description=description.strip() or None))
    db.commit()
    flash(request, f"Service “{name}” added.")
    return _redirect("/service-types")


@router.post("/service-types/{service_id}/edit", dependencies=[Depends(require_admin)])
def edit_service(
    service_id: int,
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/service-types")):
        return bad
    service = db.get(ServiceType, service_id)
    if service is None or not name.strip():
        flash(request, "Enter a valid service name.", "error")
        return _redirect("/service-types")
    service.name = name.strip()
    service.description = description.strip() or None
    service.updated_at = utcnow()
    db.commit()
    flash(request, f"Service “{service.name}” updated. Existing records keep their original name.")
    return _redirect("/service-types")


@router.post(
    "/service-types/{service_id}/toggle",
    dependencies=[Depends(require_admin)],
)
def toggle_service(
    service_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/service-types")):
        return bad
    service = db.get(ServiceType, service_id)
    if service is None:
        flash(request, "That service no longer exists.", "error")
        return _redirect("/service-types")
    service.is_active = not service.is_active
    service.updated_at = utcnow()
    db.commit()
    flash(request, f"Service “{service.name}” {'activated' if service.is_active else 'deactivated'}.")
    return _redirect("/service-types")


@router.post(
    "/service-types/{service_id}/delete",
    dependencies=[Depends(require_admin)],
)
def delete_service(
    service_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/service-types")):
        return bad
    service = db.get(ServiceType, service_id)
    if service is None:
        flash(request, "That Service Type no longer exists.", "error")
        return _redirect("/service-types")
    name = service.name
    outcome = _delete_or_deactivate(db, ServiceType, service_id)
    if outcome == "deleted":
        flash(request, f"Service Type “{name}” permanently deleted.")
    else:
        flash(
            request,
            f"Service Type “{name}” is referenced by history and was deactivated instead.",
        )
    return _redirect("/service-types")


# ---------------------------------------------------------------- devices


@router.get("/devices", dependencies=[Depends(require_admin)])
def devices_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    return _redirect("/pricing/items")
    stmt = select(DeviceCatalog).order_by(
        DeviceCatalog.is_active.desc(), DeviceCatalog.name, DeviceCatalog.model
    )
    term = q.strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                DeviceCatalog.name.ilike(like),
                DeviceCatalog.manufacturer.ilike(like),
                DeviceCatalog.model.ilike(like),
                DeviceCatalog.description.ilike(like),
            )
        )
    devices = list(db.scalars(stmt))
    usage = {
        row[0]: int(row[1])
        for row in db.execute(
            select(InstalledDevice.device_id, func.count()).group_by(
                InstalledDevice.device_id
            )
        ).all()
    }
    return render(
        request,
        "devices.html",
        {
            "active_nav": "devices",
            "devices": devices,
            "q": term,
            "usage": usage,
        },
    )


@router.post("/devices", dependencies=[Depends(require_admin)])
def create_device(
    request: Request,
    name: str = Form(""),
    manufacturer: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/devices")):
        return bad
    flash(request, "Create and manage service equipment from Pricing Items.")
    return _redirect("/pricing/items")
    name, model = name.strip(), model.strip()
    if not name or not model:
        flash(request, "Device name and model are required.", "error")
        return _redirect("/devices")
    exists = db.scalar(
        select(DeviceCatalog).where(
            func.lower(DeviceCatalog.name) == name.lower(),
            func.lower(DeviceCatalog.model) == model.lower(),
        )
    )
    if exists:
        flash(request, f"“{name} — {model}” already exists.", "error")
        return _redirect("/devices")
    db.add(
        DeviceCatalog(
            name=name,
            manufacturer=manufacturer.strip() or None,
            model=model,
            description=description.strip() or None,
        )
    )
    db.commit()
    flash(request, f"Device “{name} — {model}” added.")
    return _redirect("/devices")


@router.post("/devices/{device_id}/edit", dependencies=[Depends(require_admin)])
def edit_device(
    device_id: int,
    request: Request,
    name: str = Form(""),
    manufacturer: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/devices")):
        return bad
    flash(request, "Create and manage service equipment from Pricing Items.")
    return _redirect("/pricing/items")
    device = db.get(DeviceCatalog, device_id)
    name, model = name.strip(), model.strip()
    if device is None or not name or not model:
        flash(request, "Enter a valid device name and model.", "error")
        return _redirect("/devices")
    exists = db.scalar(
        select(DeviceCatalog).where(
            DeviceCatalog.id != device.id,
            func.lower(DeviceCatalog.name) == name.lower(),
            func.lower(DeviceCatalog.model) == model.lower(),
        )
    )
    if exists:
        flash(request, f"“{name} — {model}” already exists.", "error")
        return _redirect("/devices")
    device.name = name
    device.manufacturer = manufacturer.strip() or None
    device.model = model
    device.description = description.strip() or None
    device.updated_at = utcnow()
    db.commit()
    flash(request, f"Device “{device.display_label}” updated. Existing records keep their snapshots.")
    return _redirect("/devices")


@router.post(
    "/devices/{device_id}/toggle",
    dependencies=[Depends(require_admin)],
)
def toggle_device(
    device_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/devices")):
        return bad
    flash(request, "Activate or deactivate service equipment from Pricing Items.")
    return _redirect("/pricing/items")
    device = db.get(DeviceCatalog, device_id)
    if device is None:
        flash(request, "That device no longer exists.", "error")
        return _redirect("/devices")
    device.is_active = not device.is_active
    device.updated_at = utcnow()
    db.commit()
    flash(
        request,
        f"Device “{device.display_label}” {'activated' if device.is_active else 'deactivated'}.",
    )
    return _redirect("/devices")


@router.post(
    "/devices/{device_id}/delete",
    dependencies=[Depends(require_admin)],
)
def delete_device(
    device_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/devices")):
        return bad
    flash(request, "Delete service equipment from Pricing Items.")
    return _redirect("/pricing/items")
    device = db.get(DeviceCatalog, device_id)
    if device is None:
        flash(request, "That Device no longer exists.", "error")
        return _redirect("/devices")
    label = device.display_label
    outcome = _delete_or_deactivate(db, DeviceCatalog, device_id)
    if outcome == "deleted":
        flash(request, f"Device “{label}” permanently deleted.")
    else:
        flash(
            request,
            f"Device “{label}” is referenced by history and was deactivated instead.",
        )
    return _redirect("/devices")


# ------------------------------------------------------------------ users


@router.get("/users", dependencies=[Depends(require_admin)])
def users_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    stmt = select(User).order_by(User.is_active.desc(), User.full_name)
    term = q.strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.username.ilike(like)))
    users = list(db.scalars(stmt))
    recovery_contacts = {
        contact.user_id: contact
        for contact in db.scalars(select(AdminRecoveryContact))
    }
    usage = {
        row[0]: int(row[1])
        for row in db.execute(
            select(MaintenanceRecord.submitted_by_id, func.count()).group_by(
                MaintenanceRecord.submitted_by_id
            )
        ).all()
    }
    return render(
        request,
        "users.html",
        {
            "active_nav": "users",
            "users": users,
            "projects": list(db.scalars(select(Site).order_by(Site.name))),
            "q": term,
            "usage": usage,
            "recovery_contacts": recovery_contacts,
            "departments": list(db.scalars(select(Department).where(Department.is_active.is_(True)).order_by(Department.name))),
        },
    )


@router.post("/users", dependencies=[Depends(require_admin)])
def create_user(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form(UserRole.TECHNICAL.value),
    email: str = Form(""),
    department_ids: list[str] = Form(default=[]),
    primary_department_id: str = Form(""),
    project_ids: list[str] = Form(default=[]),
    pricing_access: str = Form(""),
    technical_documents_manage: str = Form(""),
    wiring_diagrams_manage: str = Form(""),
    store_access: str = Form(""),
    store_receive: str = Form(""),
    store_issue: str = Form(""),
    store_transfer: str = Form(""),
    store_custody_transfer: str = Form(""),
    store_manage_items: str = Form(""),
    store_manage_warehouses: str = Form(""),
    store_adjust: str = Form(""),
    store_reports: str = Form(""),
    phone: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/users")):
        return bad

    full_name, username = full_name.strip(), username.strip()
    if not full_name or not username:
        flash(request, "Full name and email or username are required.", "error")
        return _redirect("/users")
    if len(password) < MIN_PASSWORD_LENGTH:
        flash(request, f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.", "error")
        return _redirect("/users")
    try:
        role_value = UserRole(role)
    except ValueError:
        flash(request, "Pick a valid user type.", "error")
        return _redirect("/users")
    selected_project_ids = {
        parsed
        for project_id in project_ids
        if (parsed := entity_id(project_id)) is not None
    }
    selected_projects = list(
        db.scalars(select(Site).where(Site.id.in_(selected_project_ids)))
    )
    if len(selected_projects) != len(selected_project_ids):
        flash(request, "One of the selected Projects no longer exists.", "error")
        return _redirect("/users")
    if role_value == UserRole.CUSTOMER and not selected_projects:
        flash(request, "Assign at least one Project to a Customer.", "error")
        return _redirect("/users")
    if db.scalar(select(User).where(func.lower(User.username) == username.lower())):
        flash(request, f"“{username}” is already taken.", "error")
        return _redirect("/users")
    clean_email = email.strip().lower()
    if clean_email and not valid_email(clean_email):
        flash(request, "Enter a valid email address.", "error")
        return _redirect("/users")
    if clean_email and db.scalar(select(User.id).where(func.lower(User.email) == clean_email)):
        flash(request, "That email address is already in use.", "error")
        return _redirect("/users")
    selected_department_ids = {
        parsed for value in department_ids if (parsed := entity_id(value)) is not None
    }
    if role_value != UserRole.CUSTOMER:
        valid_department_ids = set(
            db.scalars(
                select(Department.id).where(
                    Department.id.in_(selected_department_ids), Department.is_active.is_(True)
                )
            )
        )
        if not valid_department_ids:
            flash(request, "Choose at least one active Department for this user.", "error")
            return _redirect("/users")
        parsed_primary_id = entity_id(primary_department_id)
        primary_id = parsed_primary_id if parsed_primary_id in valid_department_ids else min(valid_department_ids)
    else:
        valid_department_ids, primary_id = set(), None

    new_user = User(
        full_name=full_name,
        username=username,
        password_hash=hash_password(password),
        role=role_value,
        phone=phone.strip() or None,
        email=clean_email or None,
        pricing_access=(
            pricing_access == "1" and role_value == UserRole.TECHNICAL
        ),
        technical_documents_manage=technical_documents_manage == "1" and role_value == UserRole.TECHNICAL,
        wiring_diagrams_manage=wiring_diagrams_manage == "1" and role_value == UserRole.TECHNICAL,
        store_access=store_access == "1" and role_value == UserRole.TECHNICAL,
        store_receive=store_receive == "1" and role_value == UserRole.TECHNICAL,
        store_issue=store_issue == "1" and role_value == UserRole.TECHNICAL,
        store_transfer=store_transfer == "1" and role_value == UserRole.TECHNICAL,
        store_custody_transfer=store_custody_transfer == "1" and role_value == UserRole.TECHNICAL,
        store_manage_items=store_manage_items == "1" and role_value == UserRole.TECHNICAL,
        store_manage_warehouses=store_manage_warehouses == "1" and role_value == UserRole.TECHNICAL,
        store_adjust=store_adjust == "1" and role_value == UserRole.TECHNICAL,
        store_reports=store_reports == "1" and role_value == UserRole.TECHNICAL,
    )
    if role_value == UserRole.CUSTOMER:
        new_user.customer_project_assignments = [
            CustomerProjectAssignment(project=project)
            for project in selected_projects
        ]
    db.add(new_user)
    db.flush()
    for department_id in valid_department_ids:
        db.add(
            UserDepartment(
                user_id=new_user.id,
                department_id=department_id,
                is_primary=department_id == primary_id,
            )
        )
    db.commit()
    flash(request, f"{role_value.label} “{full_name}” created. Set the user's roles and permissions.")
    if role_value != UserRole.CUSTOMER:
        return _redirect(f"/users/{new_user.id}/access")
    return _redirect("/users")


@router.post(
    "/users/{user_id}/recovery-email",
    dependencies=[Depends(require_admin)],
)
def set_recovery_email(
    user_id: int,
    request: Request,
    recovery_email: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/users")):
        return bad
    target = db.get(User, user_id)
    if target is None:
        flash(request, "That user no longer exists.", "error")
        return _redirect("/users")
    if target.role != UserRole.ADMIN:
        flash(
            request,
            "Recovery email is available only for Administrator accounts.",
            "error",
        )
        return _redirect("/users")
    email = recovery_email.strip().lower()
    if not valid_email(email):
        flash(request, "Enter a valid recovery email address.", "error")
        return _redirect("/users")
    clash = db.scalar(
        select(AdminRecoveryContact).where(
            func.lower(AdminRecoveryContact.email) == email,
            AdminRecoveryContact.user_id != target.id,
        )
    )
    if clash:
        flash(request, "That recovery email is already registered.", "error")
        return _redirect("/users")

    contact = db.get(AdminRecoveryContact, target.id)
    if contact is None:
        contact = AdminRecoveryContact(user_id=target.id, email=email)
        db.add(contact)
    elif contact.email.lower() != email:
        contact.email = email
        contact.verified_at = None
    contact.updated_at = utcnow()
    token = issue_token(db, target.id, VERIFY_PURPOSE, VERIFY_LIFETIME)
    db.commit()
    try:
        send_verification_email(email, token)
    except MailDeliveryError:
        flash(
            request,
            "Recovery email saved but verification could not be sent. "
            "Configure SMTP and send it again.",
            "error",
        )
        return _redirect("/users")
    flash(request, f"Verification link sent to {email}.")
    return _redirect("/users")


@router.post("/users/{user_id}/edit", dependencies=[Depends(require_admin)])
def edit_user(
    user_id: int,
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    email: str = Form(""),
    role: str = Form(""),
    project_ids: list[str] = Form(default=[]),
    pricing_access: str = Form(""),
    technical_documents_manage: str = Form(""),
    wiring_diagrams_manage: str = Form(""),
    store_access: str = Form(""),
    store_receive: str = Form(""),
    store_issue: str = Form(""),
    store_transfer: str = Form(""),
    store_custody_transfer: str = Form(""),
    store_manage_items: str = Form(""),
    store_manage_warehouses: str = Form(""),
    store_adjust: str = Form(""),
    store_reports: str = Form(""),
    phone: str = Form(""),
    admin: User = Depends(require_admin),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/users")):
        return bad
    target = db.get(User, user_id)
    if target is None:
        flash(request, "That user no longer exists.", "error")
        return _redirect("/users")
    if not full_name.strip() or not username.strip():
        flash(request, "Full name and email or username are required.", "error")
        return _redirect("/users")
    clash = db.scalar(
        select(User).where(
            func.lower(User.username) == username.strip().lower(), User.id != user_id
        )
    )
    if clash:
        flash(request, f"“{username.strip()}” is already taken.", "error")
        return _redirect("/users")
    clean_email = email.strip().lower()
    if clean_email and not valid_email(clean_email):
        flash(request, "Enter a valid email address.", "error")
        return _redirect("/users")
    email_clash = db.scalar(
        select(User.id).where(func.lower(User.email) == clean_email, User.id != target.id)
    ) if clean_email else None
    if email_clash:
        flash(request, "That email address is already in use.", "error")
        return _redirect("/users")

    try:
        role_value = UserRole(role)
    except ValueError:
        flash(request, "Pick a valid user type.", "error")
        return _redirect("/users")
    if target.id == admin.id and role_value != UserRole.ADMIN:
        flash(request, "You cannot change your own Administrator role.", "error")
        return _redirect("/users")
    selected_project_ids = {
        parsed
        for project_id in project_ids
        if (parsed := entity_id(project_id)) is not None
    }
    selected_projects = list(
        db.scalars(select(Site).where(Site.id.in_(selected_project_ids)))
    )
    if len(selected_projects) != len(selected_project_ids):
        flash(request, "One of the selected Projects no longer exists.", "error")
        return _redirect("/users")
    if role_value == UserRole.CUSTOMER and not selected_projects:
        flash(request, "Assign at least one Project to a Customer.", "error")
        return _redirect("/users")

    target.full_name = full_name.strip()
    target.username = username.strip()
    target.phone = phone.strip() or None
    target.email = clean_email or None
    target.role = role_value
    target.pricing_access = (
        pricing_access == "1" and role_value == UserRole.TECHNICAL
    )
    target.technical_documents_manage = technical_documents_manage == "1" and role_value == UserRole.TECHNICAL
    target.wiring_diagrams_manage = wiring_diagrams_manage == "1" and role_value == UserRole.TECHNICAL
    target.store_access = store_access == "1" and role_value == UserRole.TECHNICAL
    target.store_receive = store_receive == "1" and role_value == UserRole.TECHNICAL
    target.store_issue = store_issue == "1" and role_value == UserRole.TECHNICAL
    target.store_transfer = store_transfer == "1" and role_value == UserRole.TECHNICAL
    target.store_custody_transfer = store_custody_transfer == "1" and role_value == UserRole.TECHNICAL
    target.store_manage_items = store_manage_items == "1" and role_value == UserRole.TECHNICAL
    target.store_manage_warehouses = store_manage_warehouses == "1" and role_value == UserRole.TECHNICAL
    target.store_adjust = store_adjust == "1" and role_value == UserRole.TECHNICAL
    target.store_reports = store_reports == "1" and role_value == UserRole.TECHNICAL
    target.customer_project_assignments.clear()
    db.flush()
    if role_value == UserRole.CUSTOMER:
        target.customer_project_assignments.extend(
            [
            CustomerProjectAssignment(project=project)
            for project in selected_projects
            ]
        )
    target.updated_at = utcnow()
    db.commit()
    flash(request, f"{target.full_name} updated. Past records keep the name used at submission.")
    return _redirect("/users")


@router.post("/users/{user_id}/toggle")
def toggle_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/users")):
        return bad
    target = db.get(User, user_id)
    if target is None:
        flash(request, "That user no longer exists.", "error")
        return _redirect("/users")
    if target.id == admin.id:
        flash(request, "You cannot deactivate your own account.", "error")
        return _redirect("/users")
    target.is_active = not target.is_active
    target.updated_at = utcnow()
    db.commit()
    flash(request, f"{target.full_name} {'activated' if target.is_active else 'deactivated'}.")
    return _redirect("/users")


@router.post(
    "/users/{user_id}/delete",
    dependencies=[Depends(require_admin)],
)
def delete_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/users")):
        return bad
    target = db.get(User, user_id)
    if target is None:
        flash(request, "That user no longer exists.", "error")
        return _redirect("/users")
    if target.id == admin.id:
        flash(request, "You cannot delete your own account.", "error")
        return _redirect("/users")
    name = target.full_name
    outcome = _delete_or_deactivate(db, User, user_id)
    if outcome == "deleted":
        flash(request, f"User “{name}” permanently deleted.")
    else:
        flash(
            request,
            f"User “{name}” is referenced by records and was deactivated instead.",
        )
    return _redirect("/users")


@router.post(
    "/users/{user_id}/reset-password",
    dependencies=[Depends(require_admin)],
)
def reset_password(
    user_id: int,
    request: Request,
    password: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/users")):
        return bad
    target = db.get(User, user_id)
    if target is None:
        flash(request, "That user no longer exists.", "error")
        return _redirect("/users")
    if len(password) < MIN_PASSWORD_LENGTH:
        flash(request, f"Passwords need at least {MIN_PASSWORD_LENGTH} characters.", "error")
        return _redirect("/users")
    target.password_hash = hash_password(password)
    target.updated_at = utcnow()
    bump_auth_version(db, target.id)
    db.commit()
    flash(request, f"Password reset for {target.full_name}.")
    return _redirect("/users")
