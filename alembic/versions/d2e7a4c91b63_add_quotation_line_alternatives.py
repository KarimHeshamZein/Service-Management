"""Add alternative relationships between quotation lines.

Revision ID: d2e7a4c91b63
Revises: a6c1e9b42f70
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e7a4c91b63"
down_revision: Union[str, Sequence[str], None] = "a6c1e9b42f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("alternative_to_line_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_pricing_quotation_lines_alternative_to_line_id"),
        "pricing_quotation_lines",
        ["alternative_to_line_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_pricing_quotation_lines_alternative_to_line_id",
        "pricing_quotation_lines",
        "pricing_quotation_lines",
        ["alternative_to_line_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_pricing_line_not_own_alternative",
        "pricing_quotation_lines",
        "alternative_to_line_id IS NULL OR alternative_to_line_id <> id",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_pricing_line_not_own_alternative",
        "pricing_quotation_lines",
        type_="check",
    )
    op.drop_constraint(
        "fk_pricing_quotation_lines_alternative_to_line_id",
        "pricing_quotation_lines",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_pricing_quotation_lines_alternative_to_line_id"),
        table_name="pricing_quotation_lines",
    )
    op.drop_column("pricing_quotation_lines", "alternative_to_line_id")
