from decimal import Decimal

from app.models import (
    PricingQuotation, PricingQuotationLine, QuotationTechnicalAttachment,
    StoreCustodyBalance, StoreItem, StoreMovement, StoreStockBalance,
    StoreWarehouse, TechnicalDocument, TechnicalRecommendation,
)
from tests.conftest import ADMIN, csrf_of, login, make_image
from tests.conftest import ensure_service_quotation


def _post(client, path, data, files=None):
    token = csrf_of(client, "/store" if path.startswith("/store") else path.rsplit("/", 1)[0])
    payload = {"csrf_token": token, **data}
    return client.post(path, data=payload, files=files)


def test_store_posts_multi_item_movements_blocks_negative_and_tracks_custody(client, db):
    login(client, *ADMIN)
    for name, kind in (("Central", "main"), ("Riyadh", "branch")):
        response = _post(client, "/store/warehouses", {"name": name, "warehouse_type": kind})
        assert response.status_code == 303
    for name in ("Camera", "Switch"):
        response = _post(client, "/store/items", {"name": name, "unit": "piece", "minimum_stock": "2"})
        assert response.status_code == 303
    central, riyadh = db.query(StoreWarehouse).order_by(StoreWarehouse.id).all()
    camera, switch = db.query(StoreItem).order_by(StoreItem.id).all()
    token = csrf_of(client, "/store")
    opening = client.post("/store/movements", data={
        "csrf_token": token, "movement_type": "opening",
        "destination_warehouse_id": str(central.id),
        "item_ids": [str(camera.id), str(switch.id)], "quantities": ["10", "5"],
    })
    assert opening.status_code == 303
    assert db.get(StoreStockBalance, (central.id, camera.id)).quantity == Decimal("10.00")
    token = csrf_of(client, "/store")
    transfer = client.post("/store/movements", data={"csrf_token":token,"movement_type":"warehouse_transfer","source_warehouse_id":central.id,"destination_warehouse_id":riyadh.id,"item_ids":camera.id,"quantities":"3"})
    assert transfer.status_code == 303
    assert db.get(StoreStockBalance, (central.id, camera.id)).quantity == Decimal("7.00")
    assert db.get(StoreStockBalance, (riyadh.id, camera.id)).quantity == Decimal("3.00")
    token = csrf_of(client, "/store")
    blocked = client.post("/store/movements", data={"csrf_token":token,"movement_type":"project_issue","source_warehouse_id":riyadh.id,"project_name":"Free-text Project","item_ids":camera.id,"quantities":"99"})
    assert blocked.status_code == 303
    assert db.get(StoreStockBalance, (riyadh.id, camera.id)).quantity == Decimal("3.00")
    token = csrf_of(client, "/store")
    custody = client.post("/store/movements", data={"csrf_token":token,"movement_type":"custody_issue","source_warehouse_id":central.id,"technician_id":"2","item_ids":camera.id,"quantities":"2"})
    assert custody.status_code == 303
    assert db.get(StoreCustodyBalance, (2, camera.id)).quantity == Decimal("2.00")
    assert db.query(StoreMovement).count() == 3
    transfer_movement = db.query(StoreMovement).filter_by(movement_type="warehouse_transfer").one()
    token = csrf_of(client, "/store")
    reversed_response = client.post(f"/store/movements/{transfer_movement.id}/reverse", data={"csrf_token":token,"reason":"Transfer entered for the wrong branch"})
    assert reversed_response.status_code == 303
    db.expire_all()
    assert db.get(StoreStockBalance, (riyadh.id, camera.id)).quantity == Decimal("0.00")
    assert db.get(StoreStockBalance, (central.id, camera.id)).quantity == Decimal("8.00")
    report = client.get("/store/reports?report_type=movements")
    assert report.status_code == 200 and "ST-" in report.text
    excel = client.get("/store/reports/export.xlsx?report_type=current_stock")
    pdf = client.get("/store/reports/export.pdf?report_type=custody")
    assert excel.status_code == 200 and excel.content.startswith(b"PK")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_data_sheet_library_uploads_recommends_and_builds_package(client, db):
    login(client, *ADMIN)
    item = db.query(StoreItem).first()  # prove Store catalogue is independent
    assert item is None
    pricing_item_id = 1
    page = client.get("/pricing/data-sheet")
    assert page.status_code == 200 and "Data Sheet" in page.text
    token = csrf_of(client, f"/pricing/data-sheet/items/main/{pricing_item_id}")
    upload = client.post(
        f"/pricing/data-sheet/items/main/{pricing_item_id}/documents",
        data={"csrf_token":token,"title":"Camera specification","notes":"Approved revision"},
        files=[("files",("camera.jpg",make_image(),"image/jpeg")),("files",("camera-2.png",make_image(fmt="PNG"),"image/png"))],
    )
    assert upload.status_code == 303
    assert db.query(TechnicalDocument).count() == 2
    token = csrf_of(client, f"/pricing/data-sheet/items/main/{pricing_item_id}")
    saved = client.post(f"/pricing/data-sheet/items/main/{pricing_item_id}/recommendation", data={"csrf_token":token,"recommendation":"Use below 50 C ambient temperature."})
    assert saved.status_code == 303
    assert db.query(TechnicalRecommendation).one().recommendation.startswith("Use below")
    recommendation = client.get(f"/pricing/data-sheet/items/main/{pricing_item_id}/recommendation.pdf")
    assert recommendation.status_code == 200 and recommendation.content.startswith(b"%PDF")
    package = client.get(f"/pricing/data-sheet/items/main/{pricing_item_id}/package.zip")
    assert package.status_code == 200 and package.content.startswith(b"PK")

    number = ensure_service_quotation()
    quotation = db.query(PricingQuotation).filter_by(quotation_number=number).one()
    quotation.lines = [PricingQuotationLine(source_item_id=pricing_item_id, item_name="IP Camera", item_model="P3265-LV", quantity=Decimal("1"), unit_price=Decimal("100"), currency="SAR", position=1)]
    db.commit()
    document_ids = [row.id for row in db.query(TechnicalDocument).all()]
    token = csrf_of(client, f"/pricing/quotations/{quotation.id}")
    selected = client.post(f"/pricing/quotations/{quotation.id}/technical-attachments", data={"csrf_token":token,"technical_document_ids":document_ids,"technical_recommendations":[f"main:{pricing_item_id}"]})
    assert selected.status_code == 303
    assert db.query(QuotationTechnicalAttachment).filter_by(quotation_id=quotation.id).count() == 3
    quote_package = client.get(f"/pricing/quotations/{quotation.id}/technical-package.zip")
    assert quote_package.status_code == 200 and quote_package.content.startswith(b"PK")
