"""Safe purchase-document storage, PDF preview, and price-analysis export."""
from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .config import settings
from .pdf_text import pdf_text, style_for_pdf_text


MAX_PURCHASE_FILES = 20
MAX_PURCHASE_FILE_BYTES = 20 * 1024 * 1024
ALLOWED_PURCHASE_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
PURCHASE_STORAGE_KEY_RE = re.compile(
    r"^purchase-documents/\d{4}/\d{2}/[0-9a-f]{32}\.(pdf|jpg|png|webp)$"
)
IMAGE_MIMES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class PurchaseDocumentError(ValueError):
    """A purchase-document error safe to show to an authenticated user."""


@dataclass(slots=True)
class StoredPurchaseFile:
    storage_key: str
    original_filename: str
    content_type: str
    file_size: int


def clean_filename(name: str) -> str:
    value = (name or "document").replace("\\", "/").split("/")[-1]
    value = re.sub(r"[^A-Za-z0-9._ -]", "_", value).strip() or "document"
    return value[:180]


def validate_purchase_file(filename: str, data: bytes) -> tuple[str, str]:
    display_name = clean_filename(filename)
    if not data:
        raise PurchaseDocumentError(f'"{display_name}" is empty.')
    if len(data) > MAX_PURCHASE_FILE_BYTES:
        raise PurchaseDocumentError(f'"{display_name}" exceeds the 20 MB file limit.')
    extension = Path(display_name).suffix.lower()
    if extension not in ALLOWED_PURCHASE_EXTENSIONS:
        raise PurchaseDocumentError(
            f'"{display_name}" must be a PDF, JPEG, PNG, or WebP file.'
        )
    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise PurchaseDocumentError(f'"{display_name}" is not a real PDF file.')
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not reader.pages:
                raise PurchaseDocumentError(
                    f'"{display_name}" must be an unencrypted PDF with at least one page.'
                )
            len(reader.pages)
        except PurchaseDocumentError:
            raise
        except Exception as exc:
            raise PurchaseDocumentError(f'"{display_name}" could not be read as a PDF.') from exc
        return "application/pdf", ".pdf"

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as probe:
            probe.load()
            image_format = (probe.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PurchaseDocumentError(f'"{display_name}" could not be read as an image.') from exc
    content_type = IMAGE_MIMES.get(image_format)
    if content_type is None:
        raise PurchaseDocumentError(f'"{display_name}" is not a supported image.')
    canonical_extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
    return content_type, canonical_extension


def store_purchase_file(filename: str, data: bytes) -> StoredPurchaseFile:
    content_type, extension = validate_purchase_file(filename, data)
    now = datetime.now(timezone.utc)
    folder = f"purchase-documents/{now:%Y}/{now:%m}"
    storage_key = f"{folder}/{uuid.uuid4().hex}{extension}"
    target = settings.upload_dir / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return StoredPurchaseFile(
        storage_key=storage_key,
        original_filename=clean_filename(filename),
        content_type=content_type,
        file_size=len(data),
    )


def resolve_purchase_file(storage_key: str) -> Path:
    if not PURCHASE_STORAGE_KEY_RE.fullmatch(storage_key or ""):
        raise PurchaseDocumentError("Invalid purchase-document storage key.")
    root = settings.upload_dir.resolve()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise PurchaseDocumentError("Invalid purchase-document storage key.")
    if not candidate.is_file():
        raise PurchaseDocumentError("Purchase-document file not found.")
    return candidate


def delete_purchase_files(*storage_keys: str | None) -> None:
    for storage_key in storage_keys:
        if not storage_key:
            continue
        try:
            resolve_purchase_file(storage_key).unlink(missing_ok=True)
        except PurchaseDocumentError:
            continue


def _image_pdf(path: Path, filename: str) -> bytes:
    output = io.BytesIO()
    page_width, page_height = A4
    canvas = pdf_canvas.Canvas(output, pagesize=A4, pageCompression=1)
    canvas.setFillColor(colors.HexColor("#17324D"))
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(15 * mm, page_height - 15 * mm, clean_filename(filename))
    with Image.open(path) as source:
        width, height = source.size
    max_width = page_width - 30 * mm
    max_height = page_height - 40 * mm
    scale = min(max_width / width, max_height / height)
    draw_width = width * scale
    draw_height = height * scale
    canvas.drawImage(
        ImageReader(str(path)),
        (page_width - draw_width) / 2,
        (page_height - draw_height) / 2 - 3 * mm,
        width=draw_width,
        height=draw_height,
        preserveAspectRatio=True,
        mask="auto",
    )
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def build_purchase_document_preview(files: list[Any]) -> bytes:
    writer = PdfWriter()
    for entry in files:
        path = resolve_purchase_file(entry.storage_key)
        payload = path.read_bytes() if entry.content_type == "application/pdf" else _image_pdf(path, entry.original_filename)
        reader = PdfReader(io.BytesIO(payload))
        for source_page in reader.pages:
            page = source_page
            page.pop(NameObject("/Annots"), None)
            page.pop(NameObject("/AA"), None)
            writer.add_page(page)
    if not writer.pages:
        raise PurchaseDocumentError("This purchase document has no previewable pages.")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def build_price_analysis_pdf(item_label: str, rows: list[dict[str, Any]]) -> bytes:
    output = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PurchaseAnalysisTitle", parent=styles["Title"], textColor=colors.HexColor("#17324D")
    )
    body_style = ParagraphStyle(
        "PurchaseAnalysisBody", parent=styles["BodyText"], fontSize=9, leading=12
    )

    def paragraph(value: Any, style: ParagraphStyle = body_style) -> Paragraph:
        return Paragraph(pdf_text(value), style_for_pdf_text(value, style))

    story = [
        paragraph("Purchase Price Analysis / تحليل أسعار الشراء", title_style),
        paragraph(item_label),
        Spacer(1, 6 * mm),
    ]
    table_rows = [[
        paragraph("Date / التاريخ"),
        paragraph("Type / النوع"),
        paragraph("Supplier / المورد"),
        paragraph("Unit price / سعر الوحدة"),
    ]]
    for row in rows:
        table_rows.append([
            paragraph(row["date"]),
            paragraph(row["type"]),
            paragraph(row["supplier"]),
            paragraph(f'{Decimal(row["price"]):,.2f} {row["currency"]}'),
        ])
    table = Table(table_rows, colWidths=[30 * mm, 42 * mm, 75 * mm, 40 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17324D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#B8C8D3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7F9")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title=f"Purchase price analysis - {item_label}",
    )
    document.build(story)
    return output.getvalue()
