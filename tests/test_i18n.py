import io
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import pytest
from pypdf import PdfReader
from sqlalchemy import text

from app.helpers import flash, fmt_date, fmt_datetime, pop_flash
from app.i18n import CATALOGS, translate
from app.models import EvidencePhotoStage, MaintenanceResult, User
from tests.conftest import (
    ADMIN,
    CUSTOMER_A,
    LEADER_A,
    csrf_of,
    login,
    submit_installation,
)


TEMPLATE_ROOT = Path(__file__).parents[1] / "app" / "templates"
STATIC_KEY = re.compile(r"\bt\(\s*(['\"])([^'\"]+)\1\s*(?:,|\))")
JINJA_BLOCK = re.compile(r"{[{%#].*?(?:}}|%}|#})", re.DOTALL)


class _VisibleLiteralScanner(HTMLParser):
    visible_attributes = {
        "placeholder",
        "aria-label",
        "title",
        "alt",
        "data-label",
        "data-saving-label",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_raw_element = 0
        self.literals: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.in_raw_element += 1
        if not self.in_raw_element:
            for name, value in attrs:
                normalized = " ".join((value or "").split())
                if name in self.visible_attributes and re.search(r"[A-Za-z]", normalized):
                    self.literals.append(normalized)

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.in_raw_element:
            self.in_raw_element -= 1

    def handle_data(self, data):
        normalized = " ".join(data.split())
        if not self.in_raw_element and re.search(r"[A-Za-z]", normalized):
            self.literals.append(normalized)


def test_catalogs_have_identical_keys_and_visible_fallbacks():
    assert set(CATALOGS["en"]) == set(CATALOGS["ar"])
    assert translate("missing.visible.key", "ar") == "missing.visible.key"
    assert translate("language.current", "en", name="Arabic") == (
        "Current language: Arabic"
    )


def test_translations_never_drop_a_placeholder():
    # A {placeholder} carries real data into the message. Translating it away
    # silently destroys that data: server.fallback once rendered every
    # unmatched server message as one generic Arabic sentence.
    placeholders = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
    english = CATALOGS["en"]
    mismatched: list[str] = []
    for key, source in english.items():
        for language, catalog in CATALOGS.items():
            if language == "en":
                continue
            expected = set(placeholders.findall(str(source)))
            actual = set(placeholders.findall(str(catalog[key])))
            if expected != actual:
                mismatched.append(
                    f"{language}:{key} expected {sorted(expected)} got {sorted(actual)}"
                )
    assert not mismatched, "translations dropped placeholders: " + "; ".join(mismatched)


def test_unmatched_server_message_survives_translation():
    # The fallback must pass the original text through in every language.
    for language in CATALOGS:
        rendered = translate("server.fallback", language, message="Select the project.")
        assert "Select the project." in rendered, language


def test_every_static_template_key_exists_in_both_catalogs():
    used: set[str] = set()
    for path in TEMPLATE_ROOT.rglob("*.html"):
        used.update(match.group(2) for match in STATIC_KEY.finditer(path.read_text(encoding="utf-8")))

    for language, catalog in CATALOGS.items():
        assert not (used - set(catalog)), f"missing {language} keys: {sorted(used - set(catalog))}"

    for result in MaintenanceResult:
        assert f"record.result.{result.value}" in CATALOGS["en"]
        assert f"record.result.{result.value}" in CATALOGS["ar"]
    for stage in EvidencePhotoStage:
        assert f"photo.stage.{stage.value}" in CATALOGS["en"]
        assert f"photo.stage.{stage.value}" in CATALOGS["ar"]


def test_remaining_templates_have_no_unmarked_latin_prose():
    # These are deliberately code-like examples, units, acronyms and deployment
    # paths. They are user data examples or operational identifiers, not UI prose.
    allowed = {
        "e.g. IP Camera",
        "e.g. Axis",
        "e.g. P3265-LV",
        "QUO-2026-00001",
        "Camera",
        "P3265-LV",
        "MB.",
        "SAR",
        "QUO",
        "e.g. Camera Service",
        "ID",
        ".env",
        "Ethernet 2",
        r"C:\ServiceManagement\backups\scheduled",
        r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
        r".\apply_windows_settings.ps1",
        r".\install_database_backup_task.ps1",
        "e.g. Gate 1",
    }
    found: list[tuple[str, str]] = []
    for path in TEMPLATE_ROOT.rglob("*.html"):
        if path.name in {"base.html", "login.html"}:
            continue
        source_without_jinja = JINJA_BLOCK.sub("", path.read_text(encoding="utf-8"))
        scanner = _VisibleLiteralScanner()
        scanner.feed(source_without_jinja)
        found.extend(
            (str(path.relative_to(TEMPLATE_ROOT)), literal)
            for literal in scanner.literals
            if literal not in allowed
        )
    assert found == []


def test_dates_use_localized_catalog_months_with_existing_format():
    assert fmt_date(date(2026, 1, 2), "en") == "02 Jan 2026"
    assert fmt_date(date(2026, 1, 2), "ar") == "02 يناير 2026"
    assert "يناير" in fmt_datetime(datetime(2026, 1, 2, 3, 4), "ar")


def test_arabic_result_label_does_not_change_stored_value_or_serial(client, db):
    login(client, *LEADER_A)
    submitted = submit_installation(client, serial_number="RTL-SERIAL-001")
    assert submitted.status_code == 303
    assert db.execute(text("SELECT result FROM installation_records")).scalar_one() == (
        MaintenanceResult.COMPLETED_SUCCESSFULLY.value
    )

    token = csrf_of(client, submitted.headers["location"])
    switched = client.post(
        "/language",
        data={
            "language": "ar",
            "next": submitted.headers["location"],
            "csrf_token": token,
        },
    )
    assert switched.status_code == 303
    detail = client.get(submitted.headers["location"])
    assert translate("record.result.completed_successfully", "ar") in detail.text
    assert "RTL-SERIAL-001" in detail.text


@pytest.mark.parametrize(
    ("credentials", "paths", "grant_pricing"),
    [
        (
            ADMIN,
            (
                "/dashboard",
                "/installations",
                "/maintenance",
                "/general-maintenance",
                "/records",
                "/installations/records",
                "/maintenance/records",
                "/general-maintenance/records",
                "/reports",
                "/reports/technician-audit",
                "/pricing/quotations",
                "/pricing/items",
                "/pricing/settings",
                "/projects",
                "/sites",
                "/service-types",
                "/devices",
                "/users",
                "/settings",
            ),
            False,
        ),
        (
            LEADER_A,
            (
                "/dashboard",
                "/installations",
                "/maintenance",
                "/general-maintenance",
                "/records",
                "/installations/records",
                "/maintenance/records",
                "/general-maintenance/records",
                "/reports",
                "/pricing/quotations",
                "/pricing/items",
                "/projects",
                "/sites",
                "/service-types",
                "/devices",
            ),
            True,
        ),
        (
            CUSTOMER_A,
            (
                "/records",
                "/installations/records",
                "/maintenance/records",
                "/general-maintenance/records",
                "/reports",
            ),
            False,
        ),
    ],
)
def test_reachable_module_pages_render_in_arabic(
    client, db, credentials, paths, grant_pricing
):
    if grant_pricing:
        technical = db.query(User).filter(User.username == credentials[0]).one()
        technical.pricing_access = True
        db.commit()

    assert login(client, *credentials).status_code == 303
    token = csrf_of(client, paths[0])
    assert client.post(
        "/language",
        data={"language": "ar", "next": paths[0], "csrf_token": token},
    ).status_code == 303

    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert '<html lang="ar" dir="rtl">' in response.text, path


def test_default_english_login_and_navigation_copy_remains_unchanged(client):
    login_page = client.get("/login")
    assert '<html lang="en" dir="ltr">' in login_page.text
    for text in (
        "Field Service",
        "Proof of the maintenance you already finished.",
        "Log the site, the service, who was with you and the photos you took. "
        "The system stamps who submitted it and when.",
        "Submit — the record is sealed as evidence",
        "Email or username",
        "Forgot password?",
        "Development accounts",
    ):
        assert text in login_page.text

    login(client, *ADMIN)
    navigation = client.get("/dashboard").text
    for text in (
        "Dashboard",
        "Data entry",
        "Preventive Maintenance",
        "All records",
        "Technician activity",
        "Price quotations",
        "Service types",
        "Log out",
    ):
        assert text in navigation


def test_anonymous_language_switch_is_plain_csrf_post_and_validated(client):
    page = client.get("/login")
    assert 'method="post" action="/language"' in page.text
    token = csrf_of(client, "/login")

    rejected_csrf = client.post(
        "/language",
        data={"language": "ar", "next": "/login", "csrf_token": "forged"},
    )
    assert rejected_csrf.status_code == 403
    assert '<html lang="en" dir="ltr">' in client.get("/login").text

    unknown = client.post(
        "/language",
        data={"language": "fr", "next": "/login", "csrf_token": token},
    )
    assert unknown.status_code == 400
    assert '<html lang="en" dir="ltr">' in client.get("/login").text

    token = csrf_of(client, "/login")
    switched = client.post(
        "/language",
        data={"language": "ar", "next": "/login", "csrf_token": token},
    )
    assert switched.status_code == 303
    assert switched.headers["location"] == "/login"
    arabic = client.get("/login")
    assert '<html lang="ar" dir="rtl">' in arabic.text
    assert "تسجيل الدخول" in arabic.text
    assert "البريد الإلكتروني أو اسم المستخدم" in arabic.text


def test_language_redirect_accepts_only_same_origin_paths(client):
    token = csrf_of(client, "/login")
    external = client.post(
        "/language",
        data={
            "language": "ar",
            "next": "https://evil.example/path",
            "csrf_token": token,
        },
    )
    assert external.status_code == 303
    assert external.headers["location"] == "/dashboard"

    token = csrf_of(client, "/login")
    protocol_relative = client.post(
        "/language",
        data={"language": "en", "next": "//evil.example", "csrf_token": token},
    )
    assert protocol_relative.headers["location"] == "/dashboard"


def test_authenticated_switch_persists_to_user_and_renders_arabic_navigation(
    client, db
):
    login(client, *ADMIN)
    token = csrf_of(client, "/dashboard")
    response = client.post(
        "/language",
        data={"language": "ar", "next": "/dashboard", "csrf_token": token},
    )
    assert response.status_code == 303

    db.expire_all()
    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    assert admin.language == "ar"
    dashboard = client.get("/dashboard")
    assert '<html lang="ar" dir="rtl">' in dashboard.text
    assert "لوحة المعلومات" in dashboard.text
    assert "مسؤول النظام" in dashboard.text
    not_found = client.get("/not-a-real-page")
    assert not_found.status_code == 404
    assert '<html lang="ar" dir="rtl">' in not_found.text


def test_anonymous_language_choice_is_carried_into_account_on_login(client, db):
    token = csrf_of(client, "/login")
    assert client.post(
        "/language",
        data={"language": "ar", "next": "/login", "csrf_token": token},
    ).status_code == 303

    assert login(client, *ADMIN).status_code == 303
    db.expire_all()
    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    assert admin.language == "ar"
    assert '<html lang="ar" dir="rtl">' in client.get("/dashboard").text


def test_unsupported_stored_user_language_falls_back_to_english(client, db):
    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    admin.language = "zz"
    db.commit()

    assert login(client, *ADMIN).status_code == 303
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert '<html lang="en" dir="ltr">' in dashboard.text
    assert "Dashboard" in dashboard.text


def test_arabic_catalog_control_copy_and_domain_terms_are_consistent():
    arabic = CATALOGS["ar"]
    assert arabic["ui.type"] == "النوع"
    assert arabic["ui.back"] == "رجوع"
    assert arabic["ui.clear"] == "مسح"
    assert arabic["ui.save"] == "حفظ"
    assert arabic["ui.run"] == "تشغيل"
    assert arabic["ui.change.history"] == "سجل التغييرات"
    assert arabic["ui.record.details"] == "تفاصيل السجل"

    known_bad_controls = {"يكتب", "خلف", "واضح", "يحفظ", "يجري", "يلغي", "يحرر", "يزيل"}
    assert known_bad_controls.isdisjoint(arabic.values())
    domain_values = (
        value
        for key, value in arabic.items()
        if "installation" in key or "quotation" in key
    )
    assert not any("تثبيت" in value or "اقتباس" in value for value in domain_values)
    assert not any(
        unicodedata.category(character) == "Mn"
        for value in arabic.values()
        for character in value
    )
    assert not any(re.search(r"\.[0-9a-f]{8}$", key) for key in arabic)


def test_flash_rendering_supports_new_references_and_legacy_cookie_shapes():
    request = SimpleNamespace(session={})
    flash(request, "Signed in as Test Admin.")
    stored = request.session["flash"][0]
    assert stored == {
        "key": "server.login.signed.in",
        "params": {"name": "Test Admin"},
        "level": "success",
    }
    assert pop_flash(request, "ar") == [
        {"message": "تم تسجيل الدخول باسم Test Admin.", "level": "success"}
    ]

    request.session["flash"] = [
        "Legacy plain flash",
        {"message": "Legacy mapped flash", "level": "error"},
    ]
    assert pop_flash(request, "ar") == [
        {"message": "Legacy plain flash", "level": "success"},
        {"message": "Legacy mapped flash", "level": "error"},
    ]


def test_flash_queued_before_language_switch_renders_in_new_language(client, db):
    token = csrf_of(client, "/login")
    signed_in = client.post(
        "/login",
        data={
            "username": ADMIN[0],
            "password": ADMIN[1],
            "csrf_token": token,
            "next": "/dashboard",
        },
    )
    assert signed_in.status_code == 303

    admin = db.query(User).filter(User.username == ADMIN[0]).one()
    admin.language = "ar"
    db.commit()
    dashboard = client.get("/dashboard")
    assert "تم تسجيل الدخول باسم Test Admin." in dashboard.text
    assert "Signed in as Test Admin." not in dashboard.text


def _switch_to_arabic(client, path="/dashboard"):
    token = csrf_of(client, path)
    response = client.post(
        "/language",
        data={"language": "ar", "next": path, "csrf_token": token},
    )
    assert response.status_code == 303


def _installation_form_tokens(client):
    page = client.get("/installations/submit")
    assert page.status_code == 200
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
    form_token = re.search(r'name="form_token" value="([^"]+)"', page.text).group(1)
    return csrf, form_token


def test_arabic_validation_is_identical_for_html_and_ajax_and_keeps_field_keys(client):
    assert login(client, *LEADER_A).status_code == 303
    _switch_to_arabic(client)

    csrf, form_token = _installation_form_tokens(client)
    html = client.post(
        "/installations/submit",
        data={"csrf_token": csrf, "form_token": form_token},
    )
    assert html.status_code == 422
    assert "اختر المشروع." in html.text
    assert 'data-error-for="project_id"' in html.text
    assert "Select the project." not in html.text

    csrf, form_token = _installation_form_tokens(client)
    ajax = client.post(
        "/installations/submit",
        data={"csrf_token": csrf, "form_token": form_token},
        headers={"x-requested-with": "XMLHttpRequest"},
    )
    assert ajax.status_code == 422
    body = ajax.json()
    assert "project_id" in body["errors"]
    assert body["errors"]["project_id"] == "اختر المشروع."
    assert body["form_token"]


def test_arabic_record_labels_render_in_html_while_pdf_stays_english(client):
    assert login(client, *LEADER_A).status_code == 303
    submitted = submit_installation(client, serial_number="AR-RECORD-LABEL-001")
    assert submitted.status_code == 303
    detail_path = submitted.headers["location"]
    _switch_to_arabic(client)

    for path in ("/records", "/reports", detail_path, detail_path + "/edit"):
        page = client.get(path)
        assert page.status_code == 200
        assert '<html lang="ar" dir="rtl">' in page.text
        assert "Installation record" not in page.text
    assert "التركيب" in client.get("/records").text
    assert "سجل التركيب" in client.get(detail_path + "/edit").text

    pdf = client.get("/reports/pdf?type=installation&q=AR-RECORD-LABEL-001")
    assert pdf.status_code == 200
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "Installation" in text


def test_login_failure_family_is_indistinguishable_in_arabic(client):
    token = csrf_of(client, "/login")
    assert client.post(
        "/language",
        data={"language": "ar", "next": "/login", "csrf_token": token},
    ).status_code == 303
    token = csrf_of(client, "/login")
    expected = translate("server.login.failed", "ar")

    unknown = client.post(
        "/login",
        data={"username": "unknown@example.test", "password": "wrong", "csrf_token": token},
    )
    wrong = client.post(
        "/login",
        data={"username": ADMIN[0], "password": "wrong", "csrf_token": token},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert expected in unknown.text and expected in wrong.text

    throttled = wrong
    for _ in range(12):
        throttled = client.post(
            "/login",
            data={"username": ADMIN[0], "password": "wrong", "csrf_token": token},
        )
        if throttled.status_code == 429:
            break
    assert throttled.status_code == 429
    assert expected in throttled.text


def test_technical_tokens_stay_literal_in_arabic_catalog_and_pages(client):
    tokens = (
        "PDF",
        "JPEG",
        "PNG",
        "WebP",
        "HTTP",
        "HTTPS",
        "TLS",
        "SMTP",
        "DNS",
        "IP",
        "IPv4",
        "PostgreSQL",
        "Windows",
        "PowerShell",
        "SAR",
        "QUO",
        "CSV",
        "URL",
    )
    for key, english in CATALOGS["en"].items():
        for token in tokens:
            if token in english:
                assert token in CATALOGS["ar"][key], f"{key} must preserve {token}"

    assert login(client, *ADMIN).status_code == 303
    submitted = submit_installation(client, serial_number="AR-TERM-CHECK-001")
    assert submitted.status_code == 303
    _switch_to_arabic(client)
    reports = client.get("/reports")
    settings_page = client.get("/settings")
    detail = client.get(submitted.headers["location"])
    assert reports.status_code == settings_page.status_code == detail.status_code == 200
    assert "PDF" in reports.text
    assert "PostgreSQL" in settings_page.text
    assert "<dt>موقع</dt>" in detail.text
    assert "<dt>مكان</dt>" in detail.text


def test_arabic_catalog_collision_diagnostic(capsys):
    """Run with -s to review intentional and suspicious translation collisions."""
    by_arabic: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for key, arabic in CATALOGS["ar"].items():
        by_arabic[arabic].append((key, CATALOGS["en"][key]))

    collisions = []
    for arabic, entries in sorted(by_arabic.items()):
        if len({english.casefold() for _, english in entries}) > 1:
            collisions.append((arabic, entries))
            labels = " | ".join(f"{key}={english}" for key, english in entries)
            print(f"{arabic}: {labels}")

    captured = capsys.readouterr()
    print(captured.out, end="")
    print(f"Arabic catalog collision diagnostic: {len(collisions)} collision(s)")
