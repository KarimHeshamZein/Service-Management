"""make entry identifiers and notes optional

Revision ID: e7c2a91bd460
Revises: d5b9e2a74c16
"""

from alembic import op
import sqlalchemy as sa


revision = "e7c2a91bd460"
down_revision = "d5b9e2a74c16"
branch_labels = None
depends_on = None


SERIAL_TABLES = (
    "installation_records",
    "installed_devices",
    "installation_record_items",
    "maintenance_record_devices",
    "maintenance_record_additional_devices",
    "maintenance_record_items",
    "general_maintenance_items",
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_installation_serial_number_present",
        "installation_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_installation_notes_present",
        "installation_records",
        type_="check",
    )
    op.drop_constraint("ck_records_notes_present", "maintenance_records", type_="check")
    for table in SERIAL_TABLES:
        op.alter_column(
            table,
            "serial_number",
            existing_type=sa.String(length=160),
            nullable=True,
        )


def downgrade() -> None:
    for table in SERIAL_TABLES:
        op.execute(
            sa.text(
                f"UPDATE {table} SET serial_number = "
                f"'UNSPECIFIED-{table}-' || CAST(id AS VARCHAR) "
                "WHERE serial_number IS NULL OR length(trim(serial_number)) = 0"
            )
        )
        op.alter_column(
            table,
            "serial_number",
            existing_type=sa.String(length=160),
            nullable=False,
        )
    op.execute(
        sa.text(
            "UPDATE installation_records SET notes = 'Not provided' "
            "WHERE length(trim(notes)) = 0"
        )
    )
    op.execute(
        sa.text(
            "UPDATE maintenance_records SET notes = 'Not provided' "
            "WHERE length(trim(notes)) = 0"
        )
    )
    op.create_check_constraint(
        "ck_installation_serial_number_present",
        "installation_records",
        "length(trim(serial_number)) > 0",
    )
    op.create_check_constraint(
        "ck_installation_notes_present",
        "installation_records",
        "length(trim(notes)) > 0",
    )
    op.create_check_constraint(
        "ck_records_notes_present",
        "maintenance_records",
        "length(trim(notes)) > 0",
    )
