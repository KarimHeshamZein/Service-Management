"""Add descriptions to Pricing Items.

Revision ID: a9e3c7b21f84
Revises: f6b8d3a42c71
Create Date: 2026-10-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a9e3c7b21f84"
down_revision = "f6b8d3a42c71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pricing_items",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("pricing_items", "description", server_default=None)


def downgrade() -> None:
    op.drop_column("pricing_items", "description")
