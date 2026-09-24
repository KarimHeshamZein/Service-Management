from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal

from pypdf import PdfReader
from reportlab.pdfgen import canvas

from app.config import settings
from app.models import (
    PricingItem,
    PricingItemCategory,
    PricingRelatedItem,
    PurchaseDocument,
    PurchaseDocumentItem,
    User,
    UserDepartmentPermission,
)
from app.uploads import store_image
from tests.conftest import ADMIN, LEADER_A, csrf_of, login, logout, make_image


def _pdf_bytes() -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(72, 760, "Supplier document page")
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _catalogue(db):
    root = PricingItemCategory(name="Cameras")
    sub = PricingItemCategory(name="Hikvision", parent=root)
    camera = db.query(PricingItem).filter_by(name="IP Camera").one()
    camera.category = sub
    camera.related_items = [PricingRelatedItem(name="Camera bracket", unit_price=Decimal("20.00"), currency="SAR")]
    recorder = PricingItem(name="Network Recorder", model="NVR-8", unit_price=Decimal("500.00"), currency="SAR", category=root)
    stored = store_image("camera.jpg", make_image())
    camera.image_storage_key = stored.storage_key
    camera.image_thumbnail_key = stored.thumbnail_key
    camera.image_original_filename = stored.original_filename
    camera.image_content_type = stored.content_type
    camera.image_file_size = stored.file_size
    db.add_all([root, recorder])
    db.commit()
    return camera, camera.related_items[0], recorder, root, sub


def _selection(*rows):
    return json.dumps([
        {"kind": kind, "id": item_id, "unit_price": price, "currency": currency}
        for kind, item_id, price, currency in rows
    ])


def _create_document(client, selection, *, supplier="Supplier A", document_type="purchase_invoice", document_date="2026-08-26"):
    token = csrf_of(client, "/pricing/purchase-documents/new")
    return client.post(
        "/pricing/purchase-documents",
        data={
            "csrf_token": token,
            "document_type": document_type,
            "supplier_name": supplier,
            "document_date": document_date,
            "selected_items_json": selection,
        },
        files=[
            ("files", ("invoice.jpg", make_image(), "image/jpeg")),
            ("files", ("terms.pdf", _pdf_bytes(), "application/pdf")),
        ],
    )


def test_purchase_documents_use_folder_and_image_catalogue(client, db):
    camera, related, recorder, root, sub = _catalogue(db)
    login(client, *ADMIN)
    navigation = client.get("/dashboard").text
    assert "Purchase documents" in navigation

    overview = client.get("/pricing/purchase-documents")
    assert overview.status_code == 200
    assert "Cameras" in overview.text
    root_page = client.get(f"/pricing/purchase-documents?category={root.id}")
    assert "Hikvision" in root_page.text
    assert "Network Recorder" in root_page.text
    sub_page = client.get(f"/pricing/purchase-documents?category={sub.id}")
    assert "IP Camera" in sub_page.text
    assert "Camera bracket" in sub_page.text
    assert f"/pricing/items/{camera.id}/image?size=thumb" in sub_page.text

    form = client.get("/pricing/purchase-documents/new")
    assert form.status_code == 200
    assert "purchase-catalogue-data" in form.text
    assert "Camera bracket" in form.text
    assert "data-open-purchase-picker" in form.text


def test_one_document_is_shared_across_main_and_related_items_with_one_preview(client, db):
    camera, related, _, _, _ = _catalogue(db)
    login(client, *ADMIN)
    response = _create_document(
        client,
        _selection(
            ("main", camera.id, "1200.00", "SAR"),
            ("related", related.id, "35.50", "SAR"),
        ),
    )
    assert response.status_code == 303

    db.expire_all()
    document = db.query(PurchaseDocument).one()
    assert len(document.item_links) == 2
    assert len(document.files) == 2
    assert {link.unit_price for link in document.item_links} == {Decimal("1200.00"), Decimal("35.50")}

    main_page = client.get(f"/pricing/purchase-documents/items/main/{camera.id}")
    related_page = client.get(f"/pricing/purchase-documents/items/related/{related.id}")
    assert "Supplier A" in main_page.text
    assert "Supplier A" in related_page.text
    assert "Shared with 2 item(s)" in main_page.text

    preview = client.get(f"/pricing/purchase-documents/{document.id}/preview")
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("application/pdf")
    assert len(PdfReader(io.BytesIO(preview.content)).pages) == 2

    download = client.get(f"/pricing/purchase-documents/{document.id}/download")
    assert download.status_code == 200
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert len(archive.namelist()) == 2


def test_edit_shared_document_replaces_item_links_without_copying_files(client, db):
    camera, related, recorder, _, _ = _catalogue(db)
    login(client, *ADMIN)
    _create_document(client, _selection(("main", camera.id, "100", "SAR"), ("related", related.id, "20", "SAR")))
    db.expire_all()
    document = db.query(PurchaseDocument).one()
    storage_keys = [entry.storage_key for entry in document.files]
    token = csrf_of(client, f"/pricing/purchase-documents/{document.id}/edit")
    response = client.post(
        f"/pricing/purchase-documents/{document.id}/edit",
        data={
            "csrf_token": token,
            "document_type": "purchase_invoice",
            "supplier_name": "Supplier A Updated",
            "document_date": "2026-08-27",
            "selected_items_json": _selection(("main", camera.id, "110", "SAR"), ("main", recorder.id, "550", "SAR")),
        },
    )
    assert response.status_code == 303
    db.expire_all()
    document = db.query(PurchaseDocument).one()
    assert len(document.files) == 2
    assert [entry.storage_key for entry in document.files] == storage_keys
    assert {(link.pricing_item_id, link.related_item_id) for link in document.item_links} == {(camera.id, None), (recorder.id, None)}
    assert db.query(PurchaseDocumentItem).filter_by(related_item_id=related.id).count() == 0


def test_item_price_analysis_filters_type_and_exports_pdf(client, db):
    camera, _, _, _, _ = _catalogue(db)
    login(client, *ADMIN)
    _create_document(client, _selection(("main", camera.id, "100", "SAR")), supplier="Supplier A", document_date="2026-08-20")
    _create_document(client, _selection(("main", camera.id, "125", "SAR")), supplier="Supplier B", document_type="supplier_quotation", document_date="2026-08-25")

    page = client.get(f"/pricing/purchase-documents/items/main/{camera.id}")
    assert "125.00 SAR" in page.text
    assert "+25.00 SAR" in page.text
    assert "Supplier A" in page.text and "Supplier B" in page.text

    filtered = client.get(f"/pricing/purchase-documents/items/main/{camera.id}?document_type=supplier_quotation")
    assert "Supplier B" in filtered.text
    assert "Supplier A" not in filtered.text
    report = client.get(f"/pricing/purchase-documents/items/main/{camera.id}/price-analysis.pdf")
    assert report.status_code == 200
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(report.content)).pages)
    assert "Supplier A" in text and "Supplier B" in text


def test_purchase_document_access_and_management_are_configurable(client, db):
    camera, _, _, _, _ = _catalogue(db)
    technical = db.query(User).filter_by(username=LEADER_A[0]).one()
    for permission_key in ("purchase_documents.view", "purchase_documents.manage"):
        permission = db.get(UserDepartmentPermission, (technical.id, 1, permission_key))
        assert permission is not None
        permission.allowed = False
    db.commit()
    login(client, *LEADER_A)
    assert client.get("/pricing/purchase-documents").status_code == 403
    logout(client)
    for override in db.query(UserDepartmentPermission).filter(
        UserDepartmentPermission.user_id == technical.id,
        UserDepartmentPermission.permission_key.in_(["purchase_documents.view", "purchase_documents.manage"]),
    ):
        override.allowed = True
    db.commit()
    login(client, *LEADER_A)
    response = _create_document(client, _selection(("main", camera.id, "", "SAR")))
    assert response.status_code == 303
    db.expire_all()
    document = db.query(PurchaseDocument).one()
    token = csrf_of(client, f"/pricing/purchase-documents/{document.id}/edit")
    keys = [entry.storage_key for entry in document.files]
    deleted = client.post(f"/pricing/purchase-documents/{document.id}/delete", data={"csrf_token": token})
    assert deleted.status_code == 303
    db.expire_all()
    assert db.query(PurchaseDocument).count() == 0
    assert all(not (settings.upload_dir / key).exists() for key in keys)


def test_deleting_an_item_keeps_shared_document_but_removes_last_link_orphan(client, db):
    camera, related, recorder, _, _ = _catalogue(db)
    login(client, *ADMIN)
    _create_document(client, _selection(("main", camera.id, "100", "SAR"), ("related", related.id, "20", "SAR")))
    _create_document(client, _selection(("main", recorder.id, "500", "SAR")), supplier="Recorder Supplier")
    db.expire_all()
    documents = db.query(PurchaseDocument).order_by(PurchaseDocument.id).all()
    shared, recorder_only = documents
    shared_id = shared.id
    recorder_document_id = recorder_only.id
    recorder_keys = [entry.storage_key for entry in recorder_only.files]

    token = csrf_of(client, "/pricing/items")
    removed_related = client.post(f"/pricing/related-items/{related.id}/delete", data={"csrf_token": token})
    assert removed_related.status_code == 303
    db.expire_all()
    assert db.get(PurchaseDocument, shared_id) is not None
    assert db.query(PurchaseDocumentItem).filter_by(document_id=shared_id).count() == 1

    token = csrf_of(client, "/pricing/items")
    removed_last_item = client.post(f"/pricing/items/{recorder.id}/delete", data={"csrf_token": token})
    assert removed_last_item.status_code == 303
    db.expire_all()
    assert db.get(PurchaseDocument, recorder_document_id) is None
    assert all(not (settings.upload_dir / key).exists() for key in recorder_keys)


def test_invalid_purchase_file_is_rejected_without_partial_storage(client, db):
    camera, _, _, _, _ = _catalogue(db)
    login(client, *ADMIN)
    token = csrf_of(client, "/pricing/purchase-documents/new")
    before = set(settings.upload_dir.rglob("*"))
    response = client.post(
        "/pricing/purchase-documents",
        data={
            "csrf_token": token,
            "document_type": "supplier_quotation",
            "supplier_name": "Unsafe Supplier",
            "document_date": "2026-08-26",
            "selected_items_json": _selection(("main", camera.id, "90", "SAR")),
        },
        files=[("files", ("fake.pdf", b"not a pdf", "application/pdf"))],
    )
    assert response.status_code == 303
    db.expire_all()
    assert db.query(PurchaseDocument).count() == 0
    assert set(settings.upload_dir.rglob("*")) == before
