"""Add an Issue Found marker to every service-record photo.

Revision ID: a1d5f7c82b60
Revises: e7c3a1b95d42
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa


revision = "a1d5f7c82b60"
down_revision = "e7c3a1b95d42"
branch_labels = None
depends_on = None


PHOTO_TABLES = (
    "maintenance_photos",
    "installation_photos",
    "installation_item_photos",
    "maintenance_item_photos",
    "general_maintenance_photos",
)


def upgrade() -> None:
    for table_name in PHOTO_TABLES:
        op.add_column(
            table_name,
            sa.Column(
                "is_issue_found",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    for table_name in reversed(PHOTO_TABLES):
        op.drop_column(table_name, "is_issue_found")
