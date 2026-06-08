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


def _table_exists(insp, table: str) -> bool:
    try:
        return table in insp.get_table_names()
    except Exception:
        return False


def _mysql_type(col_type: str, dialect: str) -> str:
    if dialect == "mysql" and "BOOLEAN" in col_type.upper():
        return col_type.upper().replace("BOOLEAN", "TINYINT(1)")
    return col_type


def _seed_pricing_global_settings(conn) -> None:
    row = conn.execute(text("SELECT id FROM pricing_global_settings WHERE id = 1")).fetchone()
    if row is not None:
        return
    logger.warning("schema_hotfix_seed_pricing_global_settings")
    conn.execute(
        text(
            """
            INSERT INTO pricing_global_settings (
                id, fx_aud_multiplier, fx_cad_multiplier, fx_usd_multiplier,
                connection_fee_pence, connection_fee_label, connection_fee_enabled,
                interview_per_min_pence, whatsapp_survey_fee_pence, wa_survey_extra_pence,
                ats_cv_scan_fee_pence, estimator_default_duration_min,
                estimator_default_interview_count, updated_at
            ) VALUES (
                1, 1.95, 1.71, 1.26,
                200, 'AI Interview — connection fee', 1,
                35, 50, 49,
                75, 12, 100, CURRENT_TIMESTAMP
            )
            """
        )
    )


def ensure_pricing_schema() -> None:
    """Create pricing tables, columns, and default row when alembic was skipped or failed."""
    import app.models.pricing  # noqa: F401
    from app.models.pricing import OrgCustomPricing, PricingGlobalSettings, TopupTier

    engine = get_engine()
    dialect = engine.dialect.name
    for table in (PricingGlobalSettings.__table__, TopupTier.__table__, OrgCustomPricing.__table__):
        table.create(bind=engine, checkfirst=True)
    ensure_schema_hotfixes()
    with engine.begin() as conn:
        insp = inspect(engine)
        if _table_exists(insp, "pricing_global_settings"):
            _seed_pricing_global_settings(conn)
        if _table_exists(insp, "plans"):
            plan_cols = {c["name"] for c in insp.get_columns("plans")}
            if "service_kind" in plan_cols:
                conn.execute(
                    text(
                        """
                        UPDATE plans
                        SET service_kind = 'voxbulk'
                        WHERE code IN ('payg', 'starter', 'pro', 'business', 'enterprise')
                          AND (
                            service_kind IS NULL
                            OR service_kind = ''
                            OR service_kind IN ('dental', 'order', 'clinic')
                          )
                        """
                    )
                )


def ensure_schema_hotfixes() -> None:
    """Idempotent DDL for columns added in recent releases when alembic was not run."""
    engine = get_engine()
    dialect = engine.dialect.name
    patches = (
        ("frontpage_call_settings", "telnyx_greeting", "TEXT NULL"),
        ("lead_sales_settings", "telnyx_greeting", "TEXT NULL"),
        ("organisations", "scheduling_config_json", "TEXT NULL"),
        ("organisations", "logo_storage_key", "VARCHAR(512) NULL"),
        ("organisations", "allowed_services_json", "TEXT NULL"),
        ("organisations", "hubspot_config_json", "TEXT NULL"),
        ("organisations", "wallet_balance_pence", "INTEGER NOT NULL DEFAULT 0"),
        ("org_usage_periods", "cv_scans_included", "INTEGER NOT NULL DEFAULT 0"),
        ("org_usage_periods", "cv_scans_used", "INTEGER NOT NULL DEFAULT 0"),
        ("service_order_recipients", "ats_score", "INTEGER NULL"),
        ("service_order_recipients", "ats_status", "VARCHAR(32) NULL"),
        ("service_order_recipients", "ats_hash", "VARCHAR(64) NULL"),
        ("service_order_recipients", "ats_error", "VARCHAR(512) NULL"),
        ("pricing_global_settings", "wa_survey_extra_pence", "INTEGER NOT NULL DEFAULT 49"),
        ("org_custom_pricing", "wa_survey_extra_pence", "INTEGER NULL"),
        ("plans", "per_min_pence", "INTEGER NOT NULL DEFAULT 0"),
        ("plans", "cv_scans_included", "INTEGER NOT NULL DEFAULT 0"),
        ("plans", "is_featured", "TINYINT(1) NOT NULL DEFAULT 0"),
        ("plans", "is_enterprise", "TINYINT(1) NOT NULL DEFAULT 0"),
        ("plans", "service_kind", "VARCHAR(32) NOT NULL DEFAULT 'voxbulk'"),
    )
    with engine.begin() as conn:
        insp = inspect(engine)
        for table, column, col_type in patches:
            if not _table_exists(insp, table):
                continue
            try:
                cols = {c["name"] for c in inspect(engine).get_columns(table)}
            except Exception:
                continue
            if column in cols:
                continue
            ddl_type = _mysql_type(col_type, dialect)
            logger.warning("schema_hotfix_add_column table=%s column=%s", table, column)
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))


def run_database_migrations() -> None:
    """Apply pending Alembic revisions on every API boot (production included)."""
    repo_root = Path(__file__).resolve().parents[2]
    alembic_ini = repo_root / "alembic.ini"
    if not alembic_ini.is_file():
        ensure_pricing_schema()
        return

    settings = get_settings()
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(cfg, "head")
        logger.info("database_migrations_applied")
    except Exception as exc:
        logger.warning("database_migrations_failed: %s", exc)
    ensure_pricing_schema()


def init_db() -> None:
    """Dev/local: migrate schema so SQLite files stay in sync with models (create_all does not add columns)."""
    import app.models  # noqa: F401

    run_database_migrations()
    env_ok = str(get_settings().env).lower() in {"dev", "development", "local"}
    if env_ok:
        try:
            Base.metadata.create_all(bind=get_engine())
        except Exception as exc:  # pragma: no cover - best-effort bootstrap
            logging.getLogger(__name__).warning("create_all failed: %s", exc)
