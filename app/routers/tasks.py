"""Department task board and notification centre."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..access_control import module_scope, permission_allowed, require_permission, set_active_department
from ..audit import set_audit_context
from ..counters import allocate_year_sequence
from ..database import get_db
from ..deps import get_current_user
from ..helpers import entity_id, flash, render, to_display, to_utc_from_display
from ..models import (
    ProjectTeamMember,
    Site,
    TaskPriority,
    TaskStatus,
    User,
    UserDepartment,
    UserNotification,
    WorkTask,
    WorkTaskComment,
    WorkTaskCounter,
    utcnow,
)
from ..notifications import create_notification, deliver_notification_email
from ..security import csrf_valid


router = APIRouter()


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _task_number(db: Session) -> str:
    year = to_display(utcnow()).year
    sequence = allocate_year_sequence(db, WorkTaskCounter, year)
    return f"TASK-{year}-{sequence:05d}"


def _parse_due(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        return to_utc_from_display(datetime.fromisoformat(value.strip()))
    except ValueError as exc:
        raise ValueError("Enter a valid due date and time.") from exc


def _load_task(db: Session, task_id: int) -> WorkTask:
    task = db.scalar(
        select(WorkTask)
        .where(WorkTask.id == task_id)
        .options(selectinload(WorkTask.comments))
    )
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


def _can_view_task(db: Session, user: User, task: WorkTask) -> bool:
    if not permission_allowed(db, user, task.department_id, "tasks.view"):
        return False
    if user.is_admin or user.id in {task.assigned_to_id, task.created_by_id}:
        return True
    scope = module_scope(user, "tasks")
    if scope.value == "department":
        return True
    return scope.value == "selected" and task.project_id in (
        db.info.get("project_ids_by_module", {}).get("tasks", set())
    )


def _can_assign_task(db: Session, user: User, task: WorkTask) -> bool:
    return user.is_admin or permission_allowed(db, user, task.department_id, "tasks.assign") or permission_allowed(
        db, user, task.department_id, "tasks.manage"
    )


def _task_assignment_choices(db: Session, task: WorkTask) -> tuple[list[User], list[Site]]:
    members = list(
        db.scalars(
            select(User)
            .join(UserDepartment, UserDepartment.user_id == User.id)
            .where(UserDepartment.department_id == task.department_id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )
    member_ids = [member.id for member in members]
    projects = list(
        db.scalars(
            select(Site)
            .join(ProjectTeamMember)
            .where(ProjectTeamMember.user_id.in_(member_ids))
            .distinct()
            .order_by(Site.name)
        )
    ) if member_ids else []
    return members, projects


@router.get("/tasks")
def task_list(
    request: Request,
    q: str = "",
    status_filter: str = "",
    view: str = "mine",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    department = require_permission(request, db, user, "tasks.view")
    statement = select(WorkTask).where(WorkTask.department_id == department.id)
    if not user.is_admin:
        scope = module_scope(user, "tasks")
        if scope.value == "department":
            if view == "mine":
                statement = statement.where(WorkTask.assigned_to_id == user.id)
        elif scope.value == "selected":
            statement = statement.where(or_(
                WorkTask.assigned_to_id == user.id,
                WorkTask.created_by_id == user.id,
                WorkTask.project_id.in_(request.state.project_ids["tasks"]),
            ))
        else:
            statement = statement.where(
                or_(WorkTask.assigned_to_id == user.id, WorkTask.created_by_id == user.id)
            )
    elif view == "mine":
        statement = statement.where(WorkTask.assigned_to_id == user.id)
    if q.strip():
        term = f"%{q.strip()}%"
        statement = statement.where(
            or_(WorkTask.task_number.ilike(term), WorkTask.title.ilike(term), WorkTask.assigned_to_name.ilike(term))
        )
    if status_filter:
        try:
            statement = statement.where(WorkTask.status == TaskStatus(status_filter))
        except ValueError:
            pass
    tasks = list(db.scalars(statement.order_by(WorkTask.created_at.desc())))
    return render(
        request,
        "tasks.html",
        {
            "active_nav": "tasks",
            "tasks": tasks,
            "q": q,
            "status_filter": status_filter,
            "view": view,
            "statuses": list(TaskStatus),
        },
    )


@router.get("/tasks/new")
def new_task(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    department = require_permission(request, db, user, "tasks.create")
    members = list(
        db.scalars(
            select(User)
            .join(UserDepartment, UserDepartment.user_id == User.id)
            .where(UserDepartment.department_id == department.id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
    )
    projects = list(db.scalars(
        select(Site)
        .where(Site.id.in_(request.state.project_ids["tasks"]))
        .order_by(Site.name)
    ))
    return render(
        request,
        "task_form.html",
        {"active_nav": "tasks", "members": members, "projects": projects, "priorities": list(TaskPriority)},
    )


@router.post("/tasks")
def create_task(
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    assigned_to_id: str = Form(""),
    project_id: str = Form(""),
    priority: str = Form(TaskPriority.NORMAL.value),
    due_at: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    department = require_permission(request, db, user, "tasks.create")
    if not csrf_valid(request, csrf_token):
        flash(request, "Your form expired. Try again.", "error")
        return _redirect("/tasks/new")
    assignee_id, selected_project_id = entity_id(assigned_to_id), entity_id(project_id)
    assignee = db.get(User, assignee_id) if assignee_id else None
    membership = db.get(UserDepartment, (assignee_id, department.id)) if assignee_id else None
    if not title.strip() or assignee is None or membership is None or not assignee.is_active:
        flash(request, "Enter a title and choose an active Department member.", "error")
        return _redirect("/tasks/new")
    project = db.get(Site, selected_project_id) if selected_project_id else None
    if selected_project_id and (
        project is None
        or db.get(ProjectTeamMember, (selected_project_id, assignee.id)) is None
        or (
            not user.is_admin
            and selected_project_id not in request.state.project_ids["tasks"]
        )
    ):
        flash(request, "The assignee must be a member of the selected Project team.", "error")
        return _redirect("/tasks/new")
    try:
        priority_value, due_value = TaskPriority(priority), _parse_due(due_at)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _redirect("/tasks/new")
    task = WorkTask(
        task_number=_task_number(db), department_id=department.id, project_id=project.id if project else None,
        title=title.strip(), description=description.strip() or None, priority=priority_value,
        assigned_to_id=assignee.id, assigned_to_name=assignee.full_name,
        created_by_id=user.id, created_by_name=user.full_name, due_at=due_value,
    )
    db.add(task)
    db.flush()
    notification = create_notification(
        db, user=assignee, kind="task_assigned", title=f"New task {task.task_number}",
        message=f"{user.full_name} assigned you: {task.title}", target_url=f"/tasks/{task.id}",
        department_id=department.id, task_id=task.id,
    )
    set_audit_context(
        request,
        action="task_created",
        entity_type="work_task",
        entity_id=task.id,
        entity_label=task.task_number,
        changes={"title": task.title, "assigned_to": assignee.full_name, "project": project.name if project else None},
    )
    db.commit()
    deliver_notification_email(db, notification, assignee)
    flash(request, f"Task {task.task_number} assigned to {assignee.full_name}.")
    return _redirect(f"/tasks/{task.id}")


@router.get("/tasks/{task_id}")
def task_detail(task_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = _load_task(db, task_id)
    if not _can_view_task(db, user, task):
        raise HTTPException(403, "Task access denied")
    set_active_department(request, db, user, task.department_id)
    members, projects = _task_assignment_choices(db, task) if _can_assign_task(db, user, task) else ([], [])
    return render(request, "task_detail.html", {
        "active_nav": "tasks", "task": task, "statuses": list(TaskStatus),
        "priorities": list(TaskPriority), "members": members, "projects": projects,
        "can_assign_task": _can_assign_task(db, user, task),
        "due_input": to_display(task.due_at).strftime("%Y-%m-%dT%H:%M") if task.due_at else "",
    })


@router.post("/tasks/{task_id}/assignment")
def update_task_assignment(
    task_id: int,
    request: Request,
    title: str = Form(""),
    description: str = Form(""),
    assigned_to_id: str = Form(""),
    project_id: str = Form(""),
    priority: str = Form(TaskPriority.NORMAL.value),
    due_at: str = Form(""),
    csrf_token: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)
    if not csrf_valid(request, csrf_token) or not _can_assign_task(db, user, task):
        raise HTTPException(403, "Task assignment denied")
    set_active_department(request, db, user, task.department_id)
    assignee_id, selected_project_id = entity_id(assigned_to_id), entity_id(project_id)
    assignee = db.get(User, assignee_id) if assignee_id else None
    membership = db.get(UserDepartment, (assignee_id, task.department_id)) if assignee_id else None
    if not title.strip() or assignee is None or membership is None or not assignee.is_active:
        flash(request, "Enter a title and choose an active Department member.", "error")
        return _redirect(f"/tasks/{task.id}")
    project = db.get(Site, selected_project_id) if selected_project_id else None
    if selected_project_id and (
        project is None
        or db.get(ProjectTeamMember, (selected_project_id, assignee.id)) is None
        or (
            not user.is_admin
            and selected_project_id not in request.state.project_ids["tasks"]
        )
    ):
        flash(request, "The assignee must be a member of the selected Project team.", "error")
        return _redirect(f"/tasks/{task.id}")
    try:
        priority_value, due_value = TaskPriority(priority), _parse_due(due_at)
    except ValueError as exc:
        flash(request, str(exc), "error")
        return _redirect(f"/tasks/{task.id}")
    previous = {
        "title": task.title,
        "assigned_to": task.assigned_to_name,
        "project": task.project.name if task.project else None,
        "priority": task.priority.value,
        "due_at": task.due_at,
    }
    reassigned = task.assigned_to_id != assignee.id
    task.title = title.strip()
    task.description = description.strip() or None
    task.assigned_to_id = assignee.id
    task.assigned_to_name = assignee.full_name
    task.project_id = project.id if project else None
    task.priority = priority_value
    task.due_at = due_value
    notification = None
    if reassigned:
        notification = create_notification(
            db, user=assignee, kind="task_reassigned", title=f"Task {task.task_number} assigned to you",
            message=f"{user.full_name} assigned you: {task.title}", target_url=f"/tasks/{task.id}",
            department_id=task.department_id, task_id=task.id,
        )
    set_audit_context(
        request,
        action="task_assignment_updated",
        entity_type="work_task",
        entity_id=task.id,
        entity_label=task.task_number,
        changes={"before": previous, "after": {
            "title": task.title, "assigned_to": assignee.full_name,
            "project": project.name if project else None, "priority": task.priority.value,
            "due_at": task.due_at,
        }},
    )
    db.commit()
    if notification is not None:
        deliver_notification_email(db, notification, assignee)
    flash(request, "Task assignment and schedule updated.")
    return _redirect(f"/tasks/{task.id}")


@router.post("/tasks/{task_id}/status")
def update_task_status(
    task_id: int, request: Request, status_value: str = Form(""), csrf_token: str = Form(""),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)
    if not csrf_valid(request, csrf_token) or not _can_view_task(db, user, task):
        raise HTTPException(403, "Task update denied")
    if user.id != task.assigned_to_id and not (user.is_admin or permission_allowed(db, user, task.department_id, "tasks.manage")):
        raise HTTPException(403, "Task update denied")
    try:
        new_status = TaskStatus(status_value)
    except ValueError:
        flash(request, "Choose a valid task status.", "error")
        return _redirect(f"/tasks/{task.id}")
    task.status = new_status
    if new_status == TaskStatus.IN_PROGRESS and task.started_at is None:
        task.started_at = utcnow()
    task.completed_at = utcnow() if new_status == TaskStatus.COMPLETED else None
    set_audit_context(
        request, action="task_status_updated", entity_type="work_task",
        entity_id=task.id, entity_label=task.task_number,
        changes={"status": new_status.value},
    )
    db.commit()
    flash(request, "Task status updated.")
    return _redirect(f"/tasks/{task.id}")


@router.post("/tasks/{task_id}/comments")
def add_comment(
    task_id: int, request: Request, body: str = Form(""), csrf_token: str = Form(""),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    task = _load_task(db, task_id)
    if not csrf_valid(request, csrf_token) or not _can_view_task(db, user, task):
        raise HTTPException(403, "Task access denied")
    if not body.strip():
        flash(request, "Enter a comment.", "error")
        return _redirect(f"/tasks/{task.id}")
    db.add(WorkTaskComment(task_id=task.id, author_id=user.id, author_name=user.full_name, body=body.strip()))
    recipient = task.assigned_to if user.id != task.assigned_to_id else task.created_by
    notification = create_notification(
        db, user=recipient, kind="task_comment", title=f"Comment on {task.task_number}",
        message=f"{user.full_name}: {body.strip()[:300]}", target_url=f"/tasks/{task.id}",
        department_id=task.department_id, task_id=task.id,
    )
    set_audit_context(
        request, action="task_comment_added", entity_type="work_task",
        entity_id=task.id, entity_label=task.task_number,
        changes={"comment": body.strip()[:500]},
    )
    db.commit()
    deliver_notification_email(db, notification, recipient)
    return _redirect(f"/tasks/{task.id}")


@router.get("/notifications")
def notifications_page(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notifications = list(
        db.scalars(
            select(UserNotification).where(UserNotification.user_id == user.id).order_by(UserNotification.created_at.desc()).limit(200)
        )
    )
    return render(request, "notifications.html", {"active_nav": "notifications", "notifications": notifications})


@router.post("/notifications/{notification_id}/read")
def read_notification(
    notification_id: int, request: Request, csrf_token: str = Form(""),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    if not csrf_valid(request, csrf_token):
        raise HTTPException(403, "Invalid form token")
    notification = db.get(UserNotification, notification_id)
    if notification is None or notification.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    if notification.department_id is not None and not user.is_customer:
        try:
            set_active_department(request, db, user, notification.department_id)
        except HTTPException:
            notification.is_read = True
            notification.read_at = utcnow()
            db.commit()
            flash(request, "That notification belongs to a Department you can no longer access.", "error")
            return _redirect("/notifications")
    notification.is_read = True
    notification.read_at = utcnow()
    db.commit()
    return _redirect(notification.target_url or "/notifications")
