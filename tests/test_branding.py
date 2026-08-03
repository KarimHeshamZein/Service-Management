import io
from pathlib import Path

from pypdf import PdfReader

from app.i18n import CATALOGS
from app.models import PricingQuotation
from app.pricing_pdf import build_quotation_pdf
from tests.conftest import (
    ADMIN,
    LEADER_A,
    csrf_of,
    ensure_service_quotation,
    login,
    logout,
    submit_installation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_IMAGE_ROOT = PROJECT_ROOT / "app" / "static" / "img"


def _switch_language(client, language: str, next_path: str) -> None:
    response = client.post(
        "/language",
        data={
            "language": language,
            "next": next_path,
            "csrf_token": csrf_of(client, next_path),
        },
    )
    assert response.status_code == 303


def _pdf(content: bytes) -> tuple[PdfReader, str]:
    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return reader, text


def _image_sizes(reader: PdfReader) -> set[tuple[int, int]]:
    return {
        image.image.size
        for page in reader.pages
        for image in page.images
    }


def _assert_logo_on_every_page(reader: PdfReader) -> None:
    assert reader.pages
    assert all(
        any(image.image.size == (380, 133) for image in page.images)
        for page in reader.pages
    )


def test_brand_assets_and_localized_logo_render_in_both_directions(client):
    png = client.get("/static/img/afaqylogo.png")
    icon = client.get("/static/img/logo.ico")
    assert png.status_code == icon.status_code == 200
    assert png.headers["content-type"] == "image/png"
    assert icon.headers["content-type"] in {"image/x-icon", "image/vnd.microsoft.icon"}

    assert (STATIC_IMAGE_ROOT / "afaqylogo.png").is_file()
    assert (STATIC_IMAGE_ROOT / "logo.ico").is_file()
    assert not (PROJECT_ROOT / "afaqylogo.png").exists()
    assert not (PROJECT_ROOT / "logo.ico").exists()
    assert not (PROJECT_ROOT / "logo.jpg").exists()

    css = (PROJECT_ROOT / "app" / "static" / "css" / "app.css").read_text(
        encoding="utf-8"
    )
    assert ".brand-logo-frame" in css
    assert ".brand-logo-plate" in css
    assert "max-width: 100%" in css
    assert "height: auto" in css
    assert 'html[dir="rtl"] .brand-logo-image { transform: none; }' in css

    assert set(CATALOGS["en"]) == set(CATALOGS["ar"])
    assert CATALOGS["en"]["app.brand.logo_alt"] == "Afaqy company logo"
    assert CATALOGS["ar"]["app.brand.logo_alt"] == "شعار شركة أفاقي"

    english_login = client.get("/login")
    assert english_login.status_code == 200
    assert '<html lang="en" dir="ltr">' in english_login.text
    assert 'href="/static/img/logo.ico"' in english_login.text
    assert 'alt="Afaqy company logo"' in english_login.text
    assert (STATIC_IMAGE_ROOT / "logo.ico").is_file()

    assert login(client, *LEADER_A).status_code == 303
    english_base = client.get("/records")
    assert english_base.status_code == 200
    assert '<html lang="en" dir="ltr">' in english_base.text
    assert 'alt="Afaqy company logo"' in english_base.text
    logout(client)

    _switch_language(client, "ar", "/login")
    arabic_login = client.get("/login")
    assert arabic_login.status_code == 200
    assert '<html lang="ar" dir="rtl">' in arabic_login.text
    assert 'alt="شعار شركة أفاقي"' in arabic_login.text

    assert login(client, *LEADER_A).status_code == 303
    arabic_base = client.get("/records")
    assert arabic_base.status_code == 200
    assert '<html lang="ar" dir="rtl">' in arabic_base.text
    assert 'alt="شعار شركة أفاقي"' in arabic_base.text


def test_logo_is_embedded_in_records_audit_and_quotation_pdfs(client, db):
    assert login(client, *LEADER_A).status_code == 303
    submitted = submit_installation(client, serial_number="BRAND-PDF-001")
    assert submitted.status_code == 303

    records_response = client.get("/reports/pdf?q=BRAND-PDF-001")
    assert records_response.status_code == 200
    records_reader, records_text = _pdf(records_response.content)
    assert "Service records report" in records_text
    assert "BRAND-PDF-001" in records_text
    assert (380, 133) in _image_sizes(records_reader)
    _assert_logo_on_every_page(records_reader)

    logout(client)
    assert login(client, *ADMIN).status_code == 303
    audit_response = client.get("/reports/technician-audit/pdf?technician_id=2")
    assert audit_response.status_code == 200
    audit_reader, audit_text = _pdf(audit_response.content)
    assert "Technician activity report" in audit_text
    assert "BRAND-PDF-001" in audit_text
    assert (380, 133) in _image_sizes(audit_reader)
    _assert_logo_on_every_page(audit_reader)

    quotation_number = ensure_service_quotation("1")
    db.expire_all()
    quotation = db.query(PricingQuotation).filter_by(
        quotation_number=quotation_number
    ).one()
    quotation_reader, quotation_text = _pdf(build_quotation_pdf(quotation))
    assert "PRICE QUOTATION" in quotation_text
    assert quotation_number in quotation_text
    assert (380, 133) in _image_sizes(quotation_reader)
    _assert_logo_on_every_page(quotation_reader)
