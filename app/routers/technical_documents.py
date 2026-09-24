"""Pricing-item Data Sheet library and technical recommendations."""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..audit import set_audit_context
from ..database import get_db
from ..deps import require_technical_documents_access, require_technical_documents_manager
from ..helpers import flash, render
from ..models import PricingItem, PricingItemCategory, PricingRelatedItem, TechnicalDocument, TechnicalRecommendation, User, utcnow
from ..purchase_documents import PurchaseDocumentError
from ..security import csrf_valid
from ..technical_documents import recommendation_pdf, resolve_technical_file, store_technical_file, technical_package
from .purchase_documents import _browser_context

router = APIRouter(prefix="/pricing/data-sheet", dependencies=[Depends(require_technical_documents_access)])


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def _target(db: Session, kind: str, item_id: int):
    if kind == "main":
        item = db.scalar(select(PricingItem).options(selectinload(PricingItem.category).selectinload(PricingItemCategory.parent)).where(PricingItem.id == item_id))
        if not item: raise HTTPException(404, "Item not found.")
        return item, item, item.name, item.model or ""
    if kind == "related":
        related = db.scalar(select(PricingRelatedItem).options(selectinload(PricingRelatedItem.main_item).selectinload(PricingItem.category).selectinload(PricingItemCategory.parent)).where(PricingRelatedItem.id == item_id))
        if not related: raise HTTPException(404, "Item not found.")
        return related, related.main_item, related.name, related.main_item.model or ""
    raise HTTPException(404, "Item not found.")


def _filters(kind: str, item_id: int):
    return (TechnicalDocument.pricing_item_id == item_id) if kind == "main" else (TechnicalDocument.related_item_id == item_id)


def _rec_filter(kind: str, item_id: int):
    return (TechnicalRecommendation.pricing_item_id == item_id) if kind == "main" else (TechnicalRecommendation.related_item_id == item_id)


def _category(main: PricingItem) -> str:
    category = main.category
    if not category: return "Uncategorized"
    return f"{category.parent.name} / {category.name}" if category.parent else category.name


@router.get("")
def home(request: Request, q: str = "", category: str = "", user: User = Depends(require_technical_documents_access), db: Session = Depends(get_db)):
    context = _browser_context(db, q=q, category=category)
    context.update({"active_nav":"technical_documents"})
    return render(request, "technical_documents.html", context)


@router.get("/items/{kind}/{item_id}")
def item_page(kind: str, item_id: int, request: Request, user: User = Depends(require_technical_documents_access), db: Session = Depends(get_db)):
    target, main, name, model = _target(db, kind, item_id)
    documents = list(db.scalars(select(TechnicalDocument).where(_filters(kind,item_id)).order_by(TechnicalDocument.created_at.desc())))
    recommendation = db.scalar(select(TechnicalRecommendation).where(_rec_filter(kind,item_id)))
    return render(request, "technical_document_item.html", {"active_nav":"technical_documents", "kind":kind, "item_id":item_id, "target":target, "main_item":main, "item_name":name, "model":model, "category_name":_category(main), "documents":documents, "recommendation":recommendation})


@router.post("/items/{kind}/{item_id}/documents", dependencies=[Depends(require_technical_documents_manager)])
async def upload_documents(kind: str, item_id: int, request: Request, title: str = Form(""), notes: str = Form(""), files: list[UploadFile] = File(default=[]), csrf_token: str = Form(""), user: User = Depends(require_technical_documents_manager), db: Session = Depends(get_db)):
    path = f"/pricing/data-sheet/items/{kind}/{item_id}"
    if not csrf_valid(request, csrf_token): flash(request, "Your form expired. Refresh and try again.", "error"); return _redirect(path)
    _target(db, kind, item_id)
    uploads = [entry for entry in files if entry.filename]
    if not uploads: flash(request, "Choose at least one PDF or image.", "error"); return _redirect(path)
    stored = []
    try:
        for entry in uploads:
            stored.append(store_technical_file(entry.filename or "document", await entry.read()))
        for key, filename, content_type, size in stored:
            db.add(TechnicalDocument(pricing_item_id=item_id if kind=="main" else None, related_item_id=item_id if kind=="related" else None, title=title.strip() or Path(filename).stem, notes=notes.strip() or None, storage_key=key, original_filename=filename, content_type=content_type, file_size=size, uploaded_by_id=user.id, uploaded_by_name=user.full_name))
        db.commit()
    except PurchaseDocumentError as exc:
        db.rollback()
        for key, *_ in stored:
            try: resolve_technical_file(key).unlink(missing_ok=True)
            except PurchaseDocumentError: pass
        flash(request, str(exc), "error"); return _redirect(path)
    set_audit_context(request, action="upload", entity_type="technical_document", entity_id=f"{kind}:{item_id}", entity_label=title.strip() or "Data Sheet", changes={"files":len(stored)})
    flash(request, f"{len(stored)} Data Sheet file(s) uploaded."); return _redirect(path)


@router.post("/items/{kind}/{item_id}/recommendation", dependencies=[Depends(require_technical_documents_manager)])
def save_recommendation(kind: str, item_id: int, request: Request, recommendation: str = Form(""), csrf_token: str = Form(""), user: User = Depends(require_technical_documents_manager), db: Session = Depends(get_db)):
    path = f"/pricing/data-sheet/items/{kind}/{item_id}"
    if not csrf_valid(request, csrf_token): flash(request, "Your form expired. Refresh and try again.", "error"); return _redirect(path)
    _target(db, kind, item_id)
    text = recommendation.strip()
    row = db.scalar(select(TechnicalRecommendation).where(_rec_filter(kind,item_id)))
    if not text:
        if row: db.delete(row); db.commit()
        flash(request, "Recommendation removed."); return _redirect(path)
    if row is None:
        row = TechnicalRecommendation(pricing_item_id=item_id if kind=="main" else None, related_item_id=item_id if kind=="related" else None, recommendation=text, updated_by_id=user.id, updated_by_name=user.full_name)
        db.add(row)
    else:
        row.recommendation=text; row.updated_by_id=user.id; row.updated_by_name=user.full_name; row.updated_at=utcnow()
    db.commit(); set_audit_context(request, action="update", entity_type="technical_recommendation", entity_id=f"{kind}:{item_id}", changes={"characters":len(text)})
    flash(request, "Technical recommendation saved."); return _redirect(path)


@router.get("/documents/{document_id}/preview")
def preview(document_id: int, request: Request, user: User = Depends(require_technical_documents_access), db: Session = Depends(get_db)):
    row = db.get(TechnicalDocument, document_id)
    if not row: raise HTTPException(404)
    set_audit_context(request, action="preview", entity_type="technical_document", entity_id=row.id, entity_label=row.title)
    return FileResponse(resolve_technical_file(row.storage_key), media_type=row.content_type, headers={"Content-Disposition":f'inline; filename="{row.original_filename}"'})


@router.get("/documents/{document_id}/download")
def download(document_id: int, request: Request, user: User = Depends(require_technical_documents_access), db: Session = Depends(get_db)):
    row = db.get(TechnicalDocument, document_id)
    if not row: raise HTTPException(404)
    set_audit_context(request, action="download", entity_type="technical_document", entity_id=row.id, entity_label=row.title)
    return FileResponse(resolve_technical_file(row.storage_key), media_type=row.content_type, filename=row.original_filename)


@router.post("/documents/{document_id}/delete", dependencies=[Depends(require_technical_documents_manager)])
def delete_document(document_id: int, request: Request, csrf_token: str = Form(""), user: User = Depends(require_technical_documents_manager), db: Session = Depends(get_db)):
    row = db.get(TechnicalDocument, document_id)
    if not row: raise HTTPException(404)
    kind, item_id = ("main",row.pricing_item_id) if row.pricing_item_id else ("related",row.related_item_id)
    path=f"/pricing/data-sheet/items/{kind}/{item_id}"
    if not csrf_valid(request,csrf_token): return _redirect(path)
    key,label=row.storage_key,row.title; db.delete(row); db.commit()
    try: resolve_technical_file(key).unlink(missing_ok=True)
    except PurchaseDocumentError: pass
    set_audit_context(request, action="delete", entity_type="technical_document", entity_id=document_id, entity_label=label)
    flash(request,"Data Sheet deleted."); return _redirect(path)


def _recommendation_payload(db: Session, kind: str, item_id: int):
    _,main,name,model=_target(db,kind,item_id); row=db.scalar(select(TechnicalRecommendation).where(_rec_filter(kind,item_id)))
    if not row: raise HTTPException(404,"No recommendation has been saved.")
    return recommendation_pdf(item_name=name,model=model,category=_category(main),recommendation=row.recommendation,updated_at=row.updated_at),name


@router.get("/items/{kind}/{item_id}/recommendation.pdf")
def recommendation_download(kind: str,item_id:int,request:Request,user:User=Depends(require_technical_documents_access),db:Session=Depends(get_db)):
    payload,name=_recommendation_payload(db,kind,item_id); set_audit_context(request,action="download",entity_type="technical_recommendation",entity_id=f"{kind}:{item_id}",entity_label=name)
    return Response(payload,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{name}-recommendation.pdf"'})


@router.get("/items/{kind}/{item_id}/package.zip")
def package(kind:str,item_id:int,request:Request,user:User=Depends(require_technical_documents_access),db:Session=Depends(get_db)):
    _,main,name,model=_target(db,kind,item_id); docs=list(db.scalars(select(TechnicalDocument).where(_filters(kind,item_id)).order_by(TechnicalDocument.created_at)))
    rec=db.scalar(select(TechnicalRecommendation).where(_rec_filter(kind,item_id))); rec_payload=recommendation_pdf(item_name=name,model=model,category=_category(main),recommendation=rec.recommendation,updated_at=rec.updated_at) if rec else None
    if not docs and not rec: raise HTTPException(404,"No technical information is available.")
    payload=technical_package(docs,rec_payload,name); set_audit_context(request,action="download_package",entity_type="technical_item",entity_id=f"{kind}:{item_id}",entity_label=name)
    return Response(payload,media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="{name}-technical-package.zip"'})
