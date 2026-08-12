"""Polished PDF output for one saved price quotation."""
from __future__ import annotations

import io
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as PdfImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .models import PricingQuotation
from .pdf_text import pdf_text, style_for_pdf_text
from .uploads import UploadError, resolve_storage_path

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#1F6F8B")
SLATE = colors.HexColor("#526575")
LIGHT = colors.HexColor("#F4F7F9")
BORDER = colors.HexColor("#D7E0E6")
WHITE = colors.white
BRAND_LOGO_PATH = Path(__file__).resolve().parent / "static" / "img" / "afaqylogo.png"
BRAND_LOGO_WIDTH = 35 * mm
BRAND_LOGO_HEIGHT = BRAND_LOGO_WIDTH * 133 / 380


def _text(value: Any, fallback: str = "-") -> str:
    return pdf_text(value, fallback)


def _amount(value: Decimal, currency: str) -> str:
    return f"{value:,.2f} {_text(currency)}"


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "QuotationTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            textColor=NAVY,
            spaceAfter=2 * mm,
        ),
        "number": ParagraphStyle(
            "QuotationNumber",
            parent=sample["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=BLUE,
            spaceAfter=5 * mm,
        ),
        "section": ParagraphStyle(
            "QuotationSection",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=NAVY,
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "QuotationBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=NAVY,
        ),
        "small": ParagraphStyle(
            "QuotationSmall",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=SLATE,
        ),
        "table_header": ParagraphStyle(
            "QuotationTableHeader",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=WHITE,
        ),
        "right": ParagraphStyle(
            "QuotationRight",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            alignment=TA_RIGHT,
            textColor=NAVY,
        ),
        "right_bold": ParagraphStyle(
            "QuotationRightBold",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=11,
            alignment=TA_RIGHT,
            textColor=NAVY,
        ),
    }


def _paragraph(value: Any, style: ParagraphStyle, fallback: str = "-") -> Paragraph:
    return Paragraph(_text(value, fallback), style_for_pdf_text(value, style))


def _page_footer(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    PdfImage(
        str(BRAND_LOGO_PATH),
        width=BRAND_LOGO_WIDTH,
        height=BRAND_LOGO_HEIGHT,
    ).drawOn(canvas, 18 * mm, height - 15 * mm)
    canvas.setStrokeColor(BORDER)
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SLATE)
    canvas.drawString(18 * mm, 8.5 * mm, "Price quotation")
    canvas.drawRightString(
        width - 18 * mm,
        8.5 * mm,
        f"Page {document.page}",
    )
    canvas.restoreState()


def _item_image(line, styles: dict[str, ParagraphStyle]):
    if not line.image_storage_key:
        return _paragraph("-", styles["small"])
    try:
        key = line.image_thumbnail_key or line.image_storage_key
        path = resolve_storage_path(key)
        with PilImage.open(path) as probe:
            width, height = probe.size
    except (UploadError, OSError, ValueError):
        return _paragraph("-", styles["small"])
    max_width = 22 * mm
    max_height = 18 * mm
    scale = min(max_width / width, max_height / height)
    image = PdfImage(str(path), width=width * scale, height=height * scale)
    image.hAlign = "CENTER"
    return image


def _installation_plan_image(quotation: PricingQuotation):
    if not quotation.plan_output_storage_key:
        return None
    try:
        path = resolve_storage_path(quotation.plan_output_storage_key)
        with PilImage.open(path) as source:
            width, height = source.size
    except (UploadError, OSError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    scale = min((170 * mm) / width, (205 * mm) / height)
    image = PdfImage(str(path), width=width * scale, height=height * scale)
    image.hAlign = "CENTER"
    return image


def _quotation_attachment_image(attachment):
    try:
        path = resolve_storage_path(attachment.storage_key)
        with PilImage.open(path) as source:
            width, height = source.size
    except (UploadError, OSError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    scale = min((170 * mm) / width, (220 * mm) / height)
    image = PdfImage(str(path), width=width * scale, height=height * scale)
    image.hAlign = "CENTER"
    return image


def build_quotation_pdf(quotation: PricingQuotation) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=19 * mm,
        title=f"Price quotation {quotation.quotation_number}",
        author=quotation.company_name or quotation.created_by_name,
        subject=f"Price quotation for {quotation.project_name}",
    )
    story: list[Any] = []

    seller_lines = [
        quotation.company_name,
        quotation.company_address,
        quotation.company_phone,
        quotation.company_email,
    ]
    seller = "\n".join(str(value) for value in seller_lines if value)
    header = Table(
        [
            [
                Paragraph("PRICE QUOTATION", styles["title"]),
                _paragraph(seller, styles["small"], " "),
            ]
        ],
        colWidths=[105 * mm, 65 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.extend(
        [
            header,
            Paragraph(_text(quotation.quotation_number), styles["number"]),
        ]
    )

    project_address = quotation.project_address
    if quotation.project_city:
        project_address = (
            f"{project_address}, {quotation.project_city}"
            if project_address
            else quotation.project_city
        )
    details = Table(
        [
            [
                Paragraph("<b>Project</b>", styles["small"]),
                _paragraph(quotation.project_name, styles["body"]),
                Paragraph("<b>Quotation date</b>", styles["small"]),
                _paragraph(quotation.quotation_date.isoformat(), styles["body"]),
            ],
            [
                Paragraph("<b>Address</b>", styles["small"]),
                _paragraph(project_address, styles["body"]),
                Paragraph("<b>Valid until</b>", styles["small"]),
                _paragraph(quotation.valid_until.isoformat(), styles["body"]),
            ],
            [
                Paragraph("<b>Contact</b>", styles["small"]),
                _paragraph(
                    " | ".join(
                        value
                        for value in (
                            quotation.contact_person,
                            quotation.contact_number,
                        )
                        if value
                    ),
                    styles["body"],
                ),
                Paragraph("<b>Prepared by</b>", styles["small"]),
                _paragraph(quotation.created_by_name, styles["body"]),
            ],
            [
                Paragraph("<b>Attention to</b>", styles["small"]),
                _paragraph(
                    " | ".join(value for value in (quotation.addressee_name, quotation.addressee_title) if value),
                    styles["body"],
                ),
                Paragraph("<b>Contact details</b>", styles["small"]),
                _paragraph(
                    " | ".join(value for value in (quotation.addressee_email, quotation.addressee_phone) if value),
                    styles["body"],
                ),
            ] if quotation.addressee_name else [
                Paragraph("<b>Attention to</b>", styles["small"]),
                _paragraph("-", styles["body"]),
                Paragraph("<b>Contact details</b>", styles["small"]),
                _paragraph("-", styles["body"]),
            ],
        ],
        colWidths=[23 * mm, 62 * mm, 28 * mm, 57 * mm],
    )
    details.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.extend([details, Paragraph("Priced items", styles["section"])])

    rows: list[list[Any]] = [
        [
            _paragraph("#", styles["table_header"]),
            _paragraph("Image", styles["table_header"]),
            _paragraph("Item", styles["table_header"]),
            _paragraph("Qty", styles["table_header"]),
            _paragraph("Unit price", styles["table_header"]),
            _paragraph("Total", styles["table_header"]),
        ]
    ]
    row_index = 0
    for position, line in enumerate(quotation.lines, start=1):
        item_description = line.item_name
        if line.item_model:
            item_description += f"\n{line.item_model}"
        if line.alternative_to:
            item_description += (
                f"\nAlternative to item {line.alternative_to.position} — "
                f"{line.alternative_to.item_name}"
            )
        rows.append(
            [
                _paragraph(position, styles["small"]),
                _item_image(line, styles),
                _paragraph(item_description, styles["body"]),
                _paragraph(line.quantity, styles["right"]),
                _paragraph(_amount(line.unit_price, line.currency), styles["right"]),
                _paragraph(_amount(line.main_total, line.currency), styles["right"]),
            ]
        )
        row_index += 1
        for related in line.related_items:
            rows.append(
                [
                    "",
                    "",
                    _paragraph(f"- {related.item_name}", styles["small"]),
                    _paragraph(related.quantity, styles["right"]),
                    _paragraph(
                        _amount(related.unit_price, related.currency),
                        styles["right"],
                    ),
                    _paragraph(_amount(related.total, related.currency), styles["right"]),
                ]
            )
            row_index += 1
        if line.skip_optional_items:
            rows.append(
                [
                    "",
                    "",
                    _paragraph("- Optional items intentionally skipped", styles["small"]),
                    "",
                    "",
                    "",
                ]
            )
            row_index += 1
    for charge in quotation.charges:
        rows.append(
            [
                _paragraph(f"C{charge.position}", styles["small"]),
                "",
                _paragraph(
                    f"{charge.label}\nRequired charge - per {charge.unit_label}",
                    styles["body"],
                ),
                _paragraph(charge.quantity, styles["right"]),
                _paragraph(
                    _amount(charge.unit_price, charge.currency),
                    styles["right"],
                ),
                _paragraph(_amount(charge.total, charge.currency), styles["right"]),
            ]
        )

    item_table = Table(
        rows,
        colWidths=[8 * mm, 25 * mm, 50 * mm, 17 * mm, 32 * mm, 38 * mm],
        repeatRows=1,
    )
    item_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(item_table)

    if quotation.notes:
        story.extend(
            [
                Paragraph("Notes", styles["section"]),
                _paragraph(quotation.notes, styles["body"]),
            ]
        )
    if quotation.terms:
        story.extend(
            [
                Paragraph("Terms and conditions", styles["section"]),
                _paragraph(quotation.terms, styles["body"]),
            ]
        )

    plan_image = _installation_plan_image(quotation)
    plan_state = quotation.installation_plan_state or {}
    plan_items = plan_state.get("items", []) if isinstance(plan_state, dict) else []
    cameras = [item for item in plan_items if item.get("kind") == "camera"]
    equipment = [item for item in plan_items if item.get("kind") != "camera"]
    equipment_names = {item.get("id"): item.get("name") for item in equipment}
    if plan_image is not None:
        story.extend(
            [
                PageBreak(),
                Paragraph("Installation plan", styles["title"]),
                Spacer(1, 6 * mm),
                plan_image,
                PageBreak(),
                Paragraph("Camera schedule", styles["section"]),
            ]
        )
        schedule_rows: list[list[Any]] = [
            [
                _paragraph("#", styles["table_header"]),
                _paragraph("Camera", styles["table_header"]),
                _paragraph("Type", styles["table_header"]),
                _paragraph("FOV", styles["table_header"]),
                _paragraph("Range", styles["table_header"]),
                _paragraph("Plan width", styles["table_header"]),
                _paragraph("Direction", styles["table_header"]),
                _paragraph("Mounted on", styles["table_header"]),
            ]
        ]
        for position, camera in enumerate(cameras, start=1):
            schedule_rows.append(
                [
                    _paragraph(position, styles["small"]),
                    _paragraph(camera.get("name"), styles["body"]),
                    _paragraph(str(camera.get("type", "")).upper(), styles["body"]),
                    _paragraph(f"{float(camera.get('fov', 0)):g} deg", styles["right"]),
                    _paragraph(f"{float(camera.get('range', 0)):g} m", styles["right"]),
                    _paragraph(f"{float(camera.get('widthMeters', 1.3)):g} m", styles["right"]),
                    _paragraph(f"{float(camera.get('rotation', 0)):g} deg", styles["right"]),
                    _paragraph(equipment_names.get(camera.get("mountedOnId"), "-"), styles["body"]),
                ]
            )
        if len(schedule_rows) == 1:
            schedule_rows.append(
                ["", _paragraph("No cameras placed.", styles["body"]), "", "", "", "", "", ""]
            )
        schedule = Table(
            schedule_rows,
            colWidths=[8 * mm, 38 * mm, 18 * mm, 20 * mm, 20 * mm, 23 * mm, 22 * mm, 26 * mm],
            repeatRows=1,
        )
        schedule.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(schedule)

        if equipment:
            story.extend(
                [Spacer(1, 7 * mm), Paragraph("Installation equipment schedule", styles["section"])]
            )
            equipment_rows: list[list[Any]] = [
                [
                    _paragraph("#", styles["table_header"]),
                    _paragraph("Item", styles["table_header"]),
                    _paragraph("Type", styles["table_header"]),
                    _paragraph("Variant", styles["table_header"]),
                    _paragraph("Plan width", styles["table_header"]),
                    _paragraph("Direction", styles["table_header"]),
                ]
            ]
            for position, item in enumerate(equipment, start=1):
                equipment_rows.append(
                    [
                        _paragraph(position, styles["small"]),
                        _paragraph(item.get("name"), styles["body"]),
                        _paragraph(str(item.get("kind", "")).replace("_", " ").title(), styles["body"]),
                        _paragraph(str(item.get("variant", "")).replace("_", " ").title(), styles["body"]),
                        _paragraph(f"{float(item.get('widthMeters', 0)):g} m", styles["right"]),
                        _paragraph(f"{float(item.get('rotation', 0)):g} deg", styles["right"]),
                    ]
                )
            equipment_table = Table(
                equipment_rows,
                colWidths=[10 * mm, 48 * mm, 34 * mm, 30 * mm, 25 * mm, 28 * mm],
                repeatRows=1,
            )
            equipment_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ]
                )
            )
            story.append(equipment_table)

    total_survey_images = len(quotation.site_survey_images)
    for position, survey_image in enumerate(quotation.site_survey_images, start=1):
        layout_image = _quotation_attachment_image(survey_image)
        if layout_image is None:
            continue
        story.extend(
            [
                PageBreak(),
                Paragraph(
                    f"Site survey layout {position} of {total_survey_images}",
                    styles["title"],
                ),
                _paragraph(survey_image.original_filename, styles["body"]),
                _paragraph(
                    f"Uploaded by {survey_image.uploaded_by_name} on "
                    f"{survey_image.uploaded_at.isoformat(sep=' ', timespec='minutes')}",
                    styles["small"],
                ),
                Spacer(1, 6 * mm),
                layout_image,
            ]
        )

    total_invoices = len(quotation.invoice_images)
    for position, invoice in enumerate(quotation.invoice_images, start=1):
        invoice_image = _quotation_attachment_image(invoice)
        if invoice_image is None:
            continue
        story.extend(
            [
                PageBreak(),
                Paragraph(
                    f"Purchase invoice proof {position} of {total_invoices}",
                    styles["title"],
                ),
                _paragraph(invoice.original_filename, styles["body"]),
                _paragraph(
                    f"Uploaded by {invoice.uploaded_by_name} on "
                    f"{invoice.uploaded_at.isoformat(sep=' ', timespec='minutes')}",
                    styles["small"],
                ),
                Spacer(1, 6 * mm),
                invoice_image,
            ]
        )

    document.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
    return buffer.getvalue()
