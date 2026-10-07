"""Safe storage and exports for the independent wiring-diagram library."""
from __future__ import annotations

import io
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .config import settings
from .purchase_documents import PurchaseDocumentError, StoredPurchaseFile, clean_filename, validate_purchase_file

STORAGE_RE = re.compile(r"^wiring-diagrams/\d{4}/\d{2}/[0-9a-f]{32}\.(pdf|jpg|png|webp)$")


def store_wiring_file(filename: str, data: bytes) -> StoredPurchaseFile:
    content_type, extension = validate_purchase_file(filename, data)
    now = datetime.now(timezone.utc)
    storage_key = f"wiring-diagrams/{now:%Y}/{now:%m}/{uuid.uuid4().hex}{extension}"
    target = settings.upload_dir / storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return StoredPurchaseFile(storage_key, clean_filename(filename), content_type, len(data))


def resolve_wiring_file(storage_key: str) -> Path:
    if not STORAGE_RE.fullmatch(storage_key or ""):
        raise PurchaseDocumentError("Invalid wiring-diagram storage key.")
    root = settings.upload_dir.resolve()
    candidate = (root / storage_key).resolve()
    if root != candidate and root not in candidate.parents:
        raise PurchaseDocumentError("Invalid wiring-diagram storage key.")
    if not candidate.is_file():
        raise PurchaseDocumentError("Wiring-diagram file not found.")
    return candidate


def delete_wiring_files(*keys: str | None) -> None:
    for key in keys:
        if not key:
            continue
        try:
            resolve_wiring_file(key).unlink(missing_ok=True)
        except PurchaseDocumentError:
            pass


def _image_pdf(path: Path, filename: str) -> bytes:
    output = io.BytesIO()
    width, height = A4
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    pdf.setFillColor(colors.HexColor("#17324D"))
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(15 * mm, height - 15 * mm, clean_filename(filename))
    with Image.open(path) as source:
        image_width, image_height = source.size
    scale = min((width - 30 * mm) / image_width, (height - 40 * mm) / image_height)
    draw_width, draw_height = image_width * scale, image_height * scale
    pdf.drawImage(ImageReader(str(path)), (width - draw_width) / 2, (height - draw_height) / 2 - 3 * mm,
                  width=draw_width, height=draw_height, preserveAspectRatio=True, mask="auto")
    pdf.showPage(); pdf.save()
    return output.getvalue()


def preview_pdf(files: list[Any]) -> bytes:
    writer = PdfWriter()
    for entry in files:
        path = resolve_wiring_file(entry.storage_key)
        payload = path.read_bytes() if entry.content_type == "application/pdf" else _image_pdf(path, entry.original_filename)
        for page in PdfReader(io.BytesIO(payload)).pages:
            page.pop(NameObject("/Annots"), None)
            page.pop(NameObject("/AA"), None)
            writer.add_page(page)
    if not writer.pages:
        raise PurchaseDocumentError("This wiring diagram has no previewable files.")
    output = io.BytesIO(); writer.write(output); return output.getvalue()


def files_zip(diagram_name: str, files: list[Any]) -> bytes:
    output = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in files:
            base = clean_filename(entry.original_filename)
            candidate, counter = base, 2
            while candidate.lower() in used:
                path = Path(base); candidate = f"{path.stem}-{counter}{path.suffix}"; counter += 1
            used.add(candidate.lower())
            archive.writestr(candidate, resolve_wiring_file(entry.storage_key).read_bytes())
    return output.getvalue()
