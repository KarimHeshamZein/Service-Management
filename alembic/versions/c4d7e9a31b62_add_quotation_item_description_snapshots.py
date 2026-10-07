"""Add catalog description snapshots to pricing quotation lines.

Revision ID: c4d7e9a31b62
Revises: a9e3c7b21f84
Create Date: 2026-10-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c4d7e9a31b62"
down_revision = "a9e3c7b21f84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("item_description", sa.Text(), nullable=False, server_default=""),
    )
    op.execute(
        sa.text(
            """
            UPDATE pricing_quotation_lines
            SET item_description = COALESCE(
                (
                    SELECT pricing_items.description
                    FROM pricing_items
                    WHERE pricing_items.id = pricing_quotation_lines.source_item_id
                ),
                ''
            )
            """
        )
    )
    op.alter_column(
        "pricing_quotation_lines",
        "item_description",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("pricing_quotation_lines", "item_description")
