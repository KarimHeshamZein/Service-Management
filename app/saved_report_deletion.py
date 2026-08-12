"""Helpers for deleting saved reports linked to a source service record."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ServiceReport, ServiceReportRecord


def linked_reports(
    db: Session,
    link_column: Any,
    record_id: int,
) -> list[ServiceReport]:
    """Return every complete saved report containing the selected source record."""
    return list(
        db.scalars(
            select(ServiceReport)
            .join(ServiceReportRecord)
            .where(link_column == record_id)
            .order_by(ServiceReport.id)
        ).unique()
    )


def delete_linked_reports(
    db: Session,
    link_column: Any,
    record_id: int,
) -> list[str]:
    """Delete complete reports so their remaining scope is never misleading."""
    reports = linked_reports(db, link_column, record_id)
    numbers = [report.report_number for report in reports]
    for report in reports:
        db.delete(report)
    if reports:
        db.flush()
    return numbers
