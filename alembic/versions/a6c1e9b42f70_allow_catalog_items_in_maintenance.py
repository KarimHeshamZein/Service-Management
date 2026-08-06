"""Allow maintenance records to reference general catalogue items.

Revision ID: a6c1e9b42f70
Revises: f4b7c9d12e60
Create Date: 2026-08-05
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6c1e9b42f70"
down_revision: Union[str, Sequence[str], None] = "f4b7c9d12e60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "maintenance_record_devices",
    "maintenance_record_additional_devices",
    "maintenance_record_items",
    "general_maintenance_items",
)


def upgrade() -> None:
    for table_name in TABLES:
        op.alter_column(
            table_name,
            "installed_device_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    for table_name in reversed(TABLES):
        op.alter_column(
            table_name,
            "installed_device_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
