"""make photo guidance profiles independent from pricing items

Revision ID: b4e8d3c71a26
Revises: f6a2c9e41b70
"""

from alembic import op
import sqlalchemy as sa


revision = "b4e8d3c71a26"
down_revision = "f6a2c9e41b70"
branch_labels = None
depends_on = None


ITEM_TABLES = (
    "installation_record_items",
    "maintenance_record_items",
    "general_maintenance_items",
)


def upgrade() -> None:
    op.add_column("project_photo_guidance_rules", sa.Column("name", sa.String(160)))
    op.execute(
        """
        UPDATE project_photo_guidance_rules AS rules
        SET name = (CASE
            WHEN NULLIF(BTRIM(items.model), '') IS NULL THEN items.name
            ELSE items.name || ' - ' || items.model
        END) || CASE
            WHEN rules.work_site_id IS NULL THEN ''
            ELSE ' - Site ' || CAST(rules.work_site_id AS VARCHAR)
        END
        FROM pricing_items AS items
        WHERE items.id = rules.pricing_item_id
        """
    )
    op.alter_column("project_photo_guidance_rules", "name", nullable=False)
    op.create_check_constraint(
        "ck_photo_guidance_profile_name_present",
        "project_photo_guidance_rules",
        "length(trim(name)) > 0",
    )
    op.create_unique_constraint(
        "uq_photo_guidance_project_profile_name",
        "project_photo_guidance_rules",
        ["project_id", "name"],
    )
    op.drop_index("uq_photo_guidance_project_item_site", table_name="project_photo_guidance_rules")
    op.drop_index("uq_photo_guidance_project_item_default", table_name="project_photo_guidance_rules")
    op.drop_index("ix_project_photo_guidance_rules_work_site_id", table_name="project_photo_guidance_rules")
    op.drop_index("ix_project_photo_guidance_rules_pricing_item_id", table_name="project_photo_guidance_rules")
    op.drop_constraint(
        "project_photo_guidance_rules_work_site_id_fkey",
        "project_photo_guidance_rules",
        type_="foreignkey",
    )
    op.drop_constraint(
        "project_photo_guidance_rules_pricing_item_id_fkey",
        "project_photo_guidance_rules",
        type_="foreignkey",
    )
    op.drop_column("project_photo_guidance_rules", "work_site_id")
    op.drop_column("project_photo_guidance_rules", "pricing_item_id")

    for table in ITEM_TABLES:
        op.add_column(table, sa.Column("photo_guidance_profile_id", sa.Integer()))
        op.create_index(
            f"ix_{table}_photo_guidance_profile_id",
            table,
            ["photo_guidance_profile_id"],
        )
        op.create_foreign_key(
            f"fk_{table}_photo_guidance_profile_id",
            table,
            "project_photo_guidance_rules",
            ["photo_guidance_profile_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for table in reversed(ITEM_TABLES):
        op.drop_constraint(
            f"fk_{table}_photo_guidance_profile_id", table, type_="foreignkey"
        )
        op.drop_index(f"ix_{table}_photo_guidance_profile_id", table_name=table)
        op.drop_column(table, "photo_guidance_profile_id")

    op.add_column(
        "project_photo_guidance_rules",
        sa.Column("pricing_item_id", sa.Integer()),
    )
    op.add_column(
        "project_photo_guidance_rules",
        sa.Column("work_site_id", sa.Integer()),
    )
    op.execute(
        """
        UPDATE project_photo_guidance_rules
        SET pricing_item_id = (
            SELECT MIN(id) FROM pricing_items
            WHERE service_enabled IS TRUE AND device_catalog_id IS NOT NULL
        )
        """
    )
    op.alter_column("project_photo_guidance_rules", "pricing_item_id", nullable=False)
    op.create_foreign_key(
        "project_photo_guidance_rules_pricing_item_id_fkey",
        "project_photo_guidance_rules",
        "pricing_items",
        ["pricing_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_photo_guidance_rules_work_site_id_fkey",
        "project_photo_guidance_rules",
        "work_sites",
        ["work_site_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_project_photo_guidance_rules_pricing_item_id",
        "project_photo_guidance_rules",
        ["pricing_item_id"],
    )
    op.create_index(
        "ix_project_photo_guidance_rules_work_site_id",
        "project_photo_guidance_rules",
        ["work_site_id"],
    )
    op.create_index(
        "uq_photo_guidance_project_item_default",
        "project_photo_guidance_rules",
        ["project_id", "pricing_item_id"],
        unique=True,
        postgresql_where=sa.text("work_site_id IS NULL"),
    )
    op.create_index(
        "uq_photo_guidance_project_item_site",
        "project_photo_guidance_rules",
        ["project_id", "pricing_item_id", "work_site_id"],
        unique=True,
        postgresql_where=sa.text("work_site_id IS NOT NULL"),
    )
    op.drop_constraint(
        "uq_photo_guidance_project_profile_name",
        "project_photo_guidance_rules",
        type_="unique",
    )
    op.drop_constraint(
        "ck_photo_guidance_profile_name_present",
        "project_photo_guidance_rules",
        type_="check",
    )
    op.drop_column("project_photo_guidance_rules", "name")
