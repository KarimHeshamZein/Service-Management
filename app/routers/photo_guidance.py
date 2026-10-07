"""Independent project-scoped photo guidance profiles."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..audit import set_audit_context
from ..database import get_db
from ..deps import require_admin, require_record_submitter
from ..helpers import entity_id, flash, render
from ..models import (
    ProjectPhotoGuidanceDescription,
    ProjectPhotoGuidanceRule,
    ProjectPhotoGuidanceSetting,
    Site,
    SubProject,
    SubProjectSite,
    User,
    utcnow,
)
from ..security import csrf_valid


router = APIRouter()
MAX_GUIDANCE_LENGTH = 1000
MAX_DESCRIPTIONS = 30


def _back(project_id: int) -> str:
    return f"/projects/{project_id}/photo-guidance"


def _project_or_404(db: Session, project_id: int) -> Site:
    project = db.get(Site, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _project_site_ids(db: Session, project_id: int) -> set[int]:
    return set(
        db.scalars(
            select(SubProjectSite.site_id)
            .join(SubProject, SubProject.id == SubProjectSite.sub_project_id)
            .where(SubProject.project_id == project_id)
        )
    )


def _description_lines(raw: str | list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    entries = raw if isinstance(raw, list) else [raw]
    for entry in entries:
        # Splitting each value keeps older clients that submit a multiline field
        # compatible with the newer one-input-per-description editor.
        for line in entry.splitlines():
            value = line.strip()
            key = value.casefold()
            if value and key not in seen:
                values.append(value)
                seen.add(key)
    return values


def _rule_snapshot(rule: ProjectPhotoGuidanceRule) -> dict:
    return {
        "name": rule.name,
        "before_alert": rule.before_alert,
        "after_alert": rule.after_alert,
        "before_descriptions": [
            entry.description for entry in rule.descriptions if entry.stage == "before"
        ],
        "after_descriptions": [
            entry.description for entry in rule.descriptions if entry.stage == "after"
        ],
    }


def _replace_descriptions(
    rule: ProjectPhotoGuidanceRule,
    before_options: list[str],
    after_options: list[str],
    db: Session,
) -> None:
    existing = {(entry.stage, entry.position): entry for entry in rule.descriptions}
    retained: list[ProjectPhotoGuidanceDescription] = []
    for stage, values in (("before", before_options), ("after", after_options)):
        for position, value in enumerate(values):
            entry = existing.pop((stage, position), None)
            if entry is None:
                entry = ProjectPhotoGuidanceDescription(
                    stage=stage,
                    position=position,
                )
            entry.description = value
            retained.append(entry)
    for entry in existing.values():
        db.delete(entry)
    rule.descriptions = retained


def _valid_rule_values(
    profile_name: str,
    before_alert: str,
    after_alert: str,
    before_descriptions: str | list[str],
    after_descriptions: str | list[str],
) -> tuple[str | None, str | None, str | None, list[str], list[str], str | None]:
    name = profile_name.strip()
    if not name:
        return None, None, None, [], [], "Enter a profile name."
    if len(name) > 160:
        return None, None, None, [], [], "Keep the profile name under 160 characters."
    before = before_alert.strip() or None
    after = after_alert.strip() or None
    before_options = _description_lines(before_descriptions)
    after_options = _description_lines(after_descriptions)
    all_text = [value for value in (before, after, *before_options, *after_options) if value]
    if any(len(value) > MAX_GUIDANCE_LENGTH for value in all_text):
        return None, None, None, [], [], f"Keep each alert or description under {MAX_GUIDANCE_LENGTH} characters."
    if len(before_options) > MAX_DESCRIPTIONS or len(after_options) > MAX_DESCRIPTIONS:
        return None, None, None, [], [], f"Keep each stage to {MAX_DESCRIPTIONS} standard descriptions or fewer."
    if not before and not after and not before_options and not after_options:
        return None, None, None, [], [], "Enter at least one alert or standard description."
    return name, before, after, before_options, after_options, None


@router.get("/projects/{project_id}/photo-guidance", dependencies=[Depends(require_admin)])
def photo_guidance_page(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    project = _project_or_404(db, project_id)
    rules = list(
        db.scalars(
            select(ProjectPhotoGuidanceRule)
            .options(
                selectinload(ProjectPhotoGuidanceRule.descriptions),
            )
            .where(ProjectPhotoGuidanceRule.project_id == project.id)
            .order_by(ProjectPhotoGuidanceRule.name)
        )
    )
    return render(
        request,
        "project_photo_guidance.html",
        {
            "active_nav": "projects",
            "project": project,
            "setting": db.scalar(
                select(ProjectPhotoGuidanceSetting).where(
                    ProjectPhotoGuidanceSetting.project_id == project.id
                )
            ),
            "rules": rules,
        },
    )


@router.post("/projects/{project_id}/photo-guidance/settings", dependencies=[Depends(require_admin)])
def save_photo_guidance_setting(
    project_id: int,
    request: Request,
    enabled: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    project = _project_or_404(db, project_id)
    if not csrf_valid(request, csrf_token):
        flash(request, "Your session expired. Please try again.", "error")
        return RedirectResponse(_back(project.id), status_code=status.HTTP_303_SEE_OTHER)
    setting = db.scalar(
        select(ProjectPhotoGuidanceSetting).where(
            ProjectPhotoGuidanceSetting.project_id == project.id
        )
    )
    before = bool(setting and setting.enabled)
    if setting is None:
        setting = ProjectPhotoGuidanceSetting(project_id=project.id)
        db.add(setting)
    setting.enabled = enabled == "on"
    setting.updated_at = utcnow()
    db.commit()
    set_audit_context(
        request,
        action="update",
        entity_type="project_photo_guidance",
        entity_id=project.id,
        entity_label=project.name,
        changes={"enabled": {"before": before, "after": setting.enabled}},
    )
    flash(request, "Photo guidance enabled for data entry." if setting.enabled else "Photo guidance disabled for data entry.")
    return RedirectResponse(_back(project.id), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/projects/{project_id}/photo-guidance/rules", dependencies=[Depends(require_admin)])
def save_photo_guidance_rule(
    project_id: int,
    request: Request,
    rule_id: str = Form(""),
    profile_name: str = Form(""),
    before_alert: str = Form(""),
    after_alert: str = Form(""),
    before_descriptions: list[str] = Form(default=[]),
    after_descriptions: list[str] = Form(default=[]),
    guidance_enabled: str = Form(""),
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    project = _project_or_404(db, project_id)
    back = _back(project.id)
    if not csrf_valid(request, csrf_token):
        flash(request, "Your session expired. Please try again.", "error")
        return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)
    profile_name_value, before, after, before_options, after_options, error = _valid_rule_values(
        profile_name, before_alert, after_alert,
        before_descriptions, after_descriptions,
    )
    if error:
        flash(request, error, "error")
        return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)
    existing_id = entity_id(rule_id) if rule_id.strip() else None
    rule = db.get(ProjectPhotoGuidanceRule, existing_id) if existing_id is not None else None
    if existing_id is not None and (rule is None or rule.project_id != project.id):
        flash(request, "That photo guidance profile no longer exists.", "error")
        return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)
    creating = rule is None
    before_snapshot = _rule_snapshot(rule) if rule is not None else None
    setting = db.scalar(
        select(ProjectPhotoGuidanceSetting).where(
            ProjectPhotoGuidanceSetting.project_id == project.id
        )
    )
    setting_before = setting.enabled if setting is not None else None
    if setting is None:
        setting = ProjectPhotoGuidanceSetting(project_id=project.id)
        db.add(setting)
    setting.enabled = guidance_enabled == "on"
    setting.updated_at = utcnow()
    if rule is None:
        rule = ProjectPhotoGuidanceRule(project_id=project.id, name=profile_name_value)
        db.add(rule)
    rule.name = profile_name_value
    rule.before_alert = before
    rule.after_alert = after
    rule.updated_at = utcnow()
    _replace_descriptions(rule, before_options, after_options, db)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "A profile with that name already exists in this Project. Edit the existing profile instead.", "error")
        return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)
    set_audit_context(
        request,
        action="create" if creating else "update",
        entity_type="project_photo_guidance_rule",
        entity_id=rule.id,
        entity_label=f"{project.name} / {profile_name_value}",
        changes={
            "photo_guidance": {
                "before": before_snapshot,
                "after": _rule_snapshot(rule),
            },
            "enabled": {"before": setting_before, "after": setting.enabled},
        },
    )
    flash(request, "Photo guidance profile saved.")
    return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/projects/{project_id}/photo-guidance/rules/{rule_id}/delete", dependencies=[Depends(require_admin)])
def delete_photo_guidance_rule(
    project_id: int,
    rule_id: int,
    request: Request,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
):
    project = _project_or_404(db, project_id)
    back = _back(project.id)
    if not csrf_valid(request, csrf_token):
        flash(request, "Your session expired. Please try again.", "error")
        return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)
    rule = db.get(ProjectPhotoGuidanceRule, rule_id)
    if rule is None or rule.project_id != project.id:
        flash(request, "That photo guidance profile no longer exists.", "error")
        return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)
    label = rule.name
    before_snapshot = _rule_snapshot(rule)
    db.delete(rule)
    db.commit()
    set_audit_context(
        request,
        action="delete",
        entity_type="project_photo_guidance_rule",
        entity_id=rule_id,
        entity_label=f"{project.name} / {label}",
        changes={"photo_guidance": {"before": before_snapshot, "after": None}},
    )
    flash(request, "Photo guidance profile deleted.")
    return RedirectResponse(back, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/photo-guidance")
def photo_guidance_profile(
    project_id: int,
    profile_id: int,
    work_site_id: int,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    setting = db.scalar(
        select(ProjectPhotoGuidanceSetting).where(
            ProjectPhotoGuidanceSetting.project_id == project_id,
        )
    )
    if setting is not None and not setting.enabled:
        return {"enabled": False}
    if work_site_id not in _project_site_ids(db, project_id):
        return {"enabled": False}
    rule = db.scalar(
        select(ProjectPhotoGuidanceRule)
        .options(selectinload(ProjectPhotoGuidanceRule.descriptions))
        .where(
            ProjectPhotoGuidanceRule.project_id == project_id,
            ProjectPhotoGuidanceRule.id == profile_id,
        )
        .limit(1)
    )
    if rule is None:
        return {"enabled": False}
    return {
        "enabled": True,
        "scope": "project",
        "before": {
            "alert": rule.before_alert or "",
            "descriptions": [entry.description for entry in rule.descriptions if entry.stage == "before"],
        },
        "after": {
            "alert": rule.after_alert or "",
            "descriptions": [entry.description for entry in rule.descriptions if entry.stage == "after"],
        },
    }
