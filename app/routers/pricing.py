"""Permission-controlled item catalogue and commercial quotations."""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import UploadFile

from ..config import settings as app_settings
from ..database import get_db
from ..deps import require_admin, require_pricing_access
from ..helpers import entity_id, flash, paginate, render
from ..audit import set_audit_context
from ..models import (
    CustomerProjectAssignment,
    DeviceCatalog,
    GeneralMaintenanceItem,
    GeneralMaintenanceRecord,
    MaintenanceRecord,
    MaintenanceRecordItem,
    PricingItem,
    PricingItemCategory,
    PricingItemPriceHistory,
    PricingQuotation,
    PricingQuotationCharge,
    PricingQuotationInvoiceImage,
    PricingQuotationLine,
    PricingQuotationRelatedLine,
    PricingQuotationSiteSurveyImage,
    PricingRelatedItem,
    PricingSettings,
    Site,
    User,
    utcnow,
)
from ..pricing import money, next_quotation_number, percentage, quantity
from ..pricing_pdf import build_quotation_pdf
from ..quotation_planner import (
    InstallationPlanSubmission,
    validate_installation_plan_submission,
)
from ..security import (
    consume_form_token,
    csrf_valid,
    form_token_available,
    issue_form_token,
)
from ..uploads import (
    StoredImage,
    UploadError,
    delete_stored,
    resolve_storage_path,
    store_image,
    validate_image,
)

router = APIRouter(
    prefix="/pricing",
    dependencies=[Depends(require_pricing_access)],
)

DEFAULT_SETTINGS = {
    "currency": "SAR",
    "default_vat_rate": Decimal("15.00"),
    "default_validity_days": 30,
    "quotation_prefix": "QUO",
    "company_name": "",
    "company_address": "",
    "company_phone": "",
    "company_email": "",
    "default_terms": "",
    "default_manpower_price": Decimal("0.00"),
    "default_transportation_price": Decimal("0.00"),
    "default_installation_price": Decimal("0.00"),
}
CURRENCIES = ("SAR", "USD")
MAX_QUOTATION_INVOICE_IMAGES = 20
MAX_INVOICE_UPLOAD_BATCH = 10
MAX_QUOTATION_SITE_SURVEY_IMAGES = 20
MAX_SITE_SURVEY_UPLOAD_BATCH = 10
LINE_ITEM_RE = re.compile(r"^line_(\d+)_item_id$")
PLANNER_HTML = Path(__file__).resolve().parents[1] / "static" / "camera-planner.html"


def _wants_json(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "camera-planner"


def _json_errors(
    errors: dict[str, str], *, form_token: str | None = None
) -> JSONResponse:
    payload: dict[str, object] = {"errors": errors}
    if form_token:
        payload["form_token"] = form_token
    return JSONResponse(payload, status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)


async def _uploaded_image(form, name: str) -> tuple[str | None, bytes | None]:
    value = form.get(name)
    if not isinstance(value, UploadFile) or not value.filename:
        return None, None
    return value.filename, await value.read()


async def _new_site_survey_submissions(
    form, errors: dict[str, str]
) -> list[tuple[str, bytes]]:
    uploads = [
        value
        for value in form.getlist("site_survey_images")
        if isinstance(value, UploadFile) and value.filename
    ]
    if len(uploads) > MAX_SITE_SURVEY_UPLOAD_BATCH:
        errors["site_survey_images"] = (
            "Upload up to 10 site survey layout images at a time."
        )
        return []
    submissions: list[tuple[str, bytes]] = []
    try:
        for upload in uploads:
            data = await upload.read()
            validate_image(upload.filename, data)
            submissions.append((upload.filename, data))
    except UploadError as exc:
        errors["site_survey_images"] = str(exc)
        return []
    return submissions


def _store_site_survey_submissions(
    submissions: list[tuple[str, bytes]],
) -> list[StoredImage]:
    stored_images: list[StoredImage] = []
    try:
        for filename, data in submissions:
            stored_images.append(store_image(filename, data))
    except UploadError:
        delete_stored(
            *[
                key
                for stored in stored_images
                for key in (stored.storage_key, stored.thumbnail_key)
            ]
        )
        raise
    return stored_images


async def _plan_submission(form, errors: dict[str, str]):
    background_name, background_data = await _uploaded_image(
        form, "installation_plan_background"
    )
    output_name, output_data = await _uploaded_image(form, "installation_plan_output")
    try:
        return validate_installation_plan_submission(
            form.get("installation_plan_state"),
            background_filename=background_name,
            background_data=background_data,
            output_filename=output_name,
            output_data=output_data,
        )
    except UploadError as exc:
        errors["installation_plan"] = str(exc)
        return None


def _store_plan_images(
    submission: InstallationPlanSubmission | None,
) -> tuple[StoredImage | None, StoredImage | None]:
    if submission is None:
        return None, None
    background = (
        store_image(submission.background_filename or "floor-plan.png", submission.background_data)
        if submission.background_data
        else None
    )
    try:
        output = store_image(submission.output_filename, submission.output_data)
    except UploadError:
        if background:
            delete_stored(background.storage_key, background.thumbnail_key)
        raise
    return background, output


def _stored_plan_keys(quotation: PricingQuotation) -> list[str | None]:
    return [
        quotation.plan_background_storage_key,
        quotation.plan_background_thumbnail_key,
        quotation.plan_output_storage_key,
        quotation.plan_output_thumbnail_key,
    ]


def _invoice_image_keys(quotation: PricingQuotation) -> list[str | None]:
    return [
        key
        for invoice in quotation.invoice_images
        for key in (invoice.storage_key, invoice.thumbnail_key)
    ]


def _site_survey_image_keys(quotation: PricingQuotation) -> list[str | None]:
    return [
        key
        for image in quotation.site_survey_images
        for key in (image.storage_key, image.thumbnail_key)
    ]


def _apply_plan(
    quotation: PricingQuotation,
    submission: InstallationPlanSubmission | None,
    background: StoredImage | None,
    output: StoredImage | None,
) -> None:
    quotation.installation_plan_state = submission.state if submission else None
    quotation.plan_background_storage_key = background.storage_key if background else None
    quotation.plan_background_thumbnail_key = background.thumbnail_key if background else None
    quotation.plan_background_content_type = background.content_type if background else None
    quotation.plan_background_file_size = background.file_size if background else None
    quotation.plan_output_storage_key = output.storage_key if output else None
    quotation.plan_output_thumbnail_key = output.thumbnail_key if output else None
    quotation.plan_output_content_type = output.content_type if output else None
    quotation.plan_output_file_size = output.file_size if output else None


def _plan_context(quotation: PricingQuotation | None) -> dict:
    if quotation is None or not quotation.installation_plan_state:
        return {"state": None, "background_url": None}
    return {
        "state": quotation.installation_plan_state,
        "background_url": (
            f"/pricing/quotations/{quotation.id}/installation-plan/background"
            if quotation.plan_background_storage_key
            else None
        ),
    }


def _currency(value: object, default: str = "") -> str | None:
    normalized = str(value or default).strip().upper()
    return normalized if normalized in CURRENCIES else None


def _sync_legacy_device(db: Session, item: PricingItem) -> None:
    """Maintain the hidden compatibility row used by installed-device history."""
    device = item.legacy_device
    if device is None:
        compatibility_model = item.model or item.name
        device = db.scalar(
            select(DeviceCatalog).where(
                func.lower(DeviceCatalog.name) == item.name.lower(),
                func.lower(DeviceCatalog.model) == compatibility_model.lower(),
            )
        ) or DeviceCatalog()
        item.legacy_device = device
    device.name = item.name
    device.model = item.model or item.name
    device.description = "Managed from Pricing Items"
    device.is_active = item.is_active and item.service_enabled
    device.updated_at = utcnow()


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def _csrf_error(request: Request, submitted: object) -> bool:
    if csrf_valid(request, str(submitted or "")):
        return False
    flash(request, "Your session expired. Reload the page and try again.", "error")
    return True


def _settings_values(saved: PricingSettings | None) -> dict:
    if saved is None:
        return dict(DEFAULT_SETTINGS)
    return {
        key: getattr(saved, key)
        for key in DEFAULT_SETTINGS
    }


def _pricing_settings(db: Session) -> dict:
    return _settings_values(db.get(PricingSettings, 1))


def _catalogue(db: Session, *, include_inactive: bool = False) -> list[PricingItem]:
    stmt = (
        select(PricingItem)
        .options(
            selectinload(PricingItem.related_items),
            selectinload(PricingItem.price_history),
            selectinload(PricingItem.related_items).selectinload(PricingRelatedItem.price_history),
            selectinload(PricingItem.category),
        )
        .order_by(PricingItem.name, PricingItem.model)
    )
    if not include_inactive:
        stmt = stmt.where(PricingItem.is_active.is_(True))
    items = list(db.scalars(stmt))
    return sorted(
        items,
        key=lambda item: (
            item.category_name.casefold() if item.category_name else "\uffff",
            item.name.casefold(),
            item.model.casefold(),
        ),
    )


def _catalogue_payload(items: list[PricingItem]) -> list[dict]:
    return [
        {
            "id": item.id,
            "label": item.display_label,
            "price": str(item.unit_price),
            "currency": item.currency,
            "category_name": item.category_name,
            "image_url": (
                f"/pricing/items/{item.id}/image?size=thumb"
                if item.image_storage_key
                else ""
            ),
            "related": [
                {
                    "id": related.id,
                    "name": related.name,
                    "price": str(related.unit_price),
                    "currency": related.currency,
                }
                for related in item.related_items
                if related.is_active
            ],
        }
        for item in items
        if item.is_active
    ]


def _item_context(
    db: Session,
    user: User,
    *,
    q: str = "",
) -> dict:
    term = q.strip()
    stmt = (
        select(PricingItem)
        .options(
            selectinload(PricingItem.related_items).selectinload(
                PricingRelatedItem.price_history
            ),
            selectinload(PricingItem.category),
            selectinload(PricingItem.price_history),
        )
        .order_by(PricingItem.is_active.desc(), PricingItem.name, PricingItem.model)
    )
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                PricingItem.name.ilike(like),
                PricingItem.model.ilike(like),
                PricingItem.category.has(PricingItemCategory.name.ilike(like)),
            )
        )
    items = list(db.scalars(stmt))
    item_ids = [item.id for item in items]
    related_ids = [related.id for item in items for related in item.related_items]
    quoted_main: dict[int, list[dict]] = {item_id: [] for item_id in item_ids}
    if item_ids:
        for line, quotation in db.execute(
            select(PricingQuotationLine, PricingQuotation)
            .join(PricingQuotation, PricingQuotation.id == PricingQuotationLine.quotation_id)
            .where(PricingQuotationLine.source_item_id.in_(item_ids))
            .order_by(PricingQuotation.quotation_date, PricingQuotationLine.id)
        ):
            quoted_main[line.source_item_id].append(
                {"price": line.unit_price, "currency": line.currency, "date": quotation.quotation_date, "label": quotation.quotation_number}
            )
    quoted_related: dict[int, list[dict]] = {related_id: [] for related_id in related_ids}
    if related_ids:
        for related_line, line, quotation in db.execute(
            select(PricingQuotationRelatedLine, PricingQuotationLine, PricingQuotation)
            .join(PricingQuotationLine, PricingQuotationLine.id == PricingQuotationRelatedLine.line_id)
            .join(PricingQuotation, PricingQuotation.id == PricingQuotationLine.quotation_id)
            .where(PricingQuotationRelatedLine.source_related_item_id.in_(related_ids))
            .order_by(PricingQuotation.quotation_date, PricingQuotationRelatedLine.id)
        ):
            quoted_related[related_line.source_related_item_id].append(
                {"price": related_line.unit_price, "currency": related_line.currency, "date": quotation.quotation_date, "label": quotation.quotation_number}
            )
    return {
        "active_nav": "pricing_items",
        "items": items,
        "quoted_main_history": quoted_main,
        "quoted_related_history": quoted_related,
        "active_items": _catalogue(db),
        "categories": list(
            db.scalars(
                select(PricingItemCategory)
                .options(selectinload(PricingItemCategory.items))
                .order_by(PricingItemCategory.name)
            )
        ),
        "q": term,
        "currency": _pricing_settings(db)["currency"],
        "currencies": CURRENCIES,
        "can_delete": user.is_admin,
    }


@router.get("")
def pricing_root(user: User = Depends(require_pricing_access)):
    return _redirect("/pricing/quotations")


@router.get("/items")
def items_page(
    request: Request,
    q: str = "",
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    return render(request, "pricing_items.html", _item_context(db, user, q=q))


@router.post("/categories")
async def create_category(
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    name = str(form.get("name") or "").strip()
    if not name:
        flash(request, "Enter a category name.", "error")
        return _redirect("/pricing/items")
    clash = db.scalar(
        select(PricingItemCategory).where(
            func.lower(PricingItemCategory.name) == name.lower()
        )
    )
    if clash:
        flash(request, f"Category “{clash.name}” already exists.", "error")
        return _redirect("/pricing/items")
    db.add(PricingItemCategory(name=name))
    db.commit()
    flash(request, f"Category “{name}” created.")
    return _redirect("/pricing/items")


@router.post("/categories/{category_id}/edit")
async def edit_category(
    category_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    category = db.get(PricingItemCategory, category_id)
    name = str(form.get("name") or "").strip()
    if category is None:
        flash(request, "That category no longer exists.", "error")
        return _redirect("/pricing/items")
    if not name:
        flash(request, "Enter a category name.", "error")
        return _redirect("/pricing/items")
    clash = db.scalar(
        select(PricingItemCategory).where(
            PricingItemCategory.id != category.id,
            func.lower(PricingItemCategory.name) == name.lower(),
        )
    )
    if clash:
        flash(request, f"Category “{clash.name}” already exists.", "error")
        return _redirect("/pricing/items")
    category.name = name
    category.updated_at = utcnow()
    db.commit()
    flash(request, "Item category updated.")
    return _redirect("/pricing/items")


@router.post(
    "/categories/{category_id}/delete",
    dependencies=[Depends(require_admin)],
)
async def delete_category(
    category_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    category = db.get(PricingItemCategory, category_id)
    if category is None:
        flash(request, "That category no longer exists.", "error")
        return _redirect("/pricing/items")
    if db.scalar(select(func.count(PricingItem.id)).where(PricingItem.category_id == category.id)):
        flash(
            request,
            "Move its items to another category or Uncategorized before deleting it.",
            "error",
        )
        return _redirect("/pricing/items")
    name = category.name
    db.delete(category)
    db.commit()
    flash(request, f"Category “{name}” deleted.")
    return _redirect("/pricing/items")


@router.post("/items")
async def create_item(
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    name = str(form.get("name") or "").strip()
    model = str(form.get("model") or "").strip()
    unit_price = money(form.get("unit_price"))
    currency = _currency(form.get("currency"), _pricing_settings(db)["currency"])
    service_enabled = (
        str(form.get("service_enabled") or "") == "1"
        if "service_enabled" in form
        else True
    )
    raw_category_id = str(form.get("category_id") or "")
    category_id = entity_id(raw_category_id)
    category = db.get(PricingItemCategory, category_id) if category_id else None
    image = form.get("image")
    if not name:
        flash(request, "Enter the main item name.", "error")
        return _redirect("/pricing/items")
    if unit_price is None or currency is None:
        flash(request, "Enter a valid non-negative item price.", "error")
        return _redirect("/pricing/items")
    if raw_category_id and category is None:
        flash(request, "Choose an existing item category.", "error")
        return _redirect("/pricing/items")
    clash = db.scalar(
        select(PricingItem).where(
            func.lower(PricingItem.name) == name.lower(),
            func.lower(PricingItem.model) == model.lower(),
        )
    )
    if clash:
        flash(request, f"“{clash.display_label}” already exists.", "error")
        return _redirect("/pricing/items")
    stored = None
    if isinstance(image, UploadFile) and image.filename:
        try:
            stored = store_image(image.filename, await image.read())
        except UploadError as exc:
            flash(request, str(exc), "error")
            return _redirect("/pricing/items")
    item = PricingItem(
        name=name,
        model=model,
        unit_price=unit_price,
        currency=currency,
        service_enabled=service_enabled,
        category=category,
    )
    _sync_legacy_device(db, item)
    if stored:
        item.image_storage_key = stored.storage_key
        item.image_thumbnail_key = stored.thumbnail_key
        item.image_original_filename = stored.original_filename
        item.image_content_type = stored.content_type
        item.image_file_size = stored.file_size
    item.price_history.append(
        PricingItemPriceHistory(
            old_price=None,
            new_price=unit_price,
            old_currency=None,
            new_currency=currency,
            changed_by_id=user.id,
            changed_by_name=user.full_name,
            source="created",
            changed_at=utcnow(),
        )
    )
    db.add(item)
    db.commit()
    set_audit_context(request, action="create", entity_type="pricing_item", entity_id=item.id, entity_label=item.display_label, changes={"price": {"before": None, "after": f"{unit_price} {currency}"}})
    flash(request, f"Main item “{name}” created.")
    return _redirect("/pricing/items")


@router.post("/items/{item_id}/edit")
async def edit_item(
    item_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    item = db.get(PricingItem, item_id)
    name = str(form.get("name") or "").strip()
    model = str(form.get("model") or "").strip()
    unit_price = money(form.get("unit_price"))
    image = form.get("image")
    if item is None:
        flash(request, "That pricing item no longer exists.", "error")
        return _redirect("/pricing/items")
    currency = _currency(form.get("currency"), item.currency)
    service_enabled = (
        str(form.get("service_enabled") or "") == "1"
        if "service_enabled" in form
        else item.service_enabled
    )
    raw_category_id = str(form.get("category_id") or "")
    category_id = entity_id(raw_category_id)
    category = db.get(PricingItemCategory, category_id) if category_id else None
    if not name or unit_price is None or currency is None:
        flash(request, "Enter a valid item name and non-negative price.", "error")
        return _redirect("/pricing/items")
    if raw_category_id and category is None:
        flash(request, "Choose an existing item category.", "error")
        return _redirect("/pricing/items")
    clash = db.scalar(
        select(PricingItem).where(
            PricingItem.id != item.id,
            func.lower(PricingItem.name) == name.lower(),
            func.lower(PricingItem.model) == model.lower(),
        )
    )
    if clash:
        flash(request, f"“{clash.display_label}” already exists.", "error")
        return _redirect("/pricing/items")
    device_clash = db.scalar(
        select(DeviceCatalog).where(
            DeviceCatalog.id != item.device_catalog_id,
            func.lower(DeviceCatalog.name) == name.lower(),
            func.lower(DeviceCatalog.model) == (model or name).lower(),
        )
    )
    if device_clash:
        flash(
            request,
            "That name and model are retained by historical service data. Choose another combination.",
            "error",
        )
        return _redirect("/pricing/items")
    stored = None
    if isinstance(image, UploadFile) and image.filename:
        try:
            stored = store_image(image.filename, await image.read())
        except UploadError as exc:
            flash(request, str(exc), "error")
            return _redirect("/pricing/items")
    old_keys = (item.image_storage_key, item.image_thumbnail_key)
    old_price, old_currency = item.unit_price, item.currency
    item.name = name
    item.model = model
    item.unit_price = unit_price
    item.currency = currency
    item.service_enabled = service_enabled
    item.category = category
    if old_price != unit_price or old_currency != currency:
        item.price_history.append(
            PricingItemPriceHistory(
                old_price=old_price,
                new_price=unit_price,
                old_currency=old_currency,
                new_currency=currency,
                changed_by_id=user.id,
                changed_by_name=user.full_name,
                source="catalog_edit",
                changed_at=utcnow(),
            )
        )
    if stored:
        item.image_storage_key = stored.storage_key
        item.image_thumbnail_key = stored.thumbnail_key
        item.image_original_filename = stored.original_filename
        item.image_content_type = stored.content_type
        item.image_file_size = stored.file_size
    item.updated_at = utcnow()
    _sync_legacy_device(db, item)
    db.commit()
    changes = {}
    if old_price != unit_price or old_currency != currency:
        changes["price"] = {"before": f"{old_price} {old_currency}", "after": f"{unit_price} {currency}"}
    set_audit_context(request, action="update", entity_type="pricing_item", entity_id=item.id, entity_label=item.display_label, changes=changes)
    if stored:
        delete_stored(*old_keys)
    flash(request, "Pricing item updated. Existing quotations keep their snapshots.")
    return _redirect("/pricing/items")


@router.post(
    "/items/{item_id}/toggle",
    dependencies=[Depends(require_admin)],
)
async def toggle_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    item = db.get(PricingItem, item_id)
    if item is None:
        flash(request, "That pricing item no longer exists.", "error")
        return _redirect("/pricing/items")
    item.is_active = not item.is_active
    item.updated_at = utcnow()
    _sync_legacy_device(db, item)
    db.commit()
    flash(request, f"Pricing item {'activated' if item.is_active else 'deactivated'}.")
    return _redirect("/pricing/items")


@router.post(
    "/items/{item_id}/delete",
    dependencies=[Depends(require_admin)],
)
async def delete_item(
    item_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    item = db.get(PricingItem, item_id)
    if item is None:
        flash(request, "That pricing item no longer exists.", "error")
        return _redirect("/pricing/items")
    label = item.display_label
    stored_keys = (item.image_storage_key, item.image_thumbnail_key)
    db.delete(item)
    db.commit()
    delete_stored(*stored_keys)
    flash(request, f"Pricing item “{label}” deleted. Quotations keep their snapshots.")
    return _redirect("/pricing/items")


@router.post("/items/{item_id}/remove-image")
async def remove_item_image(
    item_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    item = db.get(PricingItem, item_id)
    if item is None:
        flash(request, "That pricing item no longer exists.", "error")
        return _redirect("/pricing/items")
    stored_keys = (item.image_storage_key, item.image_thumbnail_key)
    item.image_storage_key = None
    item.image_thumbnail_key = None
    item.image_original_filename = None
    item.image_content_type = None
    item.image_file_size = None
    item.updated_at = utcnow()
    db.commit()
    delete_stored(*stored_keys)
    flash(request, "Item image removed.")
    return _redirect("/pricing/items")


@router.get("/items/{item_id}/image")
def item_image(
    item_id: int,
    size: str = "original",
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    item = db.get(PricingItem, item_id)
    if item is None or not item.image_storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item image not found.")
    key = (
        item.image_thumbnail_key
        if size == "thumb" and item.image_thumbnail_key
        else item.image_storage_key
    )
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item image not found.")
    return FileResponse(
        path,
        media_type=("image/jpeg" if key == item.image_thumbnail_key else item.image_content_type),
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.post("/related-items")
async def create_related_item(
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    raw_main_id = str(form.get("main_item_id") or "")
    main_item_id = entity_id(raw_main_id)
    main_item = db.get(PricingItem, main_item_id) if main_item_id is not None else None
    name = str(form.get("name") or "").strip()
    unit_price = money(form.get("unit_price"))
    currency = _currency(form.get("currency"), main_item.currency if main_item else "")
    if main_item is None or not main_item.is_active:
        flash(request, "Choose an active main item.", "error")
        return _redirect("/pricing/items")
    if not name or unit_price is None or currency is None:
        flash(request, "Enter a related item name and valid price.", "error")
        return _redirect("/pricing/items")
    clash = db.scalar(
        select(PricingRelatedItem).where(
            PricingRelatedItem.main_item_id == main_item.id,
            func.lower(PricingRelatedItem.name) == name.lower(),
        )
    )
    if clash:
        flash(request, f"“{name}” is already related to this item.", "error")
        return _redirect("/pricing/items")
    related = PricingRelatedItem(
            main_item_id=main_item.id,
            name=name,
            unit_price=unit_price,
            currency=currency,
        )
    related.price_history.append(
        PricingItemPriceHistory(
            old_price=None,
            new_price=unit_price,
            old_currency=None,
            new_currency=currency,
            changed_by_id=user.id,
            changed_by_name=user.full_name,
            source="created",
            changed_at=utcnow(),
        )
    )
    db.add(related)
    db.commit()
    set_audit_context(request, action="create", entity_type="pricing_related_item", entity_id=related.id, entity_label=name, changes={"price": {"before": None, "after": f"{unit_price} {currency}"}})
    flash(request, f"Related item “{name}” added to “{main_item.display_label}”.")
    return _redirect("/pricing/items")


@router.post("/related-items/{related_id}/edit")
async def edit_related_item(
    related_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    related = db.get(PricingRelatedItem, related_id)
    name = str(form.get("name") or "").strip()
    unit_price = money(form.get("unit_price"))
    if related is None:
        flash(request, "That related item no longer exists.", "error")
        return _redirect("/pricing/items")
    currency = _currency(form.get("currency"), related.currency)
    if not name or unit_price is None or currency is None:
        flash(request, "Enter a related item name and valid price.", "error")
        return _redirect("/pricing/items")
    clash = db.scalar(
        select(PricingRelatedItem).where(
            PricingRelatedItem.id != related.id,
            PricingRelatedItem.main_item_id == related.main_item_id,
            func.lower(PricingRelatedItem.name) == name.lower(),
        )
    )
    if clash:
        flash(request, f"“{name}” is already related to this item.", "error")
        return _redirect("/pricing/items")
    old_price, old_currency = related.unit_price, related.currency
    related.name = name
    related.unit_price = unit_price
    related.currency = currency
    if old_price != unit_price or old_currency != currency:
        related.price_history.append(
            PricingItemPriceHistory(
                old_price=old_price,
                new_price=unit_price,
                old_currency=old_currency,
                new_currency=currency,
                changed_by_id=user.id,
                changed_by_name=user.full_name,
                source="catalog_edit",
                changed_at=utcnow(),
            )
        )
    related.updated_at = utcnow()
    db.commit()
    changes = {}
    if old_price != unit_price or old_currency != currency:
        changes["price"] = {"before": f"{old_price} {old_currency}", "after": f"{unit_price} {currency}"}
    set_audit_context(request, action="update", entity_type="pricing_related_item", entity_id=related.id, entity_label=related.name, changes=changes)
    flash(request, "Related item updated. Existing quotations keep their snapshots.")
    return _redirect("/pricing/items")


@router.post(
    "/related-items/{related_id}/toggle",
    dependencies=[Depends(require_admin)],
)
async def toggle_related_item(
    related_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    related = db.get(PricingRelatedItem, related_id)
    if related is None:
        flash(request, "That related item no longer exists.", "error")
        return _redirect("/pricing/items")
    related.is_active = not related.is_active
    related.updated_at = utcnow()
    db.commit()
    flash(request, f"Related item {'activated' if related.is_active else 'deactivated'}.")
    return _redirect("/pricing/items")


@router.post(
    "/related-items/{related_id}/delete",
    dependencies=[Depends(require_admin)],
)
async def delete_related_item(
    related_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/items")
    related = db.get(PricingRelatedItem, related_id)
    if related is None:
        flash(request, "That related item no longer exists.", "error")
        return _redirect("/pricing/items")
    name = related.name
    db.delete(related)
    db.commit()
    flash(request, f"Related item “{name}” deleted. Quotations keep their snapshots.")
    return _redirect("/pricing/items")


def _quotation_query():
    return select(PricingQuotation).options(
        selectinload(PricingQuotation.lines).selectinload(
            PricingQuotationLine.related_items
        ),
        selectinload(PricingQuotation.lines).selectinload(
            PricingQuotationLine.alternative_to
        ),
        selectinload(PricingQuotation.charges),
        selectinload(PricingQuotation.invoice_images),
        selectinload(PricingQuotation.site_survey_images),
    )


def _quotation_or_404(db: Session, quotation_id: int) -> PricingQuotation:
    quotation = db.scalar(
        _quotation_query().where(PricingQuotation.id == quotation_id)
    )
    if quotation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation not found.")
    return quotation


@router.get("/quotations")
def quotations_page(
    request: Request,
    q: str = "",
    page: int = 1,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    term = q.strip()
    stmt = _quotation_query().order_by(
        PricingQuotation.quotation_date.desc(),
        PricingQuotation.id.desc(),
    )
    if term:
        like = f"%{term}%"
        stmt = stmt.where(
            or_(
                PricingQuotation.quotation_number.ilike(like),
                PricingQuotation.project_name.ilike(like),
                PricingQuotation.created_by_name.ilike(like),
            )
        )
    count_stmt = select(func.count(PricingQuotation.id))
    if term:
        count_stmt = count_stmt.where(
            or_(
                PricingQuotation.quotation_number.ilike(like),
                PricingQuotation.project_name.ilike(like),
                PricingQuotation.created_by_name.ilike(like),
            )
        )
    total = int(db.scalar(count_stmt) or 0)
    page_info = paginate(total, page, app_settings.page_size)
    visible = list(
        db.scalars(
            stmt.offset(page_info["offset"]).limit(page_info["per_page"])
        )
    )
    return render(
        request,
        "pricing_quotations.html",
        {
            "active_nav": "pricing_quotations",
            "quotations": visible,
            "page_info": page_info,
            "q": term,
            "can_delete": user.is_admin,
        },
    )


def _default_quote_form(db: Session) -> dict:
    values = _pricing_settings(db)
    today = date.today()
    return {
        "project_id": "",
        "addressee_source": "none",
        "addressee_name": "",
        "addressee_title": "",
        "addressee_email": "",
        "addressee_phone": "",
        "quotation_date": today.isoformat(),
        "valid_until": (
            today + timedelta(days=values["default_validity_days"])
        ).isoformat(),
        "discount_percent": "0.00",
        "vat_rate": "0.00",
        "notes": "",
        "terms": values["default_terms"],
        "lines": [{}],
        "charges": {
            "manpower": {
                "quantity": "1",
                "unit_price": str(values["default_manpower_price"]),
                "currency": values["currency"],
            },
            "transportation": {
                "quantity": "1",
                "unit_price": str(values["default_transportation_price"]),
                "currency": values["currency"],
            },
            "installation": {
                "quantity": "1",
                "unit_price": str(values["default_manpower_price"]),
                "currency": values["currency"],
            },
        },
    }


def _quotation_form_context(
    request: Request,
    db: Session,
    *,
    quotation: PricingQuotation | None = None,
    form: dict | None = None,
    errors: dict | None = None,
    form_token: str | None = None,
) -> dict:
    items = _catalogue(db)
    addressees = list(
        db.execute(
            select(User, CustomerProjectAssignment.project_id)
            .join(CustomerProjectAssignment, CustomerProjectAssignment.user_id == User.id)
            .where(User.is_active.is_(True))
            .order_by(User.full_name, CustomerProjectAssignment.project_id)
        )
    )
    return {
        "active_nav": "pricing_quotations",
        "quotation": quotation,
        "projects": list(
            db.scalars(
                select(Site).where(Site.is_active.is_(True)).order_by(Site.name)
            )
        ),
        "quotation_addressees": addressees,
        "catalogue": _catalogue_payload(items),
        "form": form or _default_quote_form(db),
        "errors": errors or {},
        "form_token": form_token or issue_form_token(request),
        "currency": _pricing_settings(db)["currency"],
        "currencies": CURRENCIES,
        "planner": _plan_context(quotation),
    }


def _submitted_lines(form) -> list[dict]:
    indexes = sorted(
        {
            int(match.group(1))
            for key in form.keys()
            if (match := LINE_ITEM_RE.match(str(key)))
        }
    )
    lines = []
    for index in indexes:
        related_ids = [str(value) for value in form.getlist(f"line_{index}_related_ids")]
        lines.append(
            {
                "index": index,
                "item_id": str(form.get(f"line_{index}_item_id") or ""),
                "quantity": str(form.get(f"line_{index}_quantity") or ""),
                "unit_price": str(form.get(f"line_{index}_unit_price") or ""),
                "currency": str(form.get(f"line_{index}_currency") or ""),
                "alternative_to_index": str(
                    form.get(f"line_{index}_alternative_to_index") or ""
                ),
                "skip_optional_items": (
                    str(form.get(f"line_{index}_skip_optional_items") or "")
                    == "1"
                ),
                "related": [
                    {
                        "id": related_id,
                        "quantity": str(
                            form.get(f"line_{index}_related_qty_{related_id}") or ""
                        ),
                        "unit_price": str(
                            form.get(f"line_{index}_related_price_{related_id}") or ""
                        ),
                        "currency": str(
                            form.get(f"line_{index}_related_currency_{related_id}") or ""
                        ),
                    }
                    for related_id in related_ids
                ],
            }
        )
    return lines


def _build_quote_lines(
    db: Session,
    submitted: list[dict],
    errors: dict[str, str],
) -> list[PricingQuotationLine]:
    if not submitted:
        errors["lines"] = "Add at least one item."
        return []
    if len(submitted) > 50:
        errors["lines"] = "A quotation can contain up to 50 main items."
        return []

    built: list[PricingQuotationLine] = []
    built_by_index: dict[int, PricingQuotationLine] = {}
    selected_main_ids: set[int] = set()
    for position, line_data in enumerate(submitted, start=1):
        index = line_data["index"]
        raw_item_id = line_data["item_id"]
        item_id = entity_id(raw_item_id)
        item = db.get(PricingItem, item_id) if item_id is not None else None
        line_quantity = quantity(line_data["quantity"])
        line_price = money(line_data["unit_price"])
        line_currency = _currency(line_data.get("currency"), item.currency if item else "")
        if item is None or not item.is_active:
            errors[f"line_{index}_item_id"] = "Choose an active main item."
            continue
        if item.id in selected_main_ids:
            errors[f"line_{index}_item_id"] = "Each main item can be selected once."
            continue
        selected_main_ids.add(item.id)
        if line_quantity is None:
            errors[f"line_{index}_quantity"] = "Enter a quantity greater than zero."
            continue
        if line_price is None:
            errors[f"line_{index}_unit_price"] = "Enter a valid non-negative price."
            continue
        if line_currency is None:
            errors[f"line_{index}_currency"] = "Choose SAR or USD."
            continue

        active_related_ids = {
            related.id
            for related in item.related_items
            if related.is_active
        }
        skip_optional_items = bool(line_data["skip_optional_items"])
        selected_related_ids = {
            parsed
            for selected in line_data["related"]
            if (parsed := entity_id(selected["id"])) is not None
        }
        if active_related_ids:
            if skip_optional_items and selected_related_ids:
                errors[f"line_{index}_related"] = (
                    "Select optional items or skip them, not both."
                )
            elif not skip_optional_items and not selected_related_ids:
                errors[f"line_{index}_related"] = (
                    "Select at least one optional item or tick Skip optional items."
                )
        else:
            skip_optional_items = False

        line = PricingQuotationLine(
            source_item_id=item.id,
            item_name=item.name,
            item_model=item.model,
            quantity=line_quantity,
            unit_price=line_price,
            currency=line_currency,
            position=position,
            skip_optional_items=skip_optional_items,
        )
        seen_related: set[int] = set()
        for selected in line_data["related"]:
            raw_related_id = selected["id"]
            related_id = entity_id(raw_related_id)
            related = (
                db.get(PricingRelatedItem, related_id)
                if related_id is not None
                else None
            )
            related_quantity = quantity(selected["quantity"])
            related_price = money(selected["unit_price"])
            related_currency = _currency(
                selected.get("currency"), related.currency if related else ""
            )
            if (
                related is None
                or not related.is_active
                or related.main_item_id != item.id
                or related.id in seen_related
            ):
                errors[f"line_{index}_related"] = (
                    "One selected related item is unavailable."
                )
                continue
            seen_related.add(related.id)
            if related_quantity is None:
                errors[f"line_{index}_related"] = (
                    "Enter a quantity for every selected related item."
                )
                continue
            if related_price is None:
                errors[f"line_{index}_related"] = (
                    "Enter a valid price for every selected related item."
                )
                continue
            if related_currency is None:
                errors[f"line_{index}_related"] = (
                    "Choose SAR or USD for every selected related item."
                )
                continue
            line.related_items.append(
                PricingQuotationRelatedLine(
                    source_related_item_id=related.id,
                    item_name=related.name,
                    quantity=related_quantity,
                    unit_price=related_price,
                    currency=related_currency,
                )
            )
        built.append(line)
        built_by_index[index] = line

    alternative_targets: dict[int, int] = {}
    submitted_indexes = {line_data["index"] for line_data in submitted}
    for line_data in submitted:
        index = line_data["index"]
        raw_target = str(line_data.get("alternative_to_index") or "").strip()
        if not raw_target:
            continue
        try:
            target_index = int(raw_target)
        except ValueError:
            errors[f"line_{index}_alternative_to_index"] = (
                "Choose a valid primary quotation item."
            )
            continue
        if target_index not in submitted_indexes:
            errors[f"line_{index}_alternative_to_index"] = (
                "The selected primary item is no longer in this quotation."
            )
            continue
        if target_index == index:
            errors[f"line_{index}_alternative_to_index"] = (
                "An item cannot be an alternative to itself."
            )
            continue
        alternative_targets[index] = target_index

    for start_index in alternative_targets:
        visited: set[int] = set()
        current_index = start_index
        while current_index in alternative_targets:
            if current_index in visited:
                errors[f"line_{start_index}_alternative_to_index"] = (
                    "Alternative items cannot form a circular link."
                )
                break
            visited.add(current_index)
            current_index = alternative_targets[current_index]

    for index, target_index in alternative_targets.items():
        error_key = f"line_{index}_alternative_to_index"
        if error_key in errors:
            continue
        line = built_by_index.get(index)
        target = built_by_index.get(target_index)
        if line is None or target is None:
            errors[error_key] = "Choose a valid primary quotation item."
            continue
        line.alternative_to = target
    return built


def _line_image_keys(lines: list[PricingQuotationLine]) -> list[str | None]:
    return [
        key
        for line in lines
        for key in (line.image_storage_key, line.image_thumbnail_key)
    ]


def _snapshot_line_images(
    db: Session,
    lines: list[PricingQuotationLine],
) -> list[str | None]:
    stored_keys: list[str | None] = []
    try:
        for line in lines:
            if not line.source_item_id:
                continue
            item = db.get(PricingItem, line.source_item_id)
            if item is None or not item.image_storage_key:
                continue
            source = resolve_storage_path(item.image_storage_key)
            stored = store_image(
                item.image_original_filename or "pricing-item.jpg",
                source.read_bytes(),
            )
            line.image_storage_key = stored.storage_key
            line.image_thumbnail_key = stored.thumbnail_key
            line.image_original_filename = stored.original_filename
            line.image_content_type = stored.content_type
            line.image_file_size = stored.file_size
            stored_keys.extend((stored.storage_key, stored.thumbnail_key))
    except (UploadError, OSError) as exc:
        delete_stored(*stored_keys)
        raise UploadError(
            "An item image could not be copied into the quotation. "
            "Replace that catalogue image and try again."
        ) from exc
    return stored_keys


def _quote_form_values(form, submitted: list[dict]) -> dict:
    return {
        "project_id": str(form.get("project_id") or ""),
        "addressee_source": str(form.get("addressee_source") or "none"),
        "addressee_name": str(form.get("addressee_name") or ""),
        "addressee_title": str(form.get("addressee_title") or ""),
        "addressee_email": str(form.get("addressee_email") or ""),
        "addressee_phone": str(form.get("addressee_phone") or ""),
        "quotation_date": str(form.get("quotation_date") or ""),
        "valid_until": str(form.get("valid_until") or ""),
        "discount_percent": str(form.get("discount_percent") or ""),
        "vat_rate": str(form.get("vat_rate") or ""),
        "notes": str(form.get("notes") or ""),
        "terms": str(form.get("terms") or ""),
        "lines": submitted or [{}],
        "charges": {
            "manpower": {
                "quantity": str(form.get("charge_manpower_quantity") or ""),
                "unit_price": str(form.get("charge_manpower_unit_price") or ""),
                "currency": str(form.get("charge_manpower_currency") or ""),
            },
            "transportation": {
                "quantity": str(form.get("charge_transportation_quantity") or ""),
                "unit_price": str(
                    form.get("charge_transportation_unit_price") or ""
                ),
                "currency": str(form.get("charge_transportation_currency") or ""),
            },
            "installation": {
                "quantity": str(form.get("charge_installation_quantity") or ""),
                "unit_price": str(
                    form.get("charge_installation_unit_price") or ""
                ),
                "currency": str(form.get("charge_manpower_currency") or ""),
            },
        },
    }


def _build_quote_charges(form, errors: dict[str, str]) -> list[PricingQuotationCharge]:
    definitions = (
        ("manpower", "Manpower", "worker", 1),
        ("transportation", "Transportation", "quotation", 2),
        ("installation", "Installation", "day", 3),
    )
    charges: list[PricingQuotationCharge] = []
    manpower_quantity = quantity(form.get("charge_manpower_quantity"))
    manpower_unit_price = money(form.get("charge_manpower_unit_price"))
    daily_manpower = (
        manpower_quantity * manpower_unit_price
        if manpower_quantity is not None and manpower_unit_price is not None
        else None
    )
    for charge_type, label, unit_label, position in definitions:
        raw_quantity = form.get(f"charge_{charge_type}_quantity")
        if charge_type == "transportation" and not str(raw_quantity or "").strip():
            raw_quantity = "1"
        charge_quantity = quantity(raw_quantity)
        unit_price = (
            daily_manpower
            if charge_type == "installation"
            else money(form.get(f"charge_{charge_type}_unit_price"))
        )
        charge_currency = _currency(
            form.get(
                "charge_manpower_currency"
                if charge_type == "installation"
                else f"charge_{charge_type}_currency"
            ),
            "SAR",
        )
        if charge_quantity is None:
            errors[f"charge_{charge_type}_quantity"] = (
                "Enter a quantity greater than zero."
            )
        if unit_price is None:
            errors[f"charge_{charge_type}_unit_price"] = (
                "Enter a valid non-negative cost."
            )
        if charge_currency is None:
            errors[f"charge_{charge_type}_currency"] = "Choose SAR or USD."
        if (
            charge_quantity is not None
            and unit_price is not None
            and charge_currency is not None
        ):
            charges.append(
                PricingQuotationCharge(
                    charge_type=charge_type,
                    label=label,
                    quantity=charge_quantity,
                    unit_price=unit_price,
                    currency=charge_currency,
                    unit_label=unit_label,
                    position=position,
                )
            )
    return charges


def _validate_quote_header(form, db: Session) -> tuple[dict, dict]:
    errors: dict[str, str] = {}
    raw_project_id = str(form.get("project_id") or "")
    project_id = entity_id(raw_project_id)
    project = db.get(Site, project_id) if project_id is not None else None
    addressee_source = str(form.get("addressee_source") or "none").strip()
    addressee_user = None
    addressee_name = str(form.get("addressee_name") or "").strip()
    addressee_title = str(form.get("addressee_title") or "").strip()
    addressee_email = str(form.get("addressee_email") or "").strip()
    addressee_phone = str(form.get("addressee_phone") or "").strip()
    try:
        quotation_date = date.fromisoformat(str(form.get("quotation_date") or ""))
    except ValueError:
        quotation_date = None
    try:
        valid_until = date.fromisoformat(str(form.get("valid_until") or ""))
    except ValueError:
        valid_until = None
    if project is None or not project.is_active:
        errors["project_id"] = "Choose an active Project."
    if addressee_source == "project":
        addressee_name = project.contact_person if project else ""
        addressee_phone = project.contact_number if project else ""
        addressee_title = ""
        addressee_email = ""
        if not addressee_name:
            errors["addressee_source"] = "The selected Project has no contact person. Choose a Customer user or enter a custom person."
    elif addressee_source.startswith("customer:"):
        user_id = entity_id(addressee_source.split(":", 1)[1])
        assignment = db.scalar(
            select(CustomerProjectAssignment).where(
                CustomerProjectAssignment.user_id == user_id,
                CustomerProjectAssignment.project_id == project_id,
            )
        ) if user_id and project_id else None
        addressee_user = db.get(User, user_id) if assignment else None
        if addressee_user is None or not addressee_user.is_active or not addressee_user.is_customer:
            errors["addressee_source"] = "Choose an active Customer assigned to this Project."
        else:
            addressee_name = addressee_user.full_name
            addressee_email = addressee_user.username if "@" in addressee_user.username else ""
            addressee_phone = addressee_user.phone or ""
            addressee_title = ""
    elif addressee_source == "custom":
        if not addressee_name:
            errors["addressee_name"] = "Enter the person’s name."
    elif addressee_source != "none":
        errors["addressee_source"] = "Choose a valid quotation addressee."
        addressee_source = "none"
    if quotation_date is None:
        errors["quotation_date"] = "Enter a valid quotation date."
    if valid_until is None:
        errors["valid_until"] = "Enter a valid expiry date."
    elif quotation_date and valid_until < quotation_date:
        errors["valid_until"] = "The expiry date cannot be before the quotation date."
    return {
        "project": project,
        "addressee_source": addressee_source,
        "addressee_user": addressee_user,
        "addressee_name": addressee_name[:120],
        "addressee_title": addressee_title[:120],
        "addressee_email": addressee_email[:254],
        "addressee_phone": addressee_phone[:40],
        "quotation_date": quotation_date,
        "valid_until": valid_until,
        "discount_percent": Decimal("0.00"),
        "vat_rate": Decimal("0.00"),
        "notes": str(form.get("notes") or "").strip(),
        "terms": str(form.get("terms") or "").strip(),
    }, errors


def _apply_quote_header(
    quotation: PricingQuotation,
    values: dict,
    pricing_settings: dict,
) -> None:
    project = values["project"]
    quotation.project_id = project.id
    quotation.project_name = project.name
    quotation.project_address = project.address or ""
    quotation.project_city = project.city or ""
    quotation.contact_person = project.contact_person or ""
    quotation.contact_number = project.contact_number or ""
    quotation.addressee_source = values["addressee_source"]
    quotation.addressee_user_id = values["addressee_user"].id if values["addressee_user"] else None
    quotation.addressee_name = values["addressee_name"]
    quotation.addressee_title = values["addressee_title"]
    quotation.addressee_email = values["addressee_email"]
    quotation.addressee_phone = values["addressee_phone"]
    quotation.quotation_date = values["quotation_date"]
    quotation.valid_until = values["valid_until"]
    quotation.currency = pricing_settings["currency"]
    quotation.discount_percent = values["discount_percent"]
    quotation.vat_rate = values["vat_rate"]
    quotation.notes = values["notes"]
    quotation.terms = values["terms"]
    quotation.company_name = pricing_settings["company_name"]
    quotation.company_address = pricing_settings["company_address"]
    quotation.company_phone = pricing_settings["company_phone"]
    quotation.company_email = pricing_settings["company_email"]
    quotation.updated_at = utcnow()


@router.get("/planner/embed")
def installation_planner_embed(
    user: User = Depends(require_pricing_access),
):
    return FileResponse(
        PLANNER_HTML,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "X-Frame-Options": "SAMEORIGIN",
        },
    )


@router.get("/quotations/new")
def new_quotation_page(
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "pricing_quotation_form.html",
        _quotation_form_context(request, db),
    )


@router.post("/quotations")
async def create_quotation(
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    form = await request.form()
    submitted = _submitted_lines(form)
    form_values = _quote_form_values(form, submitted)
    values, errors = _validate_quote_header(form, db)
    if not csrf_valid(request, str(form.get("csrf_token") or "")):
        errors["form"] = "Your session expired. Reload the page and try again."
    if not form_token_available(request, str(form.get("form_token") or "")):
        errors["form"] = "This quotation was already submitted. Check the quotations list."
    lines = _build_quote_lines(db, submitted, errors)
    charges = _build_quote_charges(form, errors)
    plan_submission = await _plan_submission(form, errors)
    site_survey_submissions = await _new_site_survey_submissions(form, errors)
    if errors:
        next_token = issue_form_token(request)
        if _wants_json(request):
            return _json_errors(errors, form_token=next_token)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                form=form_values,
                errors=errors,
                form_token=next_token,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        snapshot_keys = _snapshot_line_images(db, lines)
    except UploadError as exc:
        errors["form"] = str(exc)
        next_token = issue_form_token(request)
        if _wants_json(request):
            return _json_errors(errors, form_token=next_token)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                form=form_values,
                errors=errors,
                form_token=next_token,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        plan_background, plan_output = _store_plan_images(plan_submission)
    except UploadError as exc:
        delete_stored(*snapshot_keys)
        errors["installation_plan"] = str(exc)
        next_token = issue_form_token(request)
        if _wants_json(request):
            return _json_errors(errors, form_token=next_token)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                form=form_values,
                errors=errors,
                form_token=next_token,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    plan_keys = [
        plan_background.storage_key if plan_background else None,
        plan_background.thumbnail_key if plan_background else None,
        plan_output.storage_key if plan_output else None,
        plan_output.thumbnail_key if plan_output else None,
    ]
    try:
        site_survey_images = _store_site_survey_submissions(site_survey_submissions)
    except UploadError as exc:
        delete_stored(*snapshot_keys, *plan_keys)
        errors["site_survey_images"] = str(exc)
        next_token = issue_form_token(request)
        if _wants_json(request):
            return _json_errors(errors, form_token=next_token)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                form=form_values,
                errors=errors,
                form_token=next_token,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    site_survey_keys = [
        key
        for stored in site_survey_images
        for key in (stored.storage_key, stored.thumbnail_key)
    ]
    if not consume_form_token(request, str(form.get("form_token") or "")):
        delete_stored(*snapshot_keys, *plan_keys, *site_survey_keys)
        if _wants_json(request):
            return _json_errors(
                {"form": "This quotation was already submitted."},
                form_token=issue_form_token(request),
            )
        flash(request, "This quotation was already submitted.", "error")
        return _redirect("/pricing/quotations")

    pricing_settings = _pricing_settings(db)
    quotation = PricingQuotation(
        quotation_number=next_quotation_number(
            db,
            prefix=pricing_settings["quotation_prefix"],
            quotation_date=values["quotation_date"],
        ),
        project_id=values["project"].id,
        project_name=values["project"].name,
        quotation_date=values["quotation_date"],
        valid_until=values["valid_until"],
        currency=pricing_settings["currency"],
        discount_percent=values["discount_percent"],
        vat_rate=values["vat_rate"],
        created_by_id=user.id,
        created_by_name=user.full_name,
    )
    _apply_quote_header(quotation, values, pricing_settings)
    quotation.lines = lines
    quotation.charges = charges
    _apply_plan(quotation, plan_submission, plan_background, plan_output)
    quotation.site_survey_images = [
        PricingQuotationSiteSurveyImage(
            storage_key=stored.storage_key,
            thumbnail_key=stored.thumbnail_key,
            original_filename=stored.original_filename,
            content_type=stored.content_type,
            file_size=stored.file_size,
            uploaded_by_id=user.id,
            uploaded_by_name=user.full_name,
        )
        for stored in site_survey_images
    ]
    db.add(quotation)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        delete_stored(*snapshot_keys, *plan_keys, *site_survey_keys)
        errors["form"] = (
            "The quotation could not be saved. Review the form and try again."
        )
        next_token = issue_form_token(request)
        if _wants_json(request):
            return _json_errors(errors, form_token=next_token)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                form=form_values,
                errors=errors,
                form_token=next_token,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    set_audit_context(
        request,
        action="create",
        entity_type="pricing_quotation",
        entity_id=quotation.id,
        entity_label=quotation.quotation_number,
        changes={
            "project": {"before": None, "after": quotation.project_name},
            "addressee": {"before": None, "after": quotation.addressee_name},
            "line_count": {"before": 0, "after": len(quotation.lines)},
        },
    )
    flash(request, f"Quotation {quotation.quotation_number} created.")
    if _wants_json(request):
        return JSONResponse({"redirect": f"/pricing/quotations/{quotation.id}"})
    return _redirect(f"/pricing/quotations/{quotation.id}")


@router.get("/quotations/{quotation_id}")
def quotation_detail(
    quotation_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    return render(
        request,
        "pricing_quotation_detail.html",
        {
            "active_nav": "pricing_quotations",
            "quotation": quotation,
            "can_delete": user.is_admin,
        },
    )


@router.get("/quotations/{quotation_id}/pdf")
def quotation_pdf(
    quotation_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    return Response(
        content=build_quotation_pdf(quotation),
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{quotation.quotation_number}.pdf"'
            ),
            "Cache-Control": "no-store",
        },
    )


@router.get("/quotations/{quotation_id}/lines/{line_id}/image")
def quotation_line_image(
    quotation_id: int,
    line_id: int,
    size: str = "original",
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    line = next((candidate for candidate in quotation.lines if candidate.id == line_id), None)
    if line is None or not line.image_storage_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation item image not found.")
    key = (
        line.image_thumbnail_key
        if size == "thumb" and line.image_thumbnail_key
        else line.image_storage_key
    )
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Quotation item image not found.")
    return FileResponse(
        path,
        media_type=("image/jpeg" if key == line.image_thumbnail_key else line.image_content_type),
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.get("/quotations/{quotation_id}/installation-plan/{asset}")
def quotation_installation_plan_image(
    quotation_id: int,
    asset: str,
    size: str = "original",
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    if asset == "background":
        original = quotation.plan_background_storage_key
        thumbnail = quotation.plan_background_thumbnail_key
        content_type = quotation.plan_background_content_type
    elif asset == "output":
        original = quotation.plan_output_storage_key
        thumbnail = quotation.plan_output_thumbnail_key
        content_type = quotation.plan_output_content_type
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Installation plan not found.")
    if not original:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Installation plan not found.")
    key = thumbnail if size == "thumb" and thumbnail else original
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Installation plan not found.")
    return FileResponse(
        path,
        media_type="image/jpeg" if key == thumbnail else content_type,
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.post("/quotations/{quotation_id}/invoice-images")
async def upload_quotation_invoice_images(
    quotation_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    form = await request.form()
    return_path = (
        f"/pricing/quotations/{quotation.id}/edit#purchase-invoice-proof"
        if str(form.get("return_to") or "") == "edit"
        else f"/pricing/quotations/{quotation.id}"
    )
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect(return_path)
    uploads = [
        value
        for value in form.getlist("invoice_images")
        if isinstance(value, UploadFile) and value.filename
    ]
    if not uploads:
        flash(request, "Select at least one invoice image.", "error")
        return _redirect(return_path)
    if len(uploads) > MAX_INVOICE_UPLOAD_BATCH:
        flash(request, "Upload up to 10 invoice images at a time.", "error")
        return _redirect(return_path)
    if len(quotation.invoice_images) + len(uploads) > MAX_QUOTATION_INVOICE_IMAGES:
        flash(request, "A quotation can contain up to 20 invoice images.", "error")
        return _redirect(return_path)

    stored_images: list[StoredImage] = []
    try:
        for upload in uploads:
            stored_images.append(store_image(upload.filename, await upload.read()))
    except UploadError as exc:
        delete_stored(
            *[
                key
                for stored in stored_images
                for key in (stored.storage_key, stored.thumbnail_key)
            ]
        )
        flash(request, str(exc), "error")
        return _redirect(return_path)

    invoice_images = [
        PricingQuotationInvoiceImage(
            quotation_id=quotation.id,
            storage_key=stored.storage_key,
            thumbnail_key=stored.thumbnail_key,
            original_filename=stored.original_filename,
            content_type=stored.content_type,
            file_size=stored.file_size,
            uploaded_by_id=user.id,
            uploaded_by_name=user.full_name,
        )
        for stored in stored_images
    ]
    db.add_all(invoice_images)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        delete_stored(
            *[
                key
                for stored in stored_images
                for key in (stored.storage_key, stored.thumbnail_key)
            ]
        )
        flash(request, "The invoice images could not be saved. Try again.", "error")
        return _redirect(return_path)
    flash(request, f"{len(invoice_images)} invoice image(s) added.")
    return _redirect(return_path)


@router.post("/quotations/{quotation_id}/site-survey-images")
async def upload_quotation_site_survey_images(
    quotation_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    form = await request.form()
    return_path = (
        f"/pricing/quotations/{quotation.id}/edit#site-survey-layouts"
        if str(form.get("return_to") or "") == "edit"
        else f"/pricing/quotations/{quotation.id}#site-survey-layouts"
    )
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect(return_path)
    uploads = [
        value
        for value in form.getlist("site_survey_images")
        if isinstance(value, UploadFile) and value.filename
    ]
    if not uploads:
        flash(request, "Select at least one site survey layout image.", "error")
        return _redirect(return_path)
    if len(uploads) > MAX_SITE_SURVEY_UPLOAD_BATCH:
        flash(request, "Upload up to 10 site survey layout images at a time.", "error")
        return _redirect(return_path)
    if (
        len(quotation.site_survey_images) + len(uploads)
        > MAX_QUOTATION_SITE_SURVEY_IMAGES
    ):
        flash(request, "A quotation can contain up to 20 site survey layout images.", "error")
        return _redirect(return_path)

    stored_images: list[StoredImage] = []
    try:
        for upload in uploads:
            stored_images.append(store_image(upload.filename, await upload.read()))
    except UploadError as exc:
        delete_stored(
            *[
                key
                for stored in stored_images
                for key in (stored.storage_key, stored.thumbnail_key)
            ]
        )
        flash(request, str(exc), "error")
        return _redirect(return_path)

    survey_images = [
        PricingQuotationSiteSurveyImage(
            quotation_id=quotation.id,
            storage_key=stored.storage_key,
            thumbnail_key=stored.thumbnail_key,
            original_filename=stored.original_filename,
            content_type=stored.content_type,
            file_size=stored.file_size,
            uploaded_by_id=user.id,
            uploaded_by_name=user.full_name,
        )
        for stored in stored_images
    ]
    db.add_all(survey_images)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        delete_stored(
            *[
                key
                for stored in stored_images
                for key in (stored.storage_key, stored.thumbnail_key)
            ]
        )
        flash(request, "The site survey images could not be saved. Try again.", "error")
        return _redirect(return_path)
    flash(request, f"{len(survey_images)} site survey layout image(s) added.")
    return _redirect(return_path)


@router.get("/quotations/{quotation_id}/site-survey-images/{image_id}")
def quotation_site_survey_image(
    quotation_id: int,
    image_id: int,
    size: str = "original",
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    survey_image = next(
        (
            candidate
            for candidate in quotation.site_survey_images
            if candidate.id == image_id
        ),
        None,
    )
    if survey_image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site survey image not found.")
    key = (
        survey_image.thumbnail_key
        if size == "thumb" and survey_image.thumbnail_key
        else survey_image.storage_key
    )
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Site survey image not found.")
    return FileResponse(
        path,
        media_type=(
            "image/jpeg" if key == survey_image.thumbnail_key else survey_image.content_type
        ),
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.post("/quotations/{quotation_id}/site-survey-images/{image_id}/delete")
async def delete_quotation_site_survey_image(
    quotation_id: int,
    image_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    form = await request.form()
    return_path = (
        f"/pricing/quotations/{quotation.id}/edit#site-survey-layouts"
        if str(form.get("return_to") or "") == "edit"
        else f"/pricing/quotations/{quotation.id}#site-survey-layouts"
    )
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect(return_path)
    survey_image = next(
        (
            candidate
            for candidate in quotation.site_survey_images
            if candidate.id == image_id
        ),
        None,
    )
    if survey_image is None:
        flash(request, "That site survey image no longer exists.", "error")
        return _redirect(return_path)
    keys = (survey_image.storage_key, survey_image.thumbnail_key)
    db.delete(survey_image)
    db.commit()
    delete_stored(*keys)
    flash(request, "Site survey image removed.")
    return _redirect(return_path)


@router.get("/quotations/{quotation_id}/invoice-images/{invoice_id}")
def quotation_invoice_image(
    quotation_id: int,
    invoice_id: int,
    size: str = "original",
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    invoice = next(
        (candidate for candidate in quotation.invoice_images if candidate.id == invoice_id),
        None,
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice image not found.")
    key = invoice.thumbnail_key if size == "thumb" and invoice.thumbnail_key else invoice.storage_key
    try:
        path = resolve_storage_path(key)
    except UploadError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice image not found.")
    return FileResponse(
        path,
        media_type="image/jpeg" if key == invoice.thumbnail_key else invoice.content_type,
        headers={"Cache-Control": "private, max-age=600"},
    )


@router.post("/quotations/{quotation_id}/invoice-images/{invoice_id}/delete")
async def delete_quotation_invoice_image(
    quotation_id: int,
    invoice_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    form = await request.form()
    return_path = (
        f"/pricing/quotations/{quotation.id}/edit#purchase-invoice-proof"
        if str(form.get("return_to") or "") == "edit"
        else f"/pricing/quotations/{quotation.id}"
    )
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect(return_path)
    invoice = next(
        (candidate for candidate in quotation.invoice_images if candidate.id == invoice_id),
        None,
    )
    if invoice is None:
        flash(request, "That invoice image no longer exists.", "error")
        return _redirect(return_path)
    keys = (invoice.storage_key, invoice.thumbnail_key)
    db.delete(invoice)
    db.commit()
    delete_stored(*keys)
    flash(request, "Invoice image removed.")
    return _redirect(return_path)


def _existing_quote_form(quotation: PricingQuotation) -> dict:
    charge_values = {
        "manpower": {"quantity": "1", "unit_price": "0.00", "currency": "SAR"},
        "transportation": {"quantity": "1", "unit_price": "0.00", "currency": "SAR"},
        "installation": {"quantity": "1", "unit_price": "0.00", "currency": "SAR"},
    }
    for charge in quotation.charges:
        charge_values[charge.charge_type] = {
            "quantity": str(charge.quantity),
            "unit_price": str(charge.unit_price),
            "currency": charge.currency,
        }
    line_indexes = {line.id: index for index, line in enumerate(quotation.lines)}
    return {
        "project_id": str(quotation.project_id),
        "addressee_source": quotation.addressee_source,
        "addressee_name": quotation.addressee_name,
        "addressee_title": quotation.addressee_title,
        "addressee_email": quotation.addressee_email,
        "addressee_phone": quotation.addressee_phone,
        "quotation_date": quotation.quotation_date.isoformat(),
        "valid_until": quotation.valid_until.isoformat(),
        "discount_percent": str(quotation.discount_percent),
        "vat_rate": str(quotation.vat_rate),
        "notes": quotation.notes,
        "terms": quotation.terms,
        "lines": [
            {
                "index": index,
                "item_id": str(line.source_item_id or ""),
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "currency": line.currency,
                "alternative_to_index": str(
                    line_indexes[line.alternative_to_line_id]
                ) if line.alternative_to_line_id in line_indexes else "",
                "skip_optional_items": line.skip_optional_items,
                "related": [
                    {
                        "id": str(related.source_related_item_id or ""),
                        "quantity": str(related.quantity),
                        "unit_price": str(related.unit_price),
                        "currency": related.currency,
                    }
                    for related in line.related_items
                    if related.source_related_item_id
                ],
            }
            for index, line in enumerate(quotation.lines)
        ],
        "charges": charge_values,
    }


@router.get("/quotations/{quotation_id}/edit")
def edit_quotation_page(
    quotation_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    return render(
        request,
        "pricing_quotation_form.html",
        _quotation_form_context(
            request,
            db,
            quotation=quotation,
            form=_existing_quote_form(quotation),
        ),
    )


@router.post("/quotations/{quotation_id}/edit")
async def edit_quotation(
    quotation_id: int,
    request: Request,
    user: User = Depends(require_pricing_access),
    db: Session = Depends(get_db),
):
    quotation = _quotation_or_404(db, quotation_id)
    old_audit_values = {
        "project": quotation.project_name,
        "addressee": quotation.addressee_name,
        "line_count": len(quotation.lines),
    }
    form = await request.form()
    submitted = _submitted_lines(form)
    form_values = _quote_form_values(form, submitted)
    values, errors = _validate_quote_header(form, db)
    if not csrf_valid(request, str(form.get("csrf_token") or "")):
        errors["form"] = "Your session expired. Reload the page and try again."
    lines = _build_quote_lines(db, submitted, errors)
    charges = _build_quote_charges(form, errors)
    plan_submission = await _plan_submission(form, errors)
    if errors:
        if _wants_json(request):
            return _json_errors(errors)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                quotation=quotation,
                form=form_values,
                errors=errors,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        new_snapshot_keys = _snapshot_line_images(db, lines)
    except UploadError as exc:
        errors["form"] = str(exc)
        if _wants_json(request):
            return _json_errors(errors)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                quotation=quotation,
                form=form_values,
                errors=errors,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    try:
        plan_background, plan_output = _store_plan_images(plan_submission)
    except UploadError as exc:
        delete_stored(*new_snapshot_keys)
        errors["installation_plan"] = str(exc)
        if _wants_json(request):
            return _json_errors(errors)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                quotation=quotation,
                form=form_values,
                errors=errors,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    new_plan_keys = [
        plan_background.storage_key if plan_background else None,
        plan_background.thumbnail_key if plan_background else None,
        plan_output.storage_key if plan_output else None,
        plan_output.thumbnail_key if plan_output else None,
    ]
    old_snapshot_keys = _line_image_keys(quotation.lines)
    old_plan_keys = _stored_plan_keys(quotation)
    _apply_quote_header(quotation, values, _pricing_settings(db))
    quotation.lines.clear()
    db.flush()
    quotation.lines = lines
    quotation.charges.clear()
    db.flush()
    quotation.charges = charges
    _apply_plan(quotation, plan_submission, plan_background, plan_output)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        delete_stored(*new_snapshot_keys, *new_plan_keys)
        errors["form"] = (
            "The quotation could not be saved. Review the form and try again."
        )
        if _wants_json(request):
            return _json_errors(errors)
        return render(
            request,
            "pricing_quotation_form.html",
            _quotation_form_context(
                request,
                db,
                quotation=quotation,
                form=form_values,
                errors=errors,
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    delete_stored(*old_snapshot_keys)
    delete_stored(*old_plan_keys)
    set_audit_context(
        request,
        action="update",
        entity_type="pricing_quotation",
        entity_id=quotation.id,
        entity_label=quotation.quotation_number,
        changes={
            field: {"before": old_audit_values[field], "after": after}
            for field, after in {
                "project": quotation.project_name,
                "addressee": quotation.addressee_name,
                "line_count": len(quotation.lines),
            }.items()
            if old_audit_values[field] != after
        },
    )
    flash(request, f"Quotation {quotation.quotation_number} updated.")
    if _wants_json(request):
        return JSONResponse({"redirect": f"/pricing/quotations/{quotation.id}"})
    return _redirect(f"/pricing/quotations/{quotation.id}")


@router.post(
    "/quotations/{quotation_id}/delete",
    dependencies=[Depends(require_admin)],
)
async def delete_quotation(
    quotation_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/quotations")
    quotation = _quotation_or_404(db, quotation_id)
    number = quotation.quotation_number
    stored_keys = _delete_quotations(db, [quotation])
    db.commit()
    delete_stored(*stored_keys)
    flash(request, f"Quotation {number} deleted.")
    return _redirect("/pricing/quotations")


def _delete_quotations(
    db: Session,
    quotations: list[PricingQuotation],
) -> list[str | None]:
    """Stage quotation deletion while preserving every service record."""
    quotation_ids = [quotation.id for quotation in quotations]
    if not quotation_ids:
        return []
    stored_keys: list[str | None] = []
    for quotation in quotations:
        stored_keys.extend(_line_image_keys(quotation.lines))
        stored_keys.extend(_stored_plan_keys(quotation))
        stored_keys.extend(_invoice_image_keys(quotation))
        stored_keys.extend(_site_survey_image_keys(quotation))
    # Maintenance is intentionally independent from commercial quotations.
    # Clear both the live link and the old snapshot for records created before
    # that separation; the records and any saved reports remain untouched.
    for model in (
        MaintenanceRecordItem,
        GeneralMaintenanceItem,
        MaintenanceRecord,
        GeneralMaintenanceRecord,
    ):
        db.query(model).filter(model.quotation_id.in_(quotation_ids)).update(
            {model.quotation_id: None, model.quotation_number: None},
            synchronize_session=False,
        )
    for quotation in quotations:
        db.delete(quotation)
    return stored_keys


@router.post(
    "/quotations/bulk-delete",
    dependencies=[Depends(require_admin)],
)
async def bulk_delete_quotations(
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    if _csrf_error(request, form.get("csrf_token")):
        return _redirect("/pricing/quotations")
    quotation_ids: list[int] = []
    invalid_selection = False
    for raw_value in form.getlist("quotation_ids"):
        quotation_id = entity_id(raw_value)
        if quotation_id is None:
            invalid_selection = True
        elif quotation_id not in quotation_ids:
            quotation_ids.append(quotation_id)
    if invalid_selection or len(quotation_ids) > 100:
        flash(request, "The quotation selection is invalid. Select the quotations again.")
        return _redirect("/pricing/quotations")
    if not quotation_ids:
        flash(request, "Select at least one quotation to delete.")
        return _redirect("/pricing/quotations")

    quotations = list(
        db.scalars(
            _quotation_query().where(PricingQuotation.id.in_(quotation_ids))
        )
    )
    if len(quotations) != len(quotation_ids):
        flash(request, "One or more selected quotations no longer exist. Refresh and try again.")
        return _redirect("/pricing/quotations")

    numbers = [quotation.quotation_number for quotation in quotations]
    stored_keys = _delete_quotations(db, quotations)
    set_audit_context(
        request,
        action="delete",
        entity_type="pricing_quotation_bulk",
        entity_label=f"{len(quotations)} quotations",
        changes={"quotation_numbers": numbers},
    )
    db.commit()
    delete_stored(*stored_keys)
    flash(request, f"{len(quotations)} quotations deleted.")
    return _redirect("/pricing/quotations")


@router.get("/settings", dependencies=[Depends(require_admin)])
def pricing_settings_page(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "pricing_settings.html",
        {
            "active_nav": "pricing_settings",
            "profile": _pricing_settings(db),
            "errors": {},
            "saved": db.get(PricingSettings, 1),
        },
    )


@router.post("/settings", dependencies=[Depends(require_admin)])
async def update_pricing_settings(
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    form = await request.form()
    profile = {
        "currency": str(form.get("currency") or "").strip().upper(),
        "default_vat_rate": percentage(form.get("default_vat_rate")),
        "default_validity_days": str(
            form.get("default_validity_days") or ""
        ).strip(),
        "quotation_prefix": str(form.get("quotation_prefix") or "")
        .strip()
        .upper(),
        "company_name": str(form.get("company_name") or "").strip(),
        "company_address": str(form.get("company_address") or "").strip(),
        "company_phone": str(form.get("company_phone") or "").strip(),
        "company_email": str(form.get("company_email") or "").strip(),
        "default_terms": str(form.get("default_terms") or "").strip(),
        "default_manpower_price": money(form.get("default_manpower_price")),
        "default_transportation_price": money(
            form.get("default_transportation_price")
        ),
        "default_installation_price": money(form.get("default_installation_price")),
    }
    errors: dict[str, str] = {}
    if not csrf_valid(request, str(form.get("csrf_token") or "")):
        errors["form"] = "Your session expired. Reload the page and try again."
    if not re.fullmatch(r"[A-Z]{3}", profile["currency"]):
        errors["currency"] = "Enter a three-letter currency code such as SAR."
    if profile["default_vat_rate"] is None:
        errors["default_vat_rate"] = "Enter a VAT rate from 0 to 100."
    if not profile["default_validity_days"].isdigit() or not (
        1 <= int(profile["default_validity_days"]) <= 365
    ):
        errors["default_validity_days"] = "Enter a validity period from 1 to 365 days."
    if not re.fullmatch(r"[A-Z0-9-]{1,12}", profile["quotation_prefix"]):
        errors["quotation_prefix"] = (
            "Use up to 12 letters, numbers, or hyphens."
        )
    if len(profile["company_name"]) > 160:
        errors["company_name"] = "Company name must be 160 characters or fewer."
    if len(profile["company_phone"]) > 40:
        errors["company_phone"] = "Phone number must be 40 characters or fewer."
    if len(profile["company_email"]) > 254 or (
        profile["company_email"]
        and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", profile["company_email"])
    ):
        errors["company_email"] = "Enter a valid company email address."
    for key, label in (
        ("default_manpower_price", "manpower"),
        ("default_transportation_price", "transportation"),
        ("default_installation_price", "installation"),
    ):
        if profile[key] is None:
            errors[key] = f"Enter a valid non-negative default {label} cost."
    if errors:
        return render(
            request,
            "pricing_settings.html",
            {
                "active_nav": "pricing_settings",
                "profile": profile,
                "errors": errors,
                "saved": db.get(PricingSettings, 1),
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    saved = db.get(PricingSettings, 1)
    if saved is None:
        saved = PricingSettings(
            id=1,
            updated_by_id=admin.id,
            updated_by_name=admin.full_name,
        )
        db.add(saved)
    for key in DEFAULT_SETTINGS:
        value = profile[key]
        if key == "default_validity_days":
            value = int(value)
        setattr(saved, key, value)
    saved.updated_by_id = admin.id
    saved.updated_by_name = admin.full_name
    saved.updated_at = utcnow()
    db.commit()
    flash(request, "Pricing settings saved. Existing quotations keep their snapshots.")
    return _redirect("/pricing/settings")
