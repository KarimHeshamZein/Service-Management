"""Storage and customer-readable reports for Product Evaluations and Testing."""
from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import BASE_DIR, settings
from .models import ProductEvaluationRequest, ProductEvaluationSession
from .pdf_text import pdf_text, style_for_pdf_text
from .purchase_documents import PurchaseDocumentError, StoredPurchaseFile, clean_filename, validate_purchase_file

STORAGE_RE = re.compile(r"^product-evaluations/\d{4}/\d{2}/[0-9a-f]{32}\.(pdf|jpg|png|webp)$")


def store_evaluation_file(filename: str, data: bytes) -> StoredPurchaseFile:
    content_type, extension = validate_purchase_file(filename, data)
    now = datetime.now(timezone.utc)
    key = f"product-evaluations/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"
    target = settings.upload_dir / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return StoredPurchaseFile(key, clean_filename(filename), content_type, len(data))


def resolve_evaluation_file(key: str) -> Path:
    if not STORAGE_RE.fullmatch(key or ""):
        raise PurchaseDocumentError("Invalid product-evaluation storage key.")
    root = settings.upload_dir.resolve()
    candidate = (root / key).resolve()
    if root != candidate and root not in candidate.parents:
        raise PurchaseDocumentError("Invalid product-evaluation storage key.")
    if not candidate.is_file():
        raise PurchaseDocumentError("Product-evaluation file not found.")
    return candidate


def delete_evaluation_files(*keys: str | None) -> None:
    for key in keys:
        if not key:
            continue
        try:
            resolve_evaluation_file(key).unlink(missing_ok=True)
        except PurchaseDocumentError:
            pass


def elapsed_label(start: datetime | None, end: datetime | None) -> str:
    if not start or not end or end < start:
        return "-"
    seconds = int((end - start).total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    parts = []
    if days: parts.append(f"{days} day(s)")
    if hours: parts.append(f"{hours} hour(s)")
    parts.append(f"{minutes} minute(s)")
    return " ".join(parts)


def evaluation_report(evaluation: ProductEvaluationRequest, sessions: Iterable[ProductEvaluationSession] | None = None) -> bytes:
    selected = list(sessions if sessions is not None else evaluation.sessions)
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("EvalTitle", parent=styles["Title"], textColor=colors.HexColor("#17324D"), fontSize=20, leading=24)
    heading = ParagraphStyle("EvalHeading", parent=styles["Heading2"], textColor=colors.HexColor("#087F86"), fontSize=13, leading=16, spaceBefore=5*mm, spaceAfter=2*mm)
    body = ParagraphStyle("EvalBody", parent=styles["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("EvalSmall", parent=body, fontSize=8, textColor=colors.HexColor("#546777"))

    def p(value, style=body):
        value = "-" if value is None or value == "" else value
        return Paragraph(pdf_text(str(value)), style_for_pdf_text(str(value), style))

    def details(rows):
        table = Table([[p(label, small), p(value)] for label, value in rows], colWidths=[47*mm, 133*mm])
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),colors.HexColor("#EEF4F7")),("GRID",(0,0),(-1,-1),.45,colors.HexColor("#B8C8D3")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        return table

    def evidence_grid(attachments, *, include_description: bool):
        images = []
        for attachment in attachments:
            if not attachment.content_type.startswith("image/"):
                continue
            path = resolve_evaluation_file(attachment.storage_key)
            with PILImage.open(path) as probe:
                width, height = probe.size
            scale = min((56 * mm) / width, (43 * mm) / height)
            image = Image(str(path), width=width * scale, height=height * scale)
            caption = (
                attachment.description
                if include_description and attachment.description
                else attachment.original_filename
            )
            evidence_cell = Table(
                [[image], [p(caption, small)]],
                colWidths=[56 * mm],
            )
            evidence_cell.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            images.append(evidence_cell)
        if not images:
            return None
        column_count = min(3, len(images))
        rows = [images[position : position + column_count] for position in range(0, len(images), column_count)]
        if len(rows[-1]) < column_count:
            rows[-1] += [""] * (column_count - len(rows[-1]))
        grid = Table(rows, colWidths=[60 * mm] * column_count, hAlign="LEFT")
        grid.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#B8C8D3")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return grid

    story = [p("Product Evaluations and Testing", title), p(f"{evaluation.request_number} | {evaluation.device_name} | {evaluation.model}", heading)]
    story.append(details([
        ("Customer / Project", evaluation.customer_project_name), ("Manufacturer", evaluation.manufacturer or "-"), ("Serial Number", evaluation.serial_number or "Not received"),
        ("Requested By", evaluation.created_by_name), ("Assigned Admin", evaluation.assigned_admin_name), ("Sales Representative", evaluation.sales_contact_name), ("After Sales", evaluation.after_sales_name),
        ("Opened At", evaluation.created_at.strftime("%Y-%m-%d %H:%M")), ("Approved At", evaluation.approved_at.strftime("%Y-%m-%d %H:%M") if evaluation.approved_at else "-"),
        ("Received At", evaluation.received_at.strftime("%Y-%m-%d %H:%M") if evaluation.received_at else "-"), ("Request to Receipt", elapsed_label(evaluation.created_at,evaluation.received_at)),
        ("Purpose", evaluation.reason), ("Requirements", evaluation.requirements or "-"),
    ]))
    initial_evidence = evidence_grid(evaluation.attachments, include_description=False)
    if initial_evidence is not None:
        story.extend([p("Initial Request Images", heading), initial_evidence])
    if not selected:
        story.extend([Spacer(1,8*mm),p("No evaluation sessions have been completed.",heading)])
    for index, session in enumerate(selected):
        if index or len(story) > 3: story.append(PageBreak())
        story.extend([p(f"Evaluation Session {session.sequence}", title), details([
            ("Evaluator",session.assigned_user_name),("Assigned By",session.assigned_by_name),("Status",session.status.value.replace("_"," ").title()),
            ("Scheduled Start",session.scheduled_start_at.strftime("%Y-%m-%d %H:%M") if session.scheduled_start_at else "-"),("Due At",session.due_at.strftime("%Y-%m-%d %H:%M") if session.due_at else "-"),
            ("Started At",session.started_at.strftime("%Y-%m-%d %H:%M") if session.started_at else "-"),("Completed At",session.completed_at.strftime("%Y-%m-%d %H:%M") if session.completed_at else "-"),
            ("Actual Test Duration",elapsed_label(session.started_at,session.completed_at)),("Location",session.location or "-"),("Instructions",session.instructions or "-"),
        ])])
        fields=[("Tests Performed",session.tests_performed),("Results",session.results),("Strengths",session.strengths),("Weaknesses",session.weaknesses),("Issues Found",session.issues_found),("Compatibility",session.compatibility),("Recommendation",session.recommendation)]
        for label,value in fields:
            if value: story.extend([p(label,heading),p(value)])
        ratings=[("Performance",session.performance_rating),("Quality",session.quality_rating),("Installation",session.installation_rating),("Compatibility",session.compatibility_rating),("Value",session.value_rating)]
        story.append(KeepTogether([
            p("Ratings", heading),
            details([(label, f"{value}/5" if value else "-") for label,value in ratings]),
            p("Final Decision", heading),
            p(session.decision.value.replace("_", " ").title() if session.decision else "Not completed"),
        ]))
        session_evidence = evidence_grid(session.attachments, include_description=True)
        if session_evidence is not None:
            story.extend([p("Evaluation Evidence", heading), session_evidence])

    logo = BASE_DIR / "app" / "static" / "img" / "afaqylogo.png"
    def decorate(canvas, document):
        canvas.saveState()
        if logo.is_file(): canvas.drawImage(str(logo),15*mm,A4[1]-20*mm,width=28*mm,height=12*mm,preserveAspectRatio=True,mask="auto")
        canvas.setStrokeColor(colors.HexColor("#B8C8D3")); canvas.line(15*mm,12*mm,A4[0]-15*mm,12*mm)
        canvas.setFont("Helvetica",7); canvas.setFillColor(colors.HexColor("#546777")); canvas.drawString(15*mm,7*mm,evaluation.request_number); canvas.drawRightString(A4[0]-15*mm,7*mm,f"Page {document.page}")
        canvas.restoreState()
    document=SimpleDocTemplate(output,pagesize=A4,leftMargin=15*mm,rightMargin=15*mm,topMargin=25*mm,bottomMargin=18*mm,title=f"{evaluation.request_number} Product Evaluation")
    document.build(story,onFirstPage=decorate,onLaterPages=decorate)
    return output.getvalue()
