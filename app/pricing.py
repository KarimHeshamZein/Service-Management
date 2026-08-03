"""Pricing validation, totals, and quotation numbering."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.orm import Session

from .counters import allocate_year_sequence
from .models import PricingQuotation, PricingQuotationCounter

MONEY_PLACES = Decimal("0.01")
MAX_PRICE = Decimal("999999999999.99")
MAX_QUANTITY = Decimal("9999999999.99")


def decimal_value(
    raw: object,
    *,
    minimum: Decimal,
    maximum: Decimal,
) -> Decimal | None:
    try:
        value = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None
    if not value.is_finite() or value < minimum or value > maximum:
        return None
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def money(raw: object) -> Decimal | None:
    return decimal_value(raw, minimum=Decimal("0"), maximum=MAX_PRICE)


def quantity(raw: object) -> Decimal | None:
    return decimal_value(
        raw,
        minimum=Decimal("0.01"),
        maximum=MAX_QUANTITY,
    )


def percentage(raw: object) -> Decimal | None:
    return decimal_value(
        raw,
        minimum=Decimal("0"),
        maximum=Decimal("100"),
    )


def rounded(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def quotation_totals(quotation: PricingQuotation) -> dict[str, Decimal]:
    subtotal = rounded(
        sum((line.line_total for line in quotation.lines), Decimal("0.00"))
        + sum((charge.total for charge in quotation.charges), Decimal("0.00"))
    )
    discount = rounded(subtotal * quotation.discount_percent / Decimal("100"))
    taxable = rounded(subtotal - discount)
    vat = rounded(taxable * quotation.vat_rate / Decimal("100"))
    return {
        "subtotal": subtotal,
        "discount": discount,
        "taxable": taxable,
        "vat": vat,
        "grand_total": rounded(taxable + vat),
    }


def next_quotation_number(
    db: Session,
    *,
    prefix: str,
    quotation_date: date,
) -> str:
    sequence = allocate_year_sequence(
        db,
        PricingQuotationCounter,
        quotation_date.year,
    )
    return f"{prefix}-{quotation_date.year}-{sequence:05d}"
