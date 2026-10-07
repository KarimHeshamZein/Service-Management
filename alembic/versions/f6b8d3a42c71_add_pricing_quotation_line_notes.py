"""Add notes to individual pricing quotation lines.

Revision ID: f6b8d3a42c71
Revises: d4f9c2a61b30
Create Date: 2026-10-01
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f6b8d3a42c71"
down_revision = "d4f9c2a61b30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column(
        "pricing_quotation_lines",
        "notes",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("pricing_quotation_lines", "notes")
