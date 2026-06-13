from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AbuuBase(DeclarativeBase):
    pass


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:")


@lru_cache(maxsize=8)
def get_abuu_engine():
    settings = get_settings()
    url = settings.abuu_database_url
    is_sqlite = _is_sqlite(url)
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    poolclass = StaticPool if is_sqlite and ":memory:" in url else None
    return create_engine(
        url,
        echo=settings.abuu_db_echo,
        pool_pre_ping=settings.db_pool_pre_ping,
        connect_args=connect_args,
        poolclass=poolclass,
        future=True,
    )


@lru_cache(maxsize=8)
def get_abuu_sessionmaker():
    return sessionmaker(
        bind=get_abuu_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


def get_abuu_db() -> Generator[Session, None, None]:
    db = get_abuu_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def abuu_db_ping() -> bool:
    try:
        with get_abuu_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def get_abuu_migration_head() -> str | None:
    try:
        from alembic.runtime.migration import MigrationContext

        with get_abuu_engine().connect() as conn:
            context = MigrationContext.configure(conn)
            return context.get_current_revision()
    except Exception:
        return None


def abuu_tables_present() -> bool:
    try:
        insp = inspect(get_abuu_engine())
        return "abuu_restaurants" in insp.get_table_names()
    except Exception:
        return False


def run_abuu_migrations() -> None:
    """Apply pending Abuu Alembic revisions. Failures are logged; main API must still boot."""
    settings = get_settings()
    if not settings.abuu_enabled:
        logger.info("abuu_migrations_skipped disabled")
        return

    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic_abuu.ini"
    if not alembic_ini.is_file():
        logger.warning("abuu_migrations_skipped missing alembic_abuu.ini")
        return

    logger.info("abuu_migrations_start")
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", settings.abuu_database_url)
        command.upgrade(cfg, "head")
        logger.info("abuu_migrations_applied")
    except Exception as exc:
        logger.exception("abuu_migrations_failed: %s", exc)
