"""add quotation references and scheduled backup settings

Revision ID: e85a1c3d72f4
Revises: d74f0b2c91e3
Create Date: 2026-07-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e85a1c3d72f4"
down_revision: Union[str, Sequence[str], None] = "d74f0b2c91e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RECORD_TABLES = (
    "maintenance_records",
    "installation_records",
    "general_maintenance_records",
)


def upgrade() -> None:
    for table in RECORD_TABLES:
        op.add_column(table, sa.Column("quotation_id", sa.Integer(), nullable=True))
        op.add_column(
            table, sa.Column("quotation_number", sa.String(length=30), nullable=True)
        )
        op.create_index(op.f(f"ix_{table}_quotation_id"), table, ["quotation_id"])
        op.create_foreign_key(
            f"fk_{table}_quotation_id_pricing_quotations",
            table,
            "pricing_quotations",
            ["quotation_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.add_column(
        "deployment_settings",
        sa.Column(
            "backup_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "deployment_settings",
        sa.Column(
            "backup_interval_days",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "deployment_settings",
        sa.Column(
            "backup_retention_count",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )
    op.add_column(
        "deployment_settings",
        sa.Column(
            "backup_directory",
            sa.String(length=500),
            nullable=False,
            server_default=r"C:\ServiceManagement\backups\scheduled",
        ),
    )
    op.add_column(
        "deployment_settings",
        sa.Column(
            "pg_dump_executable",
            sa.String(length=500),
            nullable=False,
            server_default=r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        ),
    )
    op.create_check_constraint(
        "ck_deployment_backup_interval",
        "deployment_settings",
        "backup_interval_days BETWEEN 1 AND 365",
    )
    op.create_check_constraint(
        "ck_deployment_backup_retention",
        "deployment_settings",
        "backup_retention_count BETWEEN 1 AND 365",
    )
    for column in (
        "backup_enabled",
        "backup_interval_days",
        "backup_retention_count",
        "backup_directory",
        "pg_dump_executable",
    ):
        op.alter_column("deployment_settings", column, server_default=None)


def downgrade() -> None:
    op.drop_constraint(
        "ck_deployment_backup_retention",
        "deployment_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_deployment_backup_interval",
        "deployment_settings",
        type_="check",
    )
    for column in (
        "pg_dump_executable",
        "backup_directory",
        "backup_retention_count",
        "backup_interval_days",
        "backup_enabled",
    ):
        op.drop_column("deployment_settings", column)

    for table in reversed(RECORD_TABLES):
        op.drop_constraint(
            f"fk_{table}_quotation_id_pricing_quotations",
            table,
            type_="foreignkey",
        )
        op.drop_index(op.f(f"ix_{table}_quotation_id"), table_name=table)
        op.drop_column(table, "quotation_number")
        op.drop_column(table, "quotation_id")
