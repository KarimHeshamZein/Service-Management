"""Shared purchase documents and item-level purchase-price analysis."""
from __future__ import annotations

import json
import tempfile
import zipfile
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Iterator
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import UploadFile

from ..audit import set_audit_context
from ..access_control import permission_allowed, require_permission
from ..database import get_db
from ..deps import require_purchase_documents_access
from ..helpers import entity_id, flash, parse_date, render
from ..models import (
    PricingItem,
    PricingItemCategory,
    PricingRelatedItem,
    PurchaseDocument,
    PurchaseDocumentFile,
    PurchaseDocumentItem,
    PurchaseDocumentType,
    User,
    utcnow,
)
from ..pricing import money
from ..purchase_documents import (
    MAX_PURCHASE_FILES,
    PurchaseDocumentError,
    build_price_analysis_pdf,
    build_purchase_document_preview,
    delete_purchase_files,
    resolve_purchase_file,
    store_purchase_file,
)
from ..security import csrf_valid


router = APIRouter(
    prefix="/pricing/purchase-documents",
    dependencies=[Depends(require_purchase_documents_access)],
)
CURRENCIES = ("SAR", "USD")


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def _item_url(kind: str, item_id: int) -> str:
    return f"/pricing/purchase-documents/items/{kind}/{item_id}"


def _target(db: Session, kind: str, item_id: int) -> tuple[Any, PricingItem]:
    if kind == "main":
        item = db.scalar(
            select(PricingItem)
            .options(selectinload(PricingItem.category).selectinload(PricingItemCategory.parent))
            .where(PricingItem.id == item_id)
        )
        if item is None:
            raise HTTPException(404, "Pricing item not found.")
        return item, item
    if kind == "related":
        related = db.scalar(
            select(PricingRelatedItem)
            .options(
                selectinload(PricingRelatedItem.main_item)
                .selectinload(PricingItem.category)
                .selectinload(PricingItemCategory.parent)
            )
            .where(PricingRelatedItem.id == item_id)
        )
        if related is None:
            raise HTTPException(404, "Related pricing item not found.")
        return related, related.main_item
    raise HTTPException(404, "Pricing item not found.")


def _card(main: PricingItem, related: PricingRelatedItem | None = None) -> dict[str, Any]:
    target = related or main
    category = main.category
    return {
        "key": f'{"related" if related else "main"}:{target.id}',
        "kind": "related" if related else "main",
        "id": target.id,
        "name": target.name,
        "model": main.model if related is None else "",
        "currency": target.currency,
        "is_related": related is not None,
        "parent_name": main.name if related else "",
        "category_id": category.id if category else None,
        "root_category_id": (
            category.parent_id if category and category.parent_id else category.id if category else None
        ),
        "image_url": f"/pricing/items/{main.id}/image?size=thumb" if main.image_storage_key else "",
        "url": _item_url("related" if related else "main", target.id),
    }


def _catalogue(db: Session) -> tuple[list[PricingItemCategory], list[dict[str, Any]]]:
    categories = list(
        db.scalars(
            select(PricingItemCategory)
            .options(
                selectinload(PricingItemCategory.parent),
                selectinload(PricingItemCategory.children),
                selectinload(PricingItemCategory.items).selectinload(PricingItem.related_items),
            )
            .order_by(PricingItemCategory.name)
        ).unique()
    )
    items = list(
        db.scalars(
            select(PricingItem)
            .options(
                selectinload(PricingItem.related_items),
                selectinload(PricingItem.category).selectinload(PricingItemCategory.parent),
            )
            .order_by(PricingItem.name, PricingItem.model)
        ).unique()
    )
    cards: list[dict[str, Any]] = []
    for item in items:
        cards.append(_card(item))
        cards.extend(_card(item, related) for related in item.related_items)
    return categories, cards


def _browser_context(db: Session, *, q: str = "", category: str = "") -> dict[str, Any]:
    categories, catalogue = _catalogue(db)
    roots = [entry for entry in categories if entry.parent_id is None]
    selected = None
    category_key = category.strip()
    if category_key and category_key != "uncategorized":
        selected = next((entry for entry in categories if entry.id == entity_id(category_key)), None)
        if selected is None:
            raise HTTPException(404, "Item category not found.")
    term = q.strip().casefold()
    cards = []
    if term:
        cards = [
            card for card in catalogue
            if term in card["name"].casefold()
            or term in card["model"].casefold()
            or term in card["parent_name"].casefold()
        ]
    elif category_key == "uncategorized":
        cards = [card for card in catalogue if card["category_id"] is None]
    elif selected is not None:
        cards = [card for card in catalogue if card["category_id"] == selected.id]
    root_counts = {
        root.id: sum(1 for card in catalogue if card["root_category_id"] == root.id)
        for root in roots
    }
    return {
        "categories": categories,
        "root_categories": roots,
        "root_counts": root_counts,
        "uncategorized_count": sum(1 for card in catalogue if card["category_id"] is None),
        "selected_category": selected,
        "selected_category_key": category_key,
        "subcategories": selected.children if selected and selected.parent_id is None else [],
        "cards": cards,
        "q": q.strip(),
        "catalogue": catalogue,
    }


@router.get("")
def purchase_documents_home(
    request: Request,
    q: str = "",
    category: str = "",
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.view")
    context = _browser_context(db, q=q, category=category)
    context.update({"active_nav": "purchase_documents"})
    return render(request, "purchase_documents.html", context)


def _form_context(
    db: Session,
    *,
    document: PurchaseDocument | None = None,
    initial_kind: str = "",
    initial_item_id: int | None = None,
) -> dict[str, Any]:
    browser = _browser_context(db)
    selected: list[dict[str, Any]] = []
    if document is not None:
        for link in document.item_links:
            selected.append({
                "kind": "main" if link.pricing_item_id else "related",
                "id": link.pricing_item_id or link.related_item_id,
                "unit_price": str(link.unit_price) if link.unit_price is not None else "",
                "currency": link.currency or "SAR",
            })
    elif initial_kind and initial_item_id:
        target, _ = _target(db, initial_kind, initial_item_id)
        selected.append({
            "kind": initial_kind,
            "id": initial_item_id,
            "unit_price": "",
            "currency": target.currency,
        })
    return {
        "active_nav": "purchase_documents",
        "document": document,
        "document_types": list(PurchaseDocumentType),
        "currencies": CURRENCIES,
        "catalogue": browser["catalogue"],
        "category_tree": [
            {
                "id": root.id,
                "name": root.name,
                "children": [
                    {"id": child.id, "name": child.name}
                    for child in root.children
                ],
            }
            for root in browser["root_categories"]
        ],
        "selected_items_json": json.dumps(selected),
    }


@router.get("/new")
def new_purchase_document(
    request: Request,
    kind: str = "",
    item_id: int | None = None,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.manage")
    return render(
        request,
        "purchase_document_form.html",
        _form_context(db, initial_kind=kind, initial_item_id=item_id),
    )


def _document(db: Session, document_id: int) -> PurchaseDocument:
    document = db.scalar(
        select(PurchaseDocument)
        .options(
            selectinload(PurchaseDocument.files),
            selectinload(PurchaseDocument.item_links).selectinload(PurchaseDocumentItem.item),
            selectinload(PurchaseDocument.item_links)
            .selectinload(PurchaseDocumentItem.related_item)
            .selectinload(PricingRelatedItem.main_item),
        )
        .where(PurchaseDocument.id == document_id)
    )
    if document is None:
        raise HTTPException(404, "Purchase document not found.")
    return document


@router.get("/{document_id}/edit")
def edit_purchase_document(
    document_id: int,
    request: Request,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.manage")
    return render(
        request,
        "purchase_document_form.html",
        _form_context(db, document=_document(db, document_id)),
    )


def _selected_links(db: Session, payload: str) -> tuple[list[PurchaseDocumentItem], list[str]]:
    try:
        values = json.loads(payload)
    except (TypeError, ValueError):
        return [], ["Choose at least one item."]
    if not isinstance(values, list) or not values:
        return [], ["Choose at least one item."]
    links: list[PurchaseDocumentItem] = []
    errors: list[str] = []
    seen: set[tuple[str, int]] = set()
    for position, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append("One selected item is invalid.")
            continue
        kind = str(value.get("kind") or "")
        item_id = entity_id(str(value.get("id") or ""))
        if kind not in {"main", "related"} or item_id is None or (kind, item_id) in seen:
            errors.append("One selected item is invalid or duplicated.")
            continue
        seen.add((kind, item_id))
        try:
            target, _ = _target(db, kind, item_id)
        except HTTPException:
            errors.append("One selected item no longer exists.")
            continue
        raw_price = str(value.get("unit_price") or "").strip()
        price = money(raw_price) if raw_price else None
        currency = str(value.get("currency") or target.currency).strip().upper()
        if raw_price and price is None:
            errors.append(f"Enter a valid unit price for {target.name}.")
            continue
        if price is not None and currency not in CURRENCIES:
            errors.append(f"Choose a supported currency for {target.name}.")
            continue
        links.append(PurchaseDocumentItem(
            pricing_item_id=item_id if kind == "main" else None,
            related_item_id=item_id if kind == "related" else None,
            unit_price=price,
            currency=currency if price is not None else None,
            position=position,
        ))
    return links, errors


async def _save_document(
    request: Request,
    db: Session,
    user: User,
    document: PurchaseDocument | None,
) -> RedirectResponse:
    form = await request.form()
    return_url = f"/pricing/purchase-documents/{document.id}/edit" if document else "/pricing/purchase-documents/new"
    if not csrf_valid(request, str(form.get("csrf_token") or "")):
        flash(request, "Your form expired. Refresh the page and try again.", "error")
        return _redirect(return_url)
    try:
        selected_type = PurchaseDocumentType(str(form.get("document_type") or ""))
    except ValueError:
        selected_type = None
    supplier_name = str(form.get("supplier_name") or "").strip()
    document_date = parse_date(str(form.get("document_date") or ""))
    links, link_errors = _selected_links(db, str(form.get("selected_items_json") or ""))
    uploads = [
        entry for entry in form.getlist("files")
        if isinstance(entry, UploadFile) and entry.filename
    ]
    errors = list(link_errors)
    if selected_type is None:
        errors.append("Choose Purchase invoice or Supplier quotation.")
    if not supplier_name:
        errors.append("Enter the supplier name.")
    if document_date is None:
        errors.append("Enter a valid document date.")
    if document is None and not uploads:
        errors.append("Choose at least one document file.")
    existing_file_count = len(document.files) if document else 0
    if existing_file_count + len(uploads) > MAX_PURCHASE_FILES:
        errors.append("A purchase document can contain no more than 20 files.")
    if errors:
        flash(request, " ".join(errors), "error")
        return _redirect(return_url)

    stored = []
    try:
        for upload in uploads:
            stored.append(store_purchase_file(upload.filename or "document", await upload.read()))
    except PurchaseDocumentError as exc:
        delete_purchase_files(*[entry.storage_key for entry in stored])
        flash(request, str(exc), "error")
        return _redirect(return_url)

    creating = document is None
    if document is None:
        document = PurchaseDocument(
            uploaded_by_id=user.id,
            uploaded_by_name=user.full_name,
            created_at=utcnow(),
        )
        db.add(document)
    old_targets = [
        f"main:{link.pricing_item_id}" if link.pricing_item_id else f"related:{link.related_item_id}"
        for link in document.item_links
    ]
    document.document_type = selected_type
    document.supplier_name = supplier_name
    document.document_date = document_date
    start_position = len(document.files)
    document.files.extend([
        PurchaseDocumentFile(
            storage_key=entry.storage_key,
            original_filename=entry.original_filename,
            content_type=entry.content_type,
            file_size=entry.file_size,
            position=start_position + position,
        )
        for position, entry in enumerate(stored)
    ])
    try:
        if creating:
            document.item_links = links
        else:
            existing = {
                ("main", link.pricing_item_id) if link.pricing_item_id else ("related", link.related_item_id): link
                for link in document.item_links
            }
            # Free the unique saved positions before reordering or replacing
            # links. Reused rows retain their identity for a clean audit trail.
            for offset, link in enumerate(document.item_links):
                link.position = 100000 + offset
            db.flush()
            reconciled: list[PurchaseDocumentItem] = []
            for desired in links:
                key = (
                    ("main", desired.pricing_item_id)
                    if desired.pricing_item_id
                    else ("related", desired.related_item_id)
                )
                saved = existing.pop(key, None)
                if saved is None:
                    reconciled.append(desired)
                    continue
                saved.unit_price = desired.unit_price
                saved.currency = desired.currency
                saved.position = desired.position
                reconciled.append(saved)
            for removed in existing.values():
                document.item_links.remove(removed)
            for link in reconciled:
                if link not in document.item_links:
                    document.item_links.append(link)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        delete_purchase_files(*[entry.storage_key for entry in stored])
        flash(request, "The purchase document could not be saved. Try again.", "error")
        return _redirect(return_url)
    new_targets = [
        f"main:{link.pricing_item_id}" if link.pricing_item_id else f"related:{link.related_item_id}"
        for link in document.item_links
    ]
    set_audit_context(
        request,
        action="create" if creating else "update",
        entity_type="purchase_document",
        entity_id=document.id,
        entity_label=f"{selected_type.label} - {supplier_name}",
        changes={
            "items": {"before": old_targets, "after": new_targets},
            "supplier": {"before": None if creating else "updated", "after": supplier_name},
            "document_date": {"before": None if creating else "updated", "after": document_date.isoformat()},
            "added_files": {"before": None, "after": [entry.original_filename for entry in stored]},
        },
    )
    flash(request, "Purchase document saved.")
    return _redirect(f"/pricing/purchase-documents/{document.id}/edit")


@router.post("")
async def create_purchase_document(
    request: Request,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.manage")
    return await _save_document(request, db, user, None)


@router.post("/{document_id}/edit")
async def update_purchase_document(
    document_id: int,
    request: Request,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.manage")
    return await _save_document(request, db, user, _document(db, document_id))


def _filtered_rows(
    db: Session,
    kind: str,
    item_id: int,
    *,
    document_type: str = "",
    supplier: str = "",
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[tuple[PurchaseDocument, PurchaseDocumentItem]]:
    stmt = (
        select(PurchaseDocument, PurchaseDocumentItem)
        .join(PurchaseDocumentItem, PurchaseDocumentItem.document_id == PurchaseDocument.id)
        .options(selectinload(PurchaseDocument.files), selectinload(PurchaseDocument.item_links))
        .where(
            PurchaseDocumentItem.pricing_item_id == item_id
            if kind == "main"
            else PurchaseDocumentItem.related_item_id == item_id
        )
    )
    if document_type in {entry.value for entry in PurchaseDocumentType}:
        stmt = stmt.where(PurchaseDocument.document_type == PurchaseDocumentType(document_type))
    if supplier.strip():
        stmt = stmt.where(PurchaseDocument.supplier_name.ilike(f"%{supplier.strip()}%"))
    if date_from:
        stmt = stmt.where(PurchaseDocument.document_date >= date_from)
    if date_to:
        stmt = stmt.where(PurchaseDocument.document_date <= date_to)
    return list(db.execute(stmt.order_by(PurchaseDocument.document_date.desc(), PurchaseDocument.id.desc())).all())


def _price_series(rows: list[tuple[PurchaseDocument, PurchaseDocumentItem]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[PurchaseDocument, PurchaseDocumentItem]]] = defaultdict(list)
    for document, link in rows:
        if link.unit_price is not None and link.currency:
            grouped[link.currency].append((document, link))
    result = []
    for currency, entries in sorted(grouped.items()):
        ordered = sorted(entries, key=lambda entry: (entry[0].document_date, entry[0].id))
        prices = [entry[1].unit_price for entry in ordered]
        latest = ordered[-1][1].unit_price
        previous = ordered[-2][1].unit_price if len(ordered) > 1 else None
        change = latest - previous if previous is not None else None
        percentage = change / previous * Decimal("100") if previous else None
        result.append({
            "currency": currency,
            "latest": latest,
            "lowest": min(prices),
            "highest": max(prices),
            "change": change,
            "percentage": percentage,
            "points": ordered,
        })
    return result


@router.get("/items/{kind}/{item_id}")
def purchase_document_item(
    kind: str,
    item_id: int,
    request: Request,
    document_type: str = "",
    supplier: str = "",
    date_from: str = "",
    date_to: str = "",
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.view")
    target, main = _target(db, kind, item_id)
    rows = _filtered_rows(
        db,
        kind,
        item_id,
        document_type=document_type,
        supplier=supplier,
        date_from=parse_date(date_from),
        date_to=parse_date(date_to),
    )
    query = urlencode({
        key: value for key, value in {
            "document_type": document_type,
            "supplier": supplier,
            "date_from": date_from,
            "date_to": date_to,
        }.items() if value
    })
    return render(
        request,
        "purchase_document_item.html",
        {
            "active_nav": "purchase_documents",
            "kind": kind,
            "target": target,
            "main_item": main,
            "rows": rows,
            "document_types": list(PurchaseDocumentType),
            "selected_type": document_type,
            "supplier": supplier.strip(),
            "date_from": date_from,
            "date_to": date_to,
            "price_series": _price_series(rows),
            "can_delete": permission_allowed(db, user, db.info["department_id"], "purchase_documents.manage"),
            "price_analysis_url": f"{_item_url(kind, item_id)}/price-analysis.pdf" + (f"?{query}" if query else ""),
        },
    )


@router.get("/{document_id}/preview")
def preview_purchase_document(
    document_id: int,
    request: Request,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.view")
    document = _document(db, document_id)
    try:
        payload = build_purchase_document_preview(document.files)
    except PurchaseDocumentError as exc:
        raise HTTPException(404, str(exc))
    set_audit_context(request, action="preview", entity_type="purchase_document", entity_id=document.id, entity_label=document.supplier_name)
    return Response(payload, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="purchase-document-{document.id}.pdf"'})


@router.get("/files/{file_id}/download")
def download_purchase_file(
    file_id: int,
    request: Request,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.view")
    entry = db.scalar(
        select(PurchaseDocumentFile)
        .join(PurchaseDocument, PurchaseDocument.id == PurchaseDocumentFile.document_id)
        .where(
            PurchaseDocumentFile.id == file_id,
            PurchaseDocument.department_id == db.info.get("department_id"),
        )
    )
    if entry is None:
        raise HTTPException(404, "Purchase-document file not found.")
    try:
        path = resolve_purchase_file(entry.storage_key)
    except PurchaseDocumentError as exc:
        raise HTTPException(404, str(exc))
    set_audit_context(request, action="download", entity_type="purchase_document_file", entity_id=entry.id, entity_label=entry.original_filename)
    return FileResponse(path, media_type=entry.content_type, filename=entry.original_filename)


def _zip_stream(spool) -> Iterator[bytes]:
    try:
        while chunk := spool.read(1024 * 1024):
            yield chunk
    finally:
        spool.close()


@router.get("/{document_id}/download")
def download_purchase_document(
    document_id: int,
    request: Request,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.view")
    document = _document(db, document_id)
    if len(document.files) == 1:
        entry = document.files[0]
        return FileResponse(
            resolve_purchase_file(entry.storage_key),
            media_type=entry.content_type,
            filename=entry.original_filename,
        )
    spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
    with zipfile.ZipFile(spool, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for position, entry in enumerate(document.files, 1):
            archive.write(resolve_purchase_file(entry.storage_key), arcname=f"{position:02d}-{entry.original_filename}")
    spool.seek(0)
    set_audit_context(request, action="download_all", entity_type="purchase_document", entity_id=document.id, entity_label=document.supplier_name)
    return StreamingResponse(
        _zip_stream(spool),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="purchase-document-{document.id}.zip"'},
    )


@router.get("/items/{kind}/{item_id}/price-analysis.pdf")
def price_analysis_pdf(
    kind: str,
    item_id: int,
    request: Request,
    document_type: str = "",
    supplier: str = "",
    date_from: str = "",
    date_to: str = "",
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.view")
    target, main = _target(db, kind, item_id)
    rows = _filtered_rows(
        db, kind, item_id,
        document_type=document_type,
        supplier=supplier,
        date_from=parse_date(date_from),
        date_to=parse_date(date_to),
    )
    priced = [(document, link) for document, link in reversed(rows) if link.unit_price is not None]
    if not priced:
        flash(request, "No priced purchase documents match these filters.", "error")
        return _redirect(_item_url(kind, item_id))
    report_rows = [{
        "date": document.document_date.isoformat(),
        "type": document.document_type.label,
        "supplier": document.supplier_name,
        "price": link.unit_price,
        "currency": link.currency,
    } for document, link in priced]
    label = main.display_label if kind == "main" else f"{target.name} ({main.name})"
    payload = build_price_analysis_pdf(label, report_rows)
    set_audit_context(request, action="export_price_analysis", entity_type="purchase_document_item", entity_id=f"{kind}:{item_id}", entity_label=label)
    return Response(payload, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="purchase-price-analysis-{kind}-{item_id}.pdf"'})


@router.post("/{document_id}/delete")
async def delete_purchase_document(
    document_id: int,
    request: Request,
    user: User = Depends(require_purchase_documents_access),
    db: Session = Depends(get_db),
):
    require_permission(request, db, user, "purchase_documents.manage")
    document = _document(db, document_id)
    form = await request.form()
    if not csrf_valid(request, str(form.get("csrf_token") or "")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")
    storage_keys = [entry.storage_key for entry in document.files]
    label = f"{document.document_type.label} - {document.supplier_name}"
    db.delete(document)
    db.commit()
    delete_purchase_files(*storage_keys)
    set_audit_context(request, action="delete", entity_type="purchase_document", entity_id=document_id, entity_label=label, changes={"files": {"before": storage_keys, "after": None}})
    flash(request, "Purchase document deleted.")
    return _redirect("/pricing/purchase-documents")
