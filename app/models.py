"""Database entities."""
from __future__ import annotations

import enum
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def enum_column(enum_cls, length: int):
    """Store the enum *value* as text and hydrate back into the enum on load."""
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


def utcnow() -> datetime:
    """Server-side clock. The browser clock is never trusted."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    TECHNICAL = "technical"
    CUSTOMER = "customer"

    @property
    def label(self) -> str:
        return {
            "admin": "Administrator",
            "technical": "Technical",
            "customer": "Customer",
        }[self.value]


class MaintenanceResult(str, enum.Enum):
    COMPLETED_SUCCESSFULLY = "completed_successfully"
    COMPLETED_WITH_OBSERVATIONS = "completed_with_observations"
    FURTHER_ACTION_REQUIRED = "further_action_required"
    UNABLE_TO_COMPLETE = "unable_to_complete"

    @property
    def label(self) -> str:
        return {
            "completed_successfully": "Completed successfully",
            "completed_with_observations": "Completed with observations",
            "further_action_required": "Further action required",
            "unable_to_complete": "Unable to complete",
        }[self.value]

    @property
    def tone(self) -> str:
        return {
            "completed_successfully": "ok",
            "completed_with_observations": "note",
            "further_action_required": "warn",
            "unable_to_complete": "fail",
        }[self.value]


class EvidencePhotoStage(str, enum.Enum):
    BEFORE = "before"
    AFTER = "after"
    LEGACY = "legacy"

    @property
    def label(self) -> str:
        return {
            "before": "Before photos",
            "after": "After photos",
            "legacy": "Existing evidence",
        }[self.value]


NEEDS_ISSUE_DETAIL = {
    MaintenanceResult.COMPLETED_WITH_OBSERVATIONS,
    MaintenanceResult.FURTHER_ACTION_REQUIRED,
    MaintenanceResult.UNABLE_TO_COMPLETE,
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    role: Mapped[UserRole] = mapped_column(enum_column(UserRole, 20), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))
    pricing_access: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    records: Mapped[list["MaintenanceRecord"]] = relationship(back_populates="submitted_by")
    installation_records: Mapped[list["InstallationRecord"]] = relationship(
        back_populates="submitted_by"
    )
    customer_project_assignments: Mapped[list["CustomerProjectAssignment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="CustomerProjectAssignment.project_id",
    )

    __table_args__ = (
        CheckConstraint("length(trim(full_name)) > 0", name="ck_users_full_name_present"),
        CheckConstraint("length(trim(username)) > 0", name="ck_users_username_present"),
    )

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_technical(self) -> bool:
        return self.role == UserRole.TECHNICAL

    @property
    def is_customer(self) -> bool:
        return self.role == UserRole.CUSTOMER

    @property
    def can_submit_records(self) -> bool:
        return self.role in {UserRole.ADMIN, UserRole.TECHNICAL}

    @property
    def can_manage_catalogs(self) -> bool:
        return self.role in {UserRole.ADMIN, UserRole.TECHNICAL}

    @property
    def can_view_all_records(self) -> bool:
        return self.role in {UserRole.ADMIN, UserRole.TECHNICAL}

    @property
    def can_access_pricing(self) -> bool:
        return self.is_admin or (self.is_technical and self.pricing_access)

    @property
    def assigned_project_ids(self) -> set[int]:
        return {
            assignment.project_id
            for assignment in self.customer_project_assignments
        }

    def can_access_project(self, project_id: int) -> bool:
        return self.can_view_all_records or project_id in self.assigned_project_ids


class UserAuthState(Base):
    """Monotonic version used to invalidate signed-cookie sessions."""

    __tablename__ = "user_auth_states"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class AdminRecoveryContact(Base):
    """A separately managed and verified email for Administrator recovery."""

    __tablename__ = "admin_recovery_contacts"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )


class AccountRecoveryToken(Base):
    """Hashed, expiring, single-use email verification or password reset token."""

    __tablename__ = "account_recovery_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    purpose: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )


class AccountRecoveryAttempt(Base):
    """Anonymous request audit used for per-account and per-IP throttling."""

    __tablename__ = "account_recovery_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )


class LoginAttempt(Base):
    """Hashed failed-login audit used for per-account and per-IP throttling."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(80))
    contact_person: Mapped[str | None] = mapped_column(String(120))
    contact_number: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    records: Mapped[list["MaintenanceRecord"]] = relationship(back_populates="site")
    installation_records: Mapped[list["InstallationRecord"]] = relationship(
        back_populates="site"
    )
    customer_assignments: Mapped[list["CustomerProjectAssignment"]] = relationship(
        back_populates="project"
    )

    __table_args__ = (
        UniqueConstraint("name", "customer_name", name="uq_site_name_customer"),
        CheckConstraint("length(trim(name)) > 0", name="ck_sites_name_present"),
    )

    @property
    def display_label(self) -> str:
        return f"{self.name} — {self.customer_name}"


class CustomerProjectAssignment(Base):
    """Projects whose immutable records a Customer account may read."""

    __tablename__ = "customer_project_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True
    )

    user: Mapped[User] = relationship(back_populates="customer_project_assignments")
    project: Mapped[Site] = relationship(back_populates="customer_assignments")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            name="uq_customer_project_assignment",
        ),
    )


class RecordRevision(Base):
    """Append-only audit entry for a record edit or deletion."""

    __tablename__ = "record_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    record_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    edited_by_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    editor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    changes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    @property
    def changes(self) -> dict:
        try:
            value = json.loads(self.changes_json)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}


class ServiceType(Base):
    __tablename__ = "service_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    records: Mapped[list["MaintenanceRecord"]] = relationship(back_populates="service_type")
    installation_records: Mapped[list["InstallationRecord"]] = relationship(
        back_populates="service_type"
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_service_types_name_present"),
    )


class DeviceCatalog(Base):
    """Administrator-managed device models available for installation."""

    __tablename__ = "device_catalog"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120), index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    installed_devices: Mapped[list["InstalledDevice"]] = relationship(
        back_populates="catalog_device"
    )
    maintenance_links: Mapped[list["MaintenanceRecordDevice"]] = relationship(
        back_populates="catalog_device"
    )
    pricing_item: Mapped["PricingItem | None"] = relationship(
        back_populates="legacy_device", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("name", "model", name="uq_device_name_model"),
        CheckConstraint("length(trim(name)) > 0", name="ck_device_name_present"),
        CheckConstraint("length(trim(model)) > 0", name="ck_device_model_present"),
    )

    @property
    def display_label(self) -> str:
        maker = f"{self.manufacturer} " if self.manufacturer else ""
        return f"{self.name} — {maker}{self.model}"


class WorkSite(Base):
    """Administrator-managed site names such as Gate 1 or Gate 2."""

    __tablename__ = "work_sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    installation_links: Mapped[list["InstallationRecordSite"]] = relationship(
        back_populates="catalog_site"
    )
    installed_device_links: Mapped[list["InstalledDeviceSite"]] = relationship(
        back_populates="catalog_site"
    )
    maintenance_links: Mapped[list["MaintenanceRecordSite"]] = relationship(
        back_populates="catalog_site"
    )

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_work_site_name_present"),
    )


class MaintenanceRecord(Base):
    """Immutable evidence of maintenance that has already been performed."""

    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)

    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    submitted_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quotation_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_quotations.id", ondelete="SET NULL"), index=True
    )
    quotation_number: Mapped[str | None] = mapped_column(String(30))

    # Snapshots: history must not change when a site/service/user is renamed.
    site_name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    site_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    service_name: Mapped[str] = mapped_column(String(120), nullable=False)
    team_leader_name: Mapped[str] = mapped_column(String(120), nullable=False)

    result: Mapped[MaintenanceResult] = mapped_column(
        enum_column(MaintenanceResult, 40), nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    issue_description: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    site: Mapped[Site] = relationship(back_populates="records")
    service_type: Mapped[ServiceType] = relationship(back_populates="records")
    submitted_by: Mapped[User] = relationship(back_populates="records")
    participants: Mapped[list["MaintenanceParticipant"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", order_by="MaintenanceParticipant.id"
    )
    photos: Mapped[list["MaintenancePhoto"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", order_by="MaintenancePhoto.id"
    )
    device_evidence: Mapped["MaintenanceRecordDevice | None"] = relationship(
        back_populates="record", cascade="all, delete-orphan", uselist=False
    )
    additional_device_evidence: Mapped[list["MaintenanceRecordAdditionalDevice"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="MaintenanceRecordAdditionalDevice.id",
    )
    work_items: Mapped[list["MaintenanceRecordItem"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="MaintenanceRecordItem.position",
    )
    work_site_evidence: Mapped["MaintenanceRecordSite | None"] = relationship(
        back_populates="record", cascade="all, delete-orphan", uselist=False
    )

    __table_args__ = (
        CheckConstraint("length(trim(notes)) > 0", name="ck_records_notes_present"),
        Index("ix_records_leader_submitted", "submitted_by_id", "submitted_at"),
    )

    @property
    def participant_names(self) -> list[str]:
        return [p.name for p in self.participants]


class MaintenanceParticipant(Base):
    """A Technical user who accompanied the submitter, with a name snapshot."""

    __tablename__ = "maintenance_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    record: Mapped[MaintenanceRecord] = relationship(back_populates="participants")

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_participants_name_present"),
    )


class MaintenancePhoto(Base):
    __tablename__ = "maintenance_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    record: Mapped[MaintenanceRecord] = relationship(back_populates="photos")


class MaintenanceRecordSite(Base):
    """Immutable selected-site snapshot for preventive maintenance."""

    __tablename__ = "maintenance_record_sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("work_sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    record: Mapped[MaintenanceRecord] = relationship(back_populates="work_site_evidence")
    catalog_site: Mapped[WorkSite] = relationship(back_populates="maintenance_links")


class InstallationRecord(Base):
    """Immutable evidence of a completed equipment installation."""

    __tablename__ = "installation_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)

    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    submitted_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quotation_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_quotations.id", ondelete="SET NULL"), index=True
    )
    quotation_number: Mapped[str | None] = mapped_column(String(30))

    # Snapshots keep installation history stable after master-data changes.
    site_name: Mapped[str] = mapped_column(String(160), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False)
    site_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    service_name: Mapped[str] = mapped_column(String(120), nullable=False)
    team_leader_name: Mapped[str] = mapped_column(String(120), nullable=False)

    equipment_model: Mapped[str] = mapped_column(String(160), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    warranty_start: Mapped[date | None] = mapped_column(Date)
    result: Mapped[MaintenanceResult] = mapped_column(
        enum_column(MaintenanceResult, 40), nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    handover_notes: Mapped[str | None] = mapped_column(Text)

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    site: Mapped[Site] = relationship(back_populates="installation_records")
    service_type: Mapped[ServiceType] = relationship(back_populates="installation_records")
    submitted_by: Mapped[User] = relationship(back_populates="installation_records")
    participants: Mapped[list["InstallationParticipant"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="InstallationParticipant.id",
    )
    photos: Mapped[list["InstallationPhoto"]] = relationship(
        back_populates="record", cascade="all, delete-orphan", order_by="InstallationPhoto.id"
    )
    installed_device: Mapped["InstalledDevice | None"] = relationship(
        back_populates="installation_record",
        cascade="all, delete-orphan",
        uselist=False,
    )
    additional_devices: Mapped[list["InstallationRecordAdditionalDevice"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="InstallationRecordAdditionalDevice.id",
    )
    work_items: Mapped[list["InstallationRecordItem"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="InstallationRecordItem.position",
    )
    work_site_evidence: Mapped["InstallationRecordSite | None"] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(equipment_model)) > 0",
            name="ck_installation_equipment_model_present",
        ),
        CheckConstraint(
            "length(trim(serial_number)) > 0",
            name="ck_installation_serial_number_present",
        ),
        CheckConstraint("length(trim(notes)) > 0", name="ck_installation_notes_present"),
        Index(
            "ix_installation_leader_submitted",
            "submitted_by_id",
            "submitted_at",
        ),
    )


class InstallationParticipant(Base):
    __tablename__ = "installation_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("installation_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    record: Mapped[InstallationRecord] = relationship(back_populates="participants")

    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0",
            name="ck_installation_participants_name_present",
        ),
    )


class InstallationPhoto(Base):
    __tablename__ = "installation_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("installation_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    record: Mapped[InstallationRecord] = relationship(back_populates="photos")


class InstallationRecordSite(Base):
    """Immutable selected-site snapshot for an installation record."""

    __tablename__ = "installation_record_sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("installation_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("work_sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    record: Mapped[InstallationRecord] = relationship(
        back_populates="work_site_evidence"
    )
    catalog_site: Mapped[WorkSite] = relationship(back_populates="installation_links")


class InstalledDevice(Base):
    """A specific serialized device registered at a site by an installation."""

    __tablename__ = "installed_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_record_id: Mapped[int | None] = mapped_column(
        ForeignKey("installation_records.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
        index=True,
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("device_catalog.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    site_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    device_model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(
        String(160), nullable=False, unique=True, index=True
    )
    warranty_start: Mapped[date | None] = mapped_column(Date)
    installed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    installation_record: Mapped[InstallationRecord] = relationship(
        back_populates="installed_device"
    )
    site: Mapped[Site] = relationship()
    catalog_device: Mapped[DeviceCatalog] = relationship(
        back_populates="installed_devices"
    )
    maintenance_links: Mapped[list["MaintenanceRecordDevice"]] = relationship(
        back_populates="installed_device"
    )
    work_site_evidence: Mapped["InstalledDeviceSite | None"] = relationship(
        back_populates="installed_device",
        cascade="all, delete-orphan",
        uselist=False,
    )

    @property
    def effective_work_site_id(self) -> int | None:
        """Support devices installed before the direct site link was introduced."""
        if self.work_site_evidence:
            return self.work_site_evidence.site_id
        if self.installation_record and self.installation_record.work_site_evidence:
            return self.installation_record.work_site_evidence.site_id
        return None


class InstalledDeviceSite(Base):
    """The current catalog-site identity of an installed device."""

    __tablename__ = "installed_device_sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    installed_device_id: Mapped[int] = mapped_column(
        ForeignKey("installed_devices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    site_id: Mapped[int] = mapped_column(
        ForeignKey("work_sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    installed_device: Mapped[InstalledDevice] = relationship(
        back_populates="work_site_evidence"
    )
    catalog_site: Mapped[WorkSite] = relationship(
        back_populates="installed_device_links"
    )


class InstallationRecordAdditionalDevice(Base):
    """A second or later installed device grouped into one installation visit."""

    __tablename__ = "installation_record_additional_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("installation_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    installed_device_id: Mapped[int] = mapped_column(
        ForeignKey("installed_devices.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    record: Mapped[InstallationRecord] = relationship(back_populates="additional_devices")
    installed_device: Mapped[InstalledDevice] = relationship()
    service_type: Mapped[ServiceType] = relationship()


class InstallationRecordItem(Base):
    """Complete evidence for one device within a grouped installation visit."""

    __tablename__ = "installation_record_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("installation_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installed_device_id: Mapped[int] = mapped_column(
        ForeignKey("installed_devices.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    service_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    device_model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    warranty_start: Mapped[date | None] = mapped_column(Date)
    result: Mapped[MaintenanceResult] = mapped_column(
        enum_column(MaintenanceResult, 40), nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    handover_notes: Mapped[str | None] = mapped_column(Text)

    record: Mapped[InstallationRecord] = relationship(back_populates="work_items")
    installed_device: Mapped[InstalledDevice] = relationship()
    service_type: Mapped[ServiceType] = relationship()
    photos: Mapped[list["InstallationItemPhoto"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="InstallationItemPhoto.id",
    )


class InstallationItemPhoto(Base):
    __tablename__ = "installation_item_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("installation_record_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[EvidencePhotoStage] = mapped_column(
        enum_column(EvidencePhotoStage, 20),
        nullable=False,
        default=EvidencePhotoStage.LEGACY,
        index=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    item: Mapped[InstallationRecordItem] = relationship(back_populates="photos")


class MaintenanceRecordDevice(Base):
    """Immutable device snapshot attached to a maintenance record."""

    __tablename__ = "maintenance_record_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    installed_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("installed_devices.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    device_id: Mapped[int] = mapped_column(
        ForeignKey("device_catalog.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    device_model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(String(160), nullable=False, index=True)

    record: Mapped[MaintenanceRecord] = relationship(back_populates="device_evidence")
    installed_device: Mapped[InstalledDevice | None] = relationship(
        back_populates="maintenance_links"
    )
    catalog_device: Mapped[DeviceCatalog] = relationship(
        back_populates="maintenance_links"
    )


class MaintenanceRecordAdditionalDevice(Base):
    """A second or later device snapshot grouped into one maintenance visit."""

    __tablename__ = "maintenance_record_additional_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    installed_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("installed_devices.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("device_catalog.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    device_model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(String(160), nullable=False, index=True)

    record: Mapped[MaintenanceRecord] = relationship(
        back_populates="additional_device_evidence"
    )
    installed_device: Mapped[InstalledDevice | None] = relationship()
    service_type: Mapped[ServiceType] = relationship()
    catalog_device: Mapped[DeviceCatalog] = relationship()


class MaintenanceRecordItem(Base):
    """Complete evidence for one device within a grouped maintenance visit."""

    __tablename__ = "maintenance_record_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installed_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("installed_devices.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    service_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("device_catalog.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    device_model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result: Mapped[MaintenanceResult] = mapped_column(
        enum_column(MaintenanceResult, 40), nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    issue_description: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)

    record: Mapped[MaintenanceRecord] = relationship(back_populates="work_items")
    installed_device: Mapped[InstalledDevice | None] = relationship()
    service_type: Mapped[ServiceType] = relationship()
    catalog_device: Mapped[DeviceCatalog] = relationship()
    photos: Mapped[list["MaintenanceItemPhoto"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="MaintenanceItemPhoto.id",
    )


class MaintenanceItemPhoto(Base):
    __tablename__ = "maintenance_item_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_record_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[EvidencePhotoStage] = mapped_column(
        enum_column(EvidencePhotoStage, 20),
        nullable=False,
        default=EvidencePhotoStage.LEGACY,
        index=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    item: Mapped[MaintenanceRecordItem] = relationship(back_populates="photos")


class GeneralMaintenanceRecord(Base):
    """Immutable evidence for a normal, non-preventive maintenance visit."""

    __tablename__ = "general_maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    site_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    work_site_id: Mapped[int] = mapped_column(
        ForeignKey("work_sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    submitted_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quotation_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_quotations.id", ondelete="SET NULL"), index=True
    )
    quotation_number: Mapped[str | None] = mapped_column(String(30))
    project_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    site_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    service_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    team_leader_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result: Mapped[MaintenanceResult] = mapped_column(
        enum_column(MaintenanceResult, 40), nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    project: Mapped[Site] = relationship()
    work_site: Mapped[WorkSite] = relationship()
    service_type: Mapped[ServiceType] = relationship()
    submitted_by: Mapped[User] = relationship()
    participants: Mapped[list["GeneralMaintenanceParticipant"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="GeneralMaintenanceParticipant.id",
    )
    work_items: Mapped[list["GeneralMaintenanceItem"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="GeneralMaintenanceItem.position",
    )


class GeneralMaintenanceParticipant(Base):
    __tablename__ = "general_maintenance_participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("general_maintenance_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    record: Mapped[GeneralMaintenanceRecord] = relationship(back_populates="participants")


class GeneralMaintenanceItem(Base):
    __tablename__ = "general_maintenance_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("general_maintenance_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    installed_device_id: Mapped[int | None] = mapped_column(
        ForeignKey("installed_devices.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    service_type_id: Mapped[int] = mapped_column(
        ForeignKey("service_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    service_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("device_catalog.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    device_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(120))
    device_model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    serial_number: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result: Mapped[MaintenanceResult] = mapped_column(
        enum_column(MaintenanceResult, 40), nullable=False, index=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    issue_description: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str | None] = mapped_column(Text)

    record: Mapped[GeneralMaintenanceRecord] = relationship(back_populates="work_items")
    installed_device: Mapped[InstalledDevice | None] = relationship()
    service_type: Mapped[ServiceType] = relationship()
    catalog_device: Mapped[DeviceCatalog] = relationship()
    photos: Mapped[list["GeneralMaintenancePhoto"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="GeneralMaintenancePhoto.id",
    )


class GeneralMaintenancePhoto(Base):
    __tablename__ = "general_maintenance_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("general_maintenance_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[EvidencePhotoStage] = mapped_column(
        enum_column(EvidencePhotoStage, 20),
        nullable=False,
        default=EvidencePhotoStage.LEGACY,
        index=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    item: Mapped[GeneralMaintenanceItem] = relationship(back_populates="photos")


class RecordCounter(Base):
    """Per-year sequence backing the PM-YYYY-NNNNN record numbers."""

    __tablename__ = "record_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class InstallationRecordCounter(Base):
    """Per-year sequence backing the NI-YYYY-NNNNN record numbers."""

    __tablename__ = "installation_record_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GeneralMaintenanceRecordCounter(Base):
    """Per-year sequence backing MA-YYYY-NNNNN record numbers."""

    __tablename__ = "general_maintenance_record_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DeploymentSettings(Base):
    """Singleton Windows Server deployment profile staged by an Administrator."""

    __tablename__ = "deployment_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    public_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tls_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public_ip: Mapped[str] = mapped_column(String(45), nullable=False, default="")
    public_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8993)
    allowed_remote_ips: Mapped[str] = mapped_column(Text, nullable=False, default="")
    local_interface: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    local_ip: Mapped[str] = mapped_column(String(45), nullable=False, default="")
    local_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8993)
    configure_static_local_ip: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    local_prefix_length: Mapped[int] = mapped_column(
        Integer, nullable=False, default=24
    )
    local_gateway: Mapped[str] = mapped_column(String(45), nullable=False, default="")
    local_dns_servers: Mapped[str] = mapped_column(Text, nullable=False, default="")
    internal_port: Mapped[int] = mapped_column(Integer, nullable=False, default=8993)
    postgres_host: Mapped[str] = mapped_column(
        String(255), nullable=False, default="127.0.0.1"
    )
    postgres_port: Mapped[int] = mapped_column(Integer, nullable=False, default=5432)
    backup_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    backup_interval_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    backup_retention_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    backup_include_uploads: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    backup_upload_retention_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=7
    )
    backup_directory: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default=r"C:\ServiceManagement\backups\scheduled",
    )
    pg_dump_executable: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default=r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
    )
    configuration_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    updated_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_name: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_deployment_settings_singleton"),
        CheckConstraint(
            "public_port BETWEEN 1 AND 65535",
            name="ck_deployment_public_port",
        ),
        CheckConstraint(
            "local_port BETWEEN 1 AND 65535",
            name="ck_deployment_local_port",
        ),
        CheckConstraint(
            "internal_port BETWEEN 1 AND 65535",
            name="ck_deployment_internal_port",
        ),
        CheckConstraint(
            "postgres_port BETWEEN 1 AND 65535",
            name="ck_deployment_postgres_port",
        ),
        CheckConstraint(
            "local_prefix_length BETWEEN 1 AND 32",
            name="ck_deployment_local_prefix",
        ),
        CheckConstraint(
            "backup_interval_days BETWEEN 1 AND 365",
            name="ck_deployment_backup_interval",
        ),
        CheckConstraint(
            "backup_retention_count BETWEEN 1 AND 365",
            name="ck_deployment_backup_retention",
        ),
        CheckConstraint(
            "backup_upload_retention_count BETWEEN 1 AND 365",
            name="ck_deployment_backup_upload_retention",
        ),
    )


class DeploymentSettingsAudit(Base):
    """Append-only, secret-free history of deployment profile changes."""

    __tablename__ = "deployment_settings_audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_version: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )
    edited_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    editor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    before_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    after_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    @property
    def before(self) -> dict:
        try:
            value = json.loads(self.before_json)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @property
    def after(self) -> dict:
        try:
            value = json.loads(self.after_json)
        except (TypeError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}


class PricingItemCategory(Base):
    """User-managed grouping for Pricing Items."""

    __tablename__ = "pricing_item_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    items: Mapped[list["PricingItem"]] = relationship(back_populates="category")

    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) > 0", name="ck_pricing_item_category_name_present"
        ),
    )


class PricingItem(Base):
    """Reusable main item offered on price quotations."""

    __tablename__ = "pricing_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    service_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_item_categories.id", ondelete="SET NULL"), index=True
    )
    device_catalog_id: Mapped[int | None] = mapped_column(
        ForeignKey("device_catalog.id", ondelete="RESTRICT"), unique=True, index=True
    )
    image_storage_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    image_thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    image_original_filename: Mapped[str | None] = mapped_column(String(255))
    image_content_type: Mapped[str | None] = mapped_column(String(60))
    image_file_size: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    related_items: Mapped[list["PricingRelatedItem"]] = relationship(
        back_populates="main_item",
        cascade="all, delete-orphan",
        order_by="PricingRelatedItem.name",
    )
    category: Mapped[PricingItemCategory | None] = relationship(back_populates="items")
    legacy_device: Mapped[DeviceCatalog | None] = relationship(
        back_populates="pricing_item"
    )

    __table_args__ = (
        UniqueConstraint("name", "model", name="uq_pricing_item_name_model"),
        CheckConstraint("length(trim(name)) > 0", name="ck_pricing_item_name_present"),
        CheckConstraint("unit_price >= 0", name="ck_pricing_item_price_nonnegative"),
        CheckConstraint("length(trim(currency)) = 3", name="ck_pricing_item_currency"),
    )

    @property
    def display_label(self) -> str:
        return f"{self.name} — {self.model}" if self.model else self.name

    @property
    def category_name(self) -> str:
        return self.category.name if self.category else ""


class PricingRelatedItem(Base):
    """Optional priced item that can accompany one main pricing item."""

    __tablename__ = "pricing_related_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    main_item_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    main_item: Mapped[PricingItem] = relationship(back_populates="related_items")

    __table_args__ = (
        UniqueConstraint(
            "main_item_id", "name", name="uq_pricing_related_item_parent_name"
        ),
        CheckConstraint(
            "length(trim(name)) > 0", name="ck_pricing_related_item_name_present"
        ),
        CheckConstraint(
            "unit_price >= 0", name="ck_pricing_related_item_price_nonnegative"
        ),
        CheckConstraint(
            "length(trim(currency)) = 3", name="ck_pricing_related_item_currency"
        ),
    )


class PricingSettings(Base):
    """Administrator-managed defaults and seller details for quotations."""

    __tablename__ = "pricing_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    default_vat_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("15.00")
    )
    default_validity_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    quotation_prefix: Mapped[str] = mapped_column(
        String(12), nullable=False, default="QUO"
    )
    company_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    company_address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    company_phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    company_email: Mapped[str] = mapped_column(String(254), nullable=False, default="")
    default_terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_manpower_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    default_transportation_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    default_installation_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00")
    )
    updated_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_by_name: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_pricing_settings_singleton"),
        CheckConstraint(
            "default_vat_rate BETWEEN 0 AND 100",
            name="ck_pricing_settings_vat_rate",
        ),
        CheckConstraint(
            "default_validity_days BETWEEN 1 AND 365",
            name="ck_pricing_settings_validity_days",
        ),
        CheckConstraint(
            "length(trim(currency)) = 3",
            name="ck_pricing_settings_currency",
        ),
        CheckConstraint(
            "length(trim(quotation_prefix)) > 0",
            name="ck_pricing_settings_prefix",
        ),
        CheckConstraint(
            "default_manpower_price >= 0",
            name="ck_pricing_settings_manpower_price",
        ),
        CheckConstraint(
            "default_transportation_price >= 0",
            name="ck_pricing_settings_transportation_price",
        ),
        CheckConstraint(
            "default_installation_price >= 0",
            name="ck_pricing_settings_installation_price",
        ),
    )


class PricingQuotation(Base):
    """Commercial quotation whose project, seller, and prices are snapshots."""

    __tablename__ = "pricing_quotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_number: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_address: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    project_city: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    contact_person: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    contact_number: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    quotation_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    discount_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00")
    )
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    terms: Mapped[str] = mapped_column(Text, nullable=False, default="")
    company_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    company_address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    company_phone: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    company_email: Mapped[str] = mapped_column(String(254), nullable=False, default="")
    installation_plan_state: Mapped[dict | None] = mapped_column(JSON)
    plan_background_storage_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    plan_background_thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    plan_background_content_type: Mapped[str | None] = mapped_column(String(60))
    plan_background_file_size: Mapped[int | None] = mapped_column(Integer)
    plan_output_storage_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    plan_output_thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    plan_output_content_type: Mapped[str | None] = mapped_column(String(60))
    plan_output_file_size: Mapped[int | None] = mapped_column(Integer)
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    lines: Mapped[list["PricingQuotationLine"]] = relationship(
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="PricingQuotationLine.position",
    )
    charges: Mapped[list["PricingQuotationCharge"]] = relationship(
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="PricingQuotationCharge.position",
    )
    invoice_images: Mapped[list["PricingQuotationInvoiceImage"]] = relationship(
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="PricingQuotationInvoiceImage.id",
    )
    site_survey_images: Mapped[list["PricingQuotationSiteSurveyImage"]] = relationship(
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="PricingQuotationSiteSurveyImage.id",
    )

    __table_args__ = (
        CheckConstraint(
            "discount_percent BETWEEN 0 AND 100",
            name="ck_pricing_quotation_discount",
        ),
        CheckConstraint(
            "vat_rate BETWEEN 0 AND 100", name="ck_pricing_quotation_vat_rate"
        ),
        CheckConstraint(
            "valid_until >= quotation_date", name="ck_pricing_quotation_validity"
        ),
    )


class PricingQuotationInvoiceImage(Base):
    """Protected post-purchase invoice proof attached to a quotation."""

    __tablename__ = "pricing_quotation_invoice_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_by_name: Mapped[str] = mapped_column(String(120), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    quotation: Mapped[PricingQuotation] = relationship(back_populates="invoice_images")


class PricingQuotationSiteSurveyImage(Base):
    """Protected site-survey layout image attached to a quotation."""

    __tablename__ = "pricing_quotation_site_survey_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    uploaded_by_name: Mapped[str] = mapped_column(String(120), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )

    quotation: Mapped[PricingQuotation] = relationship(
        back_populates="site_survey_images"
    )


class PricingQuotationLine(Base):
    """Main quotation line with immutable catalogue and price snapshots."""

    __tablename__ = "pricing_quotation_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_items.id", ondelete="SET NULL"), index=True
    )
    alternative_to_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_quotation_lines.id", ondelete="SET NULL"), index=True
    )
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    item_model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    skip_optional_items: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    image_storage_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    image_thumbnail_key: Mapped[str | None] = mapped_column(String(255))
    image_original_filename: Mapped[str | None] = mapped_column(String(255))
    image_content_type: Mapped[str | None] = mapped_column(String(60))
    image_file_size: Mapped[int | None] = mapped_column(Integer)

    quotation: Mapped[PricingQuotation] = relationship(back_populates="lines")
    alternative_to: Mapped["PricingQuotationLine | None"] = relationship(
        "PricingQuotationLine",
        back_populates="alternatives",
        foreign_keys=[alternative_to_line_id],
        remote_side="PricingQuotationLine.id",
        post_update=True,
    )
    alternatives: Mapped[list["PricingQuotationLine"]] = relationship(
        "PricingQuotationLine",
        back_populates="alternative_to",
        foreign_keys="PricingQuotationLine.alternative_to_line_id",
    )
    related_items: Mapped[list["PricingQuotationRelatedLine"]] = relationship(
        back_populates="line",
        cascade="all, delete-orphan",
        order_by="PricingQuotationRelatedLine.id",
    )

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_pricing_line_quantity_positive"),
        CheckConstraint(
            "unit_price >= 0", name="ck_pricing_line_price_nonnegative"
        ),
        CheckConstraint("length(trim(currency)) = 3", name="ck_pricing_line_currency"),
        CheckConstraint(
            "alternative_to_line_id IS NULL OR alternative_to_line_id <> id",
            name="ck_pricing_line_not_own_alternative",
        ),
        UniqueConstraint(
            "quotation_id", "position", name="uq_pricing_quotation_line_position"
        ),
    )

    @property
    def main_total(self) -> Decimal:
        return self.quantity * self.unit_price

    @property
    def line_total(self) -> Decimal:
        return self.main_total + sum(
            (related.total for related in self.related_items), Decimal("0.00")
        )


class PricingQuotationRelatedLine(Base):
    """Selected related item with its own immutable price snapshot."""

    __tablename__ = "pricing_quotation_related_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_quotation_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_related_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("pricing_related_items.id", ondelete="SET NULL"), index=True
    )
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")

    line: Mapped[PricingQuotationLine] = relationship(back_populates="related_items")

    __table_args__ = (
        CheckConstraint(
            "quantity > 0", name="ck_pricing_related_line_quantity_positive"
        ),
        CheckConstraint(
            "unit_price >= 0", name="ck_pricing_related_line_price_nonnegative"
        ),
        CheckConstraint(
            "length(trim(currency)) = 3", name="ck_pricing_related_line_currency"
        ),
    )

    @property
    def total(self) -> Decimal:
        return self.quantity * self.unit_price


class PricingQuotationCharge(Base):
    """Required manpower, transportation, or installation quotation charge."""

    __tablename__ = "pricing_quotation_charges"

    id: Mapped[int] = mapped_column(primary_key=True)
    quotation_id: Mapped[int] = mapped_column(
        ForeignKey("pricing_quotations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    charge_type: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="SAR")
    unit_label: Mapped[str] = mapped_column(String(40), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    quotation: Mapped[PricingQuotation] = relationship(back_populates="charges")

    __table_args__ = (
        CheckConstraint(
            "charge_type IN ('manpower', 'transportation', 'installation')",
            name="ck_pricing_charge_type",
        ),
        CheckConstraint(
            "quantity > 0", name="ck_pricing_charge_quantity_positive"
        ),
        CheckConstraint(
            "unit_price >= 0", name="ck_pricing_charge_price_nonnegative"
        ),
        CheckConstraint("length(trim(currency)) = 3", name="ck_pricing_charge_currency"),
        UniqueConstraint(
            "quotation_id", "charge_type", name="uq_pricing_quotation_charge_type"
        ),
        UniqueConstraint(
            "quotation_id", "position", name="uq_pricing_quotation_charge_position"
        ),
    )

    @property
    def total(self) -> Decimal:
        return self.quantity * self.unit_price


class PricingQuotationCounter(Base):
    """Per-year sequence backing configurable quotation numbers."""

    __tablename__ = "pricing_quotation_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
