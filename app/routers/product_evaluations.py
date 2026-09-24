"""Product Evaluations and Testing requests, tasks, evidence, and reports."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import UploadFile

from ..audit import set_audit_context
from ..access_control import module_scope, require_permission
from ..database import get_db
from ..deps import require_product_evaluations_access
from ..helpers import flash, render, to_display, to_utc_from_display
from ..models import (AccessScope, ProductEvaluationCounter, ProductEvaluationDecision, ProductEvaluationRequest, ProductEvaluationRequestAttachment, ProductEvaluationSession, ProductEvaluationSessionAttachment, ProductEvaluationSessionStatus, ProductEvaluationStatus, User, UserDepartment, UserRole, utcnow)
from ..product_evaluations import delete_evaluation_files, elapsed_label, evaluation_report, resolve_evaluation_file, store_evaluation_file
from ..purchase_documents import PurchaseDocumentError, clean_filename
from ..security import csrf_valid

router = APIRouter(prefix="/product-evaluations", dependencies=[Depends(require_product_evaluations_access)])


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path,status_code=303)


def _load(db: Session, request_id: int) -> ProductEvaluationRequest:
    row=db.scalar(select(ProductEvaluationRequest).options(selectinload(ProductEvaluationRequest.attachments),selectinload(ProductEvaluationRequest.sessions).selectinload(ProductEvaluationSession.attachments)).where(ProductEvaluationRequest.id==request_id))
    if not row: raise HTTPException(404,"Product evaluation request not found.")
    return row


def _session(db:Session,session_id:int)->ProductEvaluationSession:
    row=db.scalar(select(ProductEvaluationSession).join(ProductEvaluationRequest).options(selectinload(ProductEvaluationSession.attachments),selectinload(ProductEvaluationSession.evaluation_request)).where(ProductEvaluationSession.id==session_id,ProductEvaluationRequest.department_id==db.info.get("department_id")))
    if not row: raise HTTPException(404,"Evaluation session not found.")
    return row


def _active_users(db:Session):
    return list(db.scalars(select(User).join(UserDepartment, UserDepartment.user_id == User.id).where(UserDepartment.department_id == db.info.get("department_id"), User.is_active.is_(True)).order_by(User.full_name)))


def _active_workers(db:Session):
    return list(db.scalars(select(User).join(UserDepartment, UserDepartment.user_id == User.id).where(UserDepartment.department_id == db.info.get("department_id"),User.is_active.is_(True),User.role!=UserRole.CUSTOMER).order_by(User.full_name)))


def _admins(db:Session):
    return list(db.scalars(select(User).where(User.is_active.is_(True),User.role==UserRole.ADMIN).order_by(User.full_name)))


def _contact(db:Session,user_raw:str,external:str,label:str):
    user=None
    if user_raw.strip().isdigit(): user=db.get(User,int(user_raw))
    is_member = user and db.scalar(select(UserDepartment.user_id).where(UserDepartment.user_id == user.id, UserDepartment.department_id == db.info.get("department_id")))
    if user and user.is_active and is_member: return user.id,user.full_name
    if external.strip(): return None,external.strip()
    raise PurchaseDocumentError(f"Choose or enter the {label}.")


def _dt(raw:str)->datetime|None:
    if not raw.strip(): return None
    try: return to_utc_from_display(datetime.fromisoformat(raw.strip()))
    except ValueError: raise PurchaseDocumentError("Enter a valid schedule date and time.")


async def _store_uploads(entries:list[UploadFile],limit:int=20):
    actual=[entry for entry in entries if entry.filename]
    if len(actual)>limit: raise PurchaseDocumentError(f"Upload no more than {limit} files at once.")
    stored=[]
    try:
        for entry in actual: stored.append(store_evaluation_file(entry.filename or "evidence",await entry.read()))
    except Exception:
        delete_evaluation_files(*(item.storage_key for item in stored)); raise
    return stored


def _next_number(db:Session)->str:
    year=to_display(utcnow()).year
    counter=db.get(ProductEvaluationCounter,year,with_for_update=True)
    if not counter:
        counter=ProductEvaluationCounter(year=year,last_sequence=0); db.add(counter); db.flush()
    counter.last_sequence+=1
    return f"PE-{year}-{counter.last_sequence:05d}"


@router.get("")
def list_requests(request:Request,q:str="",status_filter:str="",view:str="my",from_at:str="",to_at:str="",user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    statement=select(ProductEvaluationRequest).options(selectinload(ProductEvaluationRequest.sessions)).order_by(ProductEvaluationRequest.created_at.desc())
    if view=="assigned": statement=statement.join(ProductEvaluationSession).where(ProductEvaluationSession.assigned_user_id==user.id).distinct()
    elif view=="approvals": statement=statement.where(ProductEvaluationRequest.assigned_admin_id==user.id,ProductEvaluationRequest.status==ProductEvaluationStatus.PENDING_APPROVAL)
    elif view=="all" and (user.is_admin or module_scope(user,"product_evaluations")==AccessScope.DEPARTMENT): pass
    else: statement=statement.where(ProductEvaluationRequest.created_by_id==user.id)
    if q.strip():
        term=f"%{q.strip()}%"; statement=statement.where(or_(ProductEvaluationRequest.request_number.ilike(term),ProductEvaluationRequest.device_name.ilike(term),ProductEvaluationRequest.manufacturer.ilike(term),ProductEvaluationRequest.model.ilike(term),ProductEvaluationRequest.serial_number.ilike(term),ProductEvaluationRequest.customer_project_name.ilike(term),ProductEvaluationRequest.created_by_name.ilike(term)))
    if status_filter:
        try: statement=statement.where(ProductEvaluationRequest.status==ProductEvaluationStatus(status_filter))
        except ValueError: pass
    try:
        if from_at: statement=statement.where(ProductEvaluationRequest.created_at>=_dt(from_at))
        if to_at: statement=statement.where(ProductEvaluationRequest.created_at<=_dt(to_at))
    except PurchaseDocumentError: pass
    rows=list(db.scalars(statement))
    return render(request,"product_evaluations.html",{"active_nav":"product_evaluations","rows":rows,"q":q,"status_filter":status_filter,"view":view,"from_at":from_at,"to_at":to_at,"statuses":list(ProductEvaluationStatus)})


@router.get("/new")
def new(request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.create")
    return render(request,"product_evaluation_form.html",{"active_nav":"product_evaluations","evaluation":None,"users":_active_users(db),"admins":_admins(db)})


@router.get("/{request_id}/edit")
def edit_request(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.create")
    row=_load(db,request_id)
    if not (user.is_admin or user.id==row.created_by_id): raise HTTPException(403,"Only the requester or an Administrator can edit this request")
    if row.status not in {ProductEvaluationStatus.PENDING_APPROVAL,ProductEvaluationStatus.CHANGES_REQUESTED}: flash(request,"This request can no longer be edited.","error"); return _redirect(f"/product-evaluations/{row.id}")
    return render(request,"product_evaluation_form.html",{"active_nav":"product_evaluations","evaluation":row,"users":_active_users(db),"admins":_admins(db)})


@router.post("")
async def create(request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.create")
    form=await request.form()
    if not csrf_valid(request,str(form.get("csrf_token") or "")): return _redirect("/product-evaluations/new")
    stored=[]
    try:
        device=str(form.get("device_name") or "").strip(); model=str(form.get("model") or "").strip(); customer=str(form.get("customer_project_name") or "").strip(); reason=str(form.get("reason") or "").strip()
        if not all((device,model,customer,reason)): raise PurchaseDocumentError("Complete the required device, project, and request fields.")
        admin=db.get(User,int(str(form.get("assigned_admin_id") or "0"))) if str(form.get("assigned_admin_id") or "").isdigit() else None
        if not admin or not admin.is_active or not admin.is_admin: raise PurchaseDocumentError("Choose an active Administrator.")
        sales_id,sales_name=_contact(db,str(form.get("sales_user_id") or ""),str(form.get("sales_external") or ""),"Sales Representative")
        after_id,after_name=_contact(db,str(form.get("after_sales_user_id") or ""),str(form.get("after_sales_external") or ""),"After Sales contact")
        stored=await _store_uploads([entry for entry in form.getlist("files") if isinstance(entry,UploadFile)])
        row=ProductEvaluationRequest(request_number=_next_number(db),device_name=device,manufacturer=str(form.get("manufacturer") or "").strip() or None,model=model,customer_project_name=customer,sales_contact_user_id=sales_id,sales_contact_name=sales_name,after_sales_user_id=after_id,after_sales_name=after_name,assigned_admin_id=admin.id,assigned_admin_name=admin.full_name,reason=reason,requirements=str(form.get("requirements") or "").strip() or None,status=ProductEvaluationStatus.PENDING_APPROVAL,created_by_id=user.id,created_by_name=user.full_name)
        row.attachments=[ProductEvaluationRequestAttachment(storage_key=item.storage_key,original_filename=item.original_filename,content_type=item.content_type,file_size=item.file_size,position=index) for index,item in enumerate(stored,1)]
        db.add(row); db.commit(); db.refresh(row)
    except (PurchaseDocumentError,ValueError) as exc:
        db.rollback(); delete_evaluation_files(*(item.storage_key for item in stored)); flash(request,str(exc),"error"); return _redirect("/product-evaluations/new")
    except Exception:
        db.rollback(); delete_evaluation_files(*(item.storage_key for item in stored)); raise
    set_audit_context(request,action="create",entity_type="product_evaluation",entity_id=row.id,entity_label=row.request_number,changes={"device":row.device_name,"model":row.model,"project":row.customer_project_name,"assigned_admin":row.assigned_admin_name})
    flash(request,"Product evaluation request submitted."); return _redirect(f"/product-evaluations/{row.id}")


@router.post("/{request_id}/edit")
async def save_request(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.create")
    row=_load(db,request_id); form=await request.form(); path=f"/product-evaluations/{request_id}/edit"
    if not csrf_valid(request,str(form.get("csrf_token") or "")): return _redirect(path)
    if not (user.is_admin or user.id==row.created_by_id): raise HTTPException(403,"Only the requester or an Administrator can edit this request")
    if row.status not in {ProductEvaluationStatus.PENDING_APPROVAL,ProductEvaluationStatus.CHANGES_REQUESTED}: flash(request,"This request can no longer be edited.","error"); return _redirect(f"/product-evaluations/{row.id}")
    stored=[]
    try:
        device=str(form.get("device_name") or "").strip(); model=str(form.get("model") or "").strip(); customer=str(form.get("customer_project_name") or "").strip(); reason=str(form.get("reason") or "").strip()
        if not all((device,model,customer,reason)): raise PurchaseDocumentError("Complete the required device, project, and request fields.")
        admin=db.get(User,int(str(form.get("assigned_admin_id") or "0"))) if str(form.get("assigned_admin_id") or "").isdigit() else None
        if not admin or not admin.is_active or not admin.is_admin: raise PurchaseDocumentError("Choose an active Administrator.")
        sales_id,sales_name=_contact(db,str(form.get("sales_user_id") or ""),str(form.get("sales_external") or ""),"Sales Representative")
        after_id,after_name=_contact(db,str(form.get("after_sales_user_id") or ""),str(form.get("after_sales_external") or ""),"After Sales contact")
        stored=await _store_uploads([entry for entry in form.getlist("files") if isinstance(entry,UploadFile)])
    except PurchaseDocumentError as exc: delete_evaluation_files(*(item.storage_key for item in stored)); flash(request,str(exc),"error"); return _redirect(path)
    before={"device":row.device_name,"model":row.model,"project":row.customer_project_name,"admin":row.assigned_admin_name,"status":row.status.value}
    row.device_name=device; row.manufacturer=str(form.get("manufacturer") or "").strip() or None; row.model=model; row.customer_project_name=customer; row.sales_contact_user_id=sales_id; row.sales_contact_name=sales_name; row.after_sales_user_id=after_id; row.after_sales_name=after_name; row.assigned_admin_id=admin.id; row.assigned_admin_name=admin.full_name; row.reason=reason; row.requirements=str(form.get("requirements") or "").strip() or None; row.status=ProductEvaluationStatus.PENDING_APPROVAL
    start=len(row.attachments)+1
    for offset,item in enumerate(stored): db.add(ProductEvaluationRequestAttachment(request_id=row.id,storage_key=item.storage_key,original_filename=item.original_filename,content_type=item.content_type,file_size=item.file_size,position=start+offset))
    try: db.commit()
    except Exception: db.rollback(); delete_evaluation_files(*(item.storage_key for item in stored)); raise
    set_audit_context(request,action="resubmit",entity_type="product_evaluation",entity_id=row.id,entity_label=row.request_number,changes={"before":before,"after":{"device":row.device_name,"model":row.model,"project":row.customer_project_name,"admin":row.assigned_admin_name,"status":row.status.value},"files_added":len(stored)})
    flash(request,"Product evaluation request updated and resubmitted."); return _redirect(f"/product-evaluations/{row.id}")


@router.get("/{request_id}")
def detail(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    row=_load(db,request_id)
    return render(request,"product_evaluation_detail.html",{"active_nav":"product_evaluations","evaluation":row,"workers":_active_workers(db),"elapsed_label":elapsed_label})


@router.post("/{request_id}/decision")
async def decision(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.approve")
    row=_load(db,request_id); form=await request.form()
    if not csrf_valid(request,str(form.get("csrf_token") or "")): return _redirect(f"/product-evaluations/{request_id}")
    if row.status not in {ProductEvaluationStatus.PENDING_APPROVAL,ProductEvaluationStatus.CHANGES_REQUESTED}: flash(request,"This request is no longer awaiting an approval decision.","error"); return _redirect(f"/product-evaluations/{request_id}")
    action=str(form.get("action") or ""); notes=str(form.get("admin_notes") or "").strip() or None
    if action=="approve": row.status=ProductEvaluationStatus.WAITING_FOR_DEVICE; row.approved_at=utcnow(); row.approved_by_id=user.id; row.approved_by_name=user.full_name
    elif action=="reject":
        if not notes: flash(request,"Enter the rejection reason.","error"); return _redirect(f"/product-evaluations/{request_id}")
        row.status=ProductEvaluationStatus.REJECTED
    elif action=="changes":
        if not notes: flash(request,"Explain the required changes.","error"); return _redirect(f"/product-evaluations/{request_id}")
        row.status=ProductEvaluationStatus.CHANGES_REQUESTED
    else: raise HTTPException(400,"Invalid decision")
    row.admin_notes=notes; db.commit(); set_audit_context(request,action=action,entity_type="product_evaluation",entity_id=row.id,entity_label=row.request_number,changes={"status":row.status.value,"notes":notes})
    flash(request,"Admin decision saved."); return _redirect(f"/product-evaluations/{request_id}")


@router.post("/{request_id}/receive")
async def receive(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.approve")
    row=_load(db,request_id); form=await request.form()
    if not csrf_valid(request,str(form.get("csrf_token") or "")): return _redirect(f"/product-evaluations/{request_id}")
    if not (user.is_admin or user.id==row.created_by_id): raise HTTPException(403,"Only the requester or an Administrator can confirm receipt")
    if row.status!=ProductEvaluationStatus.WAITING_FOR_DEVICE: flash(request,"The approved request must be waiting for the device.","error"); return _redirect(f"/product-evaluations/{request_id}")
    serial=str(form.get("serial_number") or "").strip()
    if not serial: flash(request,"Serial Number is required when the device is received.","error"); return _redirect(f"/product-evaluations/{request_id}")
    duplicate=db.scalar(select(ProductEvaluationRequest).where(ProductEvaluationRequest.id!=row.id,func.lower(ProductEvaluationRequest.serial_number)==serial.lower()))
    if duplicate: flash(request,f"Serial Number already belongs to {duplicate.request_number}.","error"); return _redirect(f"/product-evaluations/{request_id}")
    row.serial_number=serial; row.received_at=utcnow(); row.received_by_id=user.id; row.received_by_name=user.full_name; row.status=ProductEvaluationStatus.DEVICE_RECEIVED; db.commit()
    set_audit_context(request,action="device_received",entity_type="product_evaluation",entity_id=row.id,entity_label=row.request_number,changes={"serial_number":serial,"received_by":user.full_name})
    flash(request,"Device receipt recorded."); return _redirect(f"/product-evaluations/{request_id}")


@router.post("/{request_id}/sessions")
async def schedule(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.assign")
    row=_load(db,request_id); form=await request.form()
    if not csrf_valid(request,str(form.get("csrf_token") or "")): return _redirect(f"/product-evaluations/{request_id}")
    if not row.received_at: flash(request,"Confirm that the device was received before scheduling a test.","error"); return _redirect(f"/product-evaluations/{request_id}")
    worker=db.get(User,int(str(form.get("assigned_user_id") or "0"))) if str(form.get("assigned_user_id") or "").isdigit() else None
    worker_membership = worker and db.scalar(select(UserDepartment.user_id).where(UserDepartment.user_id == worker.id, UserDepartment.department_id == db.info.get("department_id")))
    if not worker or not worker.is_active or worker.is_customer or not worker_membership: flash(request,"Choose an active internal user in this Department.","error"); return _redirect(f"/product-evaluations/{request_id}")
    try:
        start=_dt(str(form.get("scheduled_start_at") or "")); due=_dt(str(form.get("due_at") or ""))
        if start and due and due<start: raise PurchaseDocumentError("The expected completion must be after the scheduled start.")
    except PurchaseDocumentError as exc: flash(request,str(exc),"error"); return _redirect(f"/product-evaluations/{request_id}")
    sequence=max((session.sequence for session in row.sessions),default=0)+1
    session=ProductEvaluationSession(evaluation_request=row,sequence=sequence,assigned_user_id=worker.id,assigned_user_name=worker.full_name,assigned_by_id=user.id,assigned_by_name=user.full_name,scheduled_start_at=start,due_at=due,location=str(form.get("location") or "").strip() or None,instructions=str(form.get("instructions") or "").strip() or None,status=ProductEvaluationSessionStatus.SCHEDULED)
    db.add(session); row.status=ProductEvaluationStatus.EVALUATION_SCHEDULED; db.commit(); db.refresh(session)
    set_audit_context(request,action="assign",entity_type="product_evaluation_session",entity_id=session.id,entity_label=f"{row.request_number} / {sequence}",changes={"assigned_user":worker.full_name,"scheduled_start":start,"due":due})
    flash(request,"Evaluation task scheduled."); return _redirect(f"/product-evaluations/sessions/{session.id}")


@router.get("/sessions/{session_id}")
def session_detail(session_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    row=_session(db,session_id)
    return render(request,"product_evaluation_session.html",{"active_nav":"product_evaluations","session":row,"evaluation":row.evaluation_request,"decisions":list(ProductEvaluationDecision),"elapsed_label":elapsed_label})


@router.post("/sessions/{session_id}/start")
async def start_session(session_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.execute")
    row=_session(db,session_id); form=await request.form()
    if not csrf_valid(request,str(form.get("csrf_token") or "")): return _redirect(f"/product-evaluations/sessions/{session_id}")
    if not (user.is_admin or user.id==row.assigned_user_id): raise HTTPException(403,"This task is assigned to another user")
    if row.status!=ProductEvaluationSessionStatus.SCHEDULED: flash(request,"This evaluation has already started.","error"); return _redirect(f"/product-evaluations/sessions/{session_id}")
    row.started_at=utcnow(); row.status=ProductEvaluationSessionStatus.IN_PROGRESS; row.evaluation_request.status=ProductEvaluationStatus.EVALUATION_IN_PROGRESS; db.commit()
    set_audit_context(request,action="start",entity_type="product_evaluation_session",entity_id=row.id,entity_label=f"{row.evaluation_request.request_number} / {row.sequence}")
    flash(request,"Evaluation timer started."); return _redirect(f"/product-evaluations/sessions/{session_id}")


def _rating(form,name):
    raw=str(form.get(name) or "").strip()
    if not raw: return None
    try: value=int(raw)
    except ValueError: raise PurchaseDocumentError("Ratings must be between 1 and 5.")
    if value not in range(1,6): raise PurchaseDocumentError("Ratings must be between 1 and 5.")
    return value


@router.post("/sessions/{session_id}/save")
async def save_session(session_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"product_evaluations.execute")
    row=_session(db,session_id); form=await request.form(); path=f"/product-evaluations/sessions/{session_id}"
    if not csrf_valid(request,str(form.get("csrf_token") or "")): return _redirect(path)
    if not (user.is_admin or user.id==row.assigned_user_id): raise HTTPException(403,"This task is assigned to another user")
    if row.status==ProductEvaluationSessionStatus.SCHEDULED: flash(request,"Start the evaluation before entering results.","error"); return _redirect(path)
    was_completed = row.status == ProductEvaluationSessionStatus.COMPLETED
    action=str(form.get("action") or "save"); stored=[]
    removed_files: list[str] = []
    before = {
        "tests_performed": row.tests_performed,
        "results": row.results,
        "strengths": row.strengths,
        "weaknesses": row.weaknesses,
        "issues_found": row.issues_found,
        "compatibility": row.compatibility,
        "recommendation": row.recommendation,
        "decision": row.decision.value if row.decision else None,
        "ratings": {
            name: getattr(row, name)
            for name in ("performance_rating", "quality_rating", "installation_rating", "compatibility_rating", "value_rating")
        },
    }
    try:
        decision_value=str(form.get("decision") or "").strip(); decision=ProductEvaluationDecision(decision_value) if decision_value else None
        ratings={name:_rating(form,name) for name in ("performance_rating","quality_rating","installation_rating","compatibility_rating","value_rating")}
        tests=str(form.get("tests_performed") or "").strip() or None; results=str(form.get("results") or "").strip() or None; recommendation=str(form.get("recommendation") or "").strip() or None
        if (action=="complete" or was_completed) and (not tests or not results or not recommendation or not decision or any(value is None for value in ratings.values())): raise PurchaseDocumentError("Complete the tests, results, recommendation, final decision, and all five ratings.")
        stored=await _store_uploads([entry for entry in form.getlist("files") if isinstance(entry,UploadFile)])
    except (PurchaseDocumentError,ValueError) as exc: delete_evaluation_files(*(item.storage_key for item in stored)); flash(request,str(exc),"error"); return _redirect(path)
    row.tests_performed=tests; row.results=results; row.strengths=str(form.get("strengths") or "").strip() or None; row.weaknesses=str(form.get("weaknesses") or "").strip() or None; row.issues_found=str(form.get("issues_found") or "").strip() or None; row.compatibility=str(form.get("compatibility") or "").strip() or None; row.recommendation=recommendation; row.decision=decision
    for name,value in ratings.items(): setattr(row,name,value)
    remove_ids = {
        int(raw) for raw in form.getlist("remove_attachment_ids")
        if str(raw).isdigit()
    }
    for attachment in list(row.attachments):
        if attachment.id in remove_ids:
            removed_files.append(attachment.storage_key)
            db.delete(attachment)
            continue
        attachment.description=str(form.get(f"description_{attachment.id}") or "").strip() or None
    description=str(form.get("new_file_description") or "").strip() or None
    start=max((attachment.position for attachment in row.attachments),default=0)+1
    for offset,item in enumerate(stored): db.add(ProductEvaluationSessionAttachment(session_id=row.id,storage_key=item.storage_key,original_filename=item.original_filename,content_type=item.content_type,file_size=item.file_size,description=description,position=start+offset))
    if action=="complete" and not was_completed: row.status=ProductEvaluationSessionStatus.COMPLETED; row.completed_at=utcnow(); row.evaluation_request.status=ProductEvaluationStatus.EVALUATION_COMPLETED
    try: db.commit()
    except Exception: db.rollback(); delete_evaluation_files(*(item.storage_key for item in stored)); raise
    delete_evaluation_files(*removed_files)
    after = {
        "tests_performed": row.tests_performed,
        "results": row.results,
        "strengths": row.strengths,
        "weaknesses": row.weaknesses,
        "issues_found": row.issues_found,
        "compatibility": row.compatibility,
        "recommendation": row.recommendation,
        "decision": row.decision.value if row.decision else None,
        "ratings": {name: getattr(row, name) for name in ratings},
    }
    audit_action = "edit_completed" if was_completed else "complete" if action=="complete" else "save_progress"
    set_audit_context(request,action=audit_action,entity_type="product_evaluation_session",entity_id=row.id,entity_label=f"{row.evaluation_request.request_number} / {row.sequence}",changes={"before":before,"after":after,"files_added":len(stored),"files_removed":len(removed_files)})
    message = "Completed evaluation updated." if was_completed else "Evaluation completed." if action=="complete" else "Evaluation progress saved."
    flash(request,message); return _redirect(path)


@router.get("/files/{kind}/{file_id}/preview")
def preview_file(kind:str,file_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    row=db.scalar(select(ProductEvaluationRequestAttachment).join(ProductEvaluationRequest).where(ProductEvaluationRequestAttachment.id==file_id,ProductEvaluationRequest.department_id==db.info.get("department_id"))) if kind=="request" else db.scalar(select(ProductEvaluationSessionAttachment).join(ProductEvaluationSession).join(ProductEvaluationRequest).where(ProductEvaluationSessionAttachment.id==file_id,ProductEvaluationRequest.department_id==db.info.get("department_id"))) if kind=="session" else None
    if not row: raise HTTPException(404)
    set_audit_context(request,action="preview",entity_type="product_evaluation_file",entity_id=row.id,entity_label=row.original_filename)
    return FileResponse(resolve_evaluation_file(row.storage_key),media_type=row.content_type,headers={"Content-Disposition":f'inline; filename="{clean_filename(row.original_filename)}"'})


@router.get("/files/{kind}/{file_id}/download")
def download_file(kind:str,file_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    row=db.scalar(select(ProductEvaluationRequestAttachment).join(ProductEvaluationRequest).where(ProductEvaluationRequestAttachment.id==file_id,ProductEvaluationRequest.department_id==db.info.get("department_id"))) if kind=="request" else db.scalar(select(ProductEvaluationSessionAttachment).join(ProductEvaluationSession).join(ProductEvaluationRequest).where(ProductEvaluationSessionAttachment.id==file_id,ProductEvaluationRequest.department_id==db.info.get("department_id"))) if kind=="session" else None
    if not row: raise HTTPException(404)
    set_audit_context(request,action="download",entity_type="product_evaluation_file",entity_id=row.id,entity_label=row.original_filename)
    return FileResponse(resolve_evaluation_file(row.storage_key),media_type=row.content_type,filename=row.original_filename)


@router.get("/{request_id}/report.pdf")
def full_report(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    row=_load(db,request_id); payload=evaluation_report(row); set_audit_context(request,action="download_report",entity_type="product_evaluation",entity_id=row.id,entity_label=row.request_number)
    return Response(payload,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{row.request_number}-full-report.pdf"'})


@router.get("/sessions/{session_id}/report.pdf")
def session_report(session_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    session=_session(db,session_id); payload=evaluation_report(session.evaluation_request,[session]); set_audit_context(request,action="download_report",entity_type="product_evaluation_session",entity_id=session.id,entity_label=f"{session.evaluation_request.request_number} / {session.sequence}")
    return Response(payload,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="{session.evaluation_request.request_number}-evaluation-{session.sequence}.pdf"'})


@router.get("/{request_id}/add-to-pricing")
def add_to_pricing(request_id:int,request:Request,user:User=Depends(require_product_evaluations_access),db:Session=Depends(get_db)):
    require_permission(request,db,user,"pricing_items.manage")
    row=_load(db,request_id)
    if not any(session.status==ProductEvaluationSessionStatus.COMPLETED and session.decision in {ProductEvaluationDecision.APPROVED,ProductEvaluationDecision.APPROVED_WITH_CONDITIONS} for session in row.sessions): flash(request,"Complete and approve an evaluation before copying it to Pricing.","error"); return _redirect(f"/product-evaluations/{request_id}")
    set_audit_context(request,action="copy_to_pricing_form",entity_type="product_evaluation",entity_id=row.id,entity_label=row.request_number)
    return _redirect("/pricing/items?"+urlencode({"prefill_name":row.device_name,"prefill_model":row.model,"source":"product_evaluation"}))
