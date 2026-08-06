"""Resolve installed units and general catalogue items for maintenance records."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .helpers import entity_id
from .models import DeviceCatalog, InstalledDevice, PricingItem


CATALOG_PREFIX = "catalog:"


@dataclass(frozen=True)
class MaintenanceItemSelection:
    installed_device_id: int | None
    device_id: int
    device_name: str
    manufacturer: str | None
    device_model: str
    serial_number: str
    installed_device: InstalledDevice | None = None

    @property
    def key(self) -> tuple[str, int]:
        if self.installed_device_id is not None:
            return ("installed", self.installed_device_id)
        return ("catalog", self.device_id)


def active_catalog_items(db: Session) -> list[PricingItem]:
    """Return every active Pricing Item offered on service-entry forms."""
    return list(
        db.scalars(
            select(PricingItem)
            .options(
                selectinload(PricingItem.legacy_device),
                selectinload(PricingItem.category),
            )
            .where(
                PricingItem.is_active.is_(True),
                PricingItem.service_enabled.is_(True),
            )
            .order_by(PricingItem.name, PricingItem.model)
        )
    )


def resolve_maintenance_item(
    db: Session, raw_value: str
) -> tuple[MaintenanceItemSelection | None, str | None]:
    """Resolve a form choice while preserving legacy numeric installed-device IDs."""
    if raw_value.startswith(CATALOG_PREFIX):
        item_id = entity_id(raw_value.removeprefix(CATALOG_PREFIX))
        item = db.get(PricingItem, item_id) if item_id is not None else None
        if item is None:
            return None, "That item no longer exists."
        if not item.is_active or not item.service_enabled:
            return None, "That item is not available for service records."
        device: DeviceCatalog | None = item.legacy_device
        if device is None or not device.is_active:
            return None, "That item is not available for service records."
        return (
            MaintenanceItemSelection(
                installed_device_id=None,
                device_id=device.id,
                device_name=item.name,
                manufacturer=device.manufacturer,
                device_model=item.model or item.name,
                serial_number="",
            ),
            None,
        )

    installed_id = entity_id(raw_value)
    installed = db.get(InstalledDevice, installed_id) if installed_id is not None else None
    if installed is None:
        return None, "That installed device no longer exists."
    if not installed.is_active:
        return None, "That installed device is deactivated."
    return (
        MaintenanceItemSelection(
            installed_device_id=installed.id,
            device_id=installed.device_id,
            device_name=installed.device_name,
            manufacturer=installed.manufacturer,
            device_model=installed.device_model,
            serial_number=installed.serial_number,
            installed_device=installed,
        ),
        None,
    )
