"""Add saved hierarchical reports and imported device metadata.

Revision ID: e9b4c7a21d36
Revises: c4d8e2f71a90
Create Date: 2026-08-09
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e9b4c7a21d36"
down_revision: Union[str, Sequence[str], None] = "c4d8e2f71a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RECORD_TABLES = (
    "installation_records",
    "maintenance_records",
    "general_maintenance_records",
)
PHOTO_TABLES = (
    "installation_photos",
    "maintenance_photos",
    "installation_item_photos",
    "maintenance_item_photos",
    "general_maintenance_photos",
)


def _report_type_enum() -> sa.Enum:
    return sa.Enum(
        "installation",
        "general_maintenance",
        "maintenance",
        name="servicereporttype",
        native_enum=False,
        length=30,
    )


def upgrade() -> None:
    for table in RECORD_TABLES:
        op.add_column(table, sa.Column("sub_project_id", sa.Integer(), nullable=True))
        op.add_column(table, sa.Column("sub_project_name", sa.String(length=160), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_sub_project_id",
            table,
            "sub_projects",
            ["sub_project_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(op.f(f"ix_{table}_sub_project_id"), table, ["sub_project_id"])
        op.create_index(op.f(f"ix_{table}_sub_project_name"), table, ["sub_project_name"])

    for table in RECORD_TABLES:
        op.execute(
            sa.text(
                f"""
                UPDATE {table} AS record
                SET sub_project_id = sub_project.id,
                    sub_project_name = sub_project.name
                FROM sub_projects AS sub_project
                WHERE sub_project.project_id = record.site_id
                  AND sub_project.name = 'General'
                """
            )
        )

    for table in PHOTO_TABLES:
        op.add_column(table, sa.Column("description", sa.Text(), nullable=True))
        op.add_column(
            table,
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column(table, "position", server_default=None)

    op.add_column("installed_devices", sa.Column("sub_project_id", sa.Integer(), nullable=True))
    op.add_column("installed_devices", sa.Column("sub_project_name", sa.String(length=160), nullable=True))
    op.add_column("installed_devices", sa.Column("imei", sa.String(length=15), nullable=True))
    op.add_column("installed_devices", sa.Column("iccid", sa.String(length=22), nullable=True))
    op.add_column("installed_devices", sa.Column("sim_type", sa.String(length=20), nullable=True))
    op.add_column("installed_devices", sa.Column("phone_number", sa.String(length=40), nullable=True))
    op.add_column("installed_devices", sa.Column("remarks", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_installed_devices_sub_project_id",
        "installed_devices",
        "sub_projects",
        ["sub_project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_installed_devices_sub_project_id"), "installed_devices", ["sub_project_id"])
    op.create_index(op.f("ix_installed_devices_sub_project_name"), "installed_devices", ["sub_project_name"])
    op.create_index(op.f("ix_installed_devices_imei"), "installed_devices", ["imei"], unique=True)
    op.create_index(op.f("ix_installed_devices_iccid"), "installed_devices", ["iccid"], unique=True)
    op.create_index(op.f("ix_installed_devices_sim_type"), "installed_devices", ["sim_type"])
    op.create_check_constraint(
        "ck_installed_devices_sim_type",
        "installed_devices",
        "sim_type IS NULL OR sim_type IN ('zain', 'mobily', 'stc')",
    )

    op.execute(
        sa.text(
            """
            UPDATE installed_devices AS device
            SET sub_project_id = sub_project.id,
                sub_project_name = sub_project.name
            FROM sub_projects AS sub_project
            WHERE sub_project.project_id = device.site_id
              AND sub_project.name = 'General'
            """
        )
    )

    op.create_table(
        "service_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_number", sa.String(length=30), nullable=False),
        sa.Column("report_type", _report_type_enum(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_by_name", sa.String(length=120), nullable=False),
        sa.Column("team_leader_id", sa.Integer(), nullable=False),
        sa.Column("team_leader_name", sa.String(length=120), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("include_device_data", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_service_report_name_present"),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name="fk_service_reports_created_by_id", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["team_leader_id"], ["users.id"], name="fk_service_reports_team_leader_id", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_service_reports_report_number"), "service_reports", ["report_number"], unique=True)
    op.create_index(op.f("ix_service_reports_report_type"), "service_reports", ["report_type"])
    op.create_index(op.f("ix_service_reports_created_by_id"), "service_reports", ["created_by_id"])
    op.create_index(op.f("ix_service_reports_team_leader_id"), "service_reports", ["team_leader_id"])
    op.create_index(op.f("ix_service_reports_report_date"), "service_reports", ["report_date"])
    op.create_index(op.f("ix_service_reports_created_at"), "service_reports", ["created_at"])

    op.create_table(
        "service_report_technicians",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"], ["service_reports.id"], name="fk_service_report_technicians_report_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_service_report_technicians_user_id", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_service_report_technicians_report_id"), "service_report_technicians", ["report_id"])
    op.create_index(op.f("ix_service_report_technicians_user_id"), "service_report_technicians", ["user_id"])

    op.create_table(
        "service_report_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("installation_record_id", sa.Integer(), nullable=True),
        sa.Column("maintenance_record_id", sa.Integer(), nullable=True),
        sa.Column("preventive_record_id", sa.Integer(), nullable=True),
        sa.Column("main_project_id", sa.Integer(), nullable=False),
        sa.Column("main_project_name", sa.String(length=160), nullable=False),
        sa.Column("customer_names", sa.Text(), nullable=True),
        sa.Column("sub_project_id", sa.Integer(), nullable=True),
        sa.Column("sub_project_name", sa.String(length=160), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("site_name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(CASE WHEN installation_record_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN maintenance_record_id IS NULL THEN 0 ELSE 1 END + "
            "CASE WHEN preventive_record_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_service_report_record_one_source",
        ),
        sa.ForeignKeyConstraint(["installation_record_id"], ["installation_records.id"], name="fk_service_report_records_installation_record_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["maintenance_record_id"], ["general_maintenance_records.id"], name="fk_service_report_records_maintenance_record_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["preventive_record_id"], ["maintenance_records.id"], name="fk_service_report_records_preventive_record_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["main_project_id"], ["sites.id"], name="fk_service_report_records_main_project_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sub_project_id"], ["sub_projects.id"], name="fk_service_report_records_sub_project_id", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["work_sites.id"], name="fk_service_report_records_site_id", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["report_id"], ["service_reports.id"], name="fk_service_report_records_report_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", "installation_record_id", name="uq_report_installation_record"),
        sa.UniqueConstraint("report_id", "maintenance_record_id", name="uq_report_maintenance_record"),
        sa.UniqueConstraint("report_id", "preventive_record_id", name="uq_report_preventive_record"),
        sa.UniqueConstraint("report_id", "position", name="uq_report_record_position"),
    )
    for column in (
        "report_id",
        "installation_record_id",
        "maintenance_record_id",
        "preventive_record_id",
        "main_project_id",
        "main_project_name",
        "sub_project_id",
        "sub_project_name",
        "site_id",
        "site_name",
    ):
        op.create_index(op.f(f"ix_service_report_records_{column}"), "service_report_records", [column])

    op.create_table(
        "service_report_counters",
        sa.Column("report_type", _report_type_enum(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("report_type", "year"),
    )

    op.add_column("installed_devices", sa.Column("source_report_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_installed_devices_source_report_id",
        "installed_devices",
        "service_reports",
        ["source_report_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_installed_devices_source_report_id"), "installed_devices", ["source_report_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_installed_devices_source_report_id"), table_name="installed_devices")
    op.drop_constraint("fk_installed_devices_source_report_id", "installed_devices", type_="foreignkey")
    op.drop_column("installed_devices", "source_report_id")

    op.drop_table("service_report_counters")
    for column in reversed((
        "report_id",
        "installation_record_id",
        "maintenance_record_id",
        "preventive_record_id",
        "main_project_id",
        "main_project_name",
        "sub_project_id",
        "sub_project_name",
        "site_id",
        "site_name",
    )):
        op.drop_index(op.f(f"ix_service_report_records_{column}"), table_name="service_report_records")
    op.drop_table("service_report_records")
    op.drop_index(op.f("ix_service_report_technicians_user_id"), table_name="service_report_technicians")
    op.drop_index(op.f("ix_service_report_technicians_report_id"), table_name="service_report_technicians")
    op.drop_table("service_report_technicians")
    op.drop_index(op.f("ix_service_reports_created_at"), table_name="service_reports")
    op.drop_index(op.f("ix_service_reports_report_date"), table_name="service_reports")
    op.drop_index(op.f("ix_service_reports_team_leader_id"), table_name="service_reports")
    op.drop_index(op.f("ix_service_reports_created_by_id"), table_name="service_reports")
    op.drop_index(op.f("ix_service_reports_report_type"), table_name="service_reports")
    op.drop_index(op.f("ix_service_reports_report_number"), table_name="service_reports")
    op.drop_table("service_reports")

    op.drop_constraint("ck_installed_devices_sim_type", "installed_devices", type_="check")
    op.drop_index(op.f("ix_installed_devices_sim_type"), table_name="installed_devices")
    op.drop_index(op.f("ix_installed_devices_iccid"), table_name="installed_devices")
    op.drop_index(op.f("ix_installed_devices_imei"), table_name="installed_devices")
    op.drop_index(op.f("ix_installed_devices_sub_project_name"), table_name="installed_devices")
    op.drop_index(op.f("ix_installed_devices_sub_project_id"), table_name="installed_devices")
    op.drop_constraint("fk_installed_devices_sub_project_id", "installed_devices", type_="foreignkey")
    for column in ("remarks", "phone_number", "sim_type", "iccid", "imei", "sub_project_name", "sub_project_id"):
        op.drop_column("installed_devices", column)

    for table in reversed(PHOTO_TABLES):
        op.drop_column(table, "position")
        op.drop_column(table, "description")

    for table in reversed(RECORD_TABLES):
        op.drop_index(op.f(f"ix_{table}_sub_project_name"), table_name=table)
        op.drop_index(op.f(f"ix_{table}_sub_project_id"), table_name=table)
        op.drop_constraint(f"fk_{table}_sub_project_id", table, type_="foreignkey")
        op.drop_column(table, "sub_project_name")
        op.drop_column(table, "sub_project_id")
