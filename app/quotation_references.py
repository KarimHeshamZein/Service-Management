"""Restricted quotation-number selection for service evidence."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PricingQuotation


def quotation_choices(db: Session) -> list[PricingQuotation]:
    """Expose identifiers and Project scope, never quotation prices."""
    return list(
        db.scalars(
            select(PricingQuotation).order_by(
                PricingQuotation.quotation_date.desc(),
                PricingQuotation.id.desc(),
            )
        )
    )


def resolve_quotation_reference(
    db: Session,
    quotation_number: str,
    project_id: int | None,
) -> tuple[PricingQuotation | None, str]:
    number = quotation_number.strip()
    if not number:
        return None, "Enter the quotation ID."
    quotation = db.scalar(
        select(PricingQuotation).where(
            PricingQuotation.quotation_number == number
        )
    )
    if quotation is None:
        return None, "Select an existing quotation ID."
    if project_id is None or quotation.project_id != project_id:
        return None, "Select a quotation belonging to the selected Project."
    return quotation, ""
