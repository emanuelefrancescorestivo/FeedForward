"""
Engine and session factory.

``FEEDFORWARD_DATABASE_URL`` selects the database. Unset, the API uses a local
SQLite file so auth is still durable — it is not the in-memory dict this
replaced. Set a ``postgresql+psycopg://`` URL in any deployed environment.
``FEEDFORWARD_ENV=production`` refuses to start on a non-Postgres URL.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_DEFAULT_SQLITE = Path(__file__).resolve().parent.parent / "data" / "feedforward.db"

_engine = None
_Session: sessionmaker | None = None


def database_url() -> str:
    return os.getenv("FEEDFORWARD_DATABASE_URL") or f"sqlite:///{_DEFAULT_SQLITE}"


def is_postgres(url: str | None = None) -> bool:
    url = url if url is not None else database_url()
    return url.startswith("postgresql")


def assert_production_database() -> None:
    """Deployments must not silently run on the SQLite dev double."""
    if os.getenv("FEEDFORWARD_ENV", "").lower() == "production" and not is_postgres():
        raise RuntimeError(
            "FEEDFORWARD_ENV=production requires a PostgreSQL "
            "FEEDFORWARD_DATABASE_URL (postgresql+psycopg://...)."
        )


def get_engine(url: str | None = None, *, force: bool = False):
    """
    Process-wide engine. ``force=True`` rebuilds it — tests use this to point
    at a temporary SQLite database without leaking state into the next test.
    """
    global _engine, _Session
    target = url or database_url()
    if _engine is not None and not force and str(_engine.url) == target:
        return _engine
    if _engine is not None:
        _engine.dispose()
    connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
    _engine = create_engine(target, connect_args=connect_args, future=True)
    _Session = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False, future=True)
    return _engine


def get_sessionmaker() -> sessionmaker:
    if _Session is None:
        get_engine()
    return _Session


@contextmanager
def session_scope() -> Session:
    sm = get_sessionmaker()
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Drop the cached engine. Tests call this between cases."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None
