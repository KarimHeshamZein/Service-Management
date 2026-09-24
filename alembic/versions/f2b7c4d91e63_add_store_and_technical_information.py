"""Add independent Store and pricing technical information.

Revision ID: f2b7c4d91e63
Revises: c6a4e8f21d90
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "f2b7c4d91e63"
down_revision = "c6a4e8f21d90"
branch_labels = None
depends_on = None


def _user_permissions(add: bool) -> None:
    names = ("technical_documents_manage","store_access","store_receive","store_issue","store_transfer","store_custody_transfer","store_manage_items","store_manage_warehouses","store_adjust","store_reports")
    if add:
        for name in names:
            op.add_column("users", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
        op.alter_column("users", "technical_documents_manage", server_default=None)
        for name in names[1:]: op.alter_column("users", name, server_default=None)
    else:
        for name in reversed(names): op.drop_column("users", name)


def upgrade() -> None:
    _user_permissions(True)
    op.create_table("store_warehouses",
        sa.Column("id",sa.Integer(),primary_key=True), sa.Column("name",sa.String(160),nullable=False),
        sa.Column("warehouse_type",sa.Enum("main","branch",name="storewarehousetype",native_enum=False,length=20),nullable=False),
        sa.Column("location",sa.String(255)),sa.Column("notes",sa.Text()),sa.Column("is_active",sa.Boolean(),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0",name="ck_store_warehouse_name_present"))
    op.create_index("ix_store_warehouses_name","store_warehouses",["name"],unique=True); op.create_index("ix_store_warehouses_warehouse_type","store_warehouses",["warehouse_type"]); op.create_index("ix_store_warehouses_is_active","store_warehouses",["is_active"])
    op.create_index("uq_store_one_main_warehouse","store_warehouses",["warehouse_type"],unique=True,postgresql_where=sa.text("warehouse_type = 'main'"),sqlite_where=sa.text("warehouse_type = 'main'"))
    op.create_table("store_user_warehouses",sa.Column("user_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="CASCADE"),primary_key=True),sa.Column("warehouse_id",sa.Integer(),sa.ForeignKey("store_warehouses.id",ondelete="CASCADE"),primary_key=True))
    op.create_table("store_items",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("name",sa.String(160),nullable=False),sa.Column("model",sa.String(160)),sa.Column("serial_number",sa.String(160)),sa.Column("code",sa.String(80)),sa.Column("unit",sa.String(40),nullable=False),sa.Column("minimum_stock",sa.Numeric(14,2),nullable=False),sa.Column("image_storage_key",sa.String(255)),sa.Column("image_original_filename",sa.String(255)),sa.Column("notes",sa.Text()),sa.Column("is_active",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),sa.CheckConstraint("length(trim(name)) > 0",name="ck_store_item_name_present"),sa.CheckConstraint("minimum_stock >= 0",name="ck_store_item_minimum_nonnegative"),sa.UniqueConstraint("image_storage_key"))
    for c in ("name","model","serial_number","code","is_active"): op.create_index(f"ix_store_items_{c}","store_items",[c],unique=(c=="code"))
    op.create_table("store_stock_balances",sa.Column("warehouse_id",sa.Integer(),sa.ForeignKey("store_warehouses.id",ondelete="CASCADE"),primary_key=True),sa.Column("item_id",sa.Integer(),sa.ForeignKey("store_items.id",ondelete="CASCADE"),primary_key=True),sa.Column("quantity",sa.Numeric(16,2),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),sa.CheckConstraint("quantity >= 0",name="ck_store_stock_nonnegative"))
    op.create_table("store_custody_balances",sa.Column("technician_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),primary_key=True),sa.Column("item_id",sa.Integer(),sa.ForeignKey("store_items.id",ondelete="CASCADE"),primary_key=True),sa.Column("quantity",sa.Numeric(16,2),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),sa.CheckConstraint("quantity >= 0",name="ck_store_custody_nonnegative"))
    op.create_table("store_movements",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("movement_number",sa.String(40),nullable=False),sa.Column("movement_type",sa.Enum("opening","purchase","project_issue","warehouse_transfer","custody_issue","custody_return","custody_project_issue","adjustment","reversal",name="storemovementtype",native_enum=False,length=40),nullable=False),sa.Column("source_warehouse_id",sa.Integer(),sa.ForeignKey("store_warehouses.id",ondelete="RESTRICT")),sa.Column("destination_warehouse_id",sa.Integer(),sa.ForeignKey("store_warehouses.id",ondelete="RESTRICT")),sa.Column("technician_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT")),sa.Column("project_name",sa.String(200)),sa.Column("reason",sa.Text()),sa.Column("reversed_movement_id",sa.Integer(),sa.ForeignKey("store_movements.id",ondelete="RESTRICT")),sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("created_by_name",sa.String(120),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False),sa.UniqueConstraint("reversed_movement_id"))
    for c in ("movement_number","movement_type","source_warehouse_id","destination_warehouse_id","technician_id","project_name","created_by_id","created_at"): op.create_index(f"ix_store_movements_{c}","store_movements",[c],unique=(c=="movement_number"))
    op.create_table("store_movement_lines",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("movement_id",sa.Integer(),sa.ForeignKey("store_movements.id",ondelete="CASCADE"),nullable=False),sa.Column("item_id",sa.Integer(),sa.ForeignKey("store_items.id",ondelete="RESTRICT"),nullable=False),sa.Column("quantity",sa.Numeric(16,2),nullable=False),sa.Column("source_before",sa.Numeric(16,2)),sa.Column("source_after",sa.Numeric(16,2)),sa.Column("destination_before",sa.Numeric(16,2)),sa.Column("destination_after",sa.Numeric(16,2)),sa.Column("position",sa.Integer(),nullable=False),sa.CheckConstraint("quantity > 0",name="ck_store_movement_line_quantity_positive"),sa.UniqueConstraint("movement_id","position",name="uq_store_movement_line_position"))
    op.create_index("ix_store_movement_lines_movement_id","store_movement_lines",["movement_id"]); op.create_index("ix_store_movement_lines_item_id","store_movement_lines",["item_id"])
    op.create_table("technical_documents",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("pricing_item_id",sa.Integer(),sa.ForeignKey("pricing_items.id",ondelete="CASCADE")),sa.Column("related_item_id",sa.Integer(),sa.ForeignKey("pricing_related_items.id",ondelete="CASCADE")),sa.Column("title",sa.String(180),nullable=False),sa.Column("notes",sa.Text()),sa.Column("storage_key",sa.String(255),nullable=False),sa.Column("original_filename",sa.String(255),nullable=False),sa.Column("content_type",sa.String(60),nullable=False),sa.Column("file_size",sa.Integer(),nullable=False),sa.Column("uploaded_by_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("uploaded_by_name",sa.String(120),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),sa.CheckConstraint("(CASE WHEN pricing_item_id IS NULL THEN 0 ELSE 1 END + CASE WHEN related_item_id IS NULL THEN 0 ELSE 1 END) = 1",name="ck_technical_document_one_target"),sa.CheckConstraint("file_size > 0",name="ck_technical_document_file_size_positive"),sa.UniqueConstraint("storage_key"))
    for c in ("pricing_item_id","related_item_id","created_at"): op.create_index(f"ix_technical_documents_{c}","technical_documents",[c])
    op.create_table("technical_recommendations",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("pricing_item_id",sa.Integer(),sa.ForeignKey("pricing_items.id",ondelete="CASCADE")),sa.Column("related_item_id",sa.Integer(),sa.ForeignKey("pricing_related_items.id",ondelete="CASCADE")),sa.Column("recommendation",sa.Text(),nullable=False),sa.Column("updated_by_id",sa.Integer(),sa.ForeignKey("users.id",ondelete="RESTRICT"),nullable=False),sa.Column("updated_by_name",sa.String(120),nullable=False),sa.Column("updated_at",sa.DateTime(),nullable=False),sa.CheckConstraint("(CASE WHEN pricing_item_id IS NULL THEN 0 ELSE 1 END + CASE WHEN related_item_id IS NULL THEN 0 ELSE 1 END) = 1",name="ck_technical_recommendation_one_target"),sa.CheckConstraint("length(trim(recommendation)) > 0",name="ck_technical_recommendation_present"))
    op.create_index("ix_technical_recommendations_pricing_item_id","technical_recommendations",["pricing_item_id"],unique=True); op.create_index("ix_technical_recommendations_related_item_id","technical_recommendations",["related_item_id"],unique=True)
    op.create_table("quotation_technical_attachments",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("quotation_id",sa.Integer(),sa.ForeignKey("pricing_quotations.id",ondelete="CASCADE"),nullable=False),sa.Column("source_document_id",sa.Integer(),sa.ForeignKey("technical_documents.id",ondelete="SET NULL")),sa.Column("target_kind",sa.String(20),nullable=False),sa.Column("target_id",sa.Integer(),nullable=False),sa.Column("item_name",sa.String(180),nullable=False),sa.Column("title",sa.String(180),nullable=False),sa.Column("storage_key",sa.String(255)),sa.Column("original_filename",sa.String(255)),sa.Column("content_type",sa.String(60)),sa.Column("recommendation_snapshot",sa.Text()),sa.Column("position",sa.Integer(),nullable=False),sa.Column("created_at",sa.DateTime(),nullable=False),sa.CheckConstraint("target_kind IN ('main', 'related')",name="ck_quote_technical_target_kind"),sa.CheckConstraint("storage_key IS NOT NULL OR recommendation_snapshot IS NOT NULL",name="ck_quote_technical_has_content"),sa.UniqueConstraint("quotation_id","position",name="uq_quote_technical_position"))
    op.create_index("ix_quotation_technical_attachments_quotation_id","quotation_technical_attachments",["quotation_id"]); op.create_index("ix_quotation_technical_attachments_source_document_id","quotation_technical_attachments",["source_document_id"])


def downgrade() -> None:
    for table in ("quotation_technical_attachments","technical_recommendations","technical_documents","store_movement_lines","store_movements","store_custody_balances","store_stock_balances","store_items","store_user_warehouses","store_warehouses"):
        op.drop_table(table)
    _user_permissions(False)
