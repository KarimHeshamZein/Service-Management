"""add quotation addressee price history and audit

Revision ID: d5b9e2a74c16
Revises: a3f8d1c62b04
"""

from alembic import op
import sqlalchemy as sa


revision = "d5b9e2a74c16"
down_revision = "a3f8d1c62b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pricing_quotations", sa.Column("addressee_source", sa.String(30), nullable=False, server_default="none"))
    op.add_column("pricing_quotations", sa.Column("addressee_user_id", sa.Integer(), nullable=True))
    op.add_column("pricing_quotations", sa.Column("addressee_name", sa.String(120), nullable=False, server_default=""))
    op.add_column("pricing_quotations", sa.Column("addressee_title", sa.String(120), nullable=False, server_default=""))
    op.add_column("pricing_quotations", sa.Column("addressee_email", sa.String(254), nullable=False, server_default=""))
    op.add_column("pricing_quotations", sa.Column("addressee_phone", sa.String(40), nullable=False, server_default=""))
    op.create_foreign_key("fk_pricing_quotations_addressee_user_id", "pricing_quotations", "users", ["addressee_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_pricing_quotations_addressee_user_id", "pricing_quotations", ["addressee_user_id"])

    op.create_table(
        "pricing_item_price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pricing_item_id", sa.Integer(), sa.ForeignKey("pricing_items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("related_item_id", sa.Integer(), sa.ForeignKey("pricing_related_items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("old_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("new_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("old_currency", sa.String(3), nullable=True),
        sa.Column("new_currency", sa.String(3), nullable=False),
        sa.Column("changed_by_id", sa.Integer(), nullable=True),
        sa.Column("changed_by_name", sa.String(120), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="catalog_edit"),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("(CASE WHEN pricing_item_id IS NULL THEN 0 ELSE 1 END + CASE WHEN related_item_id IS NULL THEN 0 ELSE 1 END) = 1", name="ck_pricing_price_history_one_item"),
        sa.CheckConstraint("new_price >= 0", name="ck_pricing_price_history_nonnegative"),
    )
    for column in ("pricing_item_id", "related_item_id", "changed_by_id", "source", "changed_at"):
        op.create_index(f"ix_pricing_item_price_history_{column}", "pricing_item_price_history", [column])
    op.execute(sa.text("INSERT INTO pricing_item_price_history (pricing_item_id, old_price, new_price, old_currency, new_currency, changed_by_name, source, changed_at) SELECT id, NULL, unit_price, NULL, currency, 'System migration', 'baseline', updated_at FROM pricing_items"))
    op.execute(sa.text("INSERT INTO pricing_item_price_history (related_item_id, old_price, new_price, old_currency, new_currency, changed_by_name, source, changed_at) SELECT id, NULL, unit_price, NULL, currency, 'System migration', 'baseline', updated_at FROM pricing_related_items"))

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(120), nullable=False, server_default="Anonymous"),
        sa.Column("actor_role", sa.String(20), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("module", sa.String(60), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=True),
        sa.Column("entity_id", sa.String(80), nullable=True),
        sa.Column("entity_label", sa.String(200), nullable=True),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("changes_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    for column in ("actor_user_id", "actor_name", "actor_role", "action", "module", "entity_type", "entity_id", "path", "status_code", "ip_address", "created_at"):
        op.create_index(f"ix_audit_events_{column}", "audit_events", [column])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("pricing_item_price_history")
    op.drop_index("ix_pricing_quotations_addressee_user_id", table_name="pricing_quotations")
    op.drop_constraint("fk_pricing_quotations_addressee_user_id", "pricing_quotations", type_="foreignkey")
    for column in ("addressee_phone", "addressee_email", "addressee_title", "addressee_name", "addressee_user_id", "addressee_source"):
        op.drop_column("pricing_quotations", column)
