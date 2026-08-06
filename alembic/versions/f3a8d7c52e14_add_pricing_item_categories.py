"""Add categories for Pricing Items.

Revision ID: f3a8d7c52e14
Revises: d2e7a4c91b63
Create Date: 2026-08-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a8d7c52e14"
down_revision: Union[str, Sequence[str], None] = "d2e7a4c91b63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pricing_item_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_pricing_item_category_name_present",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pricing_item_categories_name"),
        "pricing_item_categories",
        ["name"],
        unique=True,
    )
    op.add_column(
        "pricing_items",
        sa.Column("category_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_pricing_items_category_id"),
        "pricing_items",
        ["category_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_pricing_items_category_id",
        "pricing_items",
        "pricing_item_categories",
        ["category_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_pricing_items_category_id",
        "pricing_items",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_pricing_items_category_id"), table_name="pricing_items")
    op.drop_column("pricing_items", "category_id")
    op.drop_index(
        op.f("ix_pricing_item_categories_name"),
        table_name="pricing_item_categories",
    )
    op.drop_table("pricing_item_categories")
