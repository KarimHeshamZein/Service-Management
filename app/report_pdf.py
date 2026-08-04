"""PDF rendering for filtered service-record reports."""
from __future__ import annotations

import io
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
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

from .config import settings
from .pdf_text import pdf_text, style_for_pdf_text
from .uploads import UploadError, resolve_storage_path

PAGE_SIZE = landscape(A4)
TYPE_LABELS = {
    "": "All record types",
    "maintenance": "Preventive maintenance",
    "general_maintenance": "Maintenance",
    "installation": "Installation",
}

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#1F6F8B")
PALE_BLUE = colors.HexColor("#EAF3F6")
SLATE = colors.HexColor("#526575")
LIGHT = colors.HexColor("#F4F7F9")
BORDER = colors.HexColor("#D7E0E6")
WHITE = colors.white


def _text(value: Any, fallback: str = "-") -> str:
    return pdf_text(value, fallback)


def _display_datetime(value: datetime) -> str:
    displayed = value + settings.display_tz_offset
    return f"{displayed:%Y-%m-%d %H:%M} {settings.display_tz_label}"


def _display_date(value: Any) -> str:
    return value.strftime("%Y-%m-%d") if value else "-"


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=NAVY,
            spaceAfter=4 * mm,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=sample["Normal"],
            fontSize=9,
            leading=12,
            textColor=SLATE,
            spaceAfter=5 * mm,
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=NAVY,
            spaceBefore=3 * mm,
            spaceAfter=2 * mm,
        ),
        "item": ParagraphStyle(
            "ReportItem",
            parent=sample["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=BLUE,
            spaceBefore=3 * mm,
            spaceAfter=1.5 * mm,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=NAVY,
        ),
        "small": ParagraphStyle(
            "ReportSmall",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=NAVY,
        ),
        "small_header": ParagraphStyle(
            "ReportSmallHeader",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=WHITE,
        ),
        "small_center": ParagraphStyle(
            "ReportSmallCenter",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=SLATE,
        ),
        "label": ParagraphStyle(
            "ReportLabel",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=SLATE,
        ),
    }


def _paragraph(value: Any, style: ParagraphStyle, fallback: str = "-") -> Paragraph:
    return Paragraph(_text(value, fallback), style_for_pdf_text(value, style))


def _table(
    rows: list[list[Any]],
    *,
    col_widths: list[float] | None = None,
    header: bool = False,
    padding: float = 5,
) -> Table:
    table = Table(
        rows,
        colWidths=col_widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
    )
    commands: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), padding),
        ("RIGHTPADDING", (0, 0), (-1, -1), padding),
        ("TOPPADDING", (0, 0), (-1, -1), padding),
        ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [WHITE, LIGHT]),
    ]
    if header:
        commands.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def _photo_cell(
    photo: dict[str, str | None],
    styles: dict[str, ParagraphStyle],
) -> list[Any] | None:
    key = photo.get("thumbnail_key") or photo.get("storage_key")
    if not key:
        return None
    try:
        path = resolve_storage_path(key)
        with PilImage.open(path) as probe:
            width, height = probe.size
    except (UploadError, OSError, ValueError):
        return None

    max_width = 78 * mm
    max_height = 48 * mm
    scale = min(max_width / width, max_height / height, 1)
    image = PdfImage(str(path), width=width * scale, height=height * scale)
    image.hAlign = "CENTER"
    stage_label = {
        "before": "Before",
        "after": "After",
        "legacy": "Existing evidence",
    }.get(photo.get("stage"), "Existing evidence")
    return [
        image,
        Spacer(1, 1.5 * mm),
        _paragraph(
            f"{stage_label}: {photo.get('original_filename') or 'Evidence photo'}",
            styles["small_center"],
            stage_label,
        ),
    ]


def _photos_table(
    photos: list[dict[str, str | None]],
    styles: dict[str, ParagraphStyle],
) -> Table | Paragraph:
    stage_order = {"before": 0, "after": 1, "legacy": 2}
    photos = sorted(photos, key=lambda photo: stage_order.get(photo.get("stage"), 2))
    cells = [
        cell
        for photo in photos
        if (cell := _photo_cell(photo, styles)) is not None
    ]
    if not cells:
        return _paragraph("No available evidence photos.", styles["body"])
    rows = [cells[index : index + 3] for index in range(0, len(cells), 3)]
    while len(rows[-1]) < 3:
        rows[-1].append("")
    table = Table(rows, colWidths=[86 * mm] * 3, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


PDF_PHOTOS_PER_RECORD = 20
BRAND_LOGO_PATH = Path(__file__).resolve().parent / "static" / "img" / "afaqylogo.png"
BRAND_LOGO_WIDTH = 35 * mm
BRAND_LOGO_HEIGHT = BRAND_LOGO_WIDTH * 133 / 380


def _bounded_item_photos(
    photos: list[dict[str, str | None]],
    remaining: int,
) -> tuple[list[dict[str, str | None]], int, int]:
    included = photos[:remaining]
    omitted = len(photos) - len(included)
    return included, omitted, remaining - len(included)


def _header_footer(canvas, doc) -> None:
    canvas.saveState()
    width, height = PAGE_SIZE
    PdfImage(
        str(BRAND_LOGO_PATH),
        width=BRAND_LOGO_WIDTH,
        height=BRAND_LOGO_HEIGHT,
    ).drawOn(canvas, 12 * mm, height - 15 * mm)
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(12 * mm, 11 * mm, width - 12 * mm, 11 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SLATE)
    canvas.drawString(12 * mm, 6.5 * mm, settings.app_name)
    canvas.drawRightString(
        width - 12 * mm,
        6.5 * mm,
        f"Service records report | Page {doc.page}",
    )
    canvas.restoreState()


def build_records_pdf(
    records: list[dict[str, Any]],
    filters: dict[str, str],
    generated_by: str,
    *,
    include_quotation: bool = False,
) -> bytes:
    """Render the complete filtered record set, including available photos."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=20 * mm,
        bottomMargin=17 * mm,
        title="Service records report",
        author=settings.app_name,
        subject="Filtered installation and maintenance evidence",
    )
    styles = _styles()
    story: list[Any] = []

    generated = datetime.now(timezone.utc) + settings.display_tz_offset
    story.append(_paragraph("Service records report", styles["title"]))
    story.append(
        _paragraph(
            f"Generated {_text(generated.strftime('%Y-%m-%d %H:%M'))} "
            f"{_text(settings.display_tz_label)} by {_text(generated_by)}",
            styles["subtitle"],
        )
    )

    filter_rows = [
        [
            _paragraph("Search", styles["label"]),
            _paragraph(filters["q"] or "All records", styles["body"]),
            _paragraph("Record type", styles["label"]),
            _paragraph(TYPE_LABELS[filters["type"]], styles["body"]),
        ]
    ]
    story.append(
        _table(
            filter_rows,
            col_widths=[25 * mm, 100 * mm, 28 * mm, 110 * mm],
        )
    )
    story.append(Spacer(1, 4 * mm))

    counts = Counter(record["record_type"] for record in records)
    summary_rows = [
        [
            _paragraph("Total records", styles["label"]),
            _paragraph(len(records), styles["body"]),
            _paragraph("Installations", styles["label"]),
            _paragraph(counts["Installation"], styles["body"]),
            _paragraph("Preventive maintenance", styles["label"]),
            _paragraph(counts["Preventive maintenance"], styles["body"]),
            _paragraph("Maintenance", styles["label"]),
            _paragraph(counts["Maintenance"], styles["body"]),
        ]
    ]
    story.append(_table(summary_rows))
    story.append(_paragraph("Matching records", styles["section"]))

    header = [
        Paragraph("Record", styles["small_header"]),
        Paragraph("Type", styles["small_header"]),
        Paragraph("Project / site", styles["small_header"]),
        Paragraph("Device", styles["small_header"]),
        Paragraph("Service", styles["small_header"]),
        Paragraph("Result", styles["small_header"]),
        Paragraph("Submitted by", styles["small_header"]),
        Paragraph("Submitted", styles["small_header"]),
    ]
    rows = [header]
    for record in records:
        project_site = record["site_name"]
        if record["customer_name"] != record["site_name"]:
            project_site += f"\n{record['customer_name']}"
        if record["work_site_name"] and record["work_site_name"] != record["site_name"]:
            project_site += f"\n{record['work_site_name']}"
        device_summary = record["device"]
        device_total = record.get("device_total", 1)
        if device_total > 1:
            device_summary += f" | +{device_total - 1} more"
        rows.append(
            [
                _paragraph(record["record_number"], styles["small"]),
                _paragraph(record["record_type"], styles["small"]),
                _paragraph(project_site, styles["small"]),
                _paragraph(device_summary, styles["small"]),
                _paragraph(record["service_name"], styles["small"]),
                _paragraph(record["result"].label, styles["small"]),
                _paragraph(record["team_leader_name"], styles["small"]),
                _paragraph(_display_datetime(record["submitted_at"]), styles["small"]),
            ]
        )
    if records:
        story.append(
            _table(
                rows,
                col_widths=[
                    23 * mm,
                    27 * mm,
                    39 * mm,
                    52 * mm,
                    32 * mm,
                    34 * mm,
                    30 * mm,
                    30 * mm,
                ],
                header=True,
                padding=3,
            )
        )
    else:
        story.append(
            _paragraph(
                "No records match the selected filters.",
                styles["body"],
            )
        )

    for record in records:
        story.append(PageBreak())
        story.append(
            _paragraph(
                f"{record['record_number']} - {record['record_type']}",
                styles["title"],
            )
        )
        detail_rows = [
            [
                _paragraph("Project", styles["label"]),
                _paragraph(record["customer_name"], styles["body"]),
                _paragraph("Site", styles["label"]),
                _paragraph(
                    record["work_site_name"] or record["site_name"],
                    styles["body"],
                ),
            ],
            [
                _paragraph("Location", styles["label"]),
                _paragraph(record["address"], styles["body"]),
                _paragraph("Result", styles["label"]),
                _paragraph(record["result"].label, styles["body"]),
            ],
            [
                _paragraph("Submitted by", styles["label"]),
                _paragraph(record["team_leader_name"], styles["body"]),
                _paragraph("Submitted", styles["label"]),
                _paragraph(
                    _display_datetime(record["submitted_at"]),
                    styles["body"],
                ),
            ],
            [
                _paragraph("Worked with", styles["label"]),
                _paragraph(
                    ", ".join(record["participants"]) or "Worked alone",
                    styles["body"],
                ),
                _paragraph("Items", styles["label"]),
                _paragraph(len(record["items"]), styles["body"]),
            ],
        ]
        if include_quotation and record.get("quotation_number"):
            detail_rows.append(
                [
                    _paragraph("Quotation ID", styles["label"]),
                    _paragraph(record["quotation_number"], styles["body"]),
                    "",
                    "",
                ]
            )
        story.append(
            _table(
                detail_rows,
                col_widths=[28 * mm, 105 * mm, 28 * mm, 105 * mm],
            )
        )

        remaining_photos = PDF_PHOTOS_PER_RECORD
        for index, item in enumerate(record["items"], start=1):
            title = (
                f"Work item {index}: {item['device_name']} - "
                f"{item['device_model']}"
            )
            story.append(_paragraph(title, styles["item"]))
            item_rows = [
                [
                    _paragraph("Service", styles["label"]),
                    _paragraph(item["service_name"], styles["body"]),
                    _paragraph("Serial number", styles["label"]),
                    _paragraph(item["serial_number"], styles["body"]),
                    _paragraph("Result", styles["label"]),
                    _paragraph(item["result"].label, styles["body"]),
                ]
            ]
            if item["warranty_start"]:
                item_rows.append(
                    [
                        _paragraph("Warranty start", styles["label"]),
                        _paragraph(
                            _display_date(item["warranty_start"]),
                            styles["body"],
                        ),
                        "",
                        "",
                        "",
                        "",
                    ]
                )
            story.append(
                _table(
                    item_rows,
                    col_widths=[
                        25 * mm,
                        62 * mm,
                        27 * mm,
                        62 * mm,
                        23 * mm,
                        62 * mm,
                    ],
                )
            )
            story.append(Spacer(1, 2 * mm))

            narrative: list[Any] = [
                _paragraph("Notes", styles["label"]),
                _paragraph(item["notes"], styles["body"]),
            ]
            for label, field in (
                ("Issue found", "issue_description"),
                ("Recommendations", "recommendations"),
                ("Handover notes", "handover_notes"),
            ):
                if item[field]:
                    narrative.extend(
                        [
                            Spacer(1, 1.5 * mm),
                            _paragraph(label, styles["label"]),
                            _paragraph(item[field], styles["body"]),
                        ]
                    )
            story.append(KeepTogether(narrative))
            story.append(Spacer(1, 2 * mm))
            story.append(_paragraph("Evidence photos", styles["label"]))
            photos, omitted, remaining_photos = _bounded_item_photos(
                item["photos"],
                remaining_photos,
            )
            story.append(_photos_table(photos, styles))
            if omitted:
                story.append(
                    _paragraph(
                        f"{omitted} additional evidence photo"
                        f"{'' if omitted == 1 else 's'} omitted from this PDF.",
                        styles["small"],
                    )
                )

    document.build(
        story,
        onFirstPage=_header_footer,
        onLaterPages=_header_footer,
    )
    return buffer.getvalue()


def build_technician_audit_pdf(
    audit: dict[str, Any],
    generated_by: str,
    *,
    include_photos: bool = False,
) -> bytes:
    """Render an Administrator-only technician activity review."""
    buffer = io.BytesIO()
    technician = audit["technician"]
    filters = audit["filters"]
    summary = audit["summary"]
    document = SimpleDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=20 * mm,
        bottomMargin=17 * mm,
        title=f"Technician activity - {technician.full_name}",
        author=settings.app_name,
        subject="Administrator technician work review",
    )
    styles = _styles()
    story: list[Any] = [
        _paragraph("Technician activity report", styles["title"]),
        _paragraph(
            (
                f"{technician.full_name} | {technician.username} | "
                f"{'Active' if technician.is_active else 'Inactive'} account"
            ),
            styles["subtitle"],
        ),
    ]
    generated = datetime.now(timezone.utc) + settings.display_tz_offset
    story.append(
        _paragraph(
            (
                f"Generated {generated:%Y-%m-%d %H:%M} "
                f"{settings.display_tz_label} by {generated_by}"
            ),
            styles["subtitle"],
        )
    )

    filter_rows = [
        [
            _paragraph("Period", styles["label"]),
            _paragraph(
                f"{filters['start'] or 'Any'} to {filters['end'] or 'Any'}",
                styles["body"],
            ),
            _paragraph("Record type", styles["label"]),
            _paragraph(TYPE_LABELS[filters["type"]], styles["body"]),
            _paragraph("Project", styles["label"]),
            _paragraph(filters.get("project_name") or "All projects", styles["body"]),
            _paragraph("Evidence photos", styles["label"]),
            _paragraph("Included" if include_photos else "Counts only", styles["body"]),
        ]
    ]
    story.append(
        _table(
            filter_rows,
            col_widths=[
                20 * mm,
                49 * mm,
                22 * mm,
                43 * mm,
                18 * mm,
                51 * mm,
                27 * mm,
                37 * mm,
            ],
        )
    )
    story.append(Spacer(1, 4 * mm))

    summary_rows = [
        [
            _paragraph("Visits", styles["label"]),
            _paragraph(summary["total_visits"], styles["body"]),
            _paragraph("Led", styles["label"]),
            _paragraph(summary["led_visits"], styles["body"]),
            _paragraph("Assisted", styles["label"]),
            _paragraph(summary["assisted_visits"], styles["body"]),
            _paragraph("Devices", styles["label"]),
            _paragraph(summary["total_devices"], styles["body"]),
            _paragraph("Photos", styles["label"]),
            _paragraph(summary["total_photos"], styles["body"]),
            _paragraph("Edits", styles["label"]),
            _paragraph(summary["total_edits"], styles["body"]),
        ]
    ]
    story.append(_table(summary_rows))

    breakdown_rows: list[list[Any]] = []
    for title, key in (
        ("Record types", "record_types"),
        ("Device results", "results"),
        ("Projects", "projects"),
        ("Sites", "sites"),
        ("Services", "services"),
        ("Devices", "devices"),
    ):
        values = summary[key]
        breakdown_rows.append(
            [
                _paragraph(title, styles["label"]),
                _paragraph(
                    ", ".join(
                        f"{row['label']} ({row['count']})" for row in values
                    )
                    or "-",
                    styles["body"],
                ),
            ]
        )
    story.append(_paragraph("Work breakdown", styles["section"]))
    story.append(
        _table(
            breakdown_rows,
            col_widths=[35 * mm, 232 * mm],
        )
    )

    story.append(_paragraph("Activity ledger", styles["section"]))
    ledger_rows = [
        [
            _paragraph("Submitted", styles["small_header"]),
            _paragraph("Role", styles["small_header"]),
            _paragraph("Record", styles["small_header"]),
            _paragraph("Type", styles["small_header"]),
            _paragraph("Project / site", styles["small_header"]),
            _paragraph("Service", styles["small_header"]),
            _paragraph("Devices", styles["small_header"]),
            _paragraph("Photos", styles["small_header"]),
            _paragraph("Result", styles["small_header"]),
        ]
    ]
    for record in audit["records"]:
        ledger_rows.append(
            [
                _paragraph(_display_datetime(record["submitted_at"]), styles["small"]),
                _paragraph(record["technician_role"], styles["small"]),
                _paragraph(record["record_number"], styles["small"]),
                _paragraph(record["record_type"], styles["small"]),
                _paragraph(
                    f"{record['customer_name']} / "
                    f"{record['work_site_name'] or record['site_name']}",
                    styles["small"],
                ),
                _paragraph(record["service_name"], styles["small"]),
                _paragraph(record["device_count"], styles["small"]),
                _paragraph(record["photo_count"], styles["small"]),
                _paragraph(record["result"].label, styles["small"]),
            ]
        )
    if len(ledger_rows) == 1:
        story.append(_paragraph("No work matches these filters.", styles["body"]))
    else:
        story.append(
            _table(
                ledger_rows,
                col_widths=[
                    31 * mm,
                    16 * mm,
                    27 * mm,
                    29 * mm,
                    49 * mm,
                    35 * mm,
                    17 * mm,
                    17 * mm,
                    46 * mm,
                ],
                header=True,
                padding=3,
            )
        )

    story.append(_paragraph("Record edit history", styles["section"]))
    if audit["revisions"]:
        revision_rows = [
            [
                _paragraph("Edited", styles["small_header"]),
                _paragraph("Action", styles["small_header"]),
                _paragraph("Record", styles["small_header"]),
                _paragraph("Type", styles["small_header"]),
                _paragraph("Changed fields", styles["small_header"]),
            ]
        ]
        for revision in audit["revisions"]:
            revision_rows.append(
                [
                    _paragraph(_display_datetime(revision.created_at), styles["small"]),
                    _paragraph(revision.action.title(), styles["small"]),
                    _paragraph(revision.record_number, styles["small"]),
                    _paragraph(
                        revision.record_type.replace("_", " ").title(),
                        styles["small"],
                    ),
                    _paragraph(
                        ", ".join(
                            key.replace("_", " ").title()
                            for key in revision.changes
                        )
                        or "-",
                        styles["small"],
                    ),
                ]
            )
        story.append(
            _table(
                revision_rows,
                col_widths=[
                    38 * mm,
                    24 * mm,
                    32 * mm,
                    38 * mm,
                    135 * mm,
                ],
                header=True,
                padding=3,
            )
        )
    else:
        story.append(
            _paragraph(
                "This technician made no record edits in the selected period.",
                styles["body"],
            )
        )

    for record in audit["records"]:
        story.append(PageBreak())
        story.append(
            _paragraph(
                (
                    f"{record['record_number']} - {record['record_type']} "
                    f"({record['technician_role']})"
                ),
                styles["title"],
            )
        )
        story.append(
            _table(
                [
                    [
                        _paragraph("Project", styles["label"]),
                        _paragraph(record["customer_name"], styles["body"]),
                        _paragraph("Site", styles["label"]),
                        _paragraph(
                            record["work_site_name"] or record["site_name"],
                            styles["body"],
                        ),
                    ],
                    [
                        _paragraph("Submitted by", styles["label"]),
                        _paragraph(record["team_leader_name"], styles["body"]),
                        _paragraph("Submitted", styles["label"]),
                        _paragraph(
                            _display_datetime(record["submitted_at"]),
                            styles["body"],
                        ),
                    ],
                    [
                        _paragraph("Worked with", styles["label"]),
                        _paragraph(
                            ", ".join(record["participants"]) or "Worked alone",
                            styles["body"],
                        ),
                        _paragraph("Overall result", styles["label"]),
                        _paragraph(record["result"].label, styles["body"]),
                    ],
                ],
                col_widths=[28 * mm, 105 * mm, 28 * mm, 105 * mm],
            )
        )
        remaining_photos = PDF_PHOTOS_PER_RECORD
        for index, item in enumerate(record["items"], start=1):
            story.append(
                _paragraph(
                    (
                        f"Device {index}: {item['device_name']} - "
                        f"{item['device_model']} | {item['serial_number']}"
                    ),
                    styles["item"],
                )
            )
            story.append(
                _table(
                    [
                        [
                            _paragraph("Service", styles["label"]),
                            _paragraph(item["service_name"], styles["body"]),
                            _paragraph("Result", styles["label"]),
                            _paragraph(item["result"].label, styles["body"]),
                            _paragraph("Photos", styles["label"]),
                            _paragraph(len(item["photos"]), styles["body"]),
                        ]
                    ],
                    col_widths=[
                        24 * mm,
                        77 * mm,
                        21 * mm,
                        77 * mm,
                        20 * mm,
                        47 * mm,
                    ],
                )
            )
            narrative = [
                _paragraph("Notes", styles["label"]),
                _paragraph(item["notes"], styles["body"]),
            ]
            for label, field in (
                ("Issue found", "issue_description"),
                ("Recommendations", "recommendations"),
                ("Handover notes", "handover_notes"),
            ):
                if item[field]:
                    narrative.extend(
                        [
                            Spacer(1, 1.5 * mm),
                            _paragraph(label, styles["label"]),
                            _paragraph(item[field], styles["body"]),
                        ]
                    )
            story.append(KeepTogether(narrative))
            if include_photos:
                story.append(Spacer(1, 2 * mm))
                story.append(_paragraph("Evidence photos", styles["label"]))
                photos, omitted, remaining_photos = _bounded_item_photos(
                    item["photos"],
                    remaining_photos,
                )
                story.append(_photos_table(photos, styles))
                if omitted:
                    story.append(
                        _paragraph(
                            f"{omitted} additional evidence photo"
                            f"{'' if omitted == 1 else 's'} omitted from this PDF.",
                            styles["small"],
                        )
                    )

    document.build(
        story,
        onFirstPage=_header_footer,
        onLaterPages=_header_footer,
    )
    return buffer.getvalue()
