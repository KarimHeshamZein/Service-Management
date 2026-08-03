"""add before and after photo stages

Revision ID: d74f0b2c91e3
Revises: c62e8a14d907
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d74f0b2c91e3"
down_revision: Union[str, Sequence[str], None] = "c62e8a14d907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = (
    "installation_item_photos",
    "maintenance_item_photos",
    "general_maintenance_photos",
)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column(
                "stage",
                sa.Enum(
                    "before",
                    "after",
                    "legacy",
                    name="evidencephotostage",
                    native_enum=False,
                    length=20,
                ),
                nullable=False,
                server_default="legacy",
            ),
        )
        op.create_index(op.f(f"ix_{table}_stage"), table, ["stage"], unique=False)
        op.alter_column(table, "stage", server_default=None)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(op.f(f"ix_{table}_stage"), table_name=table)
        op.drop_column(table, "stage")
