"""Pricing permissions, catalogue, quotation snapshots, totals, and PDF output."""
from __future__ import annotations

import io
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    GeneralMaintenanceRecord,
    InstallationRecord,
    MaintenanceRecord,
    PricingItem,
    PricingItemCategory,
    PricingItemPriceHistory,
    PricingQuotation,
    PricingQuotationInvoiceImage,
    PricingQuotationSiteSurveyImage,
    PricingRelatedItem,
    PricingSettings,
    User,
)
from app.pricing import quotation_totals
from app.quotation_planner import validate_installation_plan_state
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
    submit_installation,
    submit_record,
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
    files = overrides.pop("_files", None)
    headers = overrides.pop("_headers", None)
    payload.update(overrides)
    return client.post(
        "/pricing/quotations", data=payload, files=files, headers=headers
    )


def _camera_plan_state():
    return {
        "version": 1,
        "ppm": 30,
        "contentW": 1280,
        "contentH": 820,
        "hasBackground": True,
        "items": [
            {
                "id": "camera-one",
                "kind": "camera",
                "name": "Main gate camera",
                "type": "bullet",
                "shade": "black",
                "x": 220,
                "y": 180,
                "fov": 92,
                "range": 18.5,
                "rotation": 45,
                "color": "#2563eb",
                "opacity": 0.25,
                "widthMeters": 1.4,
                "mountedOnId": "solar-pole-one",
            },
            {
                "id": "barrier-one",
                "kind": "smart_barrier",
                "name": "Main gate barrier",
                "variant": "left",
                "x": 380,
                "y": 240,
                "widthMeters": 5,
                "rotation": 90,
                "opacity": 1,
            },
            {
                "id": "solar-pole-one",
                "kind": "solar_pole",
                "name": "Main gate solar pole",
                "variant": "standard",
                "x": 220,
                "y": 230,
                "widthMeters": 2,
                "rotation": 0,
                "opacity": 1,
            },
        ],
        "labels": [
            {
                "id": "label-one",
                "text": "Main gate",
                "x": 80,
                "y": 90,
                "width": 160,
                "fontSize": 22,
                "rotation": 0,
                "color": "#111827",
            }
        ],
    }


def test_camera_planner_is_embedded_and_fully_offline(client):
    login(client, *ADMIN)
    form = client.get("/pricing/quotations/new")
    assert form.status_code == 200
    assert 'src="/pricing/planner/embed"' in form.text
    planner = client.get("/pricing/planner/embed")
    assert planner.status_code == 200
    assert planner.headers["x-frame-options"] == "SAMEORIGIN"
    assert "/static/vendor/konva-9.3.22.min.js" in planner.text
    assert "/static/vendor/pdfjs-3.11.174.min.js" in planner.text
    for kind in (
        "smart_barrier",
        "generator",
        "solar_pole",
        "solar_panel",
        "guard_room",
        "metal_pole",
        "tree_pole",
        "sign",
    ):
        assert f'data-equipment-kind="{kind}"' in planner.text
    assert "/static/img/planner-equipment/barrier-left-transparent.png" in planner.text
    assert "/static/img/planner-equipment/metal-pole-white-transparent.png" in planner.text
    assert "/static/img/planner-equipment/metal-pole-black-transparent.png" in planner.text
    assert "/static/img/planner-equipment/tree-pole-front-transparent.png" in planner.text
    assert "/static/img/planner-equipment/tree-pole-side-transparent.png" in planner.text
    assert "/static/img/planner-equipment/sign-transparent.png" in planner.text
    assert 'id="cam-width"' in planner.text
    assert 'id="cam-mounted-on"' in planner.text
    assert "cdn.jsdelivr.net" not in planner.text
    assert "fonts.googleapis.com" not in planner.text


def test_tree_pole_front_and_side_variants_are_valid_plan_equipment():
    state = _camera_plan_state()
    state["items"].extend(
        [
            {
                "id": "tree-pole-front",
                "kind": "tree_pole",
                "name": "Tree pole front",
                "variant": "front",
                "x": 500,
                "y": 300,
                "widthMeters": 2.5,
                "rotation": 0,
                "opacity": 1,
            },
            {
                "id": "tree-pole-side",
                "kind": "tree_pole",
                "name": "Tree pole side",
                "variant": "side",
                "x": 600,
                "y": 300,
                "widthMeters": 2.5,
                "rotation": 0,
                "opacity": 1,
            },
        ]
    )
    normalized = validate_installation_plan_state(json.dumps(state))
    tree_variants = [
        item["variant"] for item in normalized["items"] if item["kind"] == "tree_pole"
    ]
    assert tree_variants == ["front", "side"]


def test_quotation_add_item_control_opens_catalogue_picker_at_end(client, db):
    camera, recorder = _create_catalogue(db)
    login(client, *ADMIN)
    page = client.get("/pricing/quotations/new")
    assert page.status_code == 200
    assert 'data-pricing-item-picker' in page.text
    assert 'data-pricing-item-picker-search' in page.text
    assert 'data-choose-pricing-item' in page.text
    assert f'data-item-id="{camera.id}"' in page.text
    assert f'data-item-id="{recorder.id}"' in page.text
    assert 'class="workflow-jumpbar no-print"' in page.text
    assert 'id="quotation-details"' in page.text
    assert 'id="quotation-items"' in page.text
    assert 'id="quotation-planner"' in page.text
    assert 'id="quotation-review"' in page.text
    assert 'class="sticky-form-actions no-print"' in page.text
    assert page.text.index('data-pricing-lines') < page.text.index(
        'class="pricing-add-line-footer"'
    )


def test_quotation_quantity_steppers_use_whole_units_without_changing_prices(client, db):
    _create_catalogue(db)
    login(client, *ADMIN)
    html = client.get("/pricing/quotations/new").text
    for field_name in (
        "line_0_quantity",
        "charge_manpower_quantity",
        "charge_transportation_quantity",
        "charge_installation_quantity",
    ):
        assert re.search(
            rf'name="{field_name}"[^>]*min="1" step="1"',
            html,
        )
    assert re.search(
        r'name="line_0_unit_price"[^>]*min="0" step="0.01"',
        html,
    )
    javascript = Path("app/static/js/app.js").read_text(encoding="utf-8")
    assert 'quantityInput.step = "1"' in javascript
    assert 'priceInput.step = "0.01"' in javascript


def test_quotation_camera_plan_is_saved_protected_exported_and_deleted(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    image = make_image(fmt="PNG")
    response = _submit_quote(
        client,
        camera,
        installation_plan_state=json.dumps(_camera_plan_state()),
        _files={
            "installation_plan_background": ("floor-plan.png", image, "image/png"),
            "installation_plan_output": ("camera-plan.png", image, "image/png"),
        },
    )
    assert response.status_code == 303
    quotation = db.query(PricingQuotation).order_by(PricingQuotation.id.desc()).first()
    assert quotation.installation_plan_state["items"][0]["name"] == "Main gate camera"
    assert quotation.installation_plan_state["items"][1]["name"] == "Main gate barrier"
    assert quotation.installation_plan_state["items"][0]["widthMeters"] == 1.4
    assert quotation.installation_plan_state["items"][0]["mountedOnId"] == "solar-pole-one"
    assert quotation.plan_background_storage_key
    assert quotation.plan_output_storage_key
    stored_keys = [
        quotation.plan_background_storage_key,
        quotation.plan_background_thumbnail_key,
        quotation.plan_output_storage_key,
        quotation.plan_output_thumbnail_key,
    ]
    assert all((settings.upload_dir / key).is_file() for key in stored_keys if key)

    detail = client.get(f"/pricing/quotations/{quotation.id}")
    assert detail.status_code == 200
    assert "Main gate camera" in detail.text
    assert "Main gate barrier" in detail.text
    assert "Main gate solar pole" in detail.text
    assert "Installation equipment schedule" in detail.text
    plan = client.get(f"/pricing/quotations/{quotation.id}/installation-plan/output")
    assert plan.status_code == 200
    assert plan.headers["content-type"] == "image/png"

    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    assert pdf.status_code == 200
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Installation plan" in text
    assert "Camera schedule" in text
    assert "Main gate camera" in text
    assert "Installation equipment schedule" in text
    assert "Main gate barrier" in text
    assert "Main gate solar pole" in text

    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get(
        f"/pricing/quotations/{quotation.id}/installation-plan/output"
    ).status_code == 403

    logout(client)
    login(client, *ADMIN)
    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    deleted = client.post(
        f"/pricing/quotations/{quotation.id}/delete",
        data={"csrf_token": token},
    )
    assert deleted.status_code == 303
    assert all(not (settings.upload_dir / key).exists() for key in stored_keys if key)


def test_invalid_camera_plan_is_rejected_without_saving_files(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    invalid = _camera_plan_state()
    invalid["items"][0]["fov"] = 999
    response = _submit_quote(
        client,
        camera,
        installation_plan_state=json.dumps(invalid),
        _files={
            "installation_plan_background": ("floor-plan.png", make_image(fmt="PNG"), "image/png"),
            "installation_plan_output": ("camera-plan.png", make_image(fmt="PNG"), "image/png"),
        },
        _headers={
            "Accept": "application/json",
            "X-Requested-With": "camera-planner",
        },
    )
    assert response.status_code == 422
    assert "invalid camera field of view" in response.json()["errors"]["installation_plan"]
    assert response.json()["form_token"]
    assert db.query(PricingQuotation).count() == 0


def test_invalid_equipment_variant_is_rejected(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    invalid = _camera_plan_state()
    invalid["items"][1]["variant"] = "unsupported"
    response = _submit_quote(
        client,
        camera,
        installation_plan_state=json.dumps(invalid),
        _files={
            "installation_plan_background": ("floor-plan.png", make_image(fmt="PNG"), "image/png"),
            "installation_plan_output": ("camera-plan.png", make_image(fmt="PNG"), "image/png"),
        },
        _headers={"Accept": "application/json", "X-Requested-With": "camera-planner"},
    )
    assert response.status_code == 422
    assert "invalid equipment variant" in response.json()["errors"]["installation_plan"]


def test_invalid_camera_mounting_reference_is_rejected(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    invalid = _camera_plan_state()
    invalid["items"][0]["mountedOnId"] = "missing-solar-pole"
    response = _submit_quote(
        client,
        camera,
        installation_plan_state=json.dumps(invalid),
        _files={
            "installation_plan_background": ("floor-plan.png", make_image(fmt="PNG"), "image/png"),
            "installation_plan_output": ("camera-plan.png", make_image(fmt="PNG"), "image/png"),
        },
        _headers={"Accept": "application/json", "X-Requested-With": "camera-planner"},
    )
    assert response.status_code == 422
    assert "invalid camera mounting reference" in response.json()["errors"]["installation_plan"]


def test_camera_can_be_grouped_with_a_metal_pole(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    state = _camera_plan_state()
    state["items"].append(
        {
            "id": "metal-pole-one",
            "kind": "metal_pole",
            "name": "Gate metal pole",
            "variant": "black",
            "x": 260,
            "y": 230,
            "widthMeters": 1.5,
            "rotation": 0,
            "opacity": 1,
        }
    )
    state["items"].append(
        {
            "id": "sign-one",
            "kind": "sign",
            "name": "Gate sign",
            "variant": "standard",
            "x": 520,
            "y": 260,
            "widthMeters": 3,
            "rotation": 0,
            "opacity": 1,
        }
    )
    state["items"][0]["mountedOnId"] = "metal-pole-one"
    response = _submit_quote(
        client,
        camera,
        installation_plan_state=json.dumps(state),
        _files={
            "installation_plan_background": ("floor-plan.png", make_image(fmt="PNG"), "image/png"),
            "installation_plan_output": ("camera-plan.png", make_image(fmt="PNG"), "image/png"),
        },
    )
    assert response.status_code == 303
    quotation = db.query(PricingQuotation).order_by(PricingQuotation.id.desc()).first()
    assert quotation.installation_plan_state["items"][0]["mountedOnId"] == "metal-pole-one"
    assert any(
        item["kind"] == "sign" for item in quotation.installation_plan_state["items"]
    )


def test_purchase_invoice_images_are_protected_exported_and_cleaned_up(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    assert _submit_quote(client, camera).status_code == 303
    quotation = db.query(PricingQuotation).order_by(PricingQuotation.id.desc()).first()
    edit_path = f"/pricing/quotations/{quotation.id}/edit"
    edit_page = client.get(edit_path)
    assert edit_page.status_code == 200
    assert 'id="purchase-invoice-proof"' in edit_page.text
    assert 'name="invoice_images"' in edit_page.text
    assert "data-invoice-upload-queue" in edit_page.text
    assert "data-invoice-file-list" in edit_page.text
    assert "data-invoice-upload-reminder" in edit_page.text
    assert "Remember to click Upload invoice images" in edit_page.text
    invoice_script = client.get("/static/js/app.js")
    assert invoice_script.status_code == 200
    assert "selectedFiles.push(file)" in invoice_script.text
    assert "replaceInputFiles" in invoice_script.text
    assert "reminder.hidden = selectedFiles.length === 0" in invoice_script.text
    upload_styles = client.get("/static/css/app.css")
    assert upload_styles.status_code == 200
    assert ".alert[hidden] { display: none; }" in upload_styles.text
    token = csrf_of(client, edit_path)
    uploaded = client.post(
        f"/pricing/quotations/{quotation.id}/invoice-images",
        data={"csrf_token": token, "return_to": "edit"},
        files=[
            ("invoice_images", ("supplier-invoice-1.png", make_image(fmt="PNG"), "image/png")),
            ("invoice_images", ("supplier-invoice-2.jpg", make_image(), "image/jpeg")),
        ],
    )
    assert uploaded.status_code == 303
    assert uploaded.headers["location"] == f"{edit_path}#purchase-invoice-proof"
    invoices = db.query(PricingQuotationInvoiceImage).order_by(
        PricingQuotationInvoiceImage.id
    ).all()
    assert [invoice.original_filename for invoice in invoices] == [
        "supplier-invoice-1.png",
        "supplier-invoice-2.jpg",
    ]
    stored_keys = [
        key
        for invoice in invoices
        for key in (invoice.storage_key, invoice.thumbnail_key)
        if key
    ]
    assert all((settings.upload_dir / key).is_file() for key in stored_keys)

    edited = client.get(edit_path)
    assert "supplier-invoice-1.png" in edited.text
    assert "supplier-invoice-2.jpg" in edited.text

    detail = client.get(f"/pricing/quotations/{quotation.id}")
    assert detail.status_code == 200
    assert "supplier-invoice-1.png" in detail.text
    proof = client.get(
        f"/pricing/quotations/{quotation.id}/invoice-images/{invoices[0].id}"
    )
    assert proof.status_code == 200
    assert proof.headers["content-type"] == "image/png"
    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages
    )
    assert "Purchase invoice proof 1 of 2" in pdf_text
    assert "supplier-invoice-2.jpg" in pdf_text

    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get(
        f"/pricing/quotations/{quotation.id}/invoice-images/{invoices[0].id}"
    ).status_code == 403

    logout(client)
    login(client, *ADMIN)
    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    removed_keys = (invoices[0].storage_key, invoices[0].thumbnail_key)
    removed = client.post(
        f"/pricing/quotations/{quotation.id}/invoice-images/{invoices[0].id}/delete",
        data={"csrf_token": token, "return_to": "edit"},
    )
    assert removed.status_code == 303
    assert removed.headers["location"] == f"{edit_path}#purchase-invoice-proof"
    assert all(
        not (settings.upload_dir / key).exists() for key in removed_keys if key
    )

    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    assert client.post(
        f"/pricing/quotations/{quotation.id}/delete",
        data={"csrf_token": token},
    ).status_code == 303
    assert all(not (settings.upload_dir / key).exists() for key in stored_keys)


def test_invoice_image_upload_is_atomic_when_one_file_is_invalid(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    assert _submit_quote(client, camera).status_code == 303
    quotation = db.query(PricingQuotation).order_by(PricingQuotation.id.desc()).first()
    before = {path for path in settings.upload_dir.rglob("*") if path.is_file()}
    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    response = client.post(
        f"/pricing/quotations/{quotation.id}/invoice-images",
        data={"csrf_token": token},
        files=[
            ("invoice_images", ("valid.png", make_image(fmt="PNG"), "image/png")),
            ("invoice_images", ("invalid.jpg", b"not an image", "image/jpeg")),
        ],
    )
    assert response.status_code == 303
    assert db.query(PricingQuotationInvoiceImage).count() == 0
    assert {path for path in settings.upload_dir.rglob("*") if path.is_file()} == before


def test_site_survey_images_are_separate_protected_exported_and_cleaned_up(client, db):
    login(client, *ADMIN)
    camera, _ = _create_catalogue(db)
    new_page = client.get("/pricing/quotations/new")
    assert 'name="site_survey_images"' in new_page.text
    assert "data-image-upload-reminder" in new_page.text
    assert "They will upload when you click Create quotation" in new_page.text
    assert _submit_quote(
        client,
        camera,
        _files={
            "site_survey_images": (
                "site-layout-1.png",
                make_image(fmt="PNG"),
                "image/png",
            )
        },
    ).status_code == 303
    quotation = db.query(PricingQuotation).order_by(PricingQuotation.id.desc()).first()
    edit_path = f"/pricing/quotations/{quotation.id}/edit"
    edit_page = client.get(edit_path)
    assert edit_page.status_code == 200
    assert 'id="site-survey-layouts"' in edit_page.text
    assert 'name="site_survey_images"' in edit_page.text
    assert "data-image-upload-queue" in edit_page.text
    assert "Remember to click Upload site survey images" in edit_page.text

    token = csrf_of(client, edit_path)
    uploaded = client.post(
        f"/pricing/quotations/{quotation.id}/site-survey-images",
        data={"csrf_token": token, "return_to": "edit"},
        files={
            "site_survey_images": ("site-layout-2.jpg", make_image(), "image/jpeg")
        },
    )
    assert uploaded.status_code == 303
    assert uploaded.headers["location"] == f"{edit_path}#site-survey-layouts"
    survey_images = db.query(PricingQuotationSiteSurveyImage).order_by(
        PricingQuotationSiteSurveyImage.id
    ).all()
    assert [image.original_filename for image in survey_images] == [
        "site-layout-1.png",
        "site-layout-2.jpg",
    ]
    assert db.query(PricingQuotationInvoiceImage).count() == 0
    stored_keys = [
        key
        for survey_image in survey_images
        for key in (survey_image.storage_key, survey_image.thumbnail_key)
        if key
    ]
    assert all((settings.upload_dir / key).is_file() for key in stored_keys)

    detail = client.get(f"/pricing/quotations/{quotation.id}")
    assert "site-layout-1.png" in detail.text
    image_response = client.get(
        f"/pricing/quotations/{quotation.id}/site-survey-images/{survey_images[0].id}"
    )
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages
    )
    assert "Site survey layout 1 of 2" in pdf_text
    assert "site-layout-2.jpg" in pdf_text

    logout(client)
    login(client, *CUSTOMER_A)
    assert client.get(
        f"/pricing/quotations/{quotation.id}/site-survey-images/{survey_images[0].id}"
    ).status_code == 403

    logout(client)
    login(client, *ADMIN)
    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    removed_keys = (survey_images[0].storage_key, survey_images[0].thumbnail_key)
    removed = client.post(
        f"/pricing/quotations/{quotation.id}/site-survey-images/{survey_images[0].id}/delete",
        data={"csrf_token": token, "return_to": "edit"},
    )
    assert removed.status_code == 303
    assert removed.headers["location"] == f"{edit_path}#site-survey-layouts"
    assert all(not (settings.upload_dir / key).exists() for key in removed_keys if key)

    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    assert client.post(
        f"/pricing/quotations/{quotation.id}/delete", data={"csrf_token": token}
    ).status_code == 303
    assert all(not (settings.upload_dir / key).exists() for key in stored_keys)


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


def test_item_categories_assign_existing_items_and_group_item_pickers(client, db):
    camera, _recorder = _create_catalogue(db)
    _grant_pricing(db)
    login(client, *LEADER_A)
    token = csrf_of(client, "/pricing/items")

    created = client.post(
        "/pricing/categories",
        data={"csrf_token": token, "name": "Cameras"},
    )
    assert created.status_code == 303
    category = db.query(PricingItemCategory).filter_by(name="Cameras").one()

    duplicate = client.post(
        "/pricing/categories",
        data={"csrf_token": token, "name": "cameras"},
    )
    assert duplicate.status_code == 303
    assert db.query(PricingItemCategory).count() == 1

    assigned = client.post(
        f"/pricing/items/{camera.id}/edit",
        data={
            "csrf_token": token,
            "name": camera.name,
            "model": camera.model,
            "unit_price": str(camera.unit_price),
            "currency": camera.currency,
            "category_id": str(category.id),
            "service_enabled": "1",
        },
    )
    assert assigned.status_code == 303
    db.refresh(camera)
    assert camera.category_id == category.id

    page = client.get("/pricing/items?q=Cameras")
    assert page.status_code == 200
    assert "Quotation Camera" in page.text
    assert "Cameras" in page.text

    quotation_form = client.get("/pricing/quotations/new")
    assert quotation_form.status_code == 200
    assert '<h3>Cameras</h3>' in quotation_form.text
    assert "Quotation Camera" in quotation_form.text

    installation_form = client.get("/installations/submit")
    assert installation_form.status_code == 200
    assert '<h3>Cameras</h3>' in installation_form.text

    renamed = client.post(
        f"/pricing/categories/{category.id}/edit",
        data={"csrf_token": token, "name": "Security Cameras"},
    )
    assert renamed.status_code == 303
    db.refresh(category)
    assert category.name == "Security Cameras"

    assert client.post(
        f"/pricing/categories/{category.id}/delete",
        data={"csrf_token": token},
    ).status_code == 403

    logout(client)
    login(client, *ADMIN)
    admin_token = csrf_of(client, "/pricing/items")
    in_use = client.post(
        f"/pricing/categories/{category.id}/delete",
        data={"csrf_token": admin_token},
    )
    assert in_use.status_code == 303
    assert db.get(PricingItemCategory, category.id) is not None

    unassigned = client.post(
        f"/pricing/items/{camera.id}/edit",
        data={
            "csrf_token": admin_token,
            "name": camera.name,
            "model": camera.model,
            "unit_price": str(camera.unit_price),
            "currency": camera.currency,
            "category_id": "",
            "service_enabled": "1",
        },
    )
    assert unassigned.status_code == 303
    deleted = client.post(
        f"/pricing/categories/{category.id}/delete",
        data={"csrf_token": admin_token},
    )
    assert deleted.status_code == 303
    category_id = category.id
    db.expire_all()
    assert db.get(PricingItemCategory, category_id) is None


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
        "discount": Decimal("0.00"),
        "taxable": Decimal("220.00"),
        "vat": Decimal("0.00"),
        "grand_total": Decimal("220.00"),
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
    assert quotation_totals(quotation)["grand_total"] == Decimal("220.00")


def test_quotation_numbers_lines_and_supports_multiple_alternatives(client, db):
    camera, recorder = _create_catalogue(db)
    third_item = PricingItem(
        name="Alternative Solar Camera",
        model="ALT-SOLAR-1",
        unit_price=Decimal("350.00"),
    )
    db.add(third_item)
    db.commit()
    login(client, *ADMIN)

    response = _submit_quote(
        client,
        camera,
        line_1_item_id=str(recorder.id),
        line_1_quantity="1",
        line_1_unit_price=str(recorder.unit_price),
        line_1_alternative_to_index="0",
        line_2_item_id=str(third_item.id),
        line_2_quantity="1",
        line_2_unit_price=str(third_item.unit_price),
        line_2_alternative_to_index="0",
    )

    assert response.status_code == 303
    quotation = db.query(PricingQuotation).one()
    assert [line.position for line in quotation.lines] == [1, 2, 3]
    assert quotation.lines[0].alternative_to is None
    assert quotation.lines[1].alternative_to is quotation.lines[0]
    assert quotation.lines[2].alternative_to is quotation.lines[0]
    assert quotation.lines[1].unit_price == Decimal("500.00")
    assert quotation.lines[2].unit_price == Decimal("350.00")

    detail = client.get(f"/pricing/quotations/{quotation.id}")
    assert detail.status_code == 200
    assert detail.text.count("Alternative to item 1") == 2

    edit = client.get(f"/pricing/quotations/{quotation.id}/edit")
    assert edit.status_code == 200
    assert 'name="line_1_alternative_to_index"' in edit.text
    assert '<option value="0" selected>Item 1</option>' in edit.text

    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    assert pdf.status_code == 200
    pdf_text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf.content)).pages
    )
    assert pdf_text.count("Alternative to item 1") == 2


def test_quotation_rejects_self_and_circular_alternative_links(client, db):
    camera, recorder = _create_catalogue(db)
    login(client, *ADMIN)

    self_link = _submit_quote(
        client,
        camera,
        line_0_alternative_to_index="0",
    )
    assert self_link.status_code == 422
    assert "An item cannot be an alternative to itself." in self_link.text
    assert db.query(PricingQuotation).count() == 0

    circular = _submit_quote(
        client,
        camera,
        line_0_alternative_to_index="1",
        line_1_item_id=str(recorder.id),
        line_1_quantity="1",
        line_1_unit_price=str(recorder.unit_price),
        line_1_alternative_to_index="0",
    )
    assert circular.status_code == 422
    assert "Alternative items cannot form a circular link." in circular.text
    assert db.query(PricingQuotation).count() == 0


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
        "discount": Decimal("0.00"),
        "taxable": Decimal("1070.00"),
        "vat": Decimal("0.00"),
        "grand_total": Decimal("1070.00"),
    }

    camera.unit_price = Decimal("999.00")
    related.unit_price = Decimal("888.00")
    db.commit()
    db.expire_all()
    quotation = db.query(PricingQuotation).one()
    assert quotation_totals(quotation)["grand_total"] == Decimal("1070.00")
    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf.content)).pages
    )
    assert "Manpower" in text
    assert "Transportation" in text
    assert "Installation" in text
    assert "600.00 SAR" in text
    assert "Grand total" not in text


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
    assert "500.00 SAR" in text
    assert "Grand total" not in text
    assert "Page 1" in text

    quotation_id = quotation.id
    deleted = client.post(
        f"/pricing/quotations/{quotation_id}/delete",
        data={"csrf_token": token},
    )
    assert deleted.status_code == 303
    db.expire_all()
    assert db.get(PricingQuotation, quotation_id) is None


def test_admin_deleting_quotation_preserves_all_service_records(client, db):
    camera, _ = _create_catalogue(db)
    login(client, *ADMIN)
    _submit_quote(client, camera)
    quotation = db.query(PricingQuotation).one()
    quotation_id = quotation.id
    quotation_number = quotation.quotation_number

    logout(client)
    login(client, *LEADER_A)
    assert submit_installation(client, serial_number="QUOTE-DELETE-INSTALL").status_code == 303
    assert submit_record(client, notes="Old preventive quotation link.").status_code == 303
    page = client.get("/general-maintenance")
    general = client.post(
        "/general-maintenance/submit",
        data={
            "csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1),
            "form_token": re.search(r'name="form_token" value="([^"]+)"', page.text).group(1),
            "project_id": "1",
            "work_site_id": "1",
            "service_type_id": "1",
            "installed_device_id": "1",
            "result_0": "completed_successfully",
            "notes": "Old maintenance quotation link.",
        },
        files={"photos_0": ("proof.jpg", make_image(), "image/jpeg")},
    )
    assert general.status_code == 303

    installation = db.query(InstallationRecord).one()
    preventive = db.query(MaintenanceRecord).one()
    maintenance = db.query(GeneralMaintenanceRecord).one()
    for record in (installation, preventive, maintenance):
        record.quotation_id = quotation_id
        record.quotation_number = quotation_number
        for item in record.work_items:
            item.quotation_id = quotation_id
            item.quotation_number = quotation_number
    db.commit()
    record_ids = (installation.id, preventive.id, maintenance.id)

    logout(client)
    login(client, *ADMIN)
    token = csrf_of(client, f"/pricing/quotations/{quotation_id}")
    deleted = client.post(
        f"/pricing/quotations/{quotation_id}/delete",
        data={"csrf_token": token},
    )

    assert deleted.status_code == 303
    db.expire_all()
    assert db.get(PricingQuotation, quotation_id) is None
    installation = db.get(InstallationRecord, record_ids[0])
    preventive = db.get(MaintenanceRecord, record_ids[1])
    maintenance = db.get(GeneralMaintenanceRecord, record_ids[2])
    assert installation is not None
    assert preventive is not None
    assert maintenance is not None
    assert installation.quotation_id is None
    assert installation.quotation_number == quotation_number
    assert installation.work_items[0].quotation_id is None
    assert installation.work_items[0].quotation_number == quotation_number
    for record in (preventive, maintenance):
        assert record.quotation_id is None
        assert record.quotation_number is None
        assert record.work_items[0].quotation_id is None
        assert record.work_items[0].quotation_number is None


def test_admin_can_delete_quotations_from_list_and_in_bulk(client, db):
    camera, _ = _create_catalogue(db)
    login(client, *ADMIN)
    assert _submit_quote(client, camera).status_code == 303
    assert _submit_quote(client, camera).status_code == 303
    quotations = db.query(PricingQuotation).order_by(PricingQuotation.id).all()
    quotation_ids = [quotation.id for quotation in quotations]

    page = client.get("/pricing/quotations")
    assert page.status_code == 200
    assert 'action="/pricing/quotations/bulk-delete"' in page.text
    assert page.text.count('name="quotation_ids"') == 2
    for quotation in quotations:
        assert f'formaction="/pricing/quotations/{quotation.id}/delete"' in page.text

    _grant_pricing(db)
    logout(client)
    login(client, *LEADER_A)
    technical_page = client.get("/pricing/quotations")
    assert technical_page.status_code == 200
    assert 'name="quotation_ids"' not in technical_page.text
    assert 'data-quotation-bulk-delete' not in technical_page.text
    denied = client.post(
        "/pricing/quotations/bulk-delete",
        data={
            "csrf_token": csrf_of(client, "/pricing/quotations"),
            "quotation_ids": quotation_ids,
        },
    )
    assert denied.status_code == 403

    logout(client)
    login(client, *ADMIN)
    deleted = client.post(
        "/pricing/quotations/bulk-delete",
        data={
            "csrf_token": csrf_of(client, "/pricing/quotations"),
            "quotation_ids": quotation_ids,
        },
    )
    assert deleted.status_code == 303
    db.expire_all()
    assert db.query(PricingQuotation).count() == 0


def test_mixed_currency_lines_and_derived_required_charges(client, db):
    camera, _recorder = _create_catalogue(db)
    camera.currency = "USD"
    camera.related_items[0].currency = "SAR"
    db.commit()
    login(client, *ADMIN)
    related = camera.related_items[0]

    response = _submit_quote(
        client,
        camera,
        line_0_currency="USD",
        charge_manpower_quantity="3",
        charge_manpower_unit_price="100",
        charge_manpower_currency="USD",
        charge_transportation_quantity="2",
        charge_transportation_unit_price="50",
        charge_transportation_currency="SAR",
        charge_installation_quantity="2",
        **{f"line_0_related_currency_{related.id}": "SAR"},
    )
    assert response.status_code == 303
    quotation = db.query(PricingQuotation).one()
    assert quotation.lines[0].currency == "USD"
    assert quotation.lines[0].related_items[0].currency == "SAR"
    charges = {charge.charge_type: charge for charge in quotation.charges}
    assert charges["manpower"].quantity == Decimal("3.00")
    assert charges["manpower"].currency == "USD"
    assert charges["transportation"].quantity == Decimal("2.00")
    assert charges["transportation"].currency == "SAR"
    assert charges["installation"].unit_price == Decimal("300.00")
    assert charges["installation"].currency == "USD"

    detail = client.get(response.headers["location"]).text
    assert "Grand total" not in detail
    assert "200.00 USD" in detail
    assert "100.00 SAR" in detail


def test_pricing_item_is_the_service_catalogue_source(client, db):
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/items")
    created = client.post(
        "/pricing/items",
        data={
            "csrf_token": token,
            "name": "Unified Camera",
            "model": "UC-1",
            "unit_price": "75",
            "currency": "SAR",
            "service_enabled": "1",
        },
    )
    assert created.status_code == 303
    item = db.query(PricingItem).filter_by(name="Unified Camera").one()
    assert item.legacy_device is not None
    assert item.legacy_device.is_active is True
    assert "Unified Camera" in client.get("/installations/submit").text
    assert 'href="/devices"' not in client.get("/dashboard").text
    assert client.get("/devices").headers["location"] == "/pricing/items"

    edited = client.post(
        f"/pricing/items/{item.id}/edit",
        data={
            "csrf_token": token,
            "name": item.name,
            "model": item.model,
            "unit_price": str(item.unit_price),
            "currency": item.currency,
            "service_enabled": "0",
        },
    )
    assert edited.status_code == 303
    db.refresh(item)
    assert item.service_enabled is False
    assert item.legacy_device.is_active is False
    assert "Unified Camera" not in client.get("/installations/submit").text


def test_quotation_pdf_embeds_an_arabic_font_for_catalogue_text(client, db):
    camera, _recorder = _create_catalogue(db)
    camera.name = "كاميرا البوابة"
    camera.related_items[0].name = "بطاقة اتصال"
    db.commit()
    login(client, *ADMIN)
    created = _submit_quote(client, camera)
    assert created.status_code == 303
    quotation = db.query(PricingQuotation).one()
    response = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    assert response.status_code == 200
    assert b"NotoSansArabic" in response.content


def test_quotation_custom_addressee_is_snapshotted_and_printed(client, db):
    camera, _recorder = _create_catalogue(db)
    login(client, *ADMIN)

    created = _submit_quote(
        client,
        camera,
        addressee_source="custom",
        addressee_name="Noura Al Saud",
        addressee_title="Procurement Manager",
        addressee_email="noura@example.com",
        addressee_phone="+966500000000",
    )

    assert created.status_code == 303
    quotation = db.query(PricingQuotation).one()
    assert quotation.addressee_source == "custom"
    assert quotation.addressee_name == "Noura Al Saud"
    assert quotation.addressee_title == "Procurement Manager"
    detail = client.get(f"/pricing/quotations/{quotation.id}")
    assert detail.status_code == 200
    assert "Noura Al Saud" in detail.text
    items_page = client.get("/pricing/items")
    assert items_page.status_code == 200
    assert f'data-context="{quotation.quotation_number}"' in items_page.text
    assert 'data-price="100.00 SAR"' in items_page.text
    pdf = client.get(f"/pricing/quotations/{quotation.id}/pdf")
    assert pdf.status_code == 200
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Noura Al Saud" in text


def test_quotation_can_target_customer_assigned_to_selected_project(client, db):
    camera, _recorder = _create_catalogue(db)
    login(client, *ADMIN)
    form = client.get("/pricing/quotations/new")
    assert 'value="customer:5"' in form.text

    created = _submit_quote(client, camera, addressee_source="customer:5")

    assert created.status_code == 303
    quotation = db.query(PricingQuotation).one()
    assert quotation.addressee_user_id == 5
    assert quotation.addressee_name == "Customer A"


def test_catalogue_price_edit_creates_history_and_audit_event(client, db):
    login(client, *ADMIN)
    item = db.query(PricingItem).filter_by(name="IP Camera").one()
    token = csrf_of(client, "/pricing/items")

    response = client.post(
        f"/pricing/items/{item.id}/edit",
        data={
            "csrf_token": token,
            "name": item.name,
            "model": item.model,
            "unit_price": "125.50",
            "currency": "SAR",
            "service_enabled": "1",
        },
    )

    assert response.status_code == 303
    db.expire_all()
    history = db.query(PricingItemPriceHistory).filter_by(pricing_item_id=item.id).one()
    assert history.old_price == Decimal("100.00")
    assert history.new_price == Decimal("125.50")
    assert history.changed_by_name == "Test Admin"
    price_page = client.get("/pricing/items")
    assert price_page.status_code == 200
    assert 'data-value="125.50"' in price_page.text
    assert 'data-price="125.50 SAR"' in price_page.text
    event = (
        db.query(AuditEvent)
        .filter_by(entity_type="pricing_item", entity_id=str(item.id), action="update")
        .one()
    )
    assert event.changes["price"] == {
        "before": "100.00 SAR",
        "after": "125.50 SAR",
    }
    page = client.get("/admin/audit-log")
    assert page.status_code == 200
    assert "Test Admin" in page.text
    assert "125.50 SAR" in page.text
