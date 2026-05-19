from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


@lru_cache(maxsize=8)
def get_engine():
    settings = get_settings()
    url = settings.database_url
    is_sqlite = _is_sqlite(url)
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    poolclass = StaticPool if is_sqlite and ":memory:" in url else None
    return create_engine(
        url,
        echo=settings.db_echo,
        pool_pre_ping=settings.db_pool_pre_ping,
        connect_args=connect_args,
        poolclass=poolclass,
        future=True,
    )


@lru_cache(maxsize=8)
def get_sessionmaker():
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Dev/local: migrate schema so SQLite files stay in sync with models (create_all does not add columns)."""
    import app.models  # noqa: F401

    settings = get_settings()
    url = settings.database_url
    env_ok = str(settings.env).lower() in {"dev", "development", "local"}
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic.ini"

    if env_ok and alembic_ini.is_file():
        try:
            from alembic import command
            from alembic.config import Config
            from alembic.runtime.migration import MigrationContext
            from alembic.script import ScriptDirectory

            cfg = Config(str(alembic_ini))
            cfg.set_main_option("sqlalchemy.url", url)
            engine = get_engine()
            with engine.connect() as conn:
                current = MigrationContext.configure(conn).get_current_revision()
            head = ScriptDirectory.from_config(cfg).get_current_head()
            if current == head:
                return
            command.upgrade(cfg, "head")
            return
        except Exception as exc:  # pragma: no cover - best-effort bootstrap
            logging.getLogger(__name__).warning("alembic upgrade failed; falling back to create_all: %s", exc)

    Base.metadata.create_all(bind=get_engine())
