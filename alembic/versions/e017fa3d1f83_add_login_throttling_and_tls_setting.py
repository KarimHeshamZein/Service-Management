"""add login throttling and tls setting

Revision ID: e017fa3d1f83
Revises: e85a1c3d72f4
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e017fa3d1f83"
down_revision: Union[str, Sequence[str], None] = "e85a1c3d72f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identifier_hash", sa.String(length=64), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("created_at", "identifier_hash", "ip_hash"):
        op.create_index(
            op.f(f"ix_login_attempts_{column}"),
            "login_attempts",
            [column],
        )
    op.add_column(
        "deployment_settings",
        sa.Column(
            "tls_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("deployment_settings", "tls_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("deployment_settings", "tls_enabled")
    for column in ("ip_hash", "identifier_hash", "created_at"):
        op.drop_index(
            op.f(f"ix_login_attempts_{column}"),
            table_name="login_attempts",
        )
    op.drop_table("login_attempts")
