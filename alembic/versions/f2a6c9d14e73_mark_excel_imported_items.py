"""Mark service items populated from Excel imports.

Revision ID: f2a6c9d14e73
Revises: b7e5d8c41f20
Create Date: 2026-08-09
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a6c9d14e73"
down_revision: Union[str, Sequence[str], None] = "b7e5d8c41f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ITEM_TABLES = (
    "installation_record_items",
    "maintenance_record_items",
    "general_maintenance_items",
)


def upgrade() -> None:
    for table in ITEM_TABLES:
        op.add_column(
            table,
            sa.Column(
                "imported_from_excel",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        # These snapshot fields were populated only by the Excel workflow
        # before the explicit source marker existed.
        op.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET imported_from_excel = true
                WHERE imei IS NOT NULL
                   OR iccid IS NOT NULL
                   OR sim_type IS NOT NULL
                   OR remarks IS NOT NULL
                """
            )
        )
        op.alter_column(table, "imported_from_excel", server_default=None)


def downgrade() -> None:
    for table in reversed(ITEM_TABLES):
        op.drop_column(table, "imported_from_excel")
