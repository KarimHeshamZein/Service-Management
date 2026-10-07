"""Independent warehouse stock, transfers, technician custody and reports."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..audit import set_audit_context
from ..access_control import permission_allowed, require_permission
from ..config import settings
from ..database import get_db
from ..deps import require_store_access
from ..helpers import entity_id, flash, render
from ..models import (
    StoreCustodyBalance, StoreItem, StoreMovement, StoreMovementLine,
    StoreMovementType, StoreStockBalance, StoreUserWarehouse, StoreWarehouse,
    StoreWarehouseType, User, UserRole, utcnow,
    UserDepartment,
)
from ..pdf_text import pdf_text, style_for_pdf_text
from ..security import csrf_valid

router = APIRouter(prefix="/store", dependencies=[Depends(require_store_access)])
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)


def _guard(request: Request, token: str, path: str):
    if csrf_valid(request, token):
        return None
    flash(request, "Your form expired. Refresh the page and try again.", "error")
    return _redirect(path)


def _allowed_warehouse_ids(db: Session, user: User) -> set[int]:
    if user.is_admin:
        return set(db.scalars(select(StoreWarehouse.id)))
    return set(db.scalars(select(StoreUserWarehouse.warehouse_id).where(StoreUserWarehouse.user_id == user.id)))


STORE_PERMISSION_KEYS = {
    "store_access": "store.view",
    "store_receive": "store.receive",
    "store_issue": "store.issue",
    "store_transfer": "store.transfer",
    "store_custody_transfer": "store.custody",
    "store_manage_items": "store.manage",
    "store_manage_warehouses": "store.manage",
    "store_adjust": "store.manage",
    "store_reports": "store.reports",
}


def _perm(request: Request, db: Session, user: User, name: str) -> bool:
    department_id = db.info.get("department_id")
    return bool(department_id) and permission_allowed(
        db, user, department_id, STORE_PERMISSION_KEYS.get(name, name)
    )


def _require(request: Request, db: Session, user: User, name: str) -> None:
    require_permission(request, db, user, STORE_PERMISSION_KEYS.get(name, name))


def _warehouse(db: Session, user: User, warehouse_id: int | None) -> StoreWarehouse | None:
    if warehouse_id is None:
        return None
    warehouse = db.get(StoreWarehouse, warehouse_id)
    if warehouse is None or warehouse.id not in _allowed_warehouse_ids(db, user):
        raise HTTPException(403, "Warehouse access required.")
    return warehouse


def _number(db: Session) -> str:
    year = utcnow().year
    last = db.scalar(select(func.max(StoreMovement.id))) or 0
    return f"ST-{year}-{last + 1:06d}"


def _decimal(value: str) -> Decimal | None:
    try:
        parsed = Decimal(value.strip())
    except (InvalidOperation, AttributeError):
        return None
    return parsed.quantize(Decimal("0.01")) if parsed > 0 else None


def _stock(db: Session, warehouse_id: int, item_id: int) -> StoreStockBalance:
    row = db.scalar(select(StoreStockBalance).where(
        StoreStockBalance.warehouse_id == warehouse_id,
        StoreStockBalance.item_id == item_id,
    ).with_for_update())
    if row is None:
        row = StoreStockBalance(warehouse_id=warehouse_id, item_id=item_id, quantity=Decimal("0"))
        db.add(row)
        db.flush()
    return row


def _custody(db: Session, technician_id: int, item_id: int) -> StoreCustodyBalance:
    row = db.scalar(select(StoreCustodyBalance).where(
        StoreCustodyBalance.technician_id == technician_id,
        StoreCustodyBalance.item_id == item_id,
    ).with_for_update())
    if row is None:
        row = StoreCustodyBalance(technician_id=technician_id, item_id=item_id, quantity=Decimal("0"))
        db.add(row)
        db.flush()
    return row


def _movement_permission(user: User, movement_type: StoreMovementType) -> str:
    return {
        StoreMovementType.OPENING: "store_adjust",
        StoreMovementType.PURCHASE: "store_receive",
        StoreMovementType.PROJECT_ISSUE: "store_issue",
        StoreMovementType.WAREHOUSE_TRANSFER: "store_transfer",
        StoreMovementType.CUSTODY_ISSUE: "store_custody_transfer",
        StoreMovementType.CUSTODY_RETURN: "store_custody_transfer",
        StoreMovementType.CUSTODY_PROJECT_ISSUE: "store_custody_transfer",
        StoreMovementType.ADJUSTMENT: "store_adjust",
        StoreMovementType.REVERSAL: "store_adjust",
    }[movement_type]


def _apply_line(db: Session, movement: StoreMovement, item_id: int, quantity: Decimal, position: int) -> None:
    line = StoreMovementLine(movement_id=movement.id, item_id=item_id, quantity=quantity, position=position)
    kind = movement.movement_type
    if kind in {StoreMovementType.OPENING, StoreMovementType.PURCHASE} or (kind == StoreMovementType.ADJUSTMENT and movement.destination_warehouse_id):
        target = _stock(db, movement.destination_warehouse_id, item_id)
        line.destination_before = target.quantity
        target.quantity += quantity
        line.destination_after = target.quantity
    elif kind == StoreMovementType.PROJECT_ISSUE or (kind == StoreMovementType.ADJUSTMENT and movement.source_warehouse_id):
        source = _stock(db, movement.source_warehouse_id, item_id)
        if source.quantity < quantity:
            raise ValueError("Insufficient warehouse stock.")
        line.source_before = source.quantity
        source.quantity -= quantity
        line.source_after = source.quantity
    elif kind == StoreMovementType.WAREHOUSE_TRANSFER:
        source = _stock(db, movement.source_warehouse_id, item_id)
        target = _stock(db, movement.destination_warehouse_id, item_id)
        if source.quantity < quantity:
            raise ValueError("Insufficient warehouse stock.")
        line.source_before, line.destination_before = source.quantity, target.quantity
        source.quantity -= quantity
        target.quantity += quantity
        line.source_after, line.destination_after = source.quantity, target.quantity
    elif kind == StoreMovementType.CUSTODY_ISSUE:
        source = _stock(db, movement.source_warehouse_id, item_id)
        target = _custody(db, movement.technician_id, item_id)
        if source.quantity < quantity:
            raise ValueError("Insufficient warehouse stock.")
        line.source_before, line.destination_before = source.quantity, target.quantity
        source.quantity -= quantity
        target.quantity += quantity
        line.source_after, line.destination_after = source.quantity, target.quantity
    elif kind == StoreMovementType.CUSTODY_RETURN:
        source = _custody(db, movement.technician_id, item_id)
        target = _stock(db, movement.destination_warehouse_id, item_id)
        if source.quantity < quantity:
            raise ValueError("Insufficient technician custody.")
        line.source_before, line.destination_before = source.quantity, target.quantity
        source.quantity -= quantity
        target.quantity += quantity
        line.source_after, line.destination_after = source.quantity, target.quantity
    elif kind == StoreMovementType.CUSTODY_PROJECT_ISSUE:
        source = _custody(db, movement.technician_id, item_id)
        if source.quantity < quantity:
            raise ValueError("Insufficient technician custody.")
        line.source_before = source.quantity
        source.quantity -= quantity
        line.source_after = source.quantity
    db.add(line)


@router.get("")
def home(request: Request, q: str = "", user: User = Depends(require_store_access), db: Session = Depends(get_db)):
    allowed = _allowed_warehouse_ids(db, user)
    warehouses = list(db.scalars(select(StoreWarehouse).where(StoreWarehouse.id.in_(allowed)).order_by(StoreWarehouse.warehouse_type, StoreWarehouse.name))) if allowed else []
    items_stmt = select(StoreItem).order_by(StoreItem.name)
    if q.strip():
        like = f"%{q.strip()}%"
        items_stmt = items_stmt.where(or_(StoreItem.name.ilike(like), StoreItem.model.ilike(like), StoreItem.serial_number.ilike(like), StoreItem.code.ilike(like)))
    items = list(db.scalars(items_stmt))
    balances = {(r.warehouse_id, r.item_id): r.quantity for r in db.scalars(select(StoreStockBalance).where(StoreStockBalance.warehouse_id.in_(allowed)))} if allowed else {}
    movements = list(db.scalars(select(StoreMovement).where(or_(StoreMovement.source_warehouse_id.in_(allowed), StoreMovement.destination_warehouse_id.in_(allowed), StoreMovement.technician_id == user.id)).order_by(StoreMovement.created_at.desc()).limit(20))) if allowed or user.is_technical else []
    custody = list(db.execute(select(StoreCustodyBalance, StoreItem).join(StoreItem, StoreItem.id == StoreCustodyBalance.item_id).where(StoreCustodyBalance.technician_id == user.id, StoreCustodyBalance.quantity > 0)).all())
    technicians = list(db.scalars(
        select(User)
        .join(UserDepartment, UserDepartment.user_id == User.id)
        .where(
            UserDepartment.department_id == db.info.get("department_id"),
            User.role == UserRole.TECHNICAL,
            User.is_active.is_(True),
        )
        .order_by(User.full_name)
    ))
    reversed_ids = set(db.scalars(select(StoreMovement.reversed_movement_id).where(StoreMovement.reversed_movement_id.is_not(None))))
    return render(request, "store.html", {"active_nav":"store", "warehouses":warehouses, "items":items, "balances":balances, "movements":movements, "reversed_ids":reversed_ids, "custody":custody, "store_technicians":technicians, "q":q.strip(), "can":lambda n: _perm(request,db,user,n)})


@router.post("/warehouses")
def create_warehouse(request: Request, name: str = Form(""), warehouse_type: str = Form("branch"), location: str = Form(""), notes: str = Form(""), csrf_token: str = Form(""), user: User = Depends(require_store_access), db: Session = Depends(get_db)):
    _require(request, db, user, "store_manage_warehouses")
    if (bad := _guard(request, csrf_token, "/store")): return bad
    try: kind = StoreWarehouseType(warehouse_type)
    except ValueError: kind = StoreWarehouseType.BRANCH
    if not name.strip():
        flash(request, "Warehouse name is required.", "error"); return _redirect("/store")
    if kind == StoreWarehouseType.MAIN and db.scalar(select(StoreWarehouse.id).where(StoreWarehouse.warehouse_type == StoreWarehouseType.MAIN)):
        flash(request, "Only one Main warehouse is allowed.", "error"); return _redirect("/store")
    row = StoreWarehouse(name=name.strip(), warehouse_type=kind, location=location.strip() or None, notes=notes.strip() or None)
    db.add(row); db.flush()
    if not user.is_admin:
        db.add(StoreUserWarehouse(user_id=user.id, warehouse_id=row.id))
    db.commit()
    set_audit_context(request, action="create", entity_type="store_warehouse", entity_id=row.id, entity_label=row.name)
    flash(request, "Warehouse created."); return _redirect("/store")


@router.post("/items")
async def create_item(request: Request, name: str = Form(""), model: str = Form(""), serial_number: str = Form(""), code: str = Form(""), unit: str = Form("piece"), minimum_stock: str = Form("0"), notes: str = Form(""), image: UploadFile | None = File(None), csrf_token: str = Form(""), user: User = Depends(require_store_access), db: Session = Depends(get_db)):
    _require(request, db, user, "store_manage_items")
    if (bad := _guard(request, csrf_token, "/store")): return bad
    try: minimum = max(Decimal(minimum_stock or "0"), Decimal("0"))
    except InvalidOperation: minimum = Decimal("0")
    if not name.strip(): flash(request, "Item name is required.", "error"); return _redirect("/store")
    row = StoreItem(name=name.strip(), model=model.strip() or None, serial_number=serial_number.strip() or None, code=code.strip() or None, unit=unit.strip() or "piece", minimum_stock=minimum, notes=notes.strip() or None)
    if image and image.filename:
        ext = IMAGE_TYPES.get((image.content_type or "").lower())
        data = await image.read()
        if not ext or not data or len(data) > 8 * 1024 * 1024:
            flash(request, "Item image must be JPG, PNG or WebP and no larger than 8 MB.", "error"); return _redirect("/store")
        key = f"store-items/{uuid.uuid4().hex}{ext}"
        target = settings.upload_dir / key; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        row.image_storage_key, row.image_original_filename = key, image.filename[:255]
    db.add(row); db.commit()
    set_audit_context(request, action="create", entity_type="store_item", entity_id=row.id, entity_label=row.name)
    flash(request, "Store item created."); return _redirect("/store")


@router.get("/items/{item_id}/image")
def item_image(item_id: int, user: User = Depends(require_store_access), db: Session = Depends(get_db)):
    item = db.get(StoreItem, item_id)
    if not item or not item.image_storage_key: raise HTTPException(404)
    path = (settings.upload_dir / item.image_storage_key).resolve()
    if not path.is_file(): raise HTTPException(404)
    return FileResponse(path)


@router.post("/movements")
async def create_movement(request: Request, movement_type: str = Form(""), source_warehouse_id: str = Form(""), destination_warehouse_id: str = Form(""), technician_id: str = Form(""), project_name: str = Form(""), adjustment_direction: str = Form("increase"), item_ids: list[str] = Form(default=[]), quantities: list[str] = Form(default=[]), reason: str = Form(""), csrf_token: str = Form(""), user: User = Depends(require_store_access), db: Session = Depends(get_db)):
    if (bad := _guard(request, csrf_token, "/store")): return bad
    try: kind = StoreMovementType(movement_type)
    except ValueError: flash(request, "Choose a valid movement type.", "error"); return _redirect("/store")
    _require(request, db, user, _movement_permission(user, kind))
    source_id, destination_id, tech_id = entity_id(source_warehouse_id), entity_id(destination_warehouse_id), entity_id(technician_id)
    if kind == StoreMovementType.ADJUSTMENT:
        if adjustment_direction == "increase": destination_id, source_id = source_id or destination_id, None
        else: source_id, destination_id = source_id or destination_id, None
    if source_id: _warehouse(db, user, source_id)
    if destination_id: _warehouse(db, user, destination_id)
    tech = db.get(User, tech_id) if tech_id else None
    tech_membership = db.get(UserDepartment, (tech_id, db.info.get("department_id"))) if tech_id else None
    if tech_id and (
        not tech
        or tech.role != UserRole.TECHNICAL
        or not tech.is_active
        or tech_membership is None
    ):
        flash(request, "Choose an active Technical user from this Department.", "error")
        return _redirect("/store")
    if kind in {StoreMovementType.PROJECT_ISSUE, StoreMovementType.CUSTODY_PROJECT_ISSUE} and not project_name.strip(): flash(request, "Project name is required.", "error"); return _redirect("/store")
    required = {
        StoreMovementType.OPENING: (destination_id is not None, "Choose a destination warehouse."),
        StoreMovementType.PURCHASE: (destination_id is not None, "Choose a destination warehouse."),
        StoreMovementType.PROJECT_ISSUE: (source_id is not None, "Choose a source warehouse."),
        StoreMovementType.WAREHOUSE_TRANSFER: (source_id is not None and destination_id is not None and source_id != destination_id, "Choose two different source and destination warehouses."),
        StoreMovementType.CUSTODY_ISSUE: (source_id is not None and tech_id is not None, "Choose a source warehouse and technician."),
        StoreMovementType.CUSTODY_RETURN: (destination_id is not None and tech_id is not None, "Choose a destination warehouse and technician."),
        StoreMovementType.CUSTODY_PROJECT_ISSUE: (tech_id is not None, "Choose a technician."),
        StoreMovementType.ADJUSTMENT: ((source_id is not None) != (destination_id is not None), "Choose one warehouse for the adjustment."),
    }.get(kind, (False, "Choose valid movement details."))
    if not required[0]: flash(request, required[1], "error"); return _redirect("/store")
    lines = []
    for raw_id, raw_qty in zip(item_ids, quantities):
        iid, qty = entity_id(raw_id), _decimal(raw_qty)
        if iid and qty and db.get(StoreItem, iid): lines.append((iid, qty))
    if not lines: flash(request, "Add at least one item and a positive quantity.", "error"); return _redirect("/store")
    movement = StoreMovement(movement_number=_number(db), movement_type=kind, source_warehouse_id=source_id, destination_warehouse_id=destination_id, technician_id=tech_id, project_name=project_name.strip() or None, reason=reason.strip() or None, created_by_id=user.id, created_by_name=user.full_name)
    db.add(movement); db.flush()
    try:
        for position, (iid, qty) in enumerate(lines): _apply_line(db, movement, iid, qty, position)
        db.commit()
    except ValueError as exc:
        db.rollback(); flash(request, str(exc), "error"); return _redirect("/store")
    set_audit_context(request, action="post_movement", entity_type="store_movement", entity_id=movement.id, entity_label=movement.movement_number, changes={"type": kind.value, "lines": len(lines)})
    flash(request, f"Movement {movement.movement_number} posted."); return _redirect("/store")


@router.post("/movements/{movement_id}/reverse")
def reverse_movement(movement_id: int, request: Request, reason: str = Form(""), csrf_token: str = Form(""), user: User = Depends(require_store_access), db: Session = Depends(get_db)):
    _require(request, db, user, "store_adjust")
    if (bad := _guard(request, csrf_token, "/store")): return bad
    original = db.get(StoreMovement, movement_id)
    if not original or original.movement_type == StoreMovementType.REVERSAL:
        flash(request, "That movement cannot be reversed.", "error"); return _redirect("/store")
    if db.scalar(select(StoreMovement.id).where(StoreMovement.reversed_movement_id == original.id)):
        flash(request, "That movement was already reversed.", "error"); return _redirect("/store")
    if not reason.strip(): flash(request, "A reversal reason is required.", "error"); return _redirect("/store")
    if original.source_warehouse_id: _warehouse(db,user,original.source_warehouse_id)
    if original.destination_warehouse_id: _warehouse(db,user,original.destination_warehouse_id)
    lines = list(db.scalars(select(StoreMovementLine).where(StoreMovementLine.movement_id == original.id).order_by(StoreMovementLine.position)))
    reversal = StoreMovement(movement_number=_number(db), movement_type=StoreMovementType.REVERSAL, source_warehouse_id=original.destination_warehouse_id, destination_warehouse_id=original.source_warehouse_id, technician_id=original.technician_id, project_name=original.project_name, reason=reason.strip(), reversed_movement_id=original.id, created_by_id=user.id, created_by_name=user.full_name)
    db.add(reversal); db.flush()
    try:
        for position, original_line in enumerate(lines):
            qty=original_line.quantity; line=StoreMovementLine(movement_id=reversal.id,item_id=original_line.item_id,quantity=qty,position=position)
            kind=original.movement_type
            if kind in {StoreMovementType.OPENING,StoreMovementType.PURCHASE} or (kind==StoreMovementType.ADJUSTMENT and original.destination_warehouse_id):
                stock=_stock(db,original.destination_warehouse_id,original_line.item_id)
                if stock.quantity<qty: raise ValueError("The received stock is no longer available to reverse.")
                line.source_before=stock.quantity; stock.quantity-=qty; line.source_after=stock.quantity
            elif kind==StoreMovementType.PROJECT_ISSUE or (kind==StoreMovementType.ADJUSTMENT and original.source_warehouse_id):
                stock=_stock(db,original.source_warehouse_id,original_line.item_id); line.destination_before=stock.quantity; stock.quantity+=qty; line.destination_after=stock.quantity
            elif kind==StoreMovementType.WAREHOUSE_TRANSFER:
                source=_stock(db,original.destination_warehouse_id,original_line.item_id); target=_stock(db,original.source_warehouse_id,original_line.item_id)
                if source.quantity<qty: raise ValueError("The transferred stock is no longer available to reverse.")
                line.source_before,line.destination_before=source.quantity,target.quantity; source.quantity-=qty; target.quantity+=qty; line.source_after,line.destination_after=source.quantity,target.quantity
            elif kind==StoreMovementType.CUSTODY_ISSUE:
                source=_custody(db,original.technician_id,original_line.item_id); target=_stock(db,original.source_warehouse_id,original_line.item_id)
                if source.quantity<qty: raise ValueError("The technician no longer holds enough stock to reverse.")
                line.source_before,line.destination_before=source.quantity,target.quantity; source.quantity-=qty; target.quantity+=qty; line.source_after,line.destination_after=source.quantity,target.quantity
            elif kind==StoreMovementType.CUSTODY_RETURN:
                source=_stock(db,original.destination_warehouse_id,original_line.item_id); target=_custody(db,original.technician_id,original_line.item_id)
                if source.quantity<qty: raise ValueError("The returned stock is no longer available to reverse.")
                line.source_before,line.destination_before=source.quantity,target.quantity; source.quantity-=qty; target.quantity+=qty; line.source_after,line.destination_after=source.quantity,target.quantity
            elif kind==StoreMovementType.CUSTODY_PROJECT_ISSUE:
                target=_custody(db,original.technician_id,original_line.item_id); line.destination_before=target.quantity; target.quantity+=qty; line.destination_after=target.quantity
            db.add(line)
        db.commit()
    except ValueError as exc:
        db.rollback(); flash(request,str(exc),"error"); return _redirect("/store")
    set_audit_context(request,action="reverse",entity_type="store_movement",entity_id=reversal.id,entity_label=reversal.movement_number,changes={"reverses":original.movement_number,"reason":reason.strip()})
    flash(request,f"Movement {original.movement_number} reversed by {reversal.movement_number}."); return _redirect("/store")


@router.get("/reports/export.csv")
def export_report(request: Request, user: User = Depends(require_store_access), db: Session = Depends(get_db)):
    _require(request, db, user, "store_reports")
    allowed = _allowed_warehouse_ids(db, user)
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Warehouse", "Item", "Model", "Serial", "Code", "Quantity", "Unit", "Minimum stock"])
    rows = db.execute(select(StoreWarehouse, StoreItem, StoreStockBalance).join(StoreStockBalance, StoreStockBalance.warehouse_id == StoreWarehouse.id).join(StoreItem, StoreItem.id == StoreStockBalance.item_id).where(StoreWarehouse.id.in_(allowed)).order_by(StoreWarehouse.name, StoreItem.name)).all()
    for warehouse, item, balance in rows: writer.writerow([warehouse.name, item.name, item.model or "", item.serial_number or "", item.code or "", balance.quantity, item.unit, item.minimum_stock])
    set_audit_context(request, action="export", entity_type="store_report", entity_label="Current stock")
    return StreamingResponse(iter([output.getvalue().encode("utf-8-sig")]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="store-stock-{date.today().isoformat()}.csv"'})


REPORT_TYPES = {"current_stock","custody","movements","project_issues","purchases","transfers","low_stock"}


def _report_data(db: Session, user: User, report_type: str, warehouse_id: int | None = None):
    allowed = _allowed_warehouse_ids(db,user)
    if warehouse_id:
        _warehouse(db,user,warehouse_id); allowed &= {warehouse_id}
    if report_type in {"current_stock","low_stock"}:
        headers=["Warehouse","Item","Model","Serial","Code","Quantity","Unit","Minimum stock"]
        rows=[]
        query=db.execute(select(StoreWarehouse,StoreItem,StoreStockBalance).join(StoreStockBalance,StoreStockBalance.warehouse_id==StoreWarehouse.id).join(StoreItem,StoreItem.id==StoreStockBalance.item_id).where(StoreWarehouse.id.in_(allowed)).order_by(StoreWarehouse.name,StoreItem.name)).all()
        for warehouse,item,balance in query:
            if report_type=="low_stock" and balance.quantity>=item.minimum_stock: continue
            rows.append([warehouse.name,item.name,item.model or "",item.serial_number or "",item.code or "",balance.quantity,item.unit,item.minimum_stock])
        return headers,rows
    if report_type=="custody":
        headers=["Technician","Item","Model","Serial","Quantity","Unit"]
        rows=[]
        for balance,item,tech in db.execute(select(StoreCustodyBalance,StoreItem,User).join(StoreItem,StoreItem.id==StoreCustodyBalance.item_id).join(User,User.id==StoreCustodyBalance.technician_id).where(StoreCustodyBalance.quantity>0).order_by(User.full_name,StoreItem.name)).all(): rows.append([tech.full_name,item.name,item.model or "",item.serial_number or "",balance.quantity,item.unit])
        return headers,rows
    headers=["Movement","Date","Type","Item","Quantity","Source","Destination","Technician","Project","Created by"]
    rows=[]
    stmt=select(StoreMovementLine,StoreMovement,StoreItem).join(StoreMovement,StoreMovement.id==StoreMovementLine.movement_id).join(StoreItem,StoreItem.id==StoreMovementLine.item_id).where(or_(StoreMovement.source_warehouse_id.in_(allowed),StoreMovement.destination_warehouse_id.in_(allowed),StoreMovement.technician_id==user.id)).order_by(StoreMovement.created_at.desc(),StoreMovementLine.position)
    movements={"project_issues":{StoreMovementType.PROJECT_ISSUE,StoreMovementType.CUSTODY_PROJECT_ISSUE},"purchases":{StoreMovementType.PURCHASE},"transfers":{StoreMovementType.WAREHOUSE_TRANSFER,StoreMovementType.CUSTODY_ISSUE,StoreMovementType.CUSTODY_RETURN}}
    if report_type in movements: stmt=stmt.where(StoreMovement.movement_type.in_(movements[report_type]))
    for line,movement,item in db.execute(stmt).all():
        source=db.get(StoreWarehouse,movement.source_warehouse_id) if movement.source_warehouse_id else None; destination=db.get(StoreWarehouse,movement.destination_warehouse_id) if movement.destination_warehouse_id else None; tech=db.get(User,movement.technician_id) if movement.technician_id else None
        rows.append([movement.movement_number,movement.created_at.strftime("%Y-%m-%d %H:%M"),movement.movement_type.value.replace("_"," "),item.name,line.quantity,source.name if source else "",destination.name if destination else "",tech.full_name if tech else "",movement.project_name or "",movement.created_by_name])
    return headers,rows


@router.get("/reports")
def reports_page(request:Request,report_type:str="current_stock",warehouse_id:str="",user:User=Depends(require_store_access),db:Session=Depends(get_db)):
    _require(request,db,user,"store_reports"); kind=report_type if report_type in REPORT_TYPES else "current_stock"; wid=entity_id(warehouse_id); headers,rows=_report_data(db,user,kind,wid)
    warehouses=list(db.scalars(select(StoreWarehouse).where(StoreWarehouse.id.in_(_allowed_warehouse_ids(db,user))).order_by(StoreWarehouse.name)))
    return render(request,"store_reports.html",{"active_nav":"store","report_type":kind,"warehouse_id":wid,"report_types":sorted(REPORT_TYPES),"warehouses":warehouses,"headers":headers,"rows":rows})


@router.get("/reports/export.xlsx")
def reports_excel(request:Request,report_type:str="current_stock",warehouse_id:str="",user:User=Depends(require_store_access),db:Session=Depends(get_db)):
    _require(request,db,user,"store_reports"); kind=report_type if report_type in REPORT_TYPES else "current_stock"; headers,rows=_report_data(db,user,kind,entity_id(warehouse_id)); workbook=Workbook(); sheet=workbook.active; sheet.title="Store Report"; sheet.append(headers)
    for row in rows: sheet.append(list(row))
    for cell in sheet[1]: cell.font=cell.font.copy(bold=True)
    output=io.BytesIO(); workbook.save(output); set_audit_context(request,action="export",entity_type="store_report",entity_label=kind,changes={"format":"xlsx","rows":len(rows)})
    return StreamingResponse(iter([output.getvalue()]),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="store-{kind}-{date.today().isoformat()}.xlsx"'})


@router.get("/reports/export.pdf")
def reports_pdf(request:Request,report_type:str="current_stock",warehouse_id:str="",user:User=Depends(require_store_access),db:Session=Depends(get_db)):
    _require(request,db,user,"store_reports"); kind=report_type if report_type in REPORT_TYPES else "current_stock"; headers,rows=_report_data(db,user,kind,entity_id(warehouse_id)); output=io.BytesIO(); style=ParagraphStyle("store",fontName="Helvetica",fontSize=7,leading=9,textColor=colors.HexColor("#17324D")); doc=SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=8*mm,rightMargin=8*mm,topMargin=10*mm,bottomMargin=10*mm,title=f"Store {kind}")
    data=[[Paragraph(pdf_text(value),style_for_pdf_text(value,style)) for value in headers]]+[[Paragraph(pdf_text(value),style_for_pdf_text(value,style)) for value in row] for row in rows]
    table=Table(data,repeatRows=1); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#17324D")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#B7C9D3")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),4)])); doc.build([table]); set_audit_context(request,action="export",entity_type="store_report",entity_label=kind,changes={"format":"pdf","rows":len(rows)})
    return Response(output.getvalue(),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="store-{kind}-{date.today().isoformat()}.pdf"'})
