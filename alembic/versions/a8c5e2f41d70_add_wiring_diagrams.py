"""Add independent wiring diagram library.

Revision ID: a8c5e2f41d70
Revises: f2b7c4d91e63
Create Date: 2026-08-27
"""
from alembic import op
import sqlalchemy as sa

revision = "a8c5e2f41d70"
down_revision = "f2b7c4d91e63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("wiring_diagrams_manage", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("users", "wiring_diagrams_manage", server_default=None)
    op.create_table(
        "wiring_diagram_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("wiring_diagram_categories.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_wiring_category_name_present"),
    )
    op.create_index("ix_wiring_diagram_categories_name", "wiring_diagram_categories", ["name"])
    op.create_index("ix_wiring_diagram_categories_parent_id", "wiring_diagram_categories", ["parent_id"])
    op.create_table(
        "wiring_diagrams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("wiring_diagram_categories.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("project_name", sa.String(200)),
        sa.Column("notes", sa.Text()),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_by_name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_wiring_diagram_name_present"),
    )
    for column in ("category_id", "name", "project_name", "created_at"):
        op.create_index(f"ix_wiring_diagrams_{column}", "wiring_diagrams", [column])
    op.create_table(
        "wiring_diagram_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("diagram_id", sa.Integer(), sa.ForeignKey("wiring_diagrams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(60), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("file_size > 0", name="ck_wiring_diagram_file_size_positive"),
        sa.UniqueConstraint("diagram_id", "position", name="uq_wiring_diagram_file_position"),
    )
    op.create_index("ix_wiring_diagram_files_diagram_id", "wiring_diagram_files", ["diagram_id"])


def downgrade() -> None:
    op.drop_table("wiring_diagram_files")
    op.drop_table("wiring_diagrams")
    op.drop_table("wiring_diagram_categories")
    op.drop_column("users", "wiring_diagrams_manage")
