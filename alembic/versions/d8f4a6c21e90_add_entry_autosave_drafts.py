"""add entry autosave drafts

Revision ID: d8f4a6c21e90
Revises: b4e8d3c71a26
"""

from alembic import op
import sqlalchemy as sa


revision = "d8f4a6c21e90"
down_revision = "b4e8d3c71a26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "entry_drafts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("draft_key", sa.String(180), nullable=False),
        sa.Column("page_url", sa.String(500), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(trim(draft_key)) > 0", name="ck_entry_drafts_key_present"
        ),
        sa.CheckConstraint(
            "length(trim(page_url)) > 0", name="ck_entry_drafts_page_url_present"
        ),
        sa.UniqueConstraint(
            "user_id", "draft_key", name="uq_entry_drafts_user_key"
        ),
    )
    op.create_index("ix_entry_drafts_user_id", "entry_drafts", ["user_id"])
    op.create_index("ix_entry_drafts_updated_at", "entry_drafts", ["updated_at"])
    op.create_index("ix_entry_drafts_expires_at", "entry_drafts", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_entry_drafts_expires_at", table_name="entry_drafts")
    op.drop_index("ix_entry_drafts_updated_at", table_name="entry_drafts")
    op.drop_index("ix_entry_drafts_user_id", table_name="entry_drafts")
    op.drop_table("entry_drafts")
