"""add staged Windows deployment settings

Revision ID: f12c7b39a640
Revises: d84b2a9f4c10
Create Date: 2026-07-29 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f12c7b39a640"
down_revision: Union[str, Sequence[str], None] = "d84b2a9f4c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    settings_exists = inspector.has_table("deployment_settings")
    audit_exists = inspector.has_table("deployment_settings_audit")
    if settings_exists and audit_exists:
        # Older app startup code may have created new model tables before
        # Alembic ran. Verify the complete column sets before recording the
        # revision without attempting duplicate DDL.
        expected_settings = {
            "id",
            "public_enabled",
            "public_ip",
            "public_port",
            "allowed_remote_ips",
            "local_interface",
            "local_ip",
            "local_port",
            "configure_static_local_ip",
            "local_prefix_length",
            "local_gateway",
            "local_dns_servers",
            "internal_port",
            "postgres_host",
            "postgres_port",
            "configuration_version",
            "updated_by_id",
            "updated_by_name",
            "updated_at",
        }
        expected_audit = {
            "id",
            "configuration_version",
            "edited_by_id",
            "editor_name",
            "before_json",
            "after_json",
            "created_at",
        }
        actual_settings = {
            column["name"]
            for column in inspector.get_columns("deployment_settings")
        }
        actual_audit = {
            column["name"]
            for column in inspector.get_columns("deployment_settings_audit")
        }
        if (
            actual_settings != expected_settings
            or actual_audit != expected_audit
        ):
            raise RuntimeError(
                "Existing deployment settings tables do not match this revision."
            )
        return
    if settings_exists or audit_exists:
        raise RuntimeError(
            "Deployment settings schema is incomplete; both tables must "
            "either exist together or be absent."
        )

    op.create_table(
        "deployment_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_enabled", sa.Boolean(), nullable=False),
        sa.Column("public_ip", sa.String(length=45), nullable=False),
        sa.Column("public_port", sa.Integer(), nullable=False),
        sa.Column("allowed_remote_ips", sa.Text(), nullable=False),
        sa.Column("local_interface", sa.String(length=160), nullable=False),
        sa.Column("local_ip", sa.String(length=45), nullable=False),
        sa.Column("local_port", sa.Integer(), nullable=False),
        sa.Column("configure_static_local_ip", sa.Boolean(), nullable=False),
        sa.Column("local_prefix_length", sa.Integer(), nullable=False),
        sa.Column("local_gateway", sa.String(length=45), nullable=False),
        sa.Column("local_dns_servers", sa.Text(), nullable=False),
        sa.Column("internal_port", sa.Integer(), nullable=False),
        sa.Column("postgres_host", sa.String(length=255), nullable=False),
        sa.Column("postgres_port", sa.Integer(), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=False),
        sa.Column("updated_by_name", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_deployment_settings_singleton"),
        sa.CheckConstraint(
            "internal_port BETWEEN 1 AND 65535",
            name="ck_deployment_internal_port",
        ),
        sa.CheckConstraint(
            "local_port BETWEEN 1 AND 65535",
            name="ck_deployment_local_port",
        ),
        sa.CheckConstraint(
            "local_prefix_length BETWEEN 1 AND 32",
            name="ck_deployment_local_prefix",
        ),
        sa.CheckConstraint(
            "postgres_port BETWEEN 1 AND 65535",
            name="ck_deployment_postgres_port",
        ),
        sa.CheckConstraint(
            "public_port BETWEEN 1 AND 65535",
            name="ck_deployment_public_port",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "deployment_settings_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("configuration_version", sa.Integer(), nullable=False),
        sa.Column("edited_by_id", sa.Integer(), nullable=False),
        sa.Column("editor_name", sa.String(length=120), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["edited_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deployment_settings_audit_configuration_version"),
        "deployment_settings_audit",
        ["configuration_version"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_settings_audit_created_at"),
        "deployment_settings_audit",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_deployment_settings_audit_edited_by_id"),
        "deployment_settings_audit",
        ["edited_by_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_deployment_settings_audit_edited_by_id"),
        table_name="deployment_settings_audit",
    )
    op.drop_index(
        op.f("ix_deployment_settings_audit_created_at"),
        table_name="deployment_settings_audit",
    )
    op.drop_index(
        op.f("ix_deployment_settings_audit_configuration_version"),
        table_name="deployment_settings_audit",
    )
    op.drop_table("deployment_settings_audit")
    op.drop_table("deployment_settings")
