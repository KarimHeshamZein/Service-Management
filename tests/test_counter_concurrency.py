"""Concurrency regression tests for the shared per-year counter allocator."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier
from typing import Callable

import pytest

from app.database import SessionLocal
from app.helpers import (
    next_installation_record_number,
    next_record_number,
)
from app.models import InstallationRecordCounter, RecordCounter


def _allocate_concurrently(
    allocator: Callable,
    when: datetime,
) -> list[str]:
    barrier = Barrier(2)

    def allocate() -> str:
        with SessionLocal() as db:
            barrier.wait()
            number = allocator(db, when)
            db.commit()
            return number

    with ThreadPoolExecutor(max_workers=2) as executor:
        return list(executor.map(lambda _: allocate(), range(2)))


@pytest.mark.parametrize(
    ("allocator", "counter_model", "prefix"),
    [
        (next_record_number, RecordCounter, "PM"),
        (
            next_installation_record_number,
            InstallationRecordCounter,
            "NI",
        ),
    ],
)
@pytest.mark.parametrize("preexisting", [False, True])
def test_counter_allocation_is_concurrency_safe(
    allocator,
    counter_model,
    prefix,
    preexisting,
):
    year = 2037
    starting_sequence = 5 if preexisting else 0
    if preexisting:
        with SessionLocal.begin() as db:
            db.add(
                counter_model(
                    year=year,
                    last_sequence=starting_sequence,
                )
            )

    numbers = _allocate_concurrently(
        allocator,
        datetime(year, 6, 1, 12, 0),
    )

    assert sorted(numbers) == [
        f"{prefix}-{year}-{starting_sequence + 1:05d}",
        f"{prefix}-{year}-{starting_sequence + 2:05d}",
    ]
    with SessionLocal() as db:
        counter = db.get(counter_model, year)
        assert counter is not None
        assert counter.last_sequence == starting_sequence + 2
