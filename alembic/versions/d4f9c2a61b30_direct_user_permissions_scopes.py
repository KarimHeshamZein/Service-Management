"""Use direct user permissions and module visibility scopes.

Revision ID: d4f9c2a61b30
Revises: c1e8a4f72d90
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "d4f9c2a61b30"
down_revision = "c1e8a4f72d90"
branch_labels = None
depends_on = None


SCOPED_MODULES = (
    "projects", "records", "reports", "pricing_items", "quotations",
    "purchase_documents", "technical_documents", "wiring", "store",
    "product_evaluations", "tasks",
)


def upgrade() -> None:
    op.create_table(
        "user_department_scopes",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("department_id", sa.Integer(), primary_key=True),
        sa.Column("module_key", sa.String(60), primary_key=True),
        sa.Column(
            "scope",
            sa.Enum(
                "none", "own", "selected", "department",
                name="accessscope", native_enum=False, length=20,
            ),
            nullable=False,
            server_default="none",
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id", "department_id"],
            ["user_departments.user_id", "user_departments.department_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "length(trim(module_key)) > 0",
            name="ck_user_department_scope_module_present",
        ),
    )
    op.add_column("pricing_item_categories", sa.Column("created_by_id", sa.Integer()))
    op.create_foreign_key(
        "fk_pricing_item_categories_created_by_id",
        "pricing_item_categories", "users", ["created_by_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "ix_pricing_item_categories_created_by_id", "pricing_item_categories", ["created_by_id"]
    )
    op.add_column("pricing_items", sa.Column("created_by_id", sa.Integer()))
    op.create_foreign_key(
        "fk_pricing_items_created_by_id",
        "pricing_items", "users", ["created_by_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_pricing_items_created_by_id", "pricing_items", ["created_by_id"])
    op.create_table(
        "pricing_item_user_access",
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("pricing_items.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Freeze every currently effective grant onto the user.  After this
    # migration Department defaults are retained only as legacy audit data and
    # are no longer consulted by authorization checks.
    op.execute(sa.text("""
        INSERT INTO user_department_permissions
          (user_id, department_id, permission_key, allowed)
        SELECT ud.user_id, ud.department_id, dp.permission_key, TRUE
        FROM user_departments ud
        JOIN department_permissions dp
          ON dp.department_id = ud.department_id AND dp.allowed IS TRUE
        LEFT JOIN user_department_permissions udp
          ON udp.user_id = ud.user_id
         AND udp.department_id = ud.department_id
         AND udp.permission_key = dp.permission_key
        WHERE udp.permission_key IS NULL
        ON CONFLICT (user_id, department_id, permission_key) DO NOTHING
    """))
    op.execute(sa.text("DELETE FROM user_department_permissions WHERE allowed IS FALSE"))

    for module in SCOPED_MODULES:
        view_key = {
            "pricing_items": "pricing_items.view",
            "purchase_documents": "purchase_documents.view",
            "technical_documents": "technical_documents.view",
            "product_evaluations": "product_evaluations.view",
        }.get(module, f"{module}.view")
        op.execute(sa.text("""
            INSERT INTO user_department_scopes
              (user_id, department_id, module_key, scope)
            SELECT ud.user_id, ud.department_id, :module,
                   CASE WHEN EXISTS (
                     SELECT 1 FROM user_department_permissions udp
                     WHERE udp.user_id = ud.user_id
                       AND udp.department_id = ud.department_id
                       AND udp.permission_key = :view_key
                       AND udp.allowed IS TRUE
                   ) THEN 'department' ELSE 'none' END
            FROM user_departments ud
        """).bindparams(module=module, view_key=view_key))


def downgrade() -> None:
    op.drop_table("pricing_item_user_access")
    op.drop_index("ix_pricing_items_created_by_id", table_name="pricing_items")
    op.drop_constraint("fk_pricing_items_created_by_id", "pricing_items", type_="foreignkey")
    op.drop_column("pricing_items", "created_by_id")
    op.drop_index("ix_pricing_item_categories_created_by_id", table_name="pricing_item_categories")
    op.drop_constraint(
        "fk_pricing_item_categories_created_by_id", "pricing_item_categories", type_="foreignkey"
    )
    op.drop_column("pricing_item_categories", "created_by_id")
    op.drop_table("user_department_scopes")
