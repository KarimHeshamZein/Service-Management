"""Embedded Unicode PDF fonts and Arabic visual-order preparation."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle

PDF_FONT = "NotoSansArabic"
PDF_FONT_BOLD = "NotoSansArabic-Bold"
FONT_ROOT = Path(__file__).resolve().parent / "static" / "fonts"
_ARABIC = re.compile(
    "[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]"
)
_INVISIBLE_FORMATTING = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]")
_UNSUPPORTED_SYMBOLS = re.compile("[\u2600-\u27bf\U0001f000-\U0001faff]")


def register_pdf_fonts() -> None:
    """Register the bundled fonts once in ReportLab's process-wide registry."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    if PDF_FONT not in registered:
        pdfmetrics.registerFont(
            TTFont(PDF_FONT, str(FONT_ROOT / "NotoSansArabic-Regular.ttf"))
        )
    if PDF_FONT_BOLD not in registered:
        pdfmetrics.registerFont(
            TTFont(PDF_FONT_BOLD, str(FONT_ROOT / "NotoSansArabic-Bold.ttf"))
        )
    pdfmetrics.registerFontFamily(
        PDF_FONT,
        normal=PDF_FONT,
        bold=PDF_FONT_BOLD,
        italic=PDF_FONT,
        boldItalic=PDF_FONT_BOLD,
    )


def contains_arabic(value: str) -> bool:
    return _ARABIC.search(value) is not None


def visual_text(value: str) -> str:
    """Shape Arabic and apply BiDi ordering while leaving Latin text unchanged."""
    if not contains_arabic(value):
        return value
    return get_display(arabic_reshaper.reshape(value), base_dir="R")


def style_for_pdf_text(value: Any, style: ParagraphStyle) -> ParagraphStyle:
    """Use the embedded Arabic font only when the paragraph needs its glyphs."""
    raw = "" if value is None else str(value)
    if not contains_arabic(raw):
        return style
    bold = str(style.fontName).endswith("Bold")
    return ParagraphStyle(
        f"{style.name}Arabic",
        parent=style,
        fontName=PDF_FONT_BOLD if bold else PDF_FONT,
        alignment=TA_CENTER if style.alignment == TA_CENTER else TA_RIGHT,
    )


def pdf_text(value: Any, fallback: str = "-") -> str:
    """Normalize, shape, escape and retain line breaks for a PDF paragraph."""
    if value is None or value == "":
        value = fallback
    normalized = (
        str(value)
        .replace("\u2010", "-")
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00b7", "|")
    )
    normalized = _INVISIBLE_FORMATTING.sub("", normalized)
    normalized = _UNSUPPORTED_SYMBOLS.sub("", normalized)
    normalized = "\n".join(
        re.sub(r"[ \t]+", " ", line).strip() for line in normalized.splitlines()
    )
    return "<br/>".join(
        html.escape(visual_text(line), quote=False)
        for line in normalized.splitlines() or [""]
    )


register_pdf_fonts()
