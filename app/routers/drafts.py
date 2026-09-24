"""Private autosave endpoints for long-running field-service entry forms."""
from __future__ import annotations

import json
import re
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_record_submitter
from ..helpers import flash, fmt_datetime, localized_json, render
from ..models import EntryDraft, User, utcnow
from ..security import csrf_valid


router = APIRouter(prefix="/drafts", tags=["drafts"])

MAX_DRAFT_BYTES = 2 * 1024 * 1024
MAX_DRAFTS_PER_USER = 20
DRAFT_RETENTION_DAYS = 7
_KEY_RE = re.compile(r"^[a-z0-9_:/.-]{1,180}$")


def _valid_key(value: object) -> str:
    key = str(value or "").strip().lower()
    if not _KEY_RE.fullmatch(key):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid draft key")
    return key


def _safe_page_url(value: object) -> str:
    page_url = str(value or "").strip()
    if not page_url.startswith("/") or page_url.startswith("//") or len(page_url) > 500:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid draft page")
    return page_url


def _cleanup(db: Session) -> None:
    db.execute(delete(EntryDraft).where(EntryDraft.expires_at < utcnow()))


@router.get("/keepalive")
def keepalive(
    request: Request,
    user: User = Depends(require_record_submitter),
):
    # Passing through authenticated session middleware refreshes the signed
    # cookie's Max-Age without touching any record or draft.
    request.session["keepalive_at"] = int(time.time())
    return localized_json(request, {"ok": True, "user_id": user.id})


@router.get("")
def drafts_list(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    _cleanup(db)
    drafts = list(
        db.scalars(
            select(EntryDraft)
            .where(EntryDraft.user_id == user.id)
            .order_by(EntryDraft.updated_at.desc(), EntryDraft.id.desc())
        )
    )
    db.commit()
    return render(
        request,
        "entry_drafts.html",
        {
            "drafts": drafts,
            "active_nav": "entry_drafts",
            "fmt_datetime": fmt_datetime,
        },
    )


@router.post("/{draft_id}/delete")
async def delete_draft_from_list(
    draft_id: int,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    form = await request.form()
    if not csrf_valid(request, form.get("csrf_token")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session expired")
    draft = db.scalar(
        select(EntryDraft).where(
            EntryDraft.id == draft_id, EntryDraft.user_id == user.id
        )
    )
    if draft is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Draft not found")
    db.delete(draft)
    db.commit()
    flash(request, "Draft deleted.")
    return RedirectResponse("/drafts", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/current")
def current_draft(
    draft_key: str,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    key = _valid_key(draft_key)
    _cleanup(db)
    draft = db.scalar(
        select(EntryDraft).where(
            EntryDraft.user_id == user.id, EntryDraft.draft_key == key
        )
    )
    db.commit()
    if draft is None:
        return localized_json(
            request, {"ok": True, "draft": None, "user_id": user.id}
        )
    return localized_json(
        request,
        {
            "ok": True,
            "user_id": user.id,
            "draft": {
                "payload": draft.payload,
                "page_url": draft.page_url,
                "updated_at": draft.updated_at.isoformat(),
            },
        },
    )


@router.post("/autosave")
async def autosave(
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid draft data") from exc
    if not isinstance(body, dict) or not csrf_valid(request, body.get("csrf_token")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session expired")
    key = _valid_key(body.get("draft_key"))
    page_url = _safe_page_url(body.get("page_url"))
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid draft data")
    if len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) > MAX_DRAFT_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Draft is too large")

    _cleanup(db)
    draft = db.scalar(
        select(EntryDraft).where(
            EntryDraft.user_id == user.id, EntryDraft.draft_key == key
        )
    )
    now = utcnow()
    if draft is None:
        draft = EntryDraft(
            user_id=user.id,
            draft_key=key,
            page_url=page_url,
            payload=payload,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=DRAFT_RETENTION_DAYS),
        )
        db.add(draft)
    else:
        draft.page_url = page_url
        draft.payload = payload
        draft.updated_at = now
        draft.expires_at = now + timedelta(days=DRAFT_RETENTION_DAYS)

    db.flush()
    excess = list(
        db.scalars(
            select(EntryDraft)
            .where(EntryDraft.user_id == user.id)
            .order_by(EntryDraft.updated_at.desc(), EntryDraft.id.desc())
            .offset(MAX_DRAFTS_PER_USER)
        )
    )
    for stale in excess:
        db.delete(stale)
    db.commit()
    return localized_json(
        request, {"ok": True, "updated_at": draft.updated_at.isoformat()}
    )


@router.delete("/current")
def discard_draft(
    draft_key: str,
    csrf_token: str,
    request: Request,
    user: User = Depends(require_record_submitter),
    db: Session = Depends(get_db),
):
    if not csrf_valid(request, csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session expired")
    key = _valid_key(draft_key)
    db.execute(
        delete(EntryDraft).where(
            EntryDraft.user_id == user.id, EntryDraft.draft_key == key
        )
    )
    db.commit()
    return localized_json(request, {"ok": True})
