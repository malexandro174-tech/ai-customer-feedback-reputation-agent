from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_sessions: sessionmaker[Session] | None = None


def configure_database(database_url: str | None = None) -> None:
    global _engine, _sessions
    url = database_url or get_settings().database_url
    options = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    _engine = create_engine(url, **options)
    _sessions = sessionmaker(bind=_engine, autocommit=False, autoflush=False, expire_on_commit=False)


def engine():
    if _engine is None:
        configure_database()
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _sessions is None:
        configure_database()
    assert _sessions is not None
    return _sessions


@contextmanager
def session_scope() -> Iterator[Session]:
    session = session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    from . import models  # noqa: F401 - registers all metadata
    Base.metadata.create_all(bind=engine())


def database_healthy() -> bool:
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
