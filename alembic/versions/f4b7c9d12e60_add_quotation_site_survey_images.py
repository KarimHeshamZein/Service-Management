"""Add site-survey layout images to pricing quotations.

Revision ID: f4b7c9d12e60
Revises: d2e5f7a19c40
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4b7c9d12e60"
down_revision: Union[str, Sequence[str], None] = "d2e5f7a19c40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pricing_quotation_site_survey_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quotation_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("thumbnail_key", sa.String(length=255), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=60), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_name", sa.String(length=120), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["quotation_id"], ["pricing_quotations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_pricing_quotation_site_survey_images_quotation_id",
        "pricing_quotation_site_survey_images",
        ["quotation_id"],
        unique=False,
    )
    op.create_index(
        "ix_pricing_quotation_site_survey_images_uploaded_by_id",
        "pricing_quotation_site_survey_images",
        ["uploaded_by_id"],
        unique=False,
    )
    op.create_index(
        "ix_pricing_quotation_site_survey_images_uploaded_at",
        "pricing_quotation_site_survey_images",
        ["uploaded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pricing_quotation_site_survey_images_uploaded_at",
        table_name="pricing_quotation_site_survey_images",
    )
    op.drop_index(
        "ix_pricing_quotation_site_survey_images_uploaded_by_id",
        table_name="pricing_quotation_site_survey_images",
    )
    op.drop_index(
        "ix_pricing_quotation_site_survey_images_quotation_id",
        table_name="pricing_quotation_site_survey_images",
    )
    op.drop_table("pricing_quotation_site_survey_images")
