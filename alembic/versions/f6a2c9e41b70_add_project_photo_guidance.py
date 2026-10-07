"""add project photo guidance

Revision ID: f6a2c9e41b70
Revises: c8e4f2a91d73
"""

from alembic import op
import sqlalchemy as sa


revision = "f6a2c9e41b70"
down_revision = "c8e4f2a91d73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_photo_guidance_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_project_photo_guidance_settings_project_id",
        "project_photo_guidance_settings",
        ["project_id"],
        unique=True,
    )

    op.create_table(
        "project_photo_guidance_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pricing_item_id",
            sa.Integer(),
            sa.ForeignKey("pricing_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "work_site_id",
            sa.Integer(),
            sa.ForeignKey("work_sites.id", ondelete="CASCADE"),
        ),
        sa.Column("before_alert", sa.Text()),
        sa.Column("after_alert", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_project_photo_guidance_rules_project_id",
        "project_photo_guidance_rules",
        ["project_id"],
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

    op.create_table(
        "project_photo_guidance_descriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey("project_photo_guidance_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stage", sa.String(length=10), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "stage IN ('before', 'after')", name="ck_photo_guidance_description_stage"
        ),
        sa.CheckConstraint(
            "length(trim(description)) > 0", name="ck_photo_guidance_description_present"
        ),
        sa.UniqueConstraint(
            "rule_id", "stage", "position", name="uq_photo_guidance_description_position"
        ),
    )
    op.create_index(
        "ix_project_photo_guidance_descriptions_rule_id",
        "project_photo_guidance_descriptions",
        ["rule_id"],
    )


def downgrade() -> None:
    op.drop_table("project_photo_guidance_descriptions")
    op.drop_table("project_photo_guidance_rules")
    op.drop_table("project_photo_guidance_settings")
