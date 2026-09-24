"""Add Product Evaluations and Testing workflow.

Revision ID: b9d4f6a21c80
Revises: a8c5e2f41d70
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "b9d4f6a21c80"
down_revision = "a8c5e2f41d70"
branch_labels = None
depends_on = None


def _index(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table("product_evaluation_counters", sa.Column("year",sa.Integer(),primary_key=True), sa.Column("last_sequence",sa.Integer(),nullable=False))
    op.create_table("product_evaluation_requests",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("request_number",sa.String(40),nullable=False),
        sa.Column("device_name",sa.String(180),nullable=False), sa.Column("manufacturer",sa.String(160)), sa.Column("model",sa.String(160),nullable=False), sa.Column("serial_number",sa.String(180)),
        sa.Column("customer_project_name",sa.String(220),nullable=False),
        sa.Column("sales_contact_user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="SET NULL")), sa.Column("sales_contact_name",sa.String(160),nullable=False),
        sa.Column("after_sales_user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="SET NULL")), sa.Column("after_sales_name",sa.String(160),nullable=False),
        sa.Column("assigned_admin_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False), sa.Column("assigned_admin_name",sa.String(120),nullable=False),
        sa.Column("reason",sa.Text(),nullable=False), sa.Column("requirements",sa.Text()),
        sa.Column("status",sa.Enum("pending_approval","changes_requested","rejected","waiting_for_device","device_received","evaluation_scheduled","evaluation_in_progress","evaluation_completed",name="productevaluationstatus",native_enum=False,length=40),nullable=False),
        sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False), sa.Column("created_by_name",sa.String(120),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False), sa.Column("updated_at",sa.DateTime(),nullable=False),
        sa.Column("approved_by_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="SET NULL")), sa.Column("approved_by_name",sa.String(120)), sa.Column("approved_at",sa.DateTime()), sa.Column("admin_notes",sa.Text()),
        sa.Column("received_by_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="SET NULL")), sa.Column("received_by_name",sa.String(120)), sa.Column("received_at",sa.DateTime()),
        sa.CheckConstraint("length(trim(device_name)) > 0",name="ck_product_eval_device_name_present"), sa.CheckConstraint("length(trim(model)) > 0",name="ck_product_eval_model_present"),
        sa.CheckConstraint("length(trim(customer_project_name)) > 0",name="ck_product_eval_customer_present"), sa.CheckConstraint("length(trim(reason)) > 0",name="ck_product_eval_reason_present"))
    op.create_index("ix_product_evaluation_requests_request_number", "product_evaluation_requests", ["request_number"], unique=True)
    _index("product_evaluation_requests","device_name","manufacturer","model","serial_number","customer_project_name","sales_contact_user_id","after_sales_user_id","assigned_admin_id","status","created_by_id","created_at")
    op.create_table("product_evaluation_request_attachments",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("request_id",sa.Integer(),sa.ForeignKey("product_evaluation_requests.id",ondelete="CASCADE"),nullable=False),
        sa.Column("storage_key",sa.String(255),nullable=False), sa.Column("original_filename",sa.String(255),nullable=False), sa.Column("content_type",sa.String(60),nullable=False), sa.Column("file_size",sa.Integer(),nullable=False), sa.Column("position",sa.Integer(),nullable=False), sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.CheckConstraint("file_size > 0",name="ck_product_eval_request_file_positive"), sa.UniqueConstraint("storage_key"), sa.UniqueConstraint("request_id","position",name="uq_product_eval_request_file_position"))
    _index("product_evaluation_request_attachments","request_id")
    op.create_table("product_evaluation_sessions",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("request_id",sa.Integer(),sa.ForeignKey("product_evaluation_requests.id",ondelete="CASCADE"),nullable=False), sa.Column("sequence",sa.Integer(),nullable=False),
        sa.Column("assigned_user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False), sa.Column("assigned_user_name",sa.String(120),nullable=False),
        sa.Column("assigned_by_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False), sa.Column("assigned_by_name",sa.String(120),nullable=False),
        sa.Column("scheduled_start_at",sa.DateTime()), sa.Column("due_at",sa.DateTime()), sa.Column("location",sa.String(220)), sa.Column("instructions",sa.Text()),
        sa.Column("status",sa.Enum("scheduled","in_progress","completed",name="productevaluationsessionstatus",native_enum=False,length=30),nullable=False),
        sa.Column("started_at",sa.DateTime()), sa.Column("completed_at",sa.DateTime()), sa.Column("tests_performed",sa.Text()), sa.Column("results",sa.Text()), sa.Column("strengths",sa.Text()), sa.Column("weaknesses",sa.Text()), sa.Column("issues_found",sa.Text()), sa.Column("compatibility",sa.Text()), sa.Column("recommendation",sa.Text()),
        sa.Column("performance_rating",sa.Integer()), sa.Column("quality_rating",sa.Integer()), sa.Column("installation_rating",sa.Integer()), sa.Column("compatibility_rating",sa.Integer()), sa.Column("value_rating",sa.Integer()),
        sa.Column("decision",sa.Enum("approved","approved_with_conditions","needs_more_testing","rejected",name="productevaluationdecision",native_enum=False,length=40)),
        sa.Column("created_at",sa.DateTime(),nullable=False), sa.Column("updated_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("request_id","sequence",name="uq_product_eval_session_sequence"),
        sa.CheckConstraint("performance_rating IS NULL OR performance_rating BETWEEN 1 AND 5",name="ck_product_eval_performance_rating"), sa.CheckConstraint("quality_rating IS NULL OR quality_rating BETWEEN 1 AND 5",name="ck_product_eval_quality_rating"), sa.CheckConstraint("installation_rating IS NULL OR installation_rating BETWEEN 1 AND 5",name="ck_product_eval_installation_rating"), sa.CheckConstraint("compatibility_rating IS NULL OR compatibility_rating BETWEEN 1 AND 5",name="ck_product_eval_compatibility_rating"), sa.CheckConstraint("value_rating IS NULL OR value_rating BETWEEN 1 AND 5",name="ck_product_eval_value_rating"))
    _index("product_evaluation_sessions","request_id","assigned_user_id","scheduled_start_at","due_at","status")
    op.create_table("product_evaluation_session_attachments",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("session_id",sa.Integer(),sa.ForeignKey("product_evaluation_sessions.id",ondelete="CASCADE"),nullable=False),
        sa.Column("storage_key",sa.String(255),nullable=False), sa.Column("original_filename",sa.String(255),nullable=False), sa.Column("content_type",sa.String(60),nullable=False), sa.Column("file_size",sa.Integer(),nullable=False), sa.Column("description",sa.Text()), sa.Column("position",sa.Integer(),nullable=False), sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.CheckConstraint("file_size > 0",name="ck_product_eval_session_file_positive"), sa.UniqueConstraint("storage_key"), sa.UniqueConstraint("session_id","position",name="uq_product_eval_session_file_position"))
    _index("product_evaluation_session_attachments","session_id")


def downgrade() -> None:
    for table in ("product_evaluation_session_attachments","product_evaluation_sessions","product_evaluation_request_attachments","product_evaluation_requests","product_evaluation_counters"):
        op.drop_table(table)
