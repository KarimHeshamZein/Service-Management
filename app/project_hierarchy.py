"""Shared Main Project -> Sub Project -> Site form helpers."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .helpers import entity_id
from .models import Site, SubProject, SubProjectSite, WorkSite


def active_project_hierarchy(db: Session) -> list[Site]:
    return list(
        db.scalars(
            select(Site)
            .options(
                selectinload(Site.sub_projects)
                .selectinload(SubProject.site_assignments)
                .selectinload(SubProjectSite.site)
            )
            .where(Site.is_active.is_(True))
            .order_by(Site.name)
        )
    )


def hierarchy_json(projects: list[Site]) -> list[dict]:
    return [
        {
            "project_id": project.id,
            "sub_projects": [
                {
                    "id": sub_project.id,
                    "name": sub_project.name,
                    "site_ids": [
                        assignment.site_id
                        for assignment in sub_project.site_assignments
                        if assignment.site.is_active
                    ],
                }
                for sub_project in project.sub_projects
                if sub_project.is_active
            ],
        }
        for project in projects
    ]


def resolve_entry_sub_project(
    db: Session,
    project: Site | None,
    work_site: WorkSite | None,
    raw_value: str,
) -> tuple[SubProject | None, str | None]:
    """Resolve the selected scope, with a legacy General fallback for old clients."""
    if project is None or work_site is None:
        return None, None
    sub_project_id = entity_id(raw_value)
    if sub_project_id is not None:
        sub_project = db.scalar(
            select(SubProject)
            .join(SubProjectSite)
            .where(
                SubProject.id == sub_project_id,
                SubProject.project_id == project.id,
                SubProject.is_active.is_(True),
                SubProjectSite.site_id == work_site.id,
            )
        )
        if sub_project is None:
            return None, "Select a Sub Project that contains this Site."
        return sub_project, None

    # Compatibility for submissions made by clients/tests predating hierarchy.
    sub_project = db.scalar(
        select(SubProject)
        .join(SubProjectSite)
        .where(
            SubProject.project_id == project.id,
            SubProject.is_active.is_(True),
            SubProjectSite.site_id == work_site.id,
        )
        .order_by((SubProject.name == "General").desc(), SubProject.name)
        .limit(1)
    )
    return sub_project, None
