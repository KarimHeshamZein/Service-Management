"""add browser entry data rows

Revision ID: c8e4f2a91d73
Revises: e7c2a91bd460
"""

from alembic import op
import sqlalchemy as sa


revision = "c8e4f2a91d73"
down_revision = "e7c2a91bd460"
branch_labels = None
depends_on = None


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column("scope_position", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="RESTRICT")),
        sa.Column("project_name", sa.String(length=160), nullable=False),
        sa.Column("sub_project_id", sa.Integer(), sa.ForeignKey("sub_projects.id", ondelete="SET NULL")),
        sa.Column("sub_project_name", sa.String(length=160), nullable=False),
        sa.Column("work_site_id", sa.Integer(), sa.ForeignKey("work_sites.id", ondelete="RESTRICT")),
        sa.Column("work_site_name", sa.String(length=120), nullable=False),
    ]


def _scope_indexes(table: str) -> None:
    for column in (
        "record_id",
        "scope_position",
        "project_id",
        "project_name",
        "sub_project_id",
        "sub_project_name",
        "work_site_id",
        "work_site_name",
    ):
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "installation_data_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "record_id",
            sa.Integer(),
            sa.ForeignKey("installation_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *_scope_columns(),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("model", sa.String(length=160)),
        sa.Column("serial_number", sa.String(length=160)),
        sa.Column("imei", sa.String(length=40)),
        sa.Column("iccid", sa.String(length=40)),
        sa.Column("sim_type", sa.String(length=20)),
        sa.Column("remarks", sa.Text()),
        sa.CheckConstraint("length(trim(item_name)) > 0", name="ck_installation_data_item_present"),
        sa.CheckConstraint("position >= 0", name="ck_installation_data_position_nonnegative"),
        sa.CheckConstraint("scope_position >= 0", name="ck_installation_data_scope_nonnegative"),
    )
    _scope_indexes("installation_data_rows")
    op.create_index(
        "ix_installation_data_rows_serial_number",
        "installation_data_rows",
        ["serial_number"],
    )

    for table, parent in (
        ("maintenance_data_rows", "maintenance_records"),
        ("general_maintenance_data_rows", "general_maintenance_records"),
    ):
        prefix = "general_maintenance" if table.startswith("general_") else "maintenance"
        op.create_table(
            table,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "record_id",
                sa.Integer(),
                sa.ForeignKey(f"{parent}.id", ondelete="CASCADE"),
                nullable=False,
            ),
            *_scope_columns(),
            sa.Column("item_name", sa.String(length=160), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("notes", sa.Text()),
            sa.CheckConstraint(
                "length(trim(item_name)) > 0",
                name=f"ck_{prefix}_data_item_present",
            ),
            sa.CheckConstraint(
                "quantity > 0",
                name=f"ck_{prefix}_data_quantity_positive",
            ),
            sa.CheckConstraint(
                "position >= 0",
                name=f"ck_{prefix}_data_position_nonnegative",
            ),
            sa.CheckConstraint(
                "scope_position >= 0",
                name=f"ck_{prefix}_data_scope_nonnegative",
            ),
        )
        _scope_indexes(table)

    for table in ("maintenance_record_items", "general_maintenance_items"):
        op.alter_column(
            table,
            "device_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        op.alter_column(
            table,
            "device_model",
            existing_type=sa.String(length=120),
            nullable=True,
        )


def downgrade() -> None:
    connection = op.get_bind()
    fallback_device_id = connection.execute(
        sa.text("SELECT min(id) FROM device_catalog")
    ).scalar()
    missing_devices = sum(
        connection.execute(
            sa.text(f"SELECT count(*) FROM {table} WHERE device_id IS NULL")
        ).scalar_one()
        for table in ("maintenance_record_items", "general_maintenance_items")
    )
    if missing_devices and fallback_device_id is None:
        raise RuntimeError("Cannot downgrade browser-only maintenance rows without a catalog device.")
    for table in ("maintenance_record_items", "general_maintenance_items"):
        if fallback_device_id is not None:
            connection.execute(
                sa.text(
                    f"UPDATE {table} SET device_id = :device_id "
                    "WHERE device_id IS NULL"
                ),
                {"device_id": fallback_device_id},
            )
        connection.execute(
            sa.text(
                f"UPDATE {table} SET device_model = service_name "
                "WHERE device_model IS NULL OR length(trim(device_model)) = 0"
            )
        )
        op.alter_column(
            table,
            "device_model",
            existing_type=sa.String(length=120),
            nullable=False,
        )
        op.alter_column(
            table,
            "device_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    op.drop_table("general_maintenance_data_rows")
    op.drop_table("maintenance_data_rows")
    op.drop_table("installation_data_rows")
