from __future__ import annotations

import io
import struct
import zlib
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.enums import TA_LEFT, TA_RIGHT

import app.structured_report_pdf as report_pdf
from app.models import MaintenanceResult, ServiceReportType
from app.routers import structured_reports as reports_router
from app.uploads import UploadError, validate_image


def _report_payload(*, issue: str, recommendation: str, photos=None):
    report = SimpleNamespace(
        id=41,
        report_number="PMR-2026-00041",
        name="Preventive maintenance report",
        report_type=ServiceReportType.PREVENTIVE_MAINTENANCE,
        report_date=date(2026, 9, 24),
        created_by_name="Administrator",
        created_at=datetime(2026, 9, 24, 12, 0),
        team_leader_name="Technical Team",
        notes=None,
    )
    link = SimpleNamespace(
        main_project_id=1,
        main_project_name="Qiddiya",
        customer_names="Qiddiya",
        sub_project_id=1,
        sub_project_name="General",
        site_id=1,
        site_name="Uptown A",
    )
    item = {
        "scope_position": 0,
        "project_id": 1,
        "project_name": "Qiddiya",
        "sub_project_id": 1,
        "sub_project_name": "General",
        "work_site_id": 1,
        "work_site_name": "Uptown A",
        "device_name": "Smart Gate Barrier",
        "service_name": "Smart Gate Barrier",
        "result": MaintenanceResult.FURTHER_ACTION_REQUIRED,
        "device_model": None,
        "serial_number": None,
        "notes": None,
        "issue_description": issue,
        "recommendations": recommendation,
        "photos": photos or [],
    }
    record = {
        "record_key": "maintenance",
        "id": 9,
        "record_number": "PM-2026-00009",
        "service_name": "Smart Gate Barrier",
        "result": MaintenanceResult.FURTHER_ACTION_REQUIRED,
        "team_leader_name": "Technical Team",
        "submitted_at": datetime(2026, 9, 24, 10, 0),
        "items": [item],
        "data_rows": [],
    }
    return report, [{"link": link, "record": record}]


def _oversized_png_header() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    dimensions = struct.pack(">IIBBBBB", 100_000, 100_000, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", dimensions)
        + chunk(b"IEND", b"")
    )


def test_pdf_splits_narratives_taller_than_one_page():
    repeated = "Electrical surge inspection and corrective action required. " * 450
    issue = repeated + " تم فحص الموقع وتسجيل المشكلة."
    report, entries = _report_payload(issue=issue, recommendation=repeated)

    content = report_pdf.build_structured_report_pdf(report, entries)

    assert content.startswith(b"%PDF")
    assert len(PdfReader(io.BytesIO(content)).pages) > 6


def test_pdf_preserves_latin_text_and_direction_in_bilingual_narratives():
    issue = (
        "A report was received regarding a gate system malfunction.\n\n"
        "تم استلام بلاغ بخصوص وجود عطل في نظام البوابات Barrier Gates، "
        "وتم رفع بلاغ رقم 3418."
    )
    recommendation = (
        "Inspect the generators and the ATS before restoring power.\n\n"
        "يوصى بفحص المولدات ونظام التحويل قبل إعادة التيار الكهربائي."
    )
    report, entries = _report_payload(issue=issue, recommendation=recommendation)

    content = report_pdf.build_structured_report_pdf(report, entries)
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages
    )
    paragraphs = report_pdf._multilingual_paragraphs(issue, report_pdf._styles()["body"])
    rendered_paragraphs = [
        flowable for flowable in paragraphs if hasattr(flowable, "style")
    ]

    assert "\x00" not in extracted
    assert extracted.count("A report was received regarding a gate system malfunction.") == 2
    assert extracted.count("Inspect the generators and the ATS before restoring power.") == 2
    assert extracted.count("Barrier Gates") == 2
    assert "3418" in extracted
    assert rendered_paragraphs[0].style.alignment == TA_LEFT
    assert rendered_paragraphs[1].style.alignment == TA_RIGHT
    assert 'font name="NotoSansArabic"' in rendered_paragraphs[1].text


def test_pdf_falls_back_to_original_when_thumbnail_is_unreadable(
    monkeypatch, tmp_path, caplog
):
    bad_thumbnail = tmp_path / "bad-thumbnail.png"
    bad_thumbnail.write_bytes(_oversized_png_header())
    original = tmp_path / "original.jpg"
    Image.new("RGB", (80, 60), "blue").save(original, format="JPEG")
    paths = {"bad-thumbnail": bad_thumbnail, "original": original}
    monkeypatch.setattr(report_pdf, "resolve_storage_path", paths.__getitem__)
    photos = [
        {
            "thumbnail_key": "bad-thumbnail",
            "storage_key": "original",
            "stage": "before",
            "position": 0,
            "description": "Gate power supply evidence.",
        }
    ]
    report, entries = _report_payload(
        issue="Power supply failure.",
        recommendation="Inspect the electrical supply.",
        photos=photos,
    )

    content = report_pdf.build_structured_report_pdf(report, entries)

    assert content.startswith(b"%PDF")
    assert "Skipping unreadable report photo file bad-thumbnail" in caplog.text


def test_pdf_uses_placeholder_if_all_photo_files_are_unreadable(
    monkeypatch, tmp_path
):
    bad_photo = tmp_path / "bad-photo.png"
    bad_photo.write_bytes(_oversized_png_header())
    monkeypatch.setattr(report_pdf, "resolve_storage_path", lambda key: bad_photo)
    photos = [
        {
            "thumbnail_key": "bad-thumbnail",
            "storage_key": "bad-original",
            "stage": "before",
            "position": 0,
        }
    ]
    report, entries = _report_payload(
        issue="Power supply failure.",
        recommendation="Inspect the electrical supply.",
        photos=photos,
    )

    content = report_pdf.build_structured_report_pdf(report, entries)

    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    assert "Photo unavailable." in text


def test_upload_validation_rejects_unsafe_image_dimensions():
    with pytest.raises(UploadError, match="could not be read as an image"):
        validate_image("oversized.png", _oversized_png_header())


def test_pdf_route_logs_report_identity_and_traceback(monkeypatch, caplog):
    report = SimpleNamespace(
        id=41,
        report_number="PMR-2026-00041",
        report_type=ServiceReportType.PREVENTIVE_MAINTENANCE,
    )
    monkeypatch.setattr(
        reports_router,
        "_report_record_views",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("render failed")),
    )

    with pytest.raises(RuntimeError, match="render failed"):
        reports_router._pdf_response(
            None,
            None,
            report,
            {},
            include_device_data=False,
            inline=True,
        )

    assert "report_id=41" in caplog.text
    assert "report_number=PMR-2026-00041" in caplog.text
    assert "RuntimeError: render failed" in caplog.text
