"""Administrator pages: sites, service types and users.

Nothing here is reachable without require_admin — hiding nav links is cosmetic,
the dependency is the actual control.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..account_recovery import (
    VERIFY_LIFETIME,
    VERIFY_PURPOSE,
    MailDeliveryError,
    bump_auth_version,
    issue_token,
    send_verification_email,
    valid_email,
)
from ..database import get_db
from ..deps import require_admin, require_catalog_manager
from ..helpers import entity_id, flash, render
from ..models import (
    CustomerProjectAssignment,
    AdminRecoveryContact,
    DeviceCatalog,
    InstalledDevice,
    InstallationRecordSite,
    MaintenanceRecord,
    ServiceType,
    Site,
    User,
    UserRole,
    WorkSite,
    utcnow,
)
from ..security import csrf_valid, hash_password

router = APIRouter(dependencies=[Depends(require_catalog_manager)])

MIN_PASSWORD_LENGTH = 8


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


# ------------------------------------------------------------------ sites


@router.get("/_legacy/sites")
def sites_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    return _redirect("/projects")


# --------------------------------------------------------------- projects


@router.get("/projects")
def projects_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    stmt = select(Site).order_by(Site.is_active.desc(), Site.name)
    term = q.strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                Site.name.ilike(like),
                Site.city.ilike(like),
                Site.address.ilike(like),
                Site.contact_person.ilike(like),
                Site.contact_number.ilike(like),
            )
        )
    projects = list(db.scalars(stmt))
    usage = {
        row[0]: int(row[1])
        for row in db.execute(
            select(MaintenanceRecord.site_id, func.count()).group_by(
                MaintenanceRecord.site_id
            )
        ).all()
    }
    return render(
        request,
        "projects.html",
        {
            "active_nav": "projects",
            "projects": projects,
            "q": term,
            "usage": usage,
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
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    if (bad := _guard(request, csrf_token, "/projects")):
        return bad
    name, address = name.strip(), address.strip()
    if not name or not address:
        flash(request, "Project name and address or location are required.", "error")
        return _redirect("/projects")
    if db.scalar(select(Site).where(func.lower(Site.name) == name.lower())):
        flash(request, f"“{name}” already exists.", "error")
        return _redirect("/projects")
    db.add(
        Site(
            name=name,
            customer_name=name,
            address=address,
            city=city.strip() or None,
            contact_person=contact_person.strip() or None,
            contact_number=contact_number.strip() or None,
        )
    )
    db.commit()
    flash(request, f"Project “{name}” added.")
    return _redirect("/projects")


@router.post("/projects/{project_id}/edit")
def edit_project(
    project_id: int,
    request: Request,
    name: str = Form(""),
    address: str = Form(""),
    city: str = Form(""),
    contact_person: str = Form(""),
    contact_number: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
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
    project.updated_at = utcnow()
    db.commit()
    flash(request, f"Project “{project.name}” updated. Existing records keep their original details.")
    return _redirect("/projects")


@router.post(
    "/projects/{project_id}/toggle",
    dependencies=[Depends(require_admin)],
)
def toggle_project(
    project_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
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


@router.post(
    "/projects/{project_id}/delete",
    dependencies=[Depends(require_admin)],
)
def delete_project(
    project_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
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


@router.get("/sites")
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


@router.post("/sites")
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


@router.post("/sites/{site_id}/edit")
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


@router.get("/service-types")
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


@router.post("/service-types")
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


@router.post("/service-types/{service_id}/edit")
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


@router.get("/devices")
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


@router.post("/devices")
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


@router.post("/devices/{device_id}/edit")
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
        },
    )


@router.post("/users", dependencies=[Depends(require_admin)])
def create_user(
    request: Request,
    full_name: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form(UserRole.TECHNICAL.value),
    project_ids: list[str] = Form(default=[]),
    pricing_access: str = Form(""),
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

    new_user = User(
        full_name=full_name,
        username=username,
        password_hash=hash_password(password),
        role=role_value,
        phone=phone.strip() or None,
        pricing_access=(
            pricing_access == "1" and role_value == UserRole.TECHNICAL
        ),
    )
    if role_value == UserRole.CUSTOMER:
        new_user.customer_project_assignments = [
            CustomerProjectAssignment(project=project)
            for project in selected_projects
        ]
    db.add(new_user)
    db.commit()
    flash(request, f"{role_value.label} “{full_name}” created.")
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
    role: str = Form(""),
    project_ids: list[str] = Form(default=[]),
    pricing_access: str = Form(""),
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
    target.role = role_value
    target.pricing_access = (
        pricing_access == "1" and role_value == UserRole.TECHNICAL
    )
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
