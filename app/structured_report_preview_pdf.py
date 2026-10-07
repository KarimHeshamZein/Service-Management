"""Isolated customer-report redesign preview.

This module intentionally does not replace or alter the production structured
report renderer. Each approved redesign section can be developed here and
reviewed independently before any default is changed.
"""
from __future__ import annotations

import io
from collections import OrderedDict
from pathlib import Path
from typing import Any

from PIL import Image as PilImage, ImageChops, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image as PdfImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .config import settings
from .helpers import to_display
from .models import MaintenanceResult, ServiceReport
from .pdf_text import pdf_text, style_for_pdf_text
from .structured_report_pdf import _report_summary, _scoped_entries


NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#1F6F8B")
GREEN = colors.HexColor("#16845B")
AMBER = colors.HexColor("#C9840D")
RED = colors.HexColor("#B64242")
SLATE = colors.HexColor("#526575")
LIGHT = colors.HexColor("#F4F7F9")
BORDER = colors.HexColor("#C8D5DE")
WHITE = colors.white
PALE_BLUE = colors.HexColor("#EAF3F6")
PALE_GREEN = colors.HexColor("#E8F7F0")
PALE_AMBER = colors.HexColor("#FFF5DE")
PALE_RED = colors.HexColor("#FCECEC")
LOGO_PATH = Path(__file__).resolve().parent / "static" / "img" / "afaqylogo.png"


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "PreviewEyebrow",
            parent=sample["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=BLUE,
            spaceAfter=2 * mm,
        ),
        "cover_title": ParagraphStyle(
            "PreviewCoverTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=31,
            textColor=NAVY,
            spaceAfter=3 * mm,
        ),
        "cover_name": ParagraphStyle(
            "PreviewCoverName",
            parent=sample["Heading2"],
            fontName="Helvetica",
            fontSize=15,
            leading=20,
            textColor=SLATE,
        ),
        "page_title": ParagraphStyle(
            "PreviewPageTitle",
            parent=sample["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=NAVY,
        ),
        "body": ParagraphStyle(
            "PreviewBody",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=NAVY,
        ),
        "small": ParagraphStyle(
            "PreviewSmall",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10.5,
            textColor=SLATE,
        ),
        "small_bold": ParagraphStyle(
            "PreviewSmallBold",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10.5,
            textColor=NAVY,
        ),
        "metric": ParagraphStyle(
            "PreviewMetric",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=23,
            alignment=TA_CENTER,
            textColor=NAVY,
        ),
        "metric_label": ParagraphStyle(
            "PreviewMetricLabel",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=SLATE,
        ),
        "status": ParagraphStyle(
            "PreviewStatus",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=18,
            alignment=TA_CENTER,
            textColor=NAVY,
        ),
        "status_label": ParagraphStyle(
            "PreviewStatusLabel",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=9.5,
            alignment=TA_CENTER,
            textColor=NAVY,
        ),
        "table_header": ParagraphStyle(
            "PreviewTableHeader",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=WHITE,
        ),
        "photo_caption": ParagraphStyle(
            "PreviewPhotoCaption",
            parent=sample["BodyText"],
            fontName="Helvetica",
            fontSize=11.5,
            leading=14,
            alignment=TA_CENTER,
            textColor=NAVY,
        ),
        "photo_number": ParagraphStyle(
            "PreviewPhotoNumber",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            alignment=TA_LEFT,
            textColor=NAVY,
        ),
        "photo_issue": ParagraphStyle(
            "PreviewPhotoIssue",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            alignment=TA_RIGHT,
            textColor=RED,
        ),
        "photo_section_title": ParagraphStyle(
            "PreviewPhotoSectionTitle",
            parent=sample["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=19,
            textColor=WHITE,
        ),
        "photo_section_count": ParagraphStyle(
            "PreviewPhotoSectionCount",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13,
            alignment=TA_RIGHT,
            textColor=WHITE,
        ),
        "photo_section_end": ParagraphStyle(
            "PreviewPhotoSectionEnd",
            parent=sample["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=13,
            alignment=TA_CENTER,
            textColor=BLUE,
        ),
    }


def _p(value: Any, style: ParagraphStyle, fallback: str = "-") -> Paragraph:
    return Paragraph(pdf_text(value, fallback), style_for_pdf_text(value, style))


def _display_datetime(value: Any) -> str:
    return to_display(value).strftime("%Y-%m-%d %H:%M")


def _draw_logo_watermark(canvas) -> None:
    """Draw the existing AFAQY artwork softly behind page content."""
    if not LOGO_PATH.is_file():
        return
    try:
        with PilImage.open(LOGO_PATH) as source:
            rgb = source.convert("RGB")
            watermark = rgb.convert("RGBA")
            # White becomes fully transparent while the logo colours remain at
            # a deliberately light print-safe opacity.
            darkness = ImageOps.grayscale(ImageChops.invert(rgb))
            alpha = darkness.point(lambda value: min(32, round(value * 0.14)))
            watermark.putalpha(alpha)
            image_buffer = io.BytesIO()
            watermark.save(image_buffer, format="PNG")
            image_buffer.seek(0)
            image_reader = ImageReader(image_buffer)
            source_width, source_height = watermark.size
            display_width = 155 * mm
            display_height = display_width * source_height / source_width
            page_width, page_height = landscape(A4)
            canvas.drawImage(
                image_reader,
                (page_width - display_width) / 2,
                (page_height - display_height) / 2,
                width=display_width,
                height=display_height,
                mask="auto",
                preserveAspectRatio=True,
            )
    except (OSError, ValueError):
        return


def _preview_footer(canvas, doc, report_number: str) -> None:
    canvas.saveState()
    width, height = landscape(A4)
    _draw_logo_watermark(canvas)
    canvas.setStrokeColor(BORDER)
    canvas.line(16 * mm, 12 * mm, width - 16 * mm, 12 * mm)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.setFillColor(AMBER)
    canvas.drawString(16 * mm, 7.5 * mm, "DESIGN PREVIEW - NOT FINAL")
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(SLATE)
    canvas.drawCentredString(width / 2, 7.5 * mm, report_number)
    canvas.drawRightString(width - 16 * mm, 7.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _cover(report: ServiceReport, summary: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    logo: Any = ""
    if LOGO_PATH.is_file():
        logo = PdfImage(str(LOGO_PATH), width=54 * mm, height=54 * mm * 133 / 380)
    brand = Table([[logo, _p(settings.app_name, styles["small_bold"])]], colWidths=[60 * mm, 194 * mm])
    brand.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))

    report_number = Table(
        [[_p("REPORT NUMBER", styles["table_header"]), _p(report.report_number, styles["body"])]],
        colWidths=[34 * mm, 58 * mm],
        hAlign="LEFT",
    )
    report_number.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (0, 0), WHITE),
                ("BACKGROUND", (1, 0), (1, 0), PALE_BLUE),
                ("BOX", (0, 0), (-1, -1), 0.7, NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    details = [
        ["Customer", summary["customers"], "Report date", report.report_date.isoformat()],
        ["Reporting period", summary["period"], "Created by", report.created_by_name],
        ["Team Leader", report.team_leader_name, "Created at", _display_datetime(report.created_at)],
    ]
    detail_rows = []
    for row in details:
        detail_rows.append(
            [
                _p(row[0], styles["small"]),
                _p(row[1], styles["body"]),
                _p(row[2], styles["small"]),
                _p(row[3], styles["body"]),
            ]
        )
    detail_table = Table(detail_rows, colWidths=[30 * mm, 94 * mm, 30 * mm, 110 * mm])
    detail_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.55, BORDER),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    preview_notice = Table(
        [[_p("PART 1 PREVIEW - Cover and Executive Summary only. The official PDF is unchanged.", styles["small_bold"])]],
        colWidths=[264 * mm],
    )
    preview_notice.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE_AMBER),
                ("BOX", (0, 0), (-1, -1), 0.7, AMBER),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [
        brand,
        Spacer(1, 17 * mm),
        _p(report.report_type.label.upper(), styles["eyebrow"]),
        _p(f"{report.report_type.label.title()} Report", styles["cover_title"]),
        _p(report.name, styles["cover_name"]),
        Spacer(1, 8 * mm),
        report_number,
        Spacer(1, 16 * mm),
        detail_table,
        Spacer(1, 12 * mm),
        preview_notice,
    ]


def _project_rows(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projects: OrderedDict[tuple[Any, Any], dict[str, Any]] = OrderedDict()
    for entry in entries:
        link = entry["link"]
        record = entry["record"]
        key = (link.main_project_id, link.main_project_name)
        project = projects.setdefault(
            key,
            {
                "name": link.main_project_name,
                "sites": set(),
                "records": set(),
                "services": 0,
                "attention": 0,
            },
        )
        project["sites"].add((link.sub_project_id, link.site_id, link.site_name))
        project["records"].add((record.get("record_key"), record.get("id") or record.get("record_number")))
        items = record.get("items") or []
        project["services"] += max(1, len(items))
        for item in items or [record]:
            project["attention"] += sum(
                1
                for photo in item.get("photos") or []
                if photo.get("is_issue_found")
                and str(photo.get("description") or "").strip()
            )
    return list(projects.values())


def _photo_issues(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for entry in entries:
        link = entry["link"]
        record = entry["record"]
        for item in record.get("items") or [record]:
            for photo in item.get("photos") or []:
                description = str(photo.get("description") or "").strip()
                if not photo.get("is_issue_found") or not description:
                    continue
                stage = str(photo.get("stage") or "").strip().lower()
                issues.append(
                    {
                        "project_site": f"{link.main_project_name} / {link.site_name}",
                        "record_service": (
                            f"{record.get('record_number') or '-'} / "
                            f"{item.get('device_name') or item.get('service_name') or '-'}"
                        ),
                        "stage": "Before" if stage == "before" else "After" if stage == "after" else "Photo",
                        "description": description,
                    }
                )
    return issues


def _metric_cards(values: list[tuple[Any, str]], styles: dict[str, ParagraphStyle]) -> Table:
    cells = [[_p(value, styles["metric"]), _p(label, styles["metric_label"])] for value, label in values]
    table = Table([cells], colWidths=[264 * mm / len(cells)] * len(cells))
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, BORDER),
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return table


def _status_cards(summary: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    counts = summary["status_counts"]
    values = [
        (counts[MaintenanceResult.COMPLETED_SUCCESSFULLY.value], "Successful", PALE_GREEN, GREEN),
        (counts[MaintenanceResult.COMPLETED_WITH_OBSERVATIONS.value], "With observations", PALE_AMBER, AMBER),
        (counts[MaintenanceResult.FURTHER_ACTION_REQUIRED.value], "Further action", PALE_RED, RED),
        (counts[MaintenanceResult.UNABLE_TO_COMPLETE.value], "Unable to complete", LIGHT, SLATE),
    ]
    cells = [[_p(value, styles["status"]), _p(label, styles["status_label"])] for value, label, _, _ in values]
    table = Table([cells], colWidths=[66 * mm] * 4)
    commands: list[tuple] = [
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]
    for index, (_, _, background, accent) in enumerate(values):
        commands.extend(
            [
                ("BACKGROUND", (index, 0), (index, 0), background),
                ("LINEABOVE", (index, 0), (index, 0), 3, accent),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def _summary_page(report: ServiceReport, entries: list[dict[str, Any]], summary: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    page_logo: Any = ""
    if LOGO_PATH.is_file():
        page_logo = PdfImage(str(LOGO_PATH), width=38 * mm, height=38 * mm * 133 / 380)
    projects = _project_rows(entries)
    issue_count = sum(project["attention"] for project in projects)
    headers = ["Main Project", "Sites", "Records", "Services", "Need attention"]
    rows: list[list[Any]] = [[_p(value, styles["table_header"]) for value in headers]]
    for project in projects[:8]:
        rows.append(
            [
                _p(project["name"], styles["body"]),
                _p(len(project["sites"]), styles["body"]),
                _p(len(project["records"]), styles["body"]),
                _p(project["services"], styles["body"]),
                _p(project["attention"], styles["body"]),
            ]
        )
    if len(projects) > 8:
        rows.append([_p(f"+ {len(projects) - 8} more Main Projects", styles["small_bold"]), "", "", "", ""])
    project_table = Table(rows, colWidths=[120 * mm, 32 * mm, 32 * mm, 36 * mm, 44 * mm], repeatRows=1)
    project_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.55, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return [
        Table(
            [[page_logo, _p("EXECUTIVE SUMMARY", styles["page_title"]), _p(f"{report.report_number} | {report.report_date.isoformat()}", styles["small"])]],
            colWidths=[44 * mm, 130 * mm, 90 * mm],
            style=[
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
            ],
        ),
        Spacer(1, 4 * mm),
        _metric_cards(
            [
                (summary["main_count"], "Main Projects"),
                (summary["sub_count"], "Sub Projects"),
                (summary["site_count"], "Sites"),
                (summary["record_count"], "Records"),
                (summary["service_total"], "Devices / Services"),
            ],
            styles,
        ),
        Spacer(1, 5 * mm),
        _p("RESULT OVERVIEW", styles["eyebrow"]),
        _status_cards(summary, styles),
        Spacer(1, 6 * mm),
        _p("MAIN PROJECT OVERVIEW", styles["eyebrow"]),
        project_table,
        Spacer(1, 5 * mm),
        Table(
            [[_p(
                (
                    f"{issue_count} photo issue(s) marked for the Issues Summary."
                    if issue_count
                    else "No photos are currently marked as Issue Found."
                ),
                styles["small_bold"],
            )]],
            colWidths=[264 * mm],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), PALE_AMBER if issue_count else PALE_GREEN),
                ("BOX", (0, 0), (-1, -1), 0.7, AMBER if issue_count else GREEN),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ],
        ),
    ]


def _issues_page(report: ServiceReport, entries: list[dict[str, Any]], styles: dict[str, ParagraphStyle]) -> list[Any]:
    page_logo: Any = ""
    if LOGO_PATH.is_file():
        page_logo = PdfImage(str(LOGO_PATH), width=38 * mm, height=38 * mm * 133 / 380)
    header = Table(
        [[page_logo, _p("PHOTO ISSUES SUMMARY", styles["page_title"]), _p(report.report_number, styles["small"])]],
        colWidths=[44 * mm, 130 * mm, 90 * mm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "LEFT"),
            ("ALIGN", (2, 0), (2, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
        ],
    )
    issues = _photo_issues(entries)
    if not issues:
        empty = Table(
            [[_p("No Before or After photo is marked as Issue Found in the selected records.", styles["small_bold"])]],
            colWidths=[264 * mm],
            style=[
                ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN),
                ("BOX", (0, 0), (-1, -1), 0.7, GREEN),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ],
        )
        return [header, Spacer(1, 8 * mm), empty]

    rows: list[list[Any]] = [[
        _p("#", styles["table_header"]),
        _p("Main Project / Site", styles["table_header"]),
        _p("Record / Service", styles["table_header"]),
        _p("Stage", styles["table_header"]),
        _p("Issue description from photo", styles["table_header"]),
    ]]
    for index, issue in enumerate(issues, 1):
        rows.append([
            _p(index, styles["body"]),
            _p(issue["project_site"], styles["body"]),
            _p(issue["record_service"], styles["body"]),
            _p(issue["stage"], styles["body"]),
            _p(issue["description"], styles["body"]),
        ])
    table = Table(rows, colWidths=[10 * mm, 60 * mm, 62 * mm, 24 * mm, 108 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.55, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return [
        header,
        Spacer(1, 5 * mm),
        _p("Only photos explicitly marked by the technician are listed here. The photo description is the issue text.", styles["small"]),
        Spacer(1, 4 * mm),
        table,
    ]


def build_structured_report_preview_pdf(report: ServiceReport, entries: list[dict[str, Any]]) -> bytes:
    """Build the isolated Part 1 design preview; never the official report."""
    render_entries = _scoped_entries(entries)
    summary = _report_summary(render_entries)
    styles = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=20 * mm,
        bottomMargin=17 * mm,
        title=f"Design preview - {report.report_number}",
        author=report.created_by_name,
    )
    story = [
        *_cover(report, summary, styles),
        PageBreak(),
        *_summary_page(report, render_entries, summary, styles),
        PageBreak(),
        *_issues_page(report, render_entries, styles),
    ]
    footer = lambda canvas, doc: _preview_footer(canvas, doc, report.report_number)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _fixed_photo_card(
    photo: dict[str, Any],
    number: int,
    total: int,
    styles: dict[str, ParagraphStyle],
) -> Table:
    path = Path(photo["path"])
    # Every photo receives the same landscape display frame. The source image
    # keeps its aspect ratio, so portrait photos are centred with side space
    # instead of being cropped or stretched.
    max_width = 80 * mm
    max_height = 41 * mm
    with PilImage.open(path) as source:
        source_width, source_height = source.size
    scale = min(max_width / source_width, max_height / source_height)
    image = PdfImage(
        str(path),
        width=max(1, source_width * scale),
        height=max(1, source_height * scale),
    )
    image_frame = Table(
        [[image]],
        colWidths=[82 * mm],
        rowHeights=[43 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ],
    )
    top = Table(
        [[
            _p(f"PHOTO {number} OF {total}", styles["photo_number"]),
            _p("ISSUE FOUND" if photo.get("is_issue_found") else "", styles["photo_issue"], ""),
        ]],
        colWidths=[49 * mm, 33 * mm],
        style=[
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ],
    )
    card = Table(
        [[top], [image_frame], [_p(photo.get("description"), styles["photo_caption"], "-")]],
        colWidths=[82 * mm],
        style=[
            ("BOX", (0, 0), (-1, -1), 1.35, RED if photo.get("is_issue_found") else SLATE),
            ("LINEBELOW", (0, 0), (-1, 0), 1.0, BORDER),
            ("LINEABOVE", (0, 2), (-1, 2), 1.0, SLATE),
            ("BACKGROUND", (0, 0), (-1, 0), PALE_RED if photo.get("is_issue_found") else WHITE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 1), 0),
            ("LEFTPADDING", (0, 2), (-1, 2), 6),
            ("RIGHTPADDING", (0, 2), (-1, 2), 6),
            ("TOPPADDING", (0, 2), (-1, 2), 6),
            ("BOTTOMPADDING", (0, 2), (-1, 2), 7),
        ],
    )
    return card


def _photo_section_preview(
    photos: list[dict[str, Any]],
    *,
    stage: str,
    styles: dict[str, ParagraphStyle],
) -> list[Any]:
    accent = NAVY if stage.lower() == "before" else GREEN
    title = f"{stage.upper()} PHOTOS"
    count = len(photos)
    header = Table(
        [[_p(title, styles["photo_section_title"]), _p(f"{count} PHOTOS", styles["photo_section_count"])]],
        colWidths=[184 * mm, 80 * mm],
        rowHeights=[12 * mm],
        style=[
            ("BACKGROUND", (0, 0), (-1, -1), accent),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 9),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ],
    )
    story: list[Any] = [header, Spacer(1, 4 * mm)]
    for row_start in range(0, count, 3):
        row_photos = photos[row_start : row_start + 3]
        cards = [
            _fixed_photo_card(photo, row_start + offset + 1, count, styles)
            for offset, photo in enumerate(row_photos)
        ]
        row = Table(
            [cards],
            colWidths=[86 * mm] * len(cards),
            hAlign="CENTER",
            style=[
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ],
        )
        story.append(row)
        if row_start + 3 < count:
            story.append(Spacer(1, 4 * mm))
    story.extend([
        Spacer(1, 5 * mm),
        Table(
            [[_p(f"END OF {title}", styles["photo_section_end"])]],
            colWidths=[264 * mm],
            style=[
                ("LINEABOVE", (0, 0), (-1, -1), 2.0, accent),
                ("TEXTCOLOR", (0, 0), (-1, -1), accent),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
            ],
        ),
    ])
    return story


def build_photo_layout_preview_pdf(
    photos: list[dict[str, Any]],
    *,
    stage: str = "Before",
    report_number: str = "PHOTO-LAYOUT-PREVIEW",
) -> bytes:
    """Build a standalone photo-layout prototype without querying the database."""
    styles = _styles()
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=24 * mm,
        bottomMargin=17 * mm,
        title=f"Photo layout preview - {report_number}",
        pageCompression=1,
    )
    def preview_page(canvas, doc) -> None:
        _preview_footer(canvas, doc, report_number)
        if not LOGO_PATH.is_file():
            return
        canvas.saveState()
        logo_width = 34 * mm
        logo_height = logo_width * 133 / 380
        _, page_height = landscape(A4)
        canvas.drawImage(
            str(LOGO_PATH),
            16 * mm,
            page_height - 18 * mm,
            width=logo_width,
            height=logo_height,
            preserveAspectRatio=True,
            mask="auto",
        )
        canvas.restoreState()
    document.build(
        _photo_section_preview(photos, stage=stage, styles=styles),
        onFirstPage=preview_page,
        onLaterPages=preview_page,
    )
    return buffer.getvalue()
