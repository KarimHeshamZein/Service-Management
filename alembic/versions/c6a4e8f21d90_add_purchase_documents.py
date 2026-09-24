"""Add item-linked purchase invoices and supplier quotations.

Revision ID: c6a4e8f21d90
Revises: a1d5f7c82b60
Create Date: 2026-08-26
"""

from alembic import op
import sqlalchemy as sa


revision = "c6a4e8f21d90"
down_revision = "a1d5f7c82b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "purchase_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "document_type",
            sa.Enum(
                "purchase_invoice",
                "supplier_quotation",
                name="purchasedocumenttype",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("supplier_name", sa.String(length=160), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(supplier_name)) > 0",
            name="ck_purchase_document_supplier_present",
        ),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "document_type",
        "supplier_name",
        "document_date",
        "uploaded_by_id",
        "created_at",
    ):
        op.create_index(op.f(f"ix_purchase_documents_{column}"), "purchase_documents", [column])

    op.create_table(
        "purchase_document_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("pricing_item_id", sa.Integer(), nullable=True),
        sa.Column("related_item_id", sa.Integer(), nullable=True),
        sa.Column("unit_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(CASE WHEN pricing_item_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN related_item_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_purchase_document_item_one_target",
        ),
        sa.CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name="ck_purchase_document_item_price_nonnegative",
        ),
        sa.CheckConstraint(
            "(unit_price IS NULL AND currency IS NULL) OR "
            "(unit_price IS NOT NULL AND length(trim(currency)) = 3)",
            name="ck_purchase_document_item_price_currency",
        ),
        sa.CheckConstraint(
            "position >= 0", name="ck_purchase_document_item_position"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["purchase_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["pricing_item_id"], ["pricing_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["related_item_id"], ["pricing_related_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id", "pricing_item_id", name="uq_purchase_document_main_item"
        ),
        sa.UniqueConstraint(
            "document_id", "related_item_id", name="uq_purchase_document_related_item"
        ),
        sa.UniqueConstraint(
            "document_id", "position", name="uq_purchase_document_item_position"
        ),
    )
    for column in ("document_id", "pricing_item_id", "related_item_id"):
        op.create_index(
            op.f(f"ix_purchase_document_items_{column}"),
            "purchase_document_items",
            [column],
        )

    op.create_table(
        "purchase_document_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=60), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "file_size > 0", name="ck_purchase_document_file_size_positive"
        ),
        sa.CheckConstraint(
            "position >= 0", name="ck_purchase_document_file_position"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["purchase_documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
        sa.UniqueConstraint(
            "document_id", "position", name="uq_purchase_document_file_position"
        ),
    )
    op.create_index(
        op.f("ix_purchase_document_files_document_id"),
        "purchase_document_files",
        ["document_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_purchase_document_files_document_id"),
        table_name="purchase_document_files",
    )
    op.drop_table("purchase_document_files")
    for column in reversed(("document_id", "pricing_item_id", "related_item_id")):
        op.drop_index(
            op.f(f"ix_purchase_document_items_{column}"),
            table_name="purchase_document_items",
        )
    op.drop_table("purchase_document_items")
    for column in reversed((
        "document_type",
        "supplier_name",
        "document_date",
        "uploaded_by_id",
        "created_at",
    )):
        op.drop_index(op.f(f"ix_purchase_documents_{column}"), table_name="purchase_documents")
    op.drop_table("purchase_documents")
