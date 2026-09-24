"""Independent wiring-diagram folder library."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..audit import set_audit_context
from ..database import get_db
from ..deps import require_admin, require_wiring_diagrams_access, require_wiring_diagrams_manager
from ..helpers import flash, render
from ..models import User, WiringDiagram, WiringDiagramCategory, WiringDiagramFile
from ..purchase_documents import PurchaseDocumentError, clean_filename
from ..security import csrf_valid
from ..wiring_diagrams import delete_wiring_files, files_zip, preview_pdf, resolve_wiring_file, store_wiring_file

router = APIRouter(prefix="/pricing/wiring-diagrams", dependencies=[Depends(require_wiring_diagrams_access)])


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _diagram(db: Session, diagram_id: int) -> WiringDiagram:
    row = db.scalar(select(WiringDiagram).options(selectinload(WiringDiagram.files), selectinload(WiringDiagram.category).selectinload(WiringDiagramCategory.parent)).where(WiringDiagram.id == diagram_id))
    if row is None:
        raise HTTPException(404, "Wiring diagram not found.")
    return row


def _category(db: Session, raw: str) -> WiringDiagramCategory | None:
    if not raw.strip():
        return None
    try:
        row = db.get(WiringDiagramCategory, int(raw))
    except ValueError:
        row = None
    if row is None:
        raise PurchaseDocumentError("Choose a valid category.")
    return row


def _folders(db: Session):
    roots = list(db.scalars(select(WiringDiagramCategory).options(selectinload(WiringDiagramCategory.children)).where(WiringDiagramCategory.parent_id.is_(None)).order_by(WiringDiagramCategory.name)))
    return roots


@router.get("")
def home(request: Request, q: str = "", project: str = "", category: str = "", user: User = Depends(require_wiring_diagrams_access), db: Session = Depends(get_db)):
    roots = _folders(db)
    selected = None
    if category:
        try:
            selected = db.get(WiringDiagramCategory, int(category))
        except ValueError:
            selected = None
    statement = select(WiringDiagram).options(selectinload(WiringDiagram.files), selectinload(WiringDiagram.category).selectinload(WiringDiagramCategory.parent)).order_by(WiringDiagram.name)
    if q.strip():
        term = f"%{q.strip()}%"
        statement = statement.where(or_(WiringDiagram.name.ilike(term), WiringDiagram.project_name.ilike(term), WiringDiagram.notes.ilike(term)))
    if project.strip():
        statement = statement.where(WiringDiagram.project_name.ilike(f"%{project.strip()}%"))
    if selected:
        statement = statement.where(WiringDiagram.category_id == selected.id)
    elif category == "uncategorized":
        statement = statement.where(WiringDiagram.category_id.is_(None))
    elif not q.strip() and not project.strip():
        statement = statement.where(WiringDiagram.id == -1)
    diagrams = list(db.scalars(statement))
    counts = dict(db.execute(select(WiringDiagram.category_id, func.count(WiringDiagram.id)).group_by(WiringDiagram.category_id)).all())
    root_counts = {root.id: counts.get(root.id, 0) + sum(counts.get(child.id, 0) for child in root.children) for root in roots}
    projects = list(db.scalars(select(WiringDiagram.project_name).where(WiringDiagram.project_name.is_not(None)).distinct().order_by(WiringDiagram.project_name)))
    return render(request, "wiring_diagrams.html", {"active_nav":"wiring_diagrams", "roots":roots, "selected":selected, "category_key":category, "diagrams":diagrams, "counts":counts, "root_counts":root_counts, "uncategorized_count":counts.get(None,0), "q":q, "project":project, "projects":projects})


@router.get("/new", dependencies=[Depends(require_wiring_diagrams_manager)])
def new(request: Request, user: User = Depends(require_wiring_diagrams_manager), db: Session = Depends(get_db)):
    return render(request, "wiring_diagram_form.html", {"active_nav":"wiring_diagrams", "diagram":None, "roots":_folders(db)})


async def _read_files(files: list[UploadFile]) -> list:
    actual = [entry for entry in files if entry.filename]
    if len(actual) > 20:
        raise PurchaseDocumentError("Upload no more than 20 files at once.")
    stored = []
    try:
        for entry in actual:
            stored.append(store_wiring_file(entry.filename or "diagram", await entry.read()))
    except Exception:
        delete_wiring_files(*(entry.storage_key for entry in stored))
        raise
    return stored


@router.post("", dependencies=[Depends(require_wiring_diagrams_manager)])
async def create(request: Request, name: str = Form(""), project_name: str = Form(""), category_id: str = Form(""), notes: str = Form(""), files: list[UploadFile] = File(default=[]), csrf_token: str = Form(""), user: User = Depends(require_wiring_diagrams_manager), db: Session = Depends(get_db)):
    if not csrf_valid(request, csrf_token): return _redirect("/pricing/wiring-diagrams/new")
    try:
        if not name.strip(): raise PurchaseDocumentError("Diagram name is required.")
        category = _category(db, category_id)
        stored = await _read_files(files)
        if not stored: raise PurchaseDocumentError("Add at least one PDF or image file.")
    except PurchaseDocumentError as exc:
        flash(request, str(exc), "error"); return _redirect("/pricing/wiring-diagrams/new")
    row = WiringDiagram(category=category, name=name.strip(), project_name=project_name.strip() or None, notes=notes.strip() or None, uploaded_by_id=user.id, uploaded_by_name=user.full_name)
    row.files = [WiringDiagramFile(storage_key=f.storage_key, original_filename=f.original_filename, content_type=f.content_type, file_size=f.file_size, position=index) for index, f in enumerate(stored, 1)]
    db.add(row); db.commit(); db.refresh(row)
    set_audit_context(request, action="create", entity_type="wiring_diagram", entity_id=row.id, entity_label=row.name, changes={"project_name":row.project_name, "category":category.name if category else None, "files":len(stored)})
    flash(request, "Wiring diagram created."); return _redirect(f"/pricing/wiring-diagrams/{row.id}")


@router.get("/categories", dependencies=[Depends(require_wiring_diagrams_manager)])
def categories(request: Request, user: User = Depends(require_wiring_diagrams_manager), db: Session = Depends(get_db)):
    return render(request, "wiring_diagram_categories.html", {"active_nav":"wiring_diagrams", "roots":_folders(db)})


@router.post("/categories", dependencies=[Depends(require_wiring_diagrams_manager)])
def create_category(request: Request, name: str = Form(""), parent_id: str = Form(""), csrf_token: str = Form(""), user: User = Depends(require_wiring_diagrams_manager), db: Session = Depends(get_db)):
    if not csrf_valid(request, csrf_token): return _redirect("/pricing/wiring-diagrams/categories")
    value = name.strip()
    parent = _category(db, parent_id) if parent_id.strip() else None
    if parent and parent.parent_id is not None:
        flash(request, "Only Main and Subcategories are supported.", "error"); return _redirect("/pricing/wiring-diagrams/categories")
    clash = db.scalar(select(WiringDiagramCategory).where(func.lower(WiringDiagramCategory.name) == value.lower(), WiringDiagramCategory.parent_id == (parent.id if parent else None))) if value else True
    if not value or clash:
        flash(request, "Enter a unique category name.", "error"); return _redirect("/pricing/wiring-diagrams/categories")
    row = WiringDiagramCategory(name=value, parent=parent); db.add(row); db.commit(); db.refresh(row)
    set_audit_context(request, action="create", entity_type="wiring_diagram_category", entity_id=row.id, entity_label=row.name, changes={"parent":parent.name if parent else None})
    flash(request, "Category created."); return _redirect("/pricing/wiring-diagrams/categories")


@router.post("/categories/{category_id}/delete", dependencies=[Depends(require_wiring_diagrams_manager)])
def delete_category(category_id: int, request: Request, csrf_token: str = Form(""), user: User = Depends(require_wiring_diagrams_manager), db: Session = Depends(get_db)):
    if not csrf_valid(request, csrf_token): return _redirect("/pricing/wiring-diagrams/categories")
    row = db.get(WiringDiagramCategory, category_id)
    if not row: raise HTTPException(404)
    used = db.scalar(select(func.count(WiringDiagram.id)).where(WiringDiagram.category_id == row.id)) or 0
    children = db.scalar(select(func.count(WiringDiagramCategory.id)).where(WiringDiagramCategory.parent_id == row.id)) or 0
    if used or children:
        flash(request, "Move the diagrams and delete Subcategories first.", "error"); return _redirect("/pricing/wiring-diagrams/categories")
    label=row.name; db.delete(row); db.commit(); set_audit_context(request, action="delete", entity_type="wiring_diagram_category", entity_id=category_id, entity_label=label)
    flash(request, "Category deleted."); return _redirect("/pricing/wiring-diagrams/categories")


@router.get("/{diagram_id}")
def detail(diagram_id: int, request: Request, user: User = Depends(require_wiring_diagrams_access), db: Session = Depends(get_db)):
    return render(request, "wiring_diagram_detail.html", {"active_nav":"wiring_diagrams", "diagram":_diagram(db, diagram_id)})


@router.get("/{diagram_id}/edit", dependencies=[Depends(require_wiring_diagrams_manager)])
def edit(diagram_id: int, request: Request, user: User = Depends(require_wiring_diagrams_manager), db: Session = Depends(get_db)):
    return render(request, "wiring_diagram_form.html", {"active_nav":"wiring_diagrams", "diagram":_diagram(db, diagram_id), "roots":_folders(db)})


@router.post("/{diagram_id}/edit", dependencies=[Depends(require_wiring_diagrams_manager)])
async def save_edit(diagram_id: int, request: Request, name: str = Form(""), project_name: str = Form(""), category_id: str = Form(""), notes: str = Form(""), remove_file_ids: list[str] = Form(default=[]), files: list[UploadFile] = File(default=[]), csrf_token: str = Form(""), user: User = Depends(require_wiring_diagrams_manager), db: Session = Depends(get_db)):
    row = _diagram(db, diagram_id); path=f"/pricing/wiring-diagrams/{diagram_id}/edit"
    if not csrf_valid(request, csrf_token): return _redirect(path)
    try:
        if not name.strip(): raise PurchaseDocumentError("Diagram name is required.")
        category = _category(db, category_id)
        remove_ids = {int(value) for value in remove_file_ids if value.isdigit()}
        removable = [entry for entry in row.files if entry.id in remove_ids]
        stored = await _read_files(files)
        if len(row.files) - len(removable) + len(stored) < 1: raise PurchaseDocumentError("Keep or add at least one file.")
    except PurchaseDocumentError as exc:
        flash(request, str(exc), "error"); return _redirect(path)
    old={"name":row.name,"project_name":row.project_name,"category":row.category.name if row.category else None,"files":len(row.files)}
    removed_keys=[entry.storage_key for entry in removable]
    for entry in removable: db.delete(entry)
    db.flush(); remaining=[entry for entry in row.files if entry.id not in remove_ids]
    for position, entry in enumerate(remaining,1): entry.position=position
    start=len(remaining)+1
    for offset, f in enumerate(stored): db.add(WiringDiagramFile(diagram_id=row.id, storage_key=f.storage_key, original_filename=f.original_filename, content_type=f.content_type, file_size=f.file_size, position=start+offset))
    row.name=name.strip(); row.project_name=project_name.strip() or None; row.category=category; row.notes=notes.strip() or None
    db.commit(); delete_wiring_files(*removed_keys)
    set_audit_context(request, action="edit", entity_type="wiring_diagram", entity_id=row.id, entity_label=row.name, changes={"before":old,"after":{"name":row.name,"project_name":row.project_name,"category":category.name if category else None},"files_added":len(stored),"files_removed":len(removable)})
    flash(request, "Wiring diagram updated."); return _redirect(f"/pricing/wiring-diagrams/{row.id}")


@router.get("/{diagram_id}/preview")
def preview(diagram_id: int, request: Request, user: User = Depends(require_wiring_diagrams_access), db: Session = Depends(get_db)):
    row=_diagram(db,diagram_id); payload=preview_pdf(row.files); set_audit_context(request,action="preview",entity_type="wiring_diagram",entity_id=row.id,entity_label=row.name)
    return Response(payload,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{clean_filename(row.name)}.pdf"'})


@router.get("/{diagram_id}/files/{file_id}/preview")
def file_preview(diagram_id:int,file_id:int,request:Request,user:User=Depends(require_wiring_diagrams_access),db:Session=Depends(get_db)):
    row=_diagram(db,diagram_id); entry=next((item for item in row.files if item.id==file_id),None)
    if not entry: raise HTTPException(404)
    set_audit_context(request,action="preview",entity_type="wiring_diagram_file",entity_id=entry.id,entity_label=entry.original_filename)
    return FileResponse(resolve_wiring_file(entry.storage_key),media_type=entry.content_type,headers={"Content-Disposition":f'inline; filename="{clean_filename(entry.original_filename)}"'})


@router.get("/{diagram_id}/files/{file_id}/download")
def file_download(diagram_id:int,file_id:int,request:Request,user:User=Depends(require_wiring_diagrams_access),db:Session=Depends(get_db)):
    row=_diagram(db,diagram_id); entry=next((item for item in row.files if item.id==file_id),None)
    if not entry: raise HTTPException(404)
    set_audit_context(request,action="download",entity_type="wiring_diagram_file",entity_id=entry.id,entity_label=entry.original_filename)
    return FileResponse(resolve_wiring_file(entry.storage_key),media_type=entry.content_type,filename=entry.original_filename)


@router.get("/{diagram_id}/download.zip")
def download_zip(diagram_id:int,request:Request,user:User=Depends(require_wiring_diagrams_access),db:Session=Depends(get_db)):
    row=_diagram(db,diagram_id); payload=files_zip(row.name,row.files); set_audit_context(request,action="download_package",entity_type="wiring_diagram",entity_id=row.id,entity_label=row.name)
    return Response(payload,media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="{clean_filename(row.name)}-files.zip"'})


@router.post("/{diagram_id}/delete", dependencies=[Depends(require_wiring_diagrams_manager)])
def delete(diagram_id:int,request:Request,csrf_token:str=Form(""),admin:User=Depends(require_wiring_diagrams_manager),db:Session=Depends(get_db)):
    row=_diagram(db,diagram_id)
    if not csrf_valid(request,csrf_token): return _redirect(f"/pricing/wiring-diagrams/{diagram_id}")
    keys=[entry.storage_key for entry in row.files]; label=row.name; db.delete(row); db.commit(); delete_wiring_files(*keys)
    set_audit_context(request,action="delete",entity_type="wiring_diagram",entity_id=diagram_id,entity_label=label,changes={"files":len(keys)})
    flash(request,"Wiring diagram deleted."); return _redirect("/pricing/wiring-diagrams")
