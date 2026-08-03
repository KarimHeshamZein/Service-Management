"""extend pricing images, overrides, required charges, and optional decisions

Revision ID: b41d9c7e2a53
Revises: a9d4e5f6c712
Create Date: 2026-07-30 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b41d9c7e2a53"
down_revision: Union[str, Sequence[str], None] = "a9d4e5f6c712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pricing_items",
        sa.Column("image_storage_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pricing_items",
        sa.Column("image_thumbnail_key", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pricing_items",
        sa.Column("image_original_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "pricing_items",
        sa.Column("image_content_type", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "pricing_items",
        sa.Column("image_file_size", sa.Integer(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_pricing_items_image_storage_key",
        "pricing_items",
        ["image_storage_key"],
    )

    for column_name in (
        "default_manpower_price",
        "default_transportation_price",
        "default_installation_price",
    ):
        op.add_column(
            "pricing_settings",
            sa.Column(
                column_name,
                sa.Numeric(precision=14, scale=2),
                server_default="0.00",
                nullable=False,
            ),
        )
        op.alter_column(
            "pricing_settings",
            column_name,
            server_default=None,
        )
    op.create_check_constraint(
        "ck_pricing_settings_manpower_price",
        "pricing_settings",
        "default_manpower_price >= 0",
    )
    op.create_check_constraint(
        "ck_pricing_settings_transportation_price",
        "pricing_settings",
        "default_transportation_price >= 0",
    )
    op.create_check_constraint(
        "ck_pricing_settings_installation_price",
        "pricing_settings",
        "default_installation_price >= 0",
    )

    op.add_column(
        "pricing_quotation_lines",
        sa.Column(
            "skip_optional_items",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.alter_column(
        "pricing_quotation_lines",
        "skip_optional_items",
        server_default=None,
    )

    op.create_table(
        "pricing_quotation_charges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quotation_id", sa.Integer(), nullable=False),
        sa.Column("charge_type", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("unit_label", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "charge_type IN ('manpower', 'transportation', 'installation')",
            name="ck_pricing_charge_type",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_pricing_charge_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_pricing_charge_price_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["quotation_id"],
            ["pricing_quotations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quotation_id",
            "charge_type",
            name="uq_pricing_quotation_charge_type",
        ),
        sa.UniqueConstraint(
            "quotation_id",
            "position",
            name="uq_pricing_quotation_charge_position",
        ),
    )
    op.create_index(
        op.f("ix_pricing_quotation_charges_quotation_id"),
        "pricing_quotation_charges",
        ["quotation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_pricing_quotation_charges_quotation_id"),
        table_name="pricing_quotation_charges",
    )
    op.drop_table("pricing_quotation_charges")
    op.drop_column("pricing_quotation_lines", "skip_optional_items")
    op.drop_constraint(
        "ck_pricing_settings_installation_price",
        "pricing_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_pricing_settings_transportation_price",
        "pricing_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_pricing_settings_manpower_price",
        "pricing_settings",
        type_="check",
    )
    op.drop_column("pricing_settings", "default_installation_price")
    op.drop_column("pricing_settings", "default_transportation_price")
    op.drop_column("pricing_settings", "default_manpower_price")
    op.drop_constraint(
        "uq_pricing_items_image_storage_key",
        "pricing_items",
        type_="unique",
    )
    op.drop_column("pricing_items", "image_file_size")
    op.drop_column("pricing_items", "image_content_type")
    op.drop_column("pricing_items", "image_original_filename")
    op.drop_column("pricing_items", "image_thumbnail_key")
    op.drop_column("pricing_items", "image_storage_key")
