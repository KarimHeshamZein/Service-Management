"""Concurrency-safe allocation for per-year counters."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session


def allocate_year_sequence(
    db: Session,
    counter_model: type[Any],
    year: int,
) -> int:
    """Create the year if needed, then increment its locked current value."""
    create_year = (
        insert(counter_model)
        .values(year=year, last_sequence=0)
        .on_conflict_do_nothing(index_elements=[counter_model.year])
    )
    db.execute(create_year)

    locked_counter = db.execute(
        select(counter_model)
        .where(counter_model.year == year)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    locked_counter.last_sequence += 1
    db.flush()
    return locked_counter.last_sequence
