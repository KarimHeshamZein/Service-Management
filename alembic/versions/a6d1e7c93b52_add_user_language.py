"""add user language preference

Revision ID: a6d1e7c93b52
Revises: f4c2a91d7e63
Create Date: 2026-08-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a6d1e7c93b52"
down_revision: Union[str, Sequence[str], None] = "f4c2a91d7e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "language",
            sa.String(length=5),
            nullable=False,
            server_default="en",
        ),
    )
    op.alter_column("users", "language", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "language")
