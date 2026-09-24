"""Add Department workspaces, granular access, Project teams, tasks and notifications.

Revision ID: c1e8a4f72d90
Revises: b9d4f6a21c80
Create Date: 2026-08-29
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c1e8a4f72d90"
down_revision = "b9d4f6a21c80"
branch_labels = None
depends_on = None


DEPARTMENT_TABLES = (
    "pricing_item_categories",
    "pricing_items",
    "pricing_related_items",
    "pricing_quotations",
    "purchase_documents",
    "service_reports",
    "store_warehouses",
    "store_items",
    "store_movements",
    "technical_documents",
    "technical_recommendations",
    "wiring_diagram_categories",
    "wiring_diagrams",
    "product_evaluation_requests",
)

CORE_DEFAULTS = (
    "dashboard.view", "projects.view", "projects.edit", "records.view",
    "records.create_installation", "records.create_preventive",
    "records.create_maintenance", "records.edit", "reports.view",
    "reports.create", "reports.download", "product_evaluations.view",
    "product_evaluations.create", "product_evaluations.execute",
    "tasks.view", "tasks.create",
)


def _add_department_column(table: str) -> None:
    op.add_column(table, sa.Column("department_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        f"fk_{table}_department_id", table, "departments",
        ["department_id"], ["id"], ondelete="RESTRICT",
    )
    op.execute(sa.text(f"UPDATE {table} SET department_id = 1 WHERE department_id IS NULL"))
    op.alter_column(table, "department_id", nullable=False)
    op.create_index(f"ix_{table}_department_id", table, ["department_id"])


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_general", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_departments_name_present"),
        sa.CheckConstraint("length(trim(code)) > 0", name="ck_departments_code_present"),
    )
    op.create_index("ix_departments_name", "departments", ["name"], unique=True)
    op.create_index("ix_departments_code", "departments", ["code"], unique=True)
    op.create_index("ix_departments_is_general", "departments", ["is_general"])
    op.create_index("ix_departments_is_active", "departments", ["is_active"])
    op.create_index("uq_departments_one_general", "departments", ["is_general"], unique=True, postgresql_where=sa.text("is_general IS TRUE"), sqlite_where=sa.text("is_general = 1"))
    op.execute(sa.text("INSERT INTO departments (id,name,code,is_general,is_active) VALUES (1,'General','GENERAL',TRUE,TRUE)"))
    op.execute(sa.text("SELECT setval(pg_get_serial_sequence('departments','id'), 1, true)"))

    op.add_column("users", sa.Column("email", sa.String(254)))
    op.add_column("users", sa.Column("email_notifications", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_departments",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("job_title", sa.String(160)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("joined_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("job_title IS NULL OR length(trim(job_title)) > 0", name="ck_user_department_job_title_present"),
    )
    op.create_index("ix_user_departments_is_primary", "user_departments", ["is_primary"])
    op.create_index("ix_user_departments_added_by_id", "user_departments", ["added_by_id"])
    op.create_index("uq_user_departments_one_primary", "user_departments", ["user_id"], unique=True, postgresql_where=sa.text("is_primary IS TRUE"), sqlite_where=sa.text("is_primary = 1"))

    op.create_table(
        "department_permissions",
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_key", sa.String(100), primary_key=True),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(permission_key)) > 0", name="ck_department_default_permission_key_present"),
    )
    op.create_table(
        "user_department_permissions",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("department_id", sa.Integer(), primary_key=True),
        sa.Column("permission_key", sa.String(100), primary_key=True),
        sa.Column("allowed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "department_id"], ["user_departments.user_id", "user_departments.department_id"], ondelete="CASCADE"),
        sa.CheckConstraint("length(trim(permission_key)) > 0", name="ck_department_permission_key_present"),
    )
    op.execute(sa.text("INSERT INTO user_departments (user_id,department_id,is_primary) SELECT id,1,TRUE FROM users WHERE role <> 'customer'"))
    for key in CORE_DEFAULTS:
        op.execute(sa.text("INSERT INTO department_permissions (department_id,permission_key,allowed) VALUES (1,:key,TRUE)").bindparams(key=key))

    # Preserve every legacy per-user capability as an explicit override.  The
    # General Department defaults intentionally stay conservative, so users do
    # not lose access simply because the old boolean columns are superseded.
    legacy_overrides = {
        "pricing_access IS TRUE": (
            "pricing_items.view", "pricing_items.manage", "quotations.view",
            "quotations.create", "quotations.edit", "purchase_documents.view",
            "purchase_documents.manage", "technical_documents.view",
        ),
        "technical_documents_manage IS TRUE": ("technical_documents.manage",),
        "wiring_diagrams_manage IS TRUE": ("wiring.view", "wiring.manage"),
        "role = 'technical' OR store_access IS TRUE": ("store.view",),
        "store_receive IS TRUE": ("store.receive",),
        "store_issue IS TRUE": ("store.issue",),
        "store_transfer IS TRUE": ("store.transfer",),
        "store_custody_transfer IS TRUE": ("store.custody",),
        "store_manage_items IS TRUE OR store_manage_warehouses IS TRUE OR store_adjust IS TRUE": ("store.manage",),
        "store_reports IS TRUE": ("store.reports",),
    }
    for legacy_condition, permission_keys in legacy_overrides.items():
        for key in permission_keys:
            op.execute(sa.text(f"""
                INSERT INTO user_department_permissions
                  (user_id, department_id, permission_key, allowed)
                SELECT id, 1, :key, TRUE FROM users
                WHERE role <> 'customer' AND ({legacy_condition})
                ON CONFLICT (user_id, department_id, permission_key)
                DO UPDATE SET allowed = TRUE
            """).bindparams(key=key))

    for table in DEPARTMENT_TABLES:
        _add_department_column(table)

    op.drop_constraint("uq_pricing_item_name_model", "pricing_items", type_="unique")
    op.create_unique_constraint("uq_pricing_item_department_name_model", "pricing_items", ["department_id", "name", "model"])
    op.drop_index("ix_pricing_item_categories_name", table_name="pricing_item_categories")
    op.create_index("ix_pricing_item_categories_name", "pricing_item_categories", ["name"])
    op.add_column("pricing_item_categories", sa.Column("visibility", sa.String(20), nullable=False, server_default="department"))
    op.create_check_constraint("ck_pricing_category_visibility", "pricing_item_categories", "visibility IN ('department', 'selected_users')")
    op.create_index("uq_pricing_category_root_department_name", "pricing_item_categories", ["department_id", "name"], unique=True, postgresql_where=sa.text("parent_id IS NULL"), sqlite_where=sa.text("parent_id IS NULL"))
    op.create_index("uq_pricing_category_child_department_name", "pricing_item_categories", ["department_id", "parent_id", "name"], unique=True, postgresql_where=sa.text("parent_id IS NOT NULL"), sqlite_where=sa.text("parent_id IS NOT NULL"))
    op.create_table(
        "pricing_category_user_access",
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("pricing_item_categories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("granted_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.drop_index("ix_store_warehouses_name", table_name="store_warehouses")
    op.create_index("ix_store_warehouses_name", "store_warehouses", ["name"])
    op.drop_index("uq_store_one_main_warehouse", table_name="store_warehouses")
    op.create_index("uq_store_one_main_warehouse", "store_warehouses", ["department_id", "warehouse_type"], unique=True, postgresql_where=sa.text("warehouse_type = 'main'"), sqlite_where=sa.text("warehouse_type = 'main'"))
    op.create_unique_constraint("uq_store_warehouse_department_name", "store_warehouses", ["department_id", "name"])
    op.drop_index("ix_store_items_code", table_name="store_items")
    op.create_index("ix_store_items_code", "store_items", ["code"])
    op.create_unique_constraint("uq_store_item_department_code", "store_items", ["department_id", "code"])

    op.create_table(
        "project_team_members",
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_role", sa.String(160)),
        sa.Column("can_view_records", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_create_records", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_view_reports", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("can_view_quotations", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_manage_tasks", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id", "department_id"], ["user_departments.user_id", "user_departments.department_id"], ondelete="CASCADE", name="fk_project_team_user_department"),
        sa.CheckConstraint("project_role IS NULL OR length(trim(project_role)) > 0", name="ck_project_team_role_present"),
    )
    op.create_index("ix_project_team_members_department_id", "project_team_members", ["department_id"])
    op.execute(sa.text("""
        INSERT INTO project_team_members
          (project_id,user_id,department_id,project_role,can_view_records,can_create_records,can_view_reports,can_view_quotations,can_manage_tasks)
        SELECT s.id,u.id,1,'Legacy access',TRUE,TRUE,TRUE,
               CASE WHEN u.role='admin' OR u.pricing_access IS TRUE THEN TRUE ELSE FALSE END,TRUE
        FROM sites s CROSS JOIN users u WHERE u.role <> 'customer' AND u.is_active IS TRUE
    """))

    op.create_table("work_task_counters", sa.Column("year", sa.Integer(), primary_key=True), sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "work_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_number", sa.String(40), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(220), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("priority", sa.Enum("normal","important","urgent",name="taskpriority",native_enum=False,length=20), nullable=False),
        sa.Column("status", sa.Enum("new","in_progress","blocked","completed","cancelled",name="taskstatus",native_enum=False,length=20), nullable=False),
        sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_to_name", sa.String(120), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_name", sa.String(120), nullable=False),
        sa.Column("due_at", sa.DateTime()), sa.Column("started_at", sa.DateTime()), sa.Column("completed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()), sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_work_task_title_present"),
    )
    op.create_index("ix_work_tasks_task_number", "work_tasks", ["task_number"], unique=True)
    for column in ("department_id","project_id","title","priority","status","assigned_to_id","created_by_id","due_at","created_at"):
        op.create_index(f"ix_work_tasks_{column}", "work_tasks", [column])
    op.create_table(
        "work_task_comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("work_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("author_name", sa.String(120), nullable=False), sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(body)) > 0", name="ck_work_task_comment_body_present"),
    )
    op.create_index("ix_work_task_comments_task_id", "work_task_comments", ["task_id"])
    op.create_index("ix_work_task_comments_author_id", "work_task_comments", ["author_id"])
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id", ondelete="CASCADE")),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("work_tasks.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(50), nullable=False), sa.Column("title", sa.String(220), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("target_url", sa.String(500)),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("read_at", sa.DateTime()),
        sa.Column("email_status", sa.Enum("not_requested","pending","sent","failed",name="notificationemailstatus",native_enum=False,length=30), nullable=False),
        sa.Column("email_attempted_at", sa.DateTime()), sa.Column("email_sent_at", sa.DateTime()), sa.Column("email_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("length(trim(kind)) > 0", name="ck_notification_kind_present"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_notification_title_present"),
        sa.CheckConstraint("length(trim(message)) > 0", name="ck_notification_message_present"),
    )
    for column in ("user_id","department_id","task_id","kind","is_read","email_status","created_at"):
        op.create_index(f"ix_user_notifications_{column}", "user_notifications", [column])


def downgrade() -> None:
    op.drop_table("user_notifications")
    op.drop_table("work_task_comments")
    op.drop_table("work_tasks")
    op.drop_table("work_task_counters")
    op.drop_table("project_team_members")

    op.drop_constraint("uq_store_item_department_code", "store_items", type_="unique")
    op.drop_index("ix_store_items_code", table_name="store_items")
    op.create_index("ix_store_items_code", "store_items", ["code"], unique=True)
    op.drop_constraint("uq_store_warehouse_department_name", "store_warehouses", type_="unique")
    op.drop_index("uq_store_one_main_warehouse", table_name="store_warehouses")
    op.create_index("uq_store_one_main_warehouse", "store_warehouses", ["warehouse_type"], unique=True, postgresql_where=sa.text("warehouse_type = 'main'"), sqlite_where=sa.text("warehouse_type = 'main'"))
    op.drop_index("ix_store_warehouses_name", table_name="store_warehouses")
    op.create_index("ix_store_warehouses_name", "store_warehouses", ["name"], unique=True)

    op.drop_table("pricing_category_user_access")
    op.drop_index("uq_pricing_category_child_department_name", table_name="pricing_item_categories")
    op.drop_index("uq_pricing_category_root_department_name", table_name="pricing_item_categories")
    op.drop_constraint("ck_pricing_category_visibility", "pricing_item_categories", type_="check")
    op.drop_column("pricing_item_categories", "visibility")
    op.drop_index("ix_pricing_item_categories_name", table_name="pricing_item_categories")
    op.create_index("ix_pricing_item_categories_name", "pricing_item_categories", ["name"], unique=True)
    op.drop_constraint("uq_pricing_item_department_name_model", "pricing_items", type_="unique")
    op.create_unique_constraint("uq_pricing_item_name_model", "pricing_items", ["name", "model"])

    for table in reversed(DEPARTMENT_TABLES):
        op.drop_index(f"ix_{table}_department_id", table_name=table)
        op.drop_constraint(f"fk_{table}_department_id", table, type_="foreignkey")
        op.drop_column(table, "department_id")

    op.drop_table("user_department_permissions")
    op.drop_table("department_permissions")
    op.drop_table("user_departments")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email_notifications")
    op.drop_column("users", "email")
    op.drop_table("departments")
