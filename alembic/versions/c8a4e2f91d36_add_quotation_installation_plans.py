"""Add editable camera installation plans to pricing quotations.

Revision ID: c8a4e2f91d36
Revises: b7f3c91d2a84
Create Date: 2026-08-04
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8a4e2f91d36"
down_revision: Union[str, Sequence[str], None] = "b7f3c91d2a84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = (
        sa.Column("installation_plan_state", sa.JSON(), nullable=True),
        sa.Column("plan_background_storage_key", sa.String(length=255), nullable=True),
        sa.Column("plan_background_thumbnail_key", sa.String(length=255), nullable=True),
        sa.Column("plan_background_content_type", sa.String(length=60), nullable=True),
        sa.Column("plan_background_file_size", sa.Integer(), nullable=True),
        sa.Column("plan_output_storage_key", sa.String(length=255), nullable=True),
        sa.Column("plan_output_thumbnail_key", sa.String(length=255), nullable=True),
        sa.Column("plan_output_content_type", sa.String(length=60), nullable=True),
        sa.Column("plan_output_file_size", sa.Integer(), nullable=True),
    )
    for column in columns:
        op.add_column("pricing_quotations", column)
    op.create_unique_constraint(
        "uq_pricing_quotations_plan_background_storage_key",
        "pricing_quotations",
        ["plan_background_storage_key"],
    )
    op.create_unique_constraint(
        "uq_pricing_quotations_plan_output_storage_key",
        "pricing_quotations",
        ["plan_output_storage_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_pricing_quotations_plan_output_storage_key",
        "pricing_quotations",
        type_="unique",
    )
    op.drop_constraint(
        "uq_pricing_quotations_plan_background_storage_key",
        "pricing_quotations",
        type_="unique",
    )
    for name in (
        "plan_output_file_size",
        "plan_output_content_type",
        "plan_output_thumbnail_key",
        "plan_output_storage_key",
        "plan_background_file_size",
        "plan_background_content_type",
        "plan_background_thumbnail_key",
        "plan_background_storage_key",
        "installation_plan_state",
    ):
        op.drop_column("pricing_quotations", name)
