"""Unify service items and add mixed-currency quotation snapshots.

Revision ID: b7f3c91d2a84
Revises: a6d1e7c93b52
Create Date: 2026-08-04
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7f3c91d2a84"
down_revision: Union[str, Sequence[str], None] = "a6d1e7c93b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_currency(table: str) -> None:
    op.add_column(
        table,
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="SAR"),
    )


def upgrade() -> None:
    _add_currency("pricing_items")
    op.add_column(
        "pricing_items",
        sa.Column("service_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "pricing_items",
        sa.Column("device_catalog_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_pricing_items_service_enabled",
        "pricing_items",
        ["service_enabled"],
        unique=False,
    )
    op.create_index(
        "ix_pricing_items_device_catalog_id",
        "pricing_items",
        ["device_catalog_id"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_pricing_items_device_catalog_id",
        "pricing_items",
        "device_catalog",
        ["device_catalog_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_pricing_item_currency",
        "pricing_items",
        "length(trim(currency)) = 3",
    )

    _add_currency("pricing_related_items")
    op.execute(
        """
        UPDATE pricing_related_items AS related
        SET currency = parent.currency
        FROM pricing_items AS parent
        WHERE parent.id = related.main_item_id
        """
    )
    op.create_check_constraint(
        "ck_pricing_related_item_currency",
        "pricing_related_items",
        "length(trim(currency)) = 3",
    )

    for table, constraint in (
        ("pricing_quotation_lines", "ck_pricing_line_currency"),
        ("pricing_quotation_related_lines", "ck_pricing_related_line_currency"),
        ("pricing_quotation_charges", "ck_pricing_charge_currency"),
    ):
        _add_currency(table)
        op.create_check_constraint(
            constraint,
            table,
            "length(trim(currency)) = 3",
        )

    op.execute(
        """
        UPDATE pricing_quotation_lines AS line
        SET currency = quotation.currency
        FROM pricing_quotations AS quotation
        WHERE quotation.id = line.quotation_id
        """
    )
    op.execute(
        """
        UPDATE pricing_quotation_related_lines AS related
        SET currency = line.currency
        FROM pricing_quotation_lines AS line
        WHERE line.id = related.line_id
        """
    )
    op.execute(
        """
        UPDATE pricing_quotation_charges AS charge
        SET currency = quotation.currency
        FROM pricing_quotations AS quotation
        WHERE quotation.id = charge.quotation_id
        """
    )

    connection = op.get_bind()
    default_currency = connection.execute(
        sa.text("SELECT currency FROM pricing_settings WHERE id = 1")
    ).scalar_one_or_none() or "SAR"
    devices = list(
        connection.execute(
            sa.text(
                """
                SELECT id, name, model, is_active
                FROM device_catalog
                ORDER BY id
                """
            )
        ).mappings()
    )
    for device in devices:
        item_id = connection.execute(
            sa.text(
                """
                SELECT id FROM pricing_items
                WHERE lower(name) = lower(:name) AND lower(model) = lower(:model)
                  AND device_catalog_id IS NULL
                ORDER BY id LIMIT 1
                """
            ),
            {"name": device["name"], "model": device["model"]},
        ).scalar_one_or_none()
        if item_id is None:
            item_id = connection.execute(
                sa.text(
                    """
                    INSERT INTO pricing_items
                        (name, model, unit_price, currency, service_enabled,
                         device_catalog_id, is_active, created_at, updated_at)
                    VALUES
                        (:name, :model, 0, :currency, true, :device_id,
                         :is_active, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                    """
                ),
                {
                    "name": device["name"],
                    "model": device["model"],
                    "currency": default_currency,
                    "device_id": device["id"],
                    "is_active": device["is_active"],
                },
            ).scalar_one()
        else:
            connection.execute(
                sa.text(
                    """
                    UPDATE pricing_items
                    SET device_catalog_id = :device_id, service_enabled = true
                    WHERE id = :item_id
                    """
                ),
                {"device_id": device["id"], "item_id": item_id},
            )

    unlinked_items = list(
        connection.execute(
            sa.text(
                """
                SELECT id, name, model, is_active
                FROM pricing_items
                WHERE device_catalog_id IS NULL
                ORDER BY id
                """
            )
        ).mappings()
    )
    for item in unlinked_items:
        device_id = connection.execute(
            sa.text(
                """
                INSERT INTO device_catalog
                    (name, manufacturer, model, description, is_active,
                     created_at, updated_at)
                VALUES
                    (:name, NULL, COALESCE(NULLIF(:model, ''), :name),
                     'Managed from Pricing Items', :is_active,
                     CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                RETURNING id
                """
            ),
            item,
        ).scalar_one()
        connection.execute(
            sa.text(
                "UPDATE pricing_items SET device_catalog_id = :device_id WHERE id = :item_id"
            ),
            {"device_id": device_id, "item_id": item["id"]},
        )

    # Pricing Items are now the source of truth. The legacy row remains only so
    # existing installed-device foreign keys and history continue to work.
    connection.execute(
        sa.text(
            """
            UPDATE device_catalog AS device
            SET name = item.name,
                model = COALESCE(NULLIF(item.model, ''), item.name),
                description = 'Managed from Pricing Items',
                is_active = item.is_active AND item.service_enabled,
                updated_at = CURRENT_TIMESTAMP
            FROM pricing_items AS item
            WHERE item.device_catalog_id = device.id
            """
        )
    )

    for table in (
        "pricing_items",
        "pricing_related_items",
        "pricing_quotation_lines",
        "pricing_quotation_related_lines",
        "pricing_quotation_charges",
    ):
        op.alter_column(table, "currency", server_default=None)
    op.alter_column("pricing_items", "service_enabled", server_default=None)


def downgrade() -> None:
    for table, constraint in (
        ("pricing_quotation_charges", "ck_pricing_charge_currency"),
        ("pricing_quotation_related_lines", "ck_pricing_related_line_currency"),
        ("pricing_quotation_lines", "ck_pricing_line_currency"),
        ("pricing_related_items", "ck_pricing_related_item_currency"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.drop_column(table, "currency")

    op.drop_constraint("ck_pricing_item_currency", "pricing_items", type_="check")
    op.drop_constraint(
        "fk_pricing_items_device_catalog_id", "pricing_items", type_="foreignkey"
    )
    op.drop_index("ix_pricing_items_device_catalog_id", table_name="pricing_items")
    op.drop_index("ix_pricing_items_service_enabled", table_name="pricing_items")
    op.drop_column("pricing_items", "device_catalog_id")
    op.drop_column("pricing_items", "service_enabled")
    op.drop_column("pricing_items", "currency")
