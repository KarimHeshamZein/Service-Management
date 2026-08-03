"""add pricing module and per-user pricing access

Revision ID: a9d4e5f6c712
Revises: f12c7b39a640
Create Date: 2026-07-29 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9d4e5f6c712"
down_revision: Union[str, Sequence[str], None] = "f12c7b39a640"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "pricing_access",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_users_pricing_access"),
        "users",
        ["pricing_access"],
        unique=False,
    )
    op.alter_column("users", "pricing_access", server_default=None)

    op.create_table(
        "pricing_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0", name="ck_pricing_item_name_present"
        ),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_pricing_item_price_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "model", name="uq_pricing_item_name_model"),
    )
    op.create_index(
        op.f("ix_pricing_items_is_active"),
        "pricing_items",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_items_model"),
        "pricing_items",
        ["model"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_items_name"),
        "pricing_items",
        ["name"],
        unique=False,
    )

    op.create_table(
        "pricing_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "default_vat_rate", sa.Numeric(precision=5, scale=2), nullable=False
        ),
        sa.Column("default_validity_days", sa.Integer(), nullable=False),
        sa.Column("quotation_prefix", sa.String(length=12), nullable=False),
        sa.Column("company_name", sa.String(length=160), nullable=False),
        sa.Column("company_address", sa.Text(), nullable=False),
        sa.Column("company_phone", sa.String(length=40), nullable=False),
        sa.Column("company_email", sa.String(length=254), nullable=False),
        sa.Column("default_terms", sa.Text(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_name", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_pricing_settings_singleton"),
        sa.CheckConstraint(
            "length(trim(currency)) = 3", name="ck_pricing_settings_currency"
        ),
        sa.CheckConstraint(
            "length(trim(quotation_prefix)) > 0",
            name="ck_pricing_settings_prefix",
        ),
        sa.CheckConstraint(
            "default_validity_days BETWEEN 1 AND 365",
            name="ck_pricing_settings_validity_days",
        ),
        sa.CheckConstraint(
            "default_vat_rate BETWEEN 0 AND 100",
            name="ck_pricing_settings_vat_rate",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "pricing_quotations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quotation_number", sa.String(length=30), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("project_name", sa.String(length=160), nullable=False),
        sa.Column("project_address", sa.String(length=255), nullable=False),
        sa.Column("project_city", sa.String(length=80), nullable=False),
        sa.Column("contact_person", sa.String(length=120), nullable=False),
        sa.Column("contact_number", sa.String(length=40), nullable=False),
        sa.Column("quotation_date", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "discount_percent", sa.Numeric(precision=5, scale=2), nullable=False
        ),
        sa.Column("vat_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("terms", sa.Text(), nullable=False),
        sa.Column("company_name", sa.String(length=160), nullable=False),
        sa.Column("company_address", sa.Text(), nullable=False),
        sa.Column("company_phone", sa.String(length=40), nullable=False),
        sa.Column("company_email", sa.String(length=254), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_by_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "discount_percent BETWEEN 0 AND 100",
            name="ck_pricing_quotation_discount",
        ),
        sa.CheckConstraint(
            "valid_until >= quotation_date",
            name="ck_pricing_quotation_validity",
        ),
        sa.CheckConstraint(
            "vat_rate BETWEEN 0 AND 100",
            name="ck_pricing_quotation_vat_rate",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["sites.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pricing_quotations_created_at"),
        "pricing_quotations",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_quotations_created_by_id"),
        "pricing_quotations",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_quotations_project_id"),
        "pricing_quotations",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_quotations_project_name"),
        "pricing_quotations",
        ["project_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_quotations_quotation_date"),
        "pricing_quotations",
        ["quotation_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_quotations_quotation_number"),
        "pricing_quotations",
        ["quotation_number"],
        unique=True,
    )

    op.create_table(
        "pricing_quotation_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("year"),
    )

    op.create_table(
        "pricing_related_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("main_item_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_pricing_related_item_name_present",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_pricing_related_item_price_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["main_item_id"], ["pricing_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "main_item_id",
            "name",
            name="uq_pricing_related_item_parent_name",
        ),
    )
    op.create_index(
        op.f("ix_pricing_related_items_is_active"),
        "pricing_related_items",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_related_items_main_item_id"),
        "pricing_related_items",
        ["main_item_id"],
        unique=False,
    )

    op.create_table(
        "pricing_quotation_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("quotation_id", sa.Integer(), nullable=False),
        sa.Column("source_item_id", sa.Integer(), nullable=True),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("item_model", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "quantity > 0", name="ck_pricing_line_quantity_positive"
        ),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_pricing_line_price_nonnegative"
        ),
        sa.ForeignKeyConstraint(
            ["quotation_id"], ["pricing_quotations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_item_id"], ["pricing_items.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "quotation_id",
            "position",
            name="uq_pricing_quotation_line_position",
        ),
    )
    op.create_index(
        op.f("ix_pricing_quotation_lines_quotation_id"),
        "pricing_quotation_lines",
        ["quotation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_quotation_lines_source_item_id"),
        "pricing_quotation_lines",
        ["source_item_id"],
        unique=False,
    )

    op.create_table(
        "pricing_quotation_related_lines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("source_related_item_id", sa.Integer(), nullable=True),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_pricing_related_line_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_price >= 0",
            name="ck_pricing_related_line_price_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["pricing_quotation_lines.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_related_item_id"],
            ["pricing_related_items.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pricing_quotation_related_lines_line_id"),
        "pricing_quotation_related_lines",
        ["line_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pricing_quotation_related_lines_source_related_item_id"),
        "pricing_quotation_related_lines",
        ["source_related_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_pricing_quotation_related_lines_source_related_item_id"),
        table_name="pricing_quotation_related_lines",
    )
    op.drop_index(
        op.f("ix_pricing_quotation_related_lines_line_id"),
        table_name="pricing_quotation_related_lines",
    )
    op.drop_table("pricing_quotation_related_lines")
    op.drop_index(
        op.f("ix_pricing_quotation_lines_source_item_id"),
        table_name="pricing_quotation_lines",
    )
    op.drop_index(
        op.f("ix_pricing_quotation_lines_quotation_id"),
        table_name="pricing_quotation_lines",
    )
    op.drop_table("pricing_quotation_lines")
    op.drop_index(
        op.f("ix_pricing_related_items_main_item_id"),
        table_name="pricing_related_items",
    )
    op.drop_index(
        op.f("ix_pricing_related_items_is_active"),
        table_name="pricing_related_items",
    )
    op.drop_table("pricing_related_items")
    op.drop_table("pricing_quotation_counters")
    op.drop_index(
        op.f("ix_pricing_quotations_quotation_number"),
        table_name="pricing_quotations",
    )
    op.drop_index(
        op.f("ix_pricing_quotations_quotation_date"),
        table_name="pricing_quotations",
    )
    op.drop_index(
        op.f("ix_pricing_quotations_project_name"),
        table_name="pricing_quotations",
    )
    op.drop_index(
        op.f("ix_pricing_quotations_project_id"),
        table_name="pricing_quotations",
    )
    op.drop_index(
        op.f("ix_pricing_quotations_created_by_id"),
        table_name="pricing_quotations",
    )
    op.drop_index(
        op.f("ix_pricing_quotations_created_at"),
        table_name="pricing_quotations",
    )
    op.drop_table("pricing_quotations")
    op.drop_table("pricing_settings")
    op.drop_index(op.f("ix_pricing_items_name"), table_name="pricing_items")
    op.drop_index(op.f("ix_pricing_items_model"), table_name="pricing_items")
    op.drop_index(op.f("ix_pricing_items_is_active"), table_name="pricing_items")
    op.drop_table("pricing_items")
    op.drop_index(op.f("ix_users_pricing_access"), table_name="users")
    op.drop_column("users", "pricing_access")
