"""Create the schema and load realistic development data.

Usage:
    python seed.py            # create schema, seed if empty
    python seed.py --reset    # wipe database and uploads, then seed
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
from datetime import timedelta
from decimal import Decimal

from PIL import Image, ImageDraw
from sqlalchemy.engine import make_url

from app.config import settings
from app.database import SessionLocal, engine, init_db
from app.helpers import next_record_number
from app.models import (
    DeviceCatalog,
    MaintenanceParticipant,
    MaintenancePhoto,
    MaintenanceRecord,
    MaintenanceResult,
    PricingItem,
    ServiceType,
    Site,
    User,
    UserRole,
    WorkSite,
    utcnow,
)
from app.security import hash_password
from app.uploads import store_image

ADMIN_PASSWORD = "admin123"
LEADER_PASSWORD = "Leader@12345"

PALETTE = [
    ((26, 60, 82), (224, 163, 46)),
    ((32, 74, 62), (236, 236, 236)),
    ((66, 46, 74), (255, 208, 120)),
    ((74, 44, 40), (240, 220, 200)),
]


def synthetic_photo(caption: str, subtitle: str, index: int) -> bytes:
    """Stand-in for a real site photo so the demo data is not empty."""
    bg, fg = PALETTE[index % len(PALETTE)]
    img = Image.new("RGB", (960, 720), bg)
    draw = ImageDraw.Draw(img)
    for y in range(0, 720, 40):
        draw.line([(0, y), (960, y)], fill=tuple(min(255, c + 8) for c in bg), width=1)
    draw.rectangle([40, 40, 920, 680], outline=fg, width=3)
    draw.rectangle([40, 560, 920, 680], fill=fg)
    draw.text((70, 90), "PROOF PHOTO", fill=fg)
    draw.text((70, 130), caption, fill=(255, 255, 255))
    draw.text((70, 160), subtitle, fill=(230, 230, 230))
    draw.text((70, 600), f"Frame {index + 1}", fill=bg)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


def reset() -> None:
    from app.database import Base

    Base.metadata.drop_all(bind=engine)
    if settings.upload_dir.exists():
        shutil.rmtree(settings.upload_dir)
    print("Dropped tables and removed uploaded files.")


def confirm_reset(input_fn=input) -> bool:
    if settings.environment == "production":
        print("Reset is disabled when ENVIRONMENT=production.")
        return False
    database_name = make_url(settings.database_url).database or ""
    entered = input_fn(
        f'Type the database name "{database_name}" to confirm the reset: '
    ).strip()
    if entered != database_name:
        print("Database reset cancelled.")
        return False
    return True


def seed() -> None:
    init_db(create_schema=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    try:
        if db.query(User).count():
            print("Database already has users — nothing seeded. Use --reset to start over.")
            return

        admin = User(
            full_name="Nadia Haddad",
            username="admin",
            password_hash=hash_password(ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            phone="+966 50 111 2200",
        )
        omar = User(
            full_name="Omar Al-Rashid",
            username="omar@afaqy.local",
            password_hash=hash_password(LEADER_PASSWORD),
            role=UserRole.TECHNICAL,
            phone="+966 55 402 8811",
        )
        yousef = User(
            full_name="Yousef Mansour",
            username="yousef@afaqy.local",
            password_hash=hash_password(LEADER_PASSWORD),
            role=UserRole.TECHNICAL,
            phone="+966 56 733 1904",
        )
        retired = User(
            full_name="Hani Darwish",
            username="hani@afaqy.local",
            password_hash=hash_password(LEADER_PASSWORD),
            role=UserRole.TECHNICAL,
            phone="+966 53 220 7745",
            is_active=False,
        )
        db.add_all([admin, omar, yousef, retired])
        db.flush()

        sites = [
            Site(
                name="Olaya Tower — Main Gate",
                customer_name="Riyadh Holding Co.",
                address="Olaya Street, Al Olaya District",
                city="Riyadh",
                contact_person="Faisal Al-Otaibi",
                contact_number="+966 11 288 4400",
            ),
            Site(
                name="King Fahd Logistics Yard",
                customer_name="Najd Logistics",
                address="Exit 18, Eastern Ring Road",
                city="Riyadh",
                contact_person="Sultan Bakr",
                contact_number="+966 11 490 7712",
            ),
            Site(
                name="Dammam Port Warehouse 4",
                customer_name="Gulf Freight Services",
                address="King Abdulaziz Port, Gate 3",
                city="Dammam",
                contact_person="Rami Habib",
                contact_number="+966 13 812 6650",
            ),
            Site(
                name="Al Nakheel Mall — Parking B",
                customer_name="Nakheel Retail Group",
                address="Al Thumamah Road, Al Nakheel",
                city="Riyadh",
                contact_person="Lina Saad",
                contact_number="+966 11 355 9021",
            ),
            Site(
                name="Jeddah Corniche Site Office",
                customer_name="Red Sea Contracting",
                address="North Corniche, Plot 22",
                city="Jeddah",
                contact_person="Tariq Nasser",
                contact_number="+966 12 660 3388",
            ),
            Site(
                name="Old Depot — Sulay",
                customer_name="Najd Logistics",
                address="Sulay Industrial Area, Block 7",
                city="Riyadh",
                is_active=False,
            ),
        ]
        services = [
            ServiceType(name="Gate Service", description="Barrier arms, motors, loop detectors and gate controllers."),
            ServiceType(name="Router Service", description="Site routers, SIM links, firmware and connectivity checks."),
            ServiceType(name="Camera Service", description="CCTV cameras: cleaning, focus, mounting and recording checks."),
            ServiceType(name="Network Service", description="Switches, cabling, PoE budget and link quality."),
            ServiceType(name="Access Control Service", description="Readers, controllers and door hardware."),
            ServiceType(name="Legacy Analogue Service", description="Retired analogue equipment.", is_active=False),
        ]
        devices = [
            DeviceCatalog(name="IP Camera", manufacturer="Axis", model="P3265-LV"),
            DeviceCatalog(name="Network Router", manufacturer="Teltonika", model="RUT956"),
            DeviceCatalog(name="Barrier Controller", manufacturer="FAAC", model="E045"),
            DeviceCatalog(name="PoE Switch", manufacturer="Cisco", model="CBS350-24P"),
        ]
        work_sites = [WorkSite(name=f"Gate {number}") for number in range(1, 4)]
        db.add_all(sites + services + devices + work_sites)
        db.flush()
        db.add_all(
            [
                PricingItem(
                    name=device.name,
                    model=device.model,
                    unit_price=Decimal("0.00"),
                    currency="SAR",
                    service_enabled=device.is_active,
                    legacy_device=device,
                    is_active=device.is_active,
                )
                for device in devices
            ]
        )
        db.flush()

        now = utcnow()
        blueprint = [
            {
                "site": sites[0], "service": services[2], "leader": omar,
                "result": MaintenanceResult.COMPLETED_SUCCESSFULLY,
                "when": now - timedelta(days=9, hours=3),
                "notes": "Cleaned all six dome cameras at the main gate, re-seated two loose BNC connectors and "
                         "re-focused the lane camera after cleaning. Verified 7-day playback on the NVR for every channel.",
                "issue": None,
                "recommendations": None,
                "people": ["Ahmed Saleh", "Bilal Khan"],
                "photos": 3,
            },
            {
                "site": sites[1], "service": services[0], "leader": omar,
                "result": MaintenanceResult.COMPLETED_WITH_OBSERVATIONS,
                "when": now - timedelta(days=6, hours=6),
                "notes": "Greased both barrier arm gearboxes, tightened the arm couplings and tested the loop detector "
                         "sensitivity on entry and exit lanes. Both barriers cycle correctly.",
                "issue": "The exit barrier arm has a hairline crack about 40 cm from the mount. It still operates but "
                         "the crack has grown since the last visit.",
                "recommendations": "Replace the exit barrier arm within the next month. Part is in stock at the Riyadh store.",
                "people": ["Ahmed Saleh"],
                "photos": 2,
            },
            {
                "site": sites[2], "service": services[1], "leader": yousef,
                "result": MaintenanceResult.FURTHER_ACTION_REQUIRED,
                "when": now - timedelta(days=4, hours=1),
                "notes": "Replaced the SIM in the primary router, updated firmware to the approved build and confirmed "
                         "the VPN tunnel is stable. Uplink now holds 40 Mbps down.",
                "issue": "The backup 4G router still drops every few hours. The antenna cable is damaged where it "
                         "passes through the wall gland.",
                "recommendations": "Schedule a follow-up visit with a replacement antenna cable and a weatherproof gland.",
                "people": ["Mustafa Iqbal", "Sami Nour"],
                "photos": 2,
            },
            {
                "site": sites[3], "service": services[3], "leader": yousef,
                "result": MaintenanceResult.COMPLETED_SUCCESSFULLY,
                "when": now - timedelta(days=2, hours=8),
                "notes": "Audited the parking level switch stack, cleaned the cabinet fans and re-labelled 18 patch "
                         "leads. PoE budget is at 61 percent with all cameras online.",
                "issue": None,
                "recommendations": "Consider a second uplink to the mall core switch before the next camera expansion.",
                "people": [],
                "photos": 2,
            },
            {
                "site": sites[4], "service": services[2], "leader": omar,
                "result": MaintenanceResult.UNABLE_TO_COMPLETE,
                "when": now - timedelta(days=1, hours=5),
                "notes": "Attended the site for the scheduled camera maintenance. Site power was down for planned "
                         "substation work and the contractor could not give access to the mast area.",
                "issue": "No power on site and the mast area was fenced off for crane work, so no camera could be reached.",
                "recommendations": "Return once the substation work is signed off. Confirm access with the site "
                                   "supervisor the day before travelling.",
                "people": ["Bilal Khan"],
                "photos": 1,
            },
            {
                "site": sites[0], "service": services[4], "leader": yousef,
                "result": MaintenanceResult.COMPLETED_SUCCESSFULLY,
                "when": now - timedelta(hours=4),
                "notes": "Tested all eight card readers on the tower entrances, replaced one faulty reader on door B2 "
                         "and re-synced the controller time against the site NTP server.",
                "issue": None,
                "recommendations": None,
                "people": ["Sami Nour"],
                "photos": 2,
            },
        ]

        for entry in blueprint:
            record = MaintenanceRecord(
                record_number=next_record_number(db, entry["when"]),
                site_id=entry["site"].id,
                service_type_id=entry["service"].id,
                submitted_by_id=entry["leader"].id,
                site_name=entry["site"].name,
                customer_name=entry["site"].customer_name,
                site_address=entry["site"].address,
                service_name=entry["service"].name,
                team_leader_name=entry["leader"].full_name,
                result=entry["result"],
                notes=entry["notes"],
                issue_description=entry["issue"],
                recommendations=entry["recommendations"],
                submitted_at=entry["when"],
                created_at=entry["when"],
            )
            record.participants = [MaintenanceParticipant(name=n) for n in entry["people"]]
            for i in range(entry["photos"]):
                data = synthetic_photo(entry["site"].name, entry["service"].name, i)
                stored = store_image(f"site_photo_{i + 1}.jpg", data)
                record.photos.append(
                    MaintenancePhoto(
                        storage_key=stored.storage_key,
                        thumbnail_key=stored.thumbnail_key,
                        original_filename=stored.original_filename,
                        content_type=stored.content_type,
                        file_size=stored.file_size,
                        uploaded_at=entry["when"],
                    )
                )
            db.add(record)

        db.commit()

        print("Seeded development data.")
        print(f"  Administrator  admin                 {ADMIN_PASSWORD}")
        print(f"  Technical      omar@afaqy.local     {LEADER_PASSWORD}")
        print(f"  Technical      yousef@afaqy.local   {LEADER_PASSWORD}")
        print(f"  Technical      hani@afaqy.local     {LEADER_PASSWORD}  (deactivated — cannot log in)")
        print(f"  {len(blueprint)} maintenance records, {len(sites)} sites, {len(services)} service types.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Service Management System database.")
    parser.add_argument("--reset", action="store_true", help="drop all tables and uploaded files first")
    args = parser.parse_args()
    if args.reset:
        if not confirm_reset():
            sys.exit(1)
        reset()
    seed()
    sys.exit(0)
