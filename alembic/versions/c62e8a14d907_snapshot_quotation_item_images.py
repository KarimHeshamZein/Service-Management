"""snapshot main item images on quotation lines

Revision ID: c62e8a14d907
Revises: b41d9c7e2a53
Create Date: 2026-07-30 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c62e8a14d907"
down_revision: Union[str, Sequence[str], None] = "b41d9c7e2a53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("image_storage_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("image_thumbnail_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("image_original_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("image_content_type", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "pricing_quotation_lines",
        sa.Column("image_file_size", sa.Integer(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_pricing_quotation_lines_image_storage_key",
        "pricing_quotation_lines",
        ["image_storage_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_pricing_quotation_lines_image_storage_key",
        "pricing_quotation_lines",
        type_="unique",
    )
    op.drop_column("pricing_quotation_lines", "image_file_size")
    op.drop_column("pricing_quotation_lines", "image_content_type")
    op.drop_column("pricing_quotation_lines", "image_original_filename")
    op.drop_column("pricing_quotation_lines", "image_thumbnail_key")
    op.drop_column("pricing_quotation_lines", "image_storage_key")
