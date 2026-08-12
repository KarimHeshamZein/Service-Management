"""add item site scope snapshots

Revision ID: a3f8d1c62b04
Revises: f2a6c9d14e73
"""

from alembic import op
import sqlalchemy as sa


revision = "a3f8d1c62b04"
down_revision = "f2a6c9d14e73"
branch_labels = None
depends_on = None


TABLES = (
    ("installation_record_items", "installation_records", False),
    ("maintenance_record_items", "maintenance_records", False),
    ("general_maintenance_items", "general_maintenance_records", True),
)


def upgrade() -> None:
    for table, record_table, direct_work_site in TABLES:
        op.add_column(table, sa.Column("scope_position", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("project_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("project_name", sa.String(length=160), nullable=True))
        op.add_column(table, sa.Column("project_address", sa.String(length=255), nullable=True))
        op.add_column(table, sa.Column("sub_project_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("sub_project_name", sa.String(length=160), nullable=True))
        op.add_column(table, sa.Column("work_site_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("work_site_name", sa.String(length=120), nullable=True))
        op.add_column(table, sa.Column("quotation_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("quotation_number", sa.String(length=30), nullable=True))
        op.create_foreign_key(f"fk_{table}_project_id", table, "sites", ["project_id"], ["id"], ondelete="RESTRICT")
        op.create_foreign_key(f"fk_{table}_sub_project_id", table, "sub_projects", ["sub_project_id"], ["id"], ondelete="SET NULL")
        op.create_foreign_key(f"fk_{table}_work_site_id", table, "work_sites", ["work_site_id"], ["id"], ondelete="RESTRICT")
        op.create_foreign_key(f"fk_{table}_quotation_id", table, "pricing_quotations", ["quotation_id"], ["id"], ondelete="SET NULL")
        for column in ("scope_position", "project_id", "project_name", "sub_project_id", "sub_project_name", "work_site_id", "work_site_name", "quotation_id", "quotation_number"):
            op.create_index(f"ix_{table}_{column}", table, [column])

        work_site_expr = "r.work_site_id" if direct_work_site else (
            f"(SELECT s.site_id FROM {'installation_record_sites' if table.startswith('installation') else 'maintenance_record_sites'} s WHERE s.record_id = r.id)"
        )
        op.execute(sa.text(f"""
            UPDATE {table} i
               SET scope_position = 0,
                   project_id = r.site_id,
                   project_name = {'r.project_name' if direct_work_site else 'r.customer_name'},
                   project_address = {'r.project_address' if direct_work_site else 'r.site_address'},
                   sub_project_id = r.sub_project_id,
                   sub_project_name = r.sub_project_name,
                   work_site_id = {work_site_expr},
                   work_site_name = r.site_name,
                   quotation_id = r.quotation_id,
                   quotation_number = r.quotation_number
              FROM {record_table} r
             WHERE i.record_id = r.id
        """))


def downgrade() -> None:
    for table, _record_table, _direct_work_site in reversed(TABLES):
        for column in reversed(("scope_position", "project_id", "project_name", "sub_project_id", "sub_project_name", "work_site_id", "work_site_name", "quotation_id", "quotation_number")):
            op.drop_index(f"ix_{table}_{column}", table_name=table)
        for column in ("quotation_id", "work_site_id", "sub_project_id", "project_id"):
            op.drop_constraint(f"fk_{table}_{column}", table, type_="foreignkey")
        for column in reversed(("scope_position", "project_id", "project_name", "project_address", "sub_project_id", "sub_project_name", "work_site_id", "work_site_name", "quotation_id", "quotation_number")):
            op.drop_column(table, column)
