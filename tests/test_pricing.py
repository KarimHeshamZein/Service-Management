"""Pricing permissions, catalogue, quotation snapshots, totals, and PDF output."""
from __future__ import annotations

import io
import re
from datetime import date
from decimal import Decimal

from pypdf import PdfReader
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    PricingItem,
    PricingQuotation,
    PricingRelatedItem,
    PricingSettings,
    User,
)
from app.pricing import quotation_totals
from app.config import settings
from app.uploads import store_image
from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    LEADER_A,
    csrf_of,
    login,
    logout,
    make_image,
)


def _grant_pricing(db, username=LEADER_A[0]):
    user = db.query(User).filter(User.username == username).one()
    user.pricing_access = True
    db.commit()
    return user


def _create_catalogue(db):
    camera = PricingItem(
        name="Quotation Camera",
        model="Q-CAM-1",
        unit_price=Decimal("100.00"),
    )
    camera.related_items = [
        PricingRelatedItem(name="SIM card", unit_price=Decimal("10.00")),
        PricingRelatedItem(name="Transportation", unit_price=Decimal("25.00")),
    ]
    recorder = PricingItem(
        name="Quotation Recorder",
        model="Q-NVR-1",
        unit_price=Decimal("500.00"),
    )
    db.add_all([camera, recorder])
    db.commit()
    return camera, recorder


def _attach_catalogue_image(db, item):
    stored = store_image("quotation-camera.jpg", make_image())
    item.image_storage_key = stored.storage_key
    item.image_thumbnail_key = stored.thumbnail_key
    item.image_original_filename = stored.original_filename
    item.image_content_type = stored.content_type
    item.image_file_size = stored.file_size
    db.commit()


def _quote_tokens(client):
    page = client.get("/pricing/quotations/new")
    assert page.status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    return csrf, form_token


def _submit_quote(client, camera, *, qdate="2026-07-29", **overrides):
    csrf, form_token = _quote_tokens(client)
    related = camera.related_items[0]
    payload = {
        "csrf_token": csrf,
        "form_token": form_token,
        "project_id": "1",
        "quotation_date": qdate,
        "valid_until": "2026-08-28",
        "discount_percent": "10",
        "vat_rate": "15",
        "notes": "Installation included.",
        "terms": "Payment within 30 days.",
        "line_0_item_id": str(camera.id),
        "line_0_quantity": "2",
        "line_0_unit_price": str(camera.unit_price),
        "line_0_related_ids": str(related.id),
        f"line_0_related_qty_{related.id}": "2",
        f"line_0_related_price_{related.id}": str(related.unit_price),
        "charge_manpower_quantity": "1",
        "charge_manpower_unit_price": "0",
        "charge_transportation_unit_price": "0",
        "charge_installation_quantity": "1",
        "charge_installation_unit_price": "0",
    }
    payload.update(overrides)
    return client.post("/pricing/quotations", data=payload)


def test_pricing_pages_are_protected_and_admin_pages_render(client):
    assert client.get("/pricing/items").status_code == 303

    login(client, *ADMIN)
    for path in (
        "/pricing/quotations",
        "/pricing/quotations/new",
        "/pricing/items",
        "/pricing/settings",
    ):
        response = client.get(path)
        assert response.status_code == 200
    page = client.get("/pricing/quotations").text
    assert 'data-nav-section="pricing"' in page
    assert 'href="/pricing/settings"' in page


def test_pricing_permission_is_configurable_for_technical_users(client, db):
    login(client, *LEADER_A)
    assert client.get("/pricing/items").status_code == 403
    assert 'data-nav-section="pricing"' not in client.get("/dashboard").text

    logout(client)
    login(client, *ADMIN)
    target = db.query(User).filter(User.username == LEADER_A[0]).one()
    token = csrf_of(client, "/users")
    response = client.post(
        f"/users/{target.id}/edit",
        data={
            "csrf_token": token,
            "full_name": target.full_name,
            "username": target.username,
            "role": "technical",
            "pricing_access": "1",
            "phone": "",
        },
    )
    assert response.status_code == 303
    db.refresh(target)
    assert target.pricing_access is True

    logout(client)
    login(client, *LEADER_A)
    assert client.get("/pricing/items").status_code == 200
    assert client.get("/pricing/quotations").status_code == 200
    assert client.get("/pricing/settings").status_code == 403
    page = client.get("/pricing/items").text
    assert 'data-nav-section="pricing"' in page
    assert 'href="/pricing/settings"' not in page


def test_customers_never_receive_pricing_access(client, db):
    customer = db.query(User).filter(User.username == CUSTOMER_A[0]).one()
    customer.pricing_access = True
    db.commit()
    login(client, *CUSTOMER_A)
    assert client.get("/pricing/items").status_code == 403
    assert 'data-nav-section="pricing"' not in client.get("/records").text


def test_item_and_related_item_crud_obeys_delete_rules(client, db):
    _grant_pricing(db)
    login(client, *LEADER_A)
    token = csrf_of(client, "/pricing/items")
    created = client.post(
        "/pricing/items",
        data={
            "csrf_token": token,
            "name": "Field Camera",
            "model": "FC-10",
            "unit_price": "123.45",
        },
    )
    assert created.status_code == 303
    item = db.query(PricingItem).filter(PricingItem.name == "Field Camera").one()

    related = client.post(
        "/pricing/related-items",
        data={
            "csrf_token": token,
            "main_item_id": str(item.id),
            "name": "SIM card",
            "unit_price": "12.50",
        },
    )
    assert related.status_code == 303
    child = db.query(PricingRelatedItem).filter_by(main_item_id=item.id).one()
    assert child.unit_price == Decimal("12.50")

    edited = client.post(
        f"/pricing/related-items/{child.id}/edit",
        data={"csrf_token": token, "name": "Data SIM", "unit_price": "15.00"},
    )
    assert edited.status_code == 303
    db.refresh(child)
    assert child.name == "Data SIM"
    assert client.post(
        f"/pricing/items/{item.id}/delete",
        data={"csrf_token": token},
    ).status_code == 403

    page = client.get("/pricing/items").text
    assert "Data SIM" in page
    assert "Delete" not in page


def test_main_item_image_is_validated_protected_and_removed(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    created = client.post(
        "/pricing/items",
        data={
            "csrf_token": token,
            "name": "Camera With Image",
            "model": "IMG-1",
            "unit_price": "250",
        },
        files={"image": ("camera.jpg", make_image(), "image/jpeg")},
    )
    assert created.status_code == 303
    item = db.query(PricingItem).filter_by(name="Camera With Image").one()
    assert item.image_storage_key
    assert item.image_thumbnail_key
    original_path = settings.upload_dir / item.image_storage_key
    thumbnail_path = settings.upload_dir / item.image_thumbnail_key
    assert original_path.is_file()
    assert thumbnail_path.is_file()

    image = client.get(f"/pricing/items/{item.id}/image")
    thumbnail = client.get(f"/pricing/items/{item.id}/image?size=thumb")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert thumbnail.status_code == 200

    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get(f"/pricing/items/{item.id}/image").status_code == 403

    logout(client)
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    removed = client.post(
        f"/pricing/items/{item.id}/remove-image",
        data={"csrf_token": token},
    )
    assert removed.status_code == 303
    db.refresh(item)
    assert item.image_storage_key is None
    assert not original_path.exists()
    assert not thumbnail_path.exists()


def test_invalid_pricing_item_image_is_rejected_without_creating_item(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    response = client.post(
        "/pricing/items",
        data={
            "csrf_token": token,
            "name": "Invalid Image Item",
            "model": "BAD-1",
            "unit_price": "10",
        },
        files={"image": ("fake.jpg", b"not an image", "image/jpeg")},
    )
    assert response.status_code == 303
    assert db.query(PricingItem).filter_by(name="Invalid Image Item").first() is None
    assert "not a real image" in client.get("/pricing/items").text


def test_pricing_settings_are_admin_only_and_validate(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/settings")
    invalid = client.post(
        "/pricing/settings",
        data={
            "csrf_token": token,
            "currency": "Saudi Riyal",
            "default_vat_rate": "101",
            "default_validity_days": "0",
            "quotation_prefix": "not valid!",
        },
    )
    assert invalid.status_code == 422
    assert db.get(PricingSettings, 1) is None

    saved = client.post(
        "/pricing/settings",
        data={
            "csrf_token": token,
            "currency": "sar",
            "default_vat_rate": "15",
            "default_validity_days": "45",
            "quotation_prefix": "AFQ",
            "company_name": "Afaqy Technology",
            "company_address": "Riyadh",
            "company_phone": "+966500000000",
            "company_email": "sales@example.com",
            "default_terms": "Payment within 30 days.",
            "default_manpower_price": "100",
            "default_transportation_price": "200",
            "default_installation_price": "300",
        },
    )
    assert saved.status_code == 303
    profile = db.get(PricingSettings, 1)
    assert profile.currency == "SAR"
    assert profile.quotation_prefix == "AFQ"
    assert profile.default_validity_days == 45
    assert profile.default_manpower_price == Decimal("100.00")
    assert profile.default_transportation_price == Decimal("200.00")
    assert profile.default_installation_price == Decimal("300.00")
    new_quote = client.get("/pricing/quotations/new").text
    assert 'name="charge_manpower_unit_price" type="number" min="0" step="0.01" value="100.00"' in new_quote


def test_quotation_saves_catalogue_and_project_snapshots_with_exact_totals(client, db):
    camera, _recorder = _create_catalogue(db)
    login(client, *ADMIN)
    response = _submit_quote(client, camera)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/pricing/quotations/")

    quotation = db.query(PricingQuotation).one()
    assert quotation.quotation_number == "QUO-2026-00001"
    assert quotation.project_name == "Tower A"
    assert quotation.lines[0].item_name == "Quotation Camera"
    assert quotation.lines[0].unit_price == Decimal("100.00")
    assert quotation.lines[0].related_items[0].unit_price == Decimal("10.00")
    totals = quotation_totals(quotation)
    assert totals == {
        "subtotal": Decimal("220.00"),
        "discount": Decimal("22.00"),
        "taxable": Decimal("198.00"),
        "vat": Decimal("29.70"),
        "grand_total": Decimal("227.70"),
    }

    camera.name = "Renamed Camera"
    camera.unit_price = Decimal("999.00")
    camera.related_items[0].unit_price = Decimal("88.00")
    project = quotation.project_name
    db.commit()
    db.expire_all()
    quotation = db.query(PricingQuotation).one()
    assert quotation.project_name == project
    assert quotation.lines[0].item_name == "Quotation Camera"
    assert quotation_totals(quotation)["grand_total"] == Decimal("227.70")


def test_create_quotation_commit_failure_removes_new_image_snapshots(
    client, db, monkeypatch
):
    camera, _recorder = _create_catalogue(db)
    _attach_catalogue_image(db, camera)
    login(client, *ADMIN)
    before = {path.name for path in settings.upload_dir.iterdir()}

    def fail_commit(_session):
        raise SQLAlchemyError("forced quotation commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = _submit_quote(client, camera)

    assert response.status_code == 422
    assert "The quotation could not be saved" in response.text
    assert {path.name for path in settings.upload_dir.iterdir()} == before
    assert db.query(PricingQuotation).count() == 0


def test_edit_quotation_commit_failure_removes_only_new_image_snapshots(
    client, db, monkeypatch
):
    camera, _recorder = _create_catalogue(db)
    _attach_catalogue_image(db, camera)
    login(client, *ADMIN)
    assert _submit_quote(client, camera).status_code == 303
    quotation = db.query(PricingQuotation).one()
    related = camera.related_items[0]
    edit_page = client.get(f"/pricing/quotations/{quotation.id}/edit")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', edit_page.text).group(1)
    before = {path.name for path in settings.upload_dir.iterdir()}

    def fail_commit(_session):
        raise SQLAlchemyError("forced quotation edit commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    response = client.post(
        f"/pricing/quotations/{quotation.id}/edit",
        data={
            "csrf_token": csrf,
            "project_id": "1",
            "quotation_date": "2026-07-29",
            "valid_until": "2026-08-28",
            "discount_percent": "5",
            "vat_rate": "15",
            "notes": "Edited quotation.",
            "terms": "Payment within 30 days.",
            "line_0_item_id": str(camera.id),
            "line_0_quantity": "2",
            "line_0_unit_price": str(camera.unit_price),
            "line_0_related_ids": str(related.id),
            f"line_0_related_qty_{related.id}": "2",
            f"line_0_related_price_{related.id}": str(related.unit_price),
            "charge_manpower_quantity": "1",
            "charge_manpower_unit_price": "0",
            "charge_transportation_unit_price": "0",
            "charge_installation_quantity": "1",
            "charge_installation_unit_price": "0",
        },
    )

    assert response.status_code == 422
    assert "The quotation could not be saved" in response.text
    assert {path.name for path in settings.upload_dir.iterdir()} == before


def test_quotation_rejects_unrelated_sub_item_and_duplicate_submission(client, db):
    camera, recorder = _create_catalogue(db)
    unrelated = PricingRelatedItem(
        main_item_id=recorder.id,
        name="Recorder disk",
        unit_price=Decimal("50.00"),
    )
    db.add(unrelated)
    db.commit()
    login(client, *ADMIN)
    csrf, form_token = _quote_tokens(client)
    payload = {
        "csrf_token": csrf,
        "form_token": form_token,
        "project_id": "1",
        "quotation_date": "2026-07-29",
        "valid_until": "2026-08-28",
        "discount_percent": "0",
        "vat_rate": "15",
        "line_0_item_id": str(camera.id),
        "line_0_quantity": "1",
        "line_0_unit_price": str(camera.unit_price),
        "line_0_related_ids": str(unrelated.id),
        f"line_0_related_qty_{unrelated.id}": "1",
        f"line_0_related_price_{unrelated.id}": str(unrelated.unit_price),
        "charge_manpower_quantity": "1",
        "charge_manpower_unit_price": "0",
        "charge_transportation_unit_price": "0",
        "charge_installation_quantity": "1",
        "charge_installation_unit_price": "0",
    }
    rejected = client.post("/pricing/quotations", data=payload)
    assert rejected.status_code == 422
    assert "unavailable" in rejected.text

    created = _submit_quote(client, camera)
    assert created.status_code == 303
    duplicate_payload = dict(payload)
    duplicate_payload["form_token"] = re.search(
        r'name="form_token" value="([^"]+)"',
        client.get("/pricing/quotations/new").text,
    ).group(1)
    duplicate_payload["line_0_related_ids"] = str(camera.related_items[0].id)
    duplicate_payload[f"line_0_related_qty_{camera.related_items[0].id}"] = "1"
    duplicate_payload[f"line_0_related_price_{camera.related_items[0].id}"] = str(
        camera.related_items[0].unit_price
    )
    first = client.post("/pricing/quotations", data=duplicate_payload)
    assert first.status_code == 303
    replay = client.post("/pricing/quotations", data=duplicate_payload)
    assert replay.status_code == 422
    assert "already submitted" in replay.text


def test_quotation_requires_optional_selection_or_one_skip_decision(client, db):
    camera, _recorder = _create_catalogue(db)
    login(client, *ADMIN)
    csrf, form_token = _quote_tokens(client)
    payload = {
        "csrf_token": csrf,
        "form_token": form_token,
        "project_id": "1",
        "quotation_date": "2026-07-29",
        "valid_until": "2026-08-28",
        "discount_percent": "0",
        "vat_rate": "15",
        "line_0_item_id": str(camera.id),
        "line_0_quantity": "1",
        "line_0_unit_price": "100",
        "charge_manpower_quantity": "1",
        "charge_manpower_unit_price": "0",
        "charge_transportation_unit_price": "0",
        "charge_installation_quantity": "1",
        "charge_installation_unit_price": "0",
    }
    missing_decision = client.post("/pricing/quotations", data=payload)
    assert missing_decision.status_code == 422
    assert "Select at least one optional item or tick Skip optional items." in (
        missing_decision.text
    )

    csrf, form_token = _quote_tokens(client)
    skip_payload = dict(payload)
    skip_payload.update(
        {
            "csrf_token": csrf,
            "form_token": form_token,
            "line_0_skip_optional_items": "1",
        }
    )
    skipped = client.post("/pricing/quotations", data=skip_payload)
    assert skipped.status_code == 303
    quotation = db.query(PricingQuotation).one()
    assert quotation.lines[0].skip_optional_items is True
    assert quotation.lines[0].related_items == []
    detail = client.get(f"/pricing/quotations/{quotation.id}").text
    assert "Optional items skipped" in detail


def test_quotation_rejects_selecting_and_skipping_optional_items(client, db):
    camera, _recorder = _create_catalogue(db)
    login(client, *ADMIN)
    related = camera.related_items[0]
    response = _submit_quote(
        client,
        camera,
        line_0_skip_optional_items="1",
    )
    assert response.status_code == 422
    assert "Select optional items or skip them, not both." in response.text
    assert db.query(PricingQuotation).count() == 0


def test_overridden_prices_and_required_charges_are_snapshotted_in_totals(client, db):
    camera, _recorder = _create_catalogue(db)
    login(client, *ADMIN)
    related = camera.related_items[0]
    response = _submit_quote(
        client,
        camera,
        line_0_unit_price="120",
        **{
            f"line_0_related_price_{related.id}": "15",
            "charge_manpower_quantity": "3",
            "charge_manpower_unit_price": "100",
            "charge_transportation_unit_price": "200",
            "charge_installation_quantity": "2",
            "charge_installation_unit_price": "150",
        },
    )
    assert response.status_code == 303
    quotation = db.query(PricingQuotation).one()
    assert quotation.lines[0].unit_price == Decimal("120.00")
    assert quotation.lines[0].related_items[0].unit_price == Decimal("15.00")
    assert {charge.charge_type for charge in quotation.charges} == {
        "manpower",
        "transportation",
        "installation",
    }
    totals = quotation_totals(quotation)
    assert totals == {
        "subtotal": Decimal("1070.00"),
        "discount": Decimal("107.00"),
        "taxable": Decimal("963.00"),
        "vat": Decimal("144.45"),
        "grand_total": Decimal("1107.45"),
    }

    camera.unit_price = Decimal("999.00")
    related.unit_price = Decimal("888.00")
    db.commit()
    db.expire_all()
    quotation = db.query(PricingQuotation).one()
    assert quotation_totals(quotation)["grand_total"] == Decimal("1107.45")
    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf.content)).pages
    )
    assert "Manpower" in text
    assert "Transportation" in text
    assert "Installation" in text
    assert "1,107.45 SAR" in text


def test_quotation_image_snapshot_survives_catalogue_removal_and_cleans_up(
    client,
    db,
):
    camera, _recorder = _create_catalogue(db)
    stored = store_image("quotation-camera.jpg", make_image())
    camera.image_storage_key = stored.storage_key
    camera.image_thumbnail_key = stored.thumbnail_key
    camera.image_original_filename = stored.original_filename
    camera.image_content_type = stored.content_type
    camera.image_file_size = stored.file_size
    db.commit()

    login(client, *ADMIN)
    created = _submit_quote(client, camera)
    assert created.status_code == 303
    quotation = db.query(PricingQuotation).one()
    line = quotation.lines[0]
    assert line.image_storage_key
    assert line.image_storage_key != camera.image_storage_key
    snapshot_original = settings.upload_dir / line.image_storage_key
    snapshot_thumbnail = settings.upload_dir / line.image_thumbnail_key
    assert snapshot_original.is_file()
    assert snapshot_thumbnail.is_file()

    detail = client.get(f"/pricing/quotations/{quotation.id}")
    assert detail.status_code == 200
    image_url = f"/pricing/quotations/{quotation.id}/lines/{line.id}/image"
    assert image_url in detail.text
    assert client.get(image_url).status_code == 200

    token = csrf_of(client, "/pricing/items")
    removed = client.post(
        f"/pricing/items/{camera.id}/remove-image",
        data={"csrf_token": token},
    )
    assert removed.status_code == 303
    db.refresh(camera)
    assert camera.image_storage_key is None
    assert client.get(image_url).status_code == 200
    assert snapshot_original.is_file()

    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    reader = PdfReader(io.BytesIO(pdf.content))
    assert len(reader.pages[0].images) >= 1

    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get(image_url).status_code == 403

    logout(client)
    login(client, *ADMIN)
    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    deleted = client.post(
        f"/pricing/quotations/{quotation.id}/delete",
        data={"csrf_token": token},
    )
    assert deleted.status_code == 303
    assert not snapshot_original.exists()
    assert not snapshot_thumbnail.exists()


def test_quotation_rejects_missing_required_charge(client, db):
    camera, _recorder = _create_catalogue(db)
    login(client, *ADMIN)
    response = _submit_quote(
        client,
        camera,
        charge_transportation_unit_price="",
    )
    assert response.status_code == 422
    assert "Enter a valid non-negative cost." in response.text
    assert db.query(PricingQuotation).count() == 0


def test_quotation_search_edit_pdf_and_admin_delete(client, db):
    camera, recorder = _create_catalogue(db)
    login(client, *ADMIN)
    _submit_quote(client, camera)
    quotation = db.query(PricingQuotation).one()

    search = client.get("/pricing/quotations?q=Tower+A")
    assert search.status_code == 200
    assert quotation.quotation_number in search.text
    assert client.get("/pricing/quotations?q=missing").text.count(
        quotation.quotation_number
    ) == 0

    token = csrf_of(client, f"/pricing/quotations/{quotation.id}/edit")
    edited = client.post(
        f"/pricing/quotations/{quotation.id}/edit",
        data={
            "csrf_token": token,
            "project_id": "1",
            "quotation_date": "2026-07-29",
            "valid_until": "2026-09-01",
            "discount_percent": "0",
            "vat_rate": "15",
            "notes": "Updated quotation.",
            "terms": "Updated terms.",
            "line_0_item_id": str(recorder.id),
            "line_0_quantity": "1",
            "line_0_unit_price": str(recorder.unit_price),
            "charge_manpower_quantity": "1",
            "charge_manpower_unit_price": "0",
            "charge_transportation_unit_price": "0",
            "charge_installation_quantity": "1",
            "charge_installation_unit_price": "0",
        },
    )
    assert edited.status_code == 303
    db.refresh(quotation)
    assert quotation.lines[0].item_name == "Quotation Recorder"
    assert quotation.notes == "Updated quotation."

    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf.content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert quotation.quotation_number in text
    assert "Quotation Recorder" in text
    assert "575.00 SAR" in text
    assert "Page 1" in text

    quotation_id = quotation.id
    deleted = client.post(
        f"/pricing/quotations/{quotation_id}/delete",
        data={"csrf_token": token},
    )
    assert deleted.status_code == 303
    db.expire_all()
    assert db.get(PricingQuotation, quotation_id) is None
