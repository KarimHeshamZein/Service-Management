"""Add imported device-data snapshots to service record items.

Revision ID: b7e5d8c41f20
Revises: e9b4c7a21d36
Create Date: 2026-08-09
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e5d8c41f20"
down_revision: Union[str, Sequence[str], None] = "e9b4c7a21d36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ITEM_TABLES = (
    "installation_record_items",
    "maintenance_record_items",
    "general_maintenance_items",
)
COLUMNS = (
    ("imei", sa.String(length=15)),
    ("iccid", sa.String(length=22)),
    ("sim_type", sa.String(length=20)),
    ("phone_number", sa.String(length=40)),
    ("location_name", sa.String(length=120)),
    ("remarks", sa.Text()),
)


def upgrade() -> None:
    for table in ITEM_TABLES:
        for name, column_type in COLUMNS:
            op.add_column(table, sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    for table in reversed(ITEM_TABLES):
        for name, _ in reversed(COLUMNS):
            op.drop_column(table, name)
