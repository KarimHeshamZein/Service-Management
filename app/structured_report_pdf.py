"""Professional PDF output for saved hierarchical service reports."""
from __future__ import annotations

import io
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from PIL import Image as PilImage, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
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
from .models import ServiceReport, ServiceReportType
from .pdf_text import pdf_text, style_for_pdf_text
from .uploads import UploadError, resolve_storage_path


NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#1F6F8B")
GREEN = colors.HexColor("#16845B")
PALE_BLUE = colors.HexColor("#EAF3F6")
PALE_GREEN = colors.HexColor("#E8F7F0")
SLATE = colors.HexColor("#526575")
LIGHT = colors.HexColor("#F4F7F9")
BORDER = colors.HexColor("#D7E0E6")
WHITE = colors.white
LOGO_PATH = Path(__file__).resolve().parent / "static" / "img" / "afaqylogo.png"


class _PageBreakUnlessAtTop(Flowable):
    """Start the next frame without creating an empty page at a fresh frame."""

    locChanger = 1

    def wrap(self, avail_width, avail_height):
        frame = self._doctemplateAttr("frame")
        if frame is not None and not frame._atTop:
            from reportlab.platypus.doctemplate import FrameBreak

            frame.add_generated_content(FrameBreak)
        return 0, 0

    def draw(self):
        pass


def _text(value: Any, fallback: str = "-") -> str:
    return pdf_text(value, fallback)


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "StructuredReportTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=NAVY,
            spaceAfter=2 * mm,
        ),
        "subtitle": ParagraphStyle(
            "StructuredReportSubtitle",
            parent=sample["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=SLATE,
        ),
        "main": ParagraphStyle(
            "StructuredMainProject",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=WHITE,
        ),
        "sub": ParagraphStyle(
            "StructuredSubProject",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            textColor=NAVY,
        ),
        "site": ParagraphStyle(
            "StructuredSite",
            parent=sample["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=GREEN,
        ),
        "section": ParagraphStyle(
            "StructuredPhotoSection",
            parent=sample["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=NAVY,
        ),
        "body": ParagraphStyle(
            "StructuredBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=NAVY,
        ),
        "small": ParagraphStyle(
            "StructuredSmall",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            textColor=SLATE,
        ),
        "small_center": ParagraphStyle(
            "StructuredSmallCenter",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=NAVY,
        ),
        "approval_role": ParagraphStyle(
            "StructuredApprovalRole",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=NAVY,
        ),
        "approval_hint": ParagraphStyle(
            "StructuredApprovalHint",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=9,
            alignment=TA_CENTER,
            textColor=SLATE,
        ),
        "table_header": ParagraphStyle(
            "StructuredTableHeader",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=9,
            textColor=WHITE,
        ),
    }


def _p(value: Any, style: ParagraphStyle, fallback: str = "-") -> Paragraph:
    return Paragraph(_text(value, fallback), style_for_pdf_text(value, style))


def _header_footer(canvas, doc, report_number: str = "") -> None:
    canvas.saveState()
    width, height = landscape(A4)
    canvas.setStrokeColor(BORDER)
    canvas.line(16 * mm, 12 * mm, width - 16 * mm, 12 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SLATE)
    canvas.drawString(16 * mm, 7.5 * mm, settings.app_name)
    if report_number:
        canvas.drawCentredString(width / 2, 7.5 * mm, report_number)
    canvas.drawRightString(width - 16 * mm, 7.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _metadata_table(report: ServiceReport, styles: dict[str, ParagraphStyle]) -> Table:
    technicians = ", ".join(person.name for person in report.technicians) or "-"
    rows = [
        ["Report number", report.report_number, "Report date", report.report_date.isoformat()],
        ["Created by", report.created_by_name, "Created at", report.created_at.strftime("%Y-%m-%d %H:%M")],
        ["Team Leader", report.team_leader_name, "Technicians", technicians],
    ]
    data = []
    for row in rows:
        data.append(
            [
                _p(row[0], styles["small"]),
                _p(row[1], styles["body"]),
                _p(row[2], styles["small"]),
                _p(row[3], styles["body"]),
            ]
        )
    table = Table(data, colWidths=[28 * mm, 78 * mm, 28 * mm, 126 * mm])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _photo_cell(photo: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any] | None:
    key = photo.get("thumbnail_key") or photo.get("storage_key")
    if not key:
        return None
    try:
        path = resolve_storage_path(str(key))
        with PilImage.open(path) as source:
            source = ImageOps.exif_transpose(source)
            if source.mode not in ("RGB", "L"):
                background = PilImage.new("RGB", source.size, "white")
                if "A" in source.getbands():
                    background.paste(source, mask=source.getchannel("A"))
                else:
                    background.paste(source)
                source = background
            source = source.convert("RGB")
            source_width, source_height = source.size
            scale = min(1640 / source_width, 960 / source_height)
            fitted = source.resize(
                (
                    max(1, round(source_width * scale)),
                    max(1, round(source_height * scale)),
                ),
                PilImage.Resampling.LANCZOS,
            )
            buffer = io.BytesIO()
            fitted.save(buffer, format="JPEG", quality=88, optimize=True)
            buffer.seek(0)
    except (UploadError, OSError, ValueError):
        return None
    width, height = fitted.size
    display_scale = min((82 * mm) / width, (48 * mm) / height)
    image = PdfImage(buffer, width=width * display_scale, height=height * display_scale)
    image.hAlign = "CENTER"
    frame = Table([[image]], colWidths=[82 * mm], rowHeights=[48 * mm])
    frame.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    cell: list[Any] = [frame]
    if photo.get("description"):
        cell.extend(
            [Spacer(1, 1.5 * mm), _p(photo["description"], styles["small_center"])]
        )
    return cell


def _photo_rows(photos: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> list[Any]:
    ordered = sorted(photos, key=lambda photo: (photo.get("position", 0), photo.get("original_filename", "")))
    cells = [cell for photo in ordered if (cell := _photo_cell(photo, styles)) is not None]
    if not cells:
        return [_p("No available photos.", styles["small"])]
    rows = [cells[index : index + 3] for index in range(0, len(cells), 3)]
    while len(rows[-1]) < 3:
        rows[-1].append("")
    tables: list[Table] = []
    for row in rows:
        table = Table([row], colWidths=[88 * mm] * 3, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
                    ("INNERGRID", (0, 0), (-1, -1), 0.45, BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        tables.append(table)
    return tables


def _photo_section(
    label: str,
    photos: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
    *,
    background,
    accent,
) -> list[Any]:
    rows = _photo_rows(photos, styles)
    banner = Table([[_p(label, styles["section"])]], colWidths=[264 * mm])
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    flowables: list[Any] = [
        KeepTogether(
            [
                Spacer(1, 2 * mm),
                banner,
                Spacer(1, 1.5 * mm),
                rows[0],
            ]
        )
    ]
    for row in rows[1:]:
        flowables.extend([Spacer(1, 1.5 * mm), row])
    return flowables


def _main_banner(
    main_name: str,
    customer_names: str,
    styles: dict[str, ParagraphStyle],
) -> Table:
    table = Table(
        [
            [_p(f"MAIN PROJECT  ·  {main_name}", styles["main"])],
            [_p(f"Customer: {customer_names or '-'}", styles["small"])],
        ],
        colWidths=[264 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _record_banner(record: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [_p(
                f"Record {record['record_number']} · {record['service_name']} · {record['result'].label}",
                styles["section"],
            )],
            [_p(
                f"Performed by {record['team_leader_name']} on {record['submitted_at']:%Y-%m-%d %H:%M}",
                styles["small"],
            )],
        ],
        colWidths=[264 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _device_card(
    item: dict[str, Any],
    styles: dict[str, ParagraphStyle],
    report_type: ServiceReportType,
) -> Table:
    rows: list[list[Any]] = [
        [_p(item.get("device_name"), styles["section"]), ""],
    ]
    details: list[tuple[str, Any]] = [
        ("Service", item.get("service_name")),
        ("Result", getattr(item.get("result"), "label", item.get("result"))),
    ]
    if report_type == ServiceReportType.INSTALLATION:
        details.extend(
            [
                ("Model", item.get("device_model")),
                ("Serial number", item.get("serial_number")),
                ("Warranty date", item.get("warranty_start")),
                ("Installation notes", item.get("notes")),
                ("Handover notes", item.get("handover_notes")),
            ]
        )
    else:
        details.extend(
            [
                ("Issue found", item.get("issue_description")),
                ("Recommendations", item.get("recommendations")),
            ]
        )
    rows.extend(
        [_p(label, styles["small"]), _p(value, styles["body"])]
        for label, value in details
    )
    table = Table(rows, colWidths=[38 * mm, 226 * mm])
    table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
                ("BACKGROUND", (0, 1), (0, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.55, BLUE),
                ("INNERGRID", (0, 1), (-1, -1), 0.35, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _approvals_block(styles: dict[str, ParagraphStyle]) -> list[Any]:
    roles = (
        "Customer Representative",
        "Afaqy Representative",
        "Project Manager",
    )
    cards: list[Any] = []
    for role in roles:
        cards.append(
            [
                _p(role, styles["approval_role"]),
                Spacer(1, 34 * mm),
                _p("____________________________", styles["approval_hint"]),
                _p("Signature & Stamp", styles["approval_hint"]),
            ]
        )
    table = Table([cards], colWidths=[86 * mm] * 3, rowHeights=[62 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.65, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.65, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return [
        _p("APPROVALS", styles["section"]),
        Spacer(1, 3 * mm),
        table,
    ]


def _stage_labels(report_type: ServiceReportType) -> dict[str, str]:
    if report_type == ServiceReportType.INSTALLATION:
        return {"before": "Before Installation", "after": "After Installation", "legacy": "Existing Evidence"}
    if report_type == ServiceReportType.MAINTENANCE:
        return {"before": "Before Maintenance", "after": "After Maintenance", "legacy": "Maintenance Evidence"}
    return {"before": "Before Preventive Maintenance", "after": "After Preventive Maintenance", "legacy": "Preventive Maintenance Evidence"}


def _device_table(entries: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    headers = [
        "Item / Device Name",
        "Model",
        "Serial Number",
        "IMEI",
        "SIM Serial Number",
        "Sim Type",
        "Main Project",
        "Sub Project",
        "Site",
        "Remarks",
        "Status",
    ]
    rows: list[list[Any]] = [[_p(value, styles["table_header"]) for value in headers]]
    for entry in entries:
        for item in entry["record"]["items"]:
            link = entry["link"]
            values = [
                item["device_name"],
                item["device_model"],
                item["serial_number"],
                item.get("imei"),
                item.get("iccid"),
                item.get("sim_type"),
                item.get("project_name") or link.main_project_name,
                item.get("sub_project_name") or link.sub_project_name,
                item.get("work_site_name") or item.get("location_name") or link.site_name,
                item.get("remarks"),
            ]
            rows.append(
                [
                    _p(values[0], styles["small"]),
                    _p(values[1], styles["small"]),
                    _p(values[2], styles["small"]),
                    _p(values[3], styles["small"]),
                    _p(values[4], styles["small"]),
                    _p(item["sim_type"].upper() if item.get("sim_type") else None, styles["small"]),
                    _p(values[6], styles["small"]),
                    _p(values[7], styles["small"]),
                    _p(values[8], styles["small"]),
                    _p(values[9], styles["small"]),
                    _p("Valid" if all(values) else "Invalid", styles["small"]),
                ]
            )
    widths = [28, 20, 24, 20, 26, 16, 25, 25, 20, 30, 16]
    table = Table(rows, colWidths=[value * mm for value in widths], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _direct_data_table(
    rows: list[dict[str, Any]],
    styles: dict[str, ParagraphStyle],
    *,
    installation: bool,
) -> Table:
    if installation:
        headers = [
            "No", "Item / Device Name", "Model", "Serial Number", "IMEI",
            "SIM Serial Number", "SIM Type", "Main Project", "Sub Project",
            "Site", "Remarks",
        ]
        body = [
            [
                index,
                row.get("item_name"), row.get("model"), row.get("serial_number"),
                row.get("imei"), row.get("iccid"), row.get("sim_type"),
                row.get("project_name"), row.get("sub_project_name"),
                row.get("work_site_name"), row.get("remarks"),
            ]
            for index, row in enumerate(rows, 1)
        ]
        widths = [8, 32, 23, 23, 22, 27, 16, 25, 25, 22, 34]
    else:
        headers = ["No", "Item", "Quantity", "Notes"]
        body = [
            [index, row.get("item_name"), row.get("quantity"), row.get("notes")]
            for index, row in enumerate(rows, 1)
        ]
        widths = [15, 70, 28, 150]
    table_rows = [[_p(value, styles["table_header"]) for value in headers]]
    table_rows.extend(
        [[_p(value, styles["small"]) for value in values] for values in body]
    )
    table = Table(
        table_rows,
        colWidths=[value * mm for value in widths],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _scoped_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand one parent record into render-only site sections without duplicating its ID."""
    scoped: list[dict[str, Any]] = []
    for entry in entries:
        source_link = entry["link"]
        groups: OrderedDict[tuple[Any, ...], list[dict[str, Any]]] = OrderedDict()
        for item in entry["record"]["items"]:
            key = (
                item.get("scope_position", 0),
                item.get("project_id") or source_link.main_project_id,
                item.get("project_name") or source_link.main_project_name,
                item.get("sub_project_id") or source_link.sub_project_id,
                item.get("sub_project_name") or source_link.sub_project_name,
                item.get("work_site_id") or source_link.site_id,
                item.get("work_site_name") or source_link.site_name,
            )
            groups.setdefault(key, []).append(item)
        if not groups:
            groups[(0, source_link.main_project_id, source_link.main_project_name, source_link.sub_project_id, source_link.sub_project_name, source_link.site_id, source_link.site_name)] = []
        for key, items in groups.items():
            data_rows = [
                row
                for row in entry["record"].get("data_rows", [])
                if (
                    row.get("scope_position", 0) == key[0]
                    and (row.get("project_id") or key[1]) == key[1]
                    and (row.get("sub_project_id") or key[3]) == key[3]
                    and (row.get("work_site_id") or key[5]) == key[5]
                )
            ]
            scoped.append(
                {
                    "link": SimpleNamespace(
                        main_project_id=key[1],
                        main_project_name=key[2],
                        customer_names=source_link.customer_names,
                        sub_project_id=key[3],
                        sub_project_name=key[4],
                        site_id=key[5],
                        site_name=key[6],
                    ),
                    "record": {
                        **entry["record"],
                        "items": items,
                        "data_rows": data_rows,
                    },
                }
            )
    return scoped


def build_structured_report_pdf(
    report: ServiceReport,
    entries: list[dict[str, Any]],
    *,
    include_device_data: bool = False,
) -> bytes:
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=17 * mm,
        title=f"{report.report_number} — {report.name}",
        author=report.created_by_name,
    )
    styles = _styles()
    story: list[Any] = []
    render_entries = _scoped_entries(entries)

    logo = ""
    if LOGO_PATH.is_file():
        logo = PdfImage(str(LOGO_PATH), width=35 * mm, height=35 * mm * 133 / 380)
    heading = [
        _p(report.name, styles["title"]),
        _p(f"{report.report_type.label} Report · {report.report_number}", styles["subtitle"]),
    ]
    header = Table([[logo, heading]], colWidths=[44 * mm, 220 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.extend([header, _metadata_table(report, styles)])
    if report.notes:
        story.extend([Spacer(1, 3 * mm), _p(f"Notes: {report.notes}", styles["body"])])
    story.append(Spacer(1, 5 * mm))

    hierarchy: OrderedDict[str, OrderedDict[str, OrderedDict[str, list[dict[str, Any]]]]] = OrderedDict()
    links: dict[tuple[str, str], Any] = {}
    for entry in render_entries:
        link = entry["link"]
        hierarchy.setdefault(link.main_project_name, OrderedDict()).setdefault(
            link.sub_project_name, OrderedDict()
        ).setdefault(link.site_name, []).append(entry["record"])
        links[(link.main_project_name, link.sub_project_name)] = link

    stage_labels = _stage_labels(report.report_type)
    first_site = True
    for main_name, sub_projects in hierarchy.items():
        if not first_site:
            story.append(PageBreak())
        main_link = next(entry["link"] for entry in render_entries if entry["link"].main_project_name == main_name)
        main_table = _main_banner(
            main_name,
            main_link.customer_names,
            styles,
        )
        story.extend([main_table, Spacer(1, 2 * mm)])
        first_sub = True
        for sub_name, sites in sub_projects.items():
            if not first_sub:
                story.extend(
                    [
                        PageBreak(),
                        _main_banner(main_name, main_link.customer_names, styles),
                        Spacer(1, 2 * mm),
                    ]
                )
            first_sub = False
            story.append(_p(f"SUB PROJECT  ·  {sub_name}", styles["sub"]))
            story.append(Spacer(1, 1 * mm))
            first_site_in_sub = True
            for site_name, records in sites.items():
                if not first_site_in_sub:
                    story.extend(
                        [
                            PageBreak(),
                            _main_banner(main_name, main_link.customer_names, styles),
                            Spacer(1, 2 * mm),
                            _p(f"SUB PROJECT / {sub_name}", styles["sub"]),
                        ]
                    )
                first_site_in_sub = False
                first_site = False
                site_banner = Table(
                    [[_p(f"SITE  ·  {site_name}", styles["site"]) ]],
                    colWidths=[264 * mm],
                )
                site_banner.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
                            ("BOX", (0, 0), (-1, -1), 0.7, GREEN),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )
                story.extend([site_banner, Spacer(1, 2 * mm)])
                for record_index, record in enumerate(records):
                    if record_index:
                        story.append(_PageBreakUnlessAtTop())
                    for item_index, item in enumerate(record["items"]):
                        if item_index:
                            story.append(_PageBreakUnlessAtTop())
                        story.append(
                            KeepTogether(
                                [
                                    _record_banner(record, styles),
                                    Spacer(1, 2 * mm),
                                    _device_card(item, styles, report.report_type),
                                ]
                            )
                        )
                        photos = item.get("photos") or []
                        if not photos:
                            continue
                        story.extend(
                            [
                                _PageBreakUnlessAtTop(),
                                _p("PHOTO EVIDENCE", styles["sub"]),
                                Spacer(1, 1.5 * mm),
                            ]
                        )
                        story.append(_p(item.get("device_name"), styles["section"]))
                        for stage in ("before", "after", "legacy"):
                            staged = [photo for photo in photos if photo.get("stage") == stage]
                            if not staged:
                                continue
                            stage_colors = {
                                "before": (PALE_BLUE, BLUE),
                                "after": (PALE_GREEN, GREEN),
                                "legacy": (LIGHT, SLATE),
                            }
                            background, accent = stage_colors[stage]
                            story.extend(
                                _photo_section(
                                    stage_labels[stage],
                                    staged,
                                    styles,
                                    background=background,
                                    accent=accent,
                                )
                            )

    if include_device_data and render_entries:
        table_sections = []
        for entry in render_entries:
            direct_rows = entry["record"].get("data_rows", [])
            imported_items = [
                item for item in entry["record"]["items"]
                if item.get("imported_from_excel")
            ]
            if direct_rows or imported_items:
                table_sections.append((entry, direct_rows, imported_items))
        if table_sections:
            story.extend(
                [
                    PageBreak(),
                    _p("SERVICE DATA TABLES", styles["title"]),
                    _p("Data recorded for each selected Site during service entry.", styles["subtitle"]),
                ]
            )
            for section_index, (entry, direct_rows, imported_items) in enumerate(table_sections):
                link = entry["link"]
                if section_index:
                    story.append(Spacer(1, 7 * mm))
                scope_header = Table(
                    [[_p(
                        f"MAIN PROJECT | {link.main_project_name}    "
                        f"SUB PROJECT | {link.sub_project_name}    "
                        f"SITE | {link.site_name}",
                        styles["section"],
                    )]],
                    colWidths=[264 * mm],
                )
                scope_header.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
                            ("BOX", (0, 0), (-1, -1), 0.55, BLUE),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                        ]
                    )
                )
                story.extend(
                    [
                        scope_header,
                        Spacer(1, 2 * mm),
                    ]
                )
                if direct_rows:
                    story.append(
                        _direct_data_table(
                            direct_rows,
                            styles,
                            installation=entry["record"].get("record_key") == "installation",
                        )
                    )
                else:
                    story.append(
                        _device_table(
                            [{"link": link, "record": {**entry["record"], "items": imported_items}}],
                            styles,
                        )
                    )

    story.extend([CondPageBreak(75 * mm), *_approvals_block(styles)])

    def draw_page(canvas, doc) -> None:
        _header_footer(canvas, doc, report.report_number)

    document.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    return buffer.getvalue()
