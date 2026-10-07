"""Add one-level Pricing Item subcategories.

Revision ID: e7c3a1b95d42
Revises: d8f4a6c21e90
"""

from alembic import op
import sqlalchemy as sa


revision = "e7c3a1b95d42"
down_revision = "d8f4a6c21e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pricing_item_categories",
        sa.Column("parent_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_pricing_item_categories_parent_id",
        "pricing_item_categories",
        ["parent_id"],
    )
    op.create_foreign_key(
        "fk_pricing_item_categories_parent_id",
        "pricing_item_categories",
        "pricing_item_categories",
        ["parent_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_pricing_item_categories_parent_id",
        "pricing_item_categories",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_pricing_item_categories_parent_id",
        table_name="pricing_item_categories",
    )
    op.drop_column("pricing_item_categories", "parent_id")
