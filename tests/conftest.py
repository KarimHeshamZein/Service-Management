"""Test fixtures. Each test run gets its own database and upload directory."""
from __future__ import annotations

import io
import os
import re
import shutil
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

TMP_ROOT = Path(tempfile.mkdtemp(prefix="sms-tests-"))
os.environ["DATABASE_URL"] = (
    "postgresql://postgres:postgres@localhost:5432/service_management_test"
)
os.environ["UPLOAD_DIR"] = str(TMP_ROOT / "uploads")
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["MAX_UPLOAD_MB"] = "1"
os.environ["ENVIRONMENT"] = "development"
os.environ["BCRYPT_ROUNDS"] = "4"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    CustomerProjectAssignment,
    DeviceCatalog,
    InstalledDevice,
    InstalledDeviceSite,
    MaintenanceResult,
    PricingItem,
    PricingQuotation,
    ServiceType,
    Site,
    User,
    UserRole,
    WorkSite,
)
from app.security import hash_password  # noqa: E402

ADMIN = ("admin", "admin123")
LEADER_A = ("leader.a@test.local", "Leader@12345")
LEADER_B = ("leader.b@test.local", "Leader@12345")
CUSTOMER_A = ("customer.a@test.local", "Customer@12345")
CUSTOMER_B = ("customer.b@test.local", "Customer@12345")
INACTIVE = ("gone@test.local", "Leader@12345")


def make_image(color=(20, 90, 120), size=(320, 240), fmt="JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def make_large_image(size=(2200, 2200)) -> bytes:
    """Random noise so the file cannot be compressed under the size limit."""
    noise = os.urandom(size[0] * size[1] * 3)
    buffer = io.BytesIO()
    Image.frombytes("RGB", size, noise).save(buffer, format="PNG", compress_level=0)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    if settings.upload_dir.exists():
        shutil.rmtree(settings.upload_dir)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        db.add_all(
            [
                User(full_name="Test Admin", username=ADMIN[0],
                     password_hash=hash_password(ADMIN[1]), role=UserRole.ADMIN),
                User(full_name="Leader One", username=LEADER_A[0],
                     password_hash=hash_password(LEADER_A[1]), role=UserRole.TECHNICAL),
                User(full_name="Leader Two", username=LEADER_B[0],
                     password_hash=hash_password(LEADER_B[1]), role=UserRole.TECHNICAL),
                User(full_name="Former Leader", username=INACTIVE[0],
                     password_hash=hash_password(INACTIVE[1]), role=UserRole.TECHNICAL,
                     is_active=False),
                User(full_name="Customer A", username=CUSTOMER_A[0],
                     password_hash=hash_password(CUSTOMER_A[1]), role=UserRole.CUSTOMER),
                User(full_name="Customer B", username=CUSTOMER_B[0],
                     password_hash=hash_password(CUSTOMER_B[1]), role=UserRole.CUSTOMER),
                Site(name="Tower A", customer_name="Acme Holding",
                     address="12 Ring Road", city="Riyadh"),
                Site(name="Closed Depot", customer_name="Acme Holding",
                     address="Industrial Area", is_active=False),
                Site(name="Tower B", customer_name="Beta Holding",
                     address="King Fahd Road", city="Riyadh"),
                ServiceType(name="Camera Service", description="CCTV maintenance"),
                ServiceType(name="Retired Service", is_active=False),
                DeviceCatalog(
                    name="IP Camera",
                    manufacturer="Axis",
                    model="P3265-LV",
                    description="Network dome camera",
                ),
                WorkSite(name="Gate 1"),
                WorkSite(name="Gate 2"),
                WorkSite(name="Gate 3"),
            ]
        )
        db.flush()
        catalog_device = db.get(DeviceCatalog, 1)
        db.add(
            PricingItem(
                name="IP Camera",
                model="P3265-LV",
                unit_price=Decimal("100.00"),
                currency="SAR",
                service_enabled=True,
                legacy_device=catalog_device,
            )
        )
        db.flush()
        db.add_all(
            [
                CustomerProjectAssignment(user_id=5, project_id=1),
                CustomerProjectAssignment(user_id=6, project_id=3),
            ]
        )
        installed_device = InstalledDevice(
                site_id=1,
                device_id=1,
                customer_name="Tower A",
                site_name="Gate 1",
                device_name="IP Camera",
                manufacturer="Axis",
                device_model="P3265-LV",
                serial_number="BASE-SN-001",
            )
        installed_device.work_site_evidence = InstalledDeviceSite(
            site_id=1, site_name="Gate 1"
        )
        db.add(installed_device)
        db.commit()
    finally:
        db.close()

    yield


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


# --- helpers -------------------------------------------------------------


def csrf_of(client: TestClient, path: str = "/login") -> str:
    page = client.get(path)
    match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    assert match, f"no CSRF token on {path}"
    return match.group(1)


def login(client: TestClient, username: str, password: str):
    token = csrf_of(client, "/login")
    return client.post(
        "/login",
        data={"username": username, "password": password, "csrf_token": token, "next": "/dashboard"},
    )


def logout(client: TestClient):
    token = csrf_of(client, "/records")
    return client.post("/logout", data={"csrf_token": token})


def submit_tokens(client: TestClient) -> tuple[str, str]:
    page = client.get("/maintenance/submit")
    assert page.status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    return csrf, form_token


def ensure_service_quotation(project_id: str | int = "1") -> str:
    normalized_id = int(project_id) if str(project_id).isdigit() else 1
    number = f"TEST-QUO-P{normalized_id}"
    db = SessionLocal()
    try:
        existing = db.query(PricingQuotation).filter_by(quotation_number=number).first()
        if existing:
            return existing.quotation_number
        project = db.get(Site, normalized_id) or db.get(Site, 1)
        admin = db.query(User).filter_by(role=UserRole.ADMIN).first()
        quotation = PricingQuotation(
            quotation_number=number,
            project_id=project.id,
            project_name=project.name,
            project_address=project.address,
            project_city=project.city,
            contact_person=project.contact_person,
            contact_number=project.contact_number,
            quotation_date=date.today(),
            valid_until=date.today() + timedelta(days=30),
            currency="SAR",
            discount_percent=Decimal("0.00"),
            vat_rate=Decimal("15.00"),
            notes="Test service quotation.",
            terms="",
            company_name="Test Company",
            company_address="",
            company_phone="",
            company_email="",
            created_by_id=admin.id,
            created_by_name=admin.full_name,
        )
        db.add(quotation)
        db.commit()
        return quotation.quotation_number
    finally:
        db.close()


def submit_record(client: TestClient, *, site_id="1", work_site_id="1", service_id="1", result=None,
                  notes="Cleaned and tested every camera on site.", photos=None,
                  participants=None, tokens=None, **extra):
    csrf, form_token = tokens or submit_tokens(client)
    payload = {
        "csrf_token": csrf,
        "form_token": form_token,
        "notes": notes,
        "installed_device_id": "1",
        "result": MaintenanceResult.COMPLETED_SUCCESSFULLY.value if result is None else result,
    }
    if site_id is not None:
        payload["project_id"] = site_id
    if work_site_id is not None:
        payload["work_site_id"] = work_site_id
    if service_id is not None:
        payload["service_type_id"] = service_id
    if participants:
        payload["participant_ids"] = participants
    payload["quotation_number"] = ensure_service_quotation(site_id or "1")
    payload.update(extra)

    files = photos if photos is not None else [("photos", ("proof.jpg", make_image(), "image/jpeg"))]
    return client.post("/maintenance/submit", data=payload, files=files)


def installation_tokens(client: TestClient) -> tuple[str, str]:
    page = client.get("/installations/submit")
    assert page.status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    return csrf, form_token


def submit_installation(
    client: TestClient,
    *,
    site_id="1",
    service_id="1",
    device_id="1",
    serial_number="SN-2026-0001",
    warranty_start="2026-07-28",
    result=None,
    notes="Mounted, connected, configured and commissioned the equipment.",
    photos=None,
    participants=None,
    tokens=None,
    **extra,
):
    csrf, form_token = tokens or installation_tokens(client)
    payload = {
        "csrf_token": csrf,
        "form_token": form_token,
        "customer_name": "Acme Holding",
        "device_id": device_id,
        "work_site_id": "1",
        "serial_number": serial_number,
        "warranty_start": warranty_start,
        "result": MaintenanceResult.COMPLETED_SUCCESSFULLY.value if result is None else result,
        "notes": notes,
    }
    if site_id is not None:
        payload["project_id"] = site_id
    if service_id is not None:
        payload["service_type_id"] = service_id
    if participants:
        payload["participant_ids"] = participants
    payload["quotation_number"] = ensure_service_quotation(site_id or "1")
    payload.update(extra)
    files = photos if photos is not None else [
        ("photos", ("installation.jpg", make_image(), "image/jpeg"))
    ]
    return client.post("/installations/submit", data=payload, files=files)
