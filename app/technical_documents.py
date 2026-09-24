"""Safe storage and branded outputs for item technical information."""
from __future__ import annotations

import io
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import BASE_DIR, settings
from .pdf_text import pdf_text, style_for_pdf_text
from .purchase_documents import PurchaseDocumentError, clean_filename, validate_purchase_file

TECHNICAL_KEY_RE = re.compile(r"^technical-documents/\d{4}/\d{2}/[0-9a-f]{32}\.(pdf|jpg|png|webp)$")
QUOTATION_TECHNICAL_KEY_RE = re.compile(r"^quotation-technical/\d+/[0-9a-f]{32}\.(pdf|jpg|png|webp)$")


def store_technical_file(filename: str, data: bytes) -> tuple[str, str, str, int]:
    content_type, extension = validate_purchase_file(filename, data)
    now = datetime.now(timezone.utc)
    key = f"technical-documents/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"
    target = settings.upload_dir / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return key, clean_filename(filename), content_type, len(data)


def resolve_technical_file(key: str) -> Path:
    if not TECHNICAL_KEY_RE.fullmatch(key or ""):
        raise PurchaseDocumentError("Invalid technical-document storage key.")
    root = settings.upload_dir.resolve()
    target = (root / key).resolve()
    if root != target and root not in target.parents:
        raise PurchaseDocumentError("Invalid technical-document storage key.")
    if not target.is_file():
        raise PurchaseDocumentError("Technical document not found.")
    return target


def delete_quotation_technical_files(*keys: str | None) -> None:
    root = settings.upload_dir.resolve()
    for key in keys:
        if not key or not QUOTATION_TECHNICAL_KEY_RE.fullmatch(key):
            continue
        target = (root / key).resolve()
        if root in target.parents:
            target.unlink(missing_ok=True)


def recommendation_pdf(*, item_name: str, model: str, category: str, recommendation: str, updated_at) -> bytes:
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm, title=f"Technical recommendation - {item_name}")
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=11, leading=16, textColor=colors.HexColor("#17324D"))
    heading = ParagraphStyle("heading", parent=base, fontName="Helvetica-Bold", fontSize=19, leading=24, textColor=colors.HexColor("#0B5D68"), spaceAfter=7*mm)
    body = style_for_pdf_text(recommendation, base)
    story = []
    logo = BASE_DIR / "app" / "static" / "img" / "afaqylogo.png"
    if logo.is_file():
        story.extend([Image(str(logo), width=42*mm, height=18*mm, kind="proportional"), Spacer(1, 5*mm)])
    story.append(Paragraph(pdf_text("Technical Recommendation"), heading))
    details = [["Item", item_name], ["Model", model or "—"], ["Category", category or "Uncategorized"], ["Updated", updated_at.strftime("%Y-%m-%d %H:%M")]]
    table = Table([[Paragraph(pdf_text(str(a)), base), Paragraph(pdf_text(str(b)), base)] for a,b in details], colWidths=[35*mm, 120*mm])
    table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.5,colors.HexColor("#B7C9D3")),("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EAF3F5")),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),6)]))
    story.extend([table, Spacer(1, 9*mm), Paragraph(pdf_text(recommendation).replace("\n", "<br/>"), body)])
    doc.build(story)
    return output.getvalue()


def technical_package(documents, recommendation_payload: bytes | None, item_name: str) -> bytes:
    output = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in documents:
            name = clean_filename(entry.original_filename)
            stem, suffix = Path(name).stem, Path(name).suffix
            candidate, counter = name, 2
            while candidate.casefold() in used:
                candidate = f"{stem}-{counter}{suffix}"; counter += 1
            used.add(candidate.casefold())
            archive.writestr(f"Data Sheets/{candidate}", resolve_technical_file(entry.storage_key).read_bytes())
        if recommendation_payload:
            archive.writestr(f"Recommendation/{clean_filename(item_name)}-recommendation.pdf", recommendation_payload)
    return output.getvalue()
