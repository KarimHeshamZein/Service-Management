"""add upload backup settings

Revision ID: f4c2a91d7e63
Revises: e017fa3d1f83
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4c2a91d7e63"
down_revision: Union[str, Sequence[str], None] = "e017fa3d1f83"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deployment_settings",
        sa.Column(
            "backup_include_uploads",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "deployment_settings",
        sa.Column(
            "backup_upload_retention_count",
            sa.Integer(),
            nullable=False,
            server_default="7",
        ),
    )
    op.create_check_constraint(
        "ck_deployment_backup_upload_retention",
        "deployment_settings",
        "backup_upload_retention_count BETWEEN 1 AND 365",
    )
    for column in (
        "backup_include_uploads",
        "backup_upload_retention_count",
    ):
        op.alter_column("deployment_settings", column, server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_deployment_backup_upload_retention",
        "deployment_settings",
        type_="check",
    )
    op.drop_column("deployment_settings", "backup_upload_retention_count")
    op.drop_column("deployment_settings", "backup_include_uploads")
