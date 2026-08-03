"""Database engine and session management."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def init_db(*, create_schema: bool = False) -> None:
    from . import models  # noqa: F401 - registers all ORM mappers

    if create_schema:
        Base.metadata.create_all(bind=engine)
        return
    # Normal startup never bypasses Alembic. It only verifies that PostgreSQL
    # is reachable; deployments must run `alembic upgrade head` first.
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
