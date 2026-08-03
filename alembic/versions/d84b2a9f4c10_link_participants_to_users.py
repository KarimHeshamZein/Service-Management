"""link record participants to technical user accounts

Revision ID: d84b2a9f4c10
Revises: bc0a78bbcdf8
Create Date: 2026-07-29 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d84b2a9f4c10"
down_revision: Union[str, Sequence[str], None] = "bc0a78bbcdf8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PARTICIPANT_TABLES = (
    "maintenance_participants",
    "installation_participants",
    "general_maintenance_participants",
)


def upgrade() -> None:
    for table_name in PARTICIPANT_TABLES:
        op.add_column(
            table_name,
            sa.Column("user_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            op.f(f"ix_{table_name}_user_id"),
            table_name,
            ["user_id"],
            unique=False,
        )
        op.create_foreign_key(
            f"fk_{table_name}_user_id_users",
            table_name,
            "users",
            ["user_id"],
            ["id"],
            ondelete="RESTRICT",
        )

        # Historical rows only contain a name snapshot. Link them when exactly
        # one Technical account has that name; ambiguous snapshots remain null.
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name} AS participant
                SET user_id = matched.id
                FROM users AS matched
                WHERE participant.name = matched.full_name
                  AND matched.role = 'technical'
                  AND (
                    SELECT count(*)
                    FROM users AS candidate
                    WHERE candidate.full_name = participant.name
                      AND candidate.role = 'technical'
                  ) = 1
                """
            )
        )


def downgrade() -> None:
    for table_name in reversed(PARTICIPANT_TABLES):
        op.drop_constraint(
            f"fk_{table_name}_user_id_users",
            table_name,
            type_="foreignkey",
        )
        op.drop_index(op.f(f"ix_{table_name}_user_id"), table_name=table_name)
        op.drop_column(table_name, "user_id")
