"""Add Main Project hierarchy metadata, Sub Projects, and Site assignments.

Revision ID: c4d8e2f71a90
Revises: f3a8d7c52e14
Create Date: 2026-08-09
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d8e2f71a90"
down_revision: Union[str, Sequence[str], None] = "f3a8d7c52e14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("sites", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("sites", sa.Column("end_date", sa.Date(), nullable=True))

    op.create_table(
        "sub_projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_sub_project_name_present",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["sites.id"],
            name="fk_sub_projects_project_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "name",
            name="uq_sub_project_project_name",
        ),
    )
    op.create_index(
        op.f("ix_sub_projects_project_id"),
        "sub_projects",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sub_projects_name"),
        "sub_projects",
        ["name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_sub_projects_is_active"),
        "sub_projects",
        ["is_active"],
        unique=False,
    )

    op.create_table(
        "sub_project_sites",
        sa.Column("sub_project_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["work_sites.id"],
            name="fk_sub_project_sites_site_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sub_project_id"],
            ["sub_projects.id"],
            name="fk_sub_project_sites_sub_project_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sub_project_id", "site_id"),
    )
    op.create_index(
        op.f("ix_sub_project_sites_site_id"),
        "sub_project_sites",
        ["site_id"],
        unique=False,
    )

    # Preserve every previously valid Project/Site choice. Existing forms
    # allowed every catalog Site under every Project, so each Main Project gets
    # a General Sub Project containing the full current Site catalog.
    op.execute(
        sa.text(
            """
            INSERT INTO sub_projects
                (project_id, name, description, is_active, created_at, updated_at)
            SELECT id, 'General', NULL, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM sites
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO sub_project_sites (sub_project_id, site_id, created_at)
            SELECT sub_projects.id, work_sites.id, CURRENT_TIMESTAMP
            FROM sub_projects CROSS JOIN work_sites
            WHERE sub_projects.name = 'General'
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_sub_project_sites_site_id"),
        table_name="sub_project_sites",
    )
    op.drop_table("sub_project_sites")
    op.drop_index(op.f("ix_sub_projects_is_active"), table_name="sub_projects")
    op.drop_index(op.f("ix_sub_projects_name"), table_name="sub_projects")
    op.drop_index(op.f("ix_sub_projects_project_id"), table_name="sub_projects")
    op.drop_table("sub_projects")
    op.drop_column("sites", "end_date")
    op.drop_column("sites", "start_date")
    op.drop_column("sites", "description")
