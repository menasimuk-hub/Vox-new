from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.pricing_schema import (
    WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN,
    WHATSAPP_SURVEY_FEE_PENCE_COLUMN,
)

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


def _table_columns(engine, table: str) -> set[str]:
    try:
        return {c["name"] for c in inspect(engine).get_columns(table)}
    except Exception:
        return set()


def _reconcile_whatsapp_survey_fee_column(
    engine,
    table: str,
    *,
    nullable: bool,
    default: int | None,
) -> None:
    """Ensure physical column whatsapp_survey_fee_pence exists (rename legacy name if needed)."""
    cols = _table_columns(engine, table)
    if WHATSAPP_SURVEY_FEE_PENCE_COLUMN in cols:
        return
    dialect = engine.dialect.name
    with engine.begin() as conn:
        cols = _table_columns(engine, table)
        if WHATSAPP_SURVEY_FEE_PENCE_COLUMN in cols:
            return
        if WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN in cols:
            if dialect == "mysql":
                null_sql = "NULL" if nullable else f"NOT NULL DEFAULT {int(default or 50)}"
                conn.execute(
                    text(
                        f"ALTER TABLE {table} CHANGE COLUMN {WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN} "
                        f"{WHATSAPP_SURVEY_FEE_PENCE_COLUMN} INT {null_sql}"
                    )
                )
            else:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} RENAME COLUMN {WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN} "
                        f"TO {WHATSAPP_SURVEY_FEE_PENCE_COLUMN}"
                    )
                )
            logger.warning(
                "schema_hotfix_rename_column table=%s from=%s to=%s",
                table,
                WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN,
                WHATSAPP_SURVEY_FEE_PENCE_COLUMN,
            )
            return
        null_sql = "NULL" if nullable else f"NOT NULL DEFAULT {int(default or 50)}"
        conn.execute(
            text(f"ALTER TABLE {table} ADD COLUMN {WHATSAPP_SURVEY_FEE_PENCE_COLUMN} INTEGER {null_sql}")
        )
        logger.warning("schema_hotfix_add_column table=%s column=%s", table, WHATSAPP_SURVEY_FEE_PENCE_COLUMN)


def _reconcile_pricing_wa_fee_columns(engine) -> None:
    if _table_exists(inspect(engine), "pricing_global_settings"):
        _reconcile_whatsapp_survey_fee_column(engine, "pricing_global_settings", nullable=False, default=50)
    if _table_exists(inspect(engine), "org_custom_pricing"):
        _reconcile_whatsapp_survey_fee_column(engine, "org_custom_pricing", nullable=True, default=None)


def _seed_pricing_global_settings(conn, engine) -> None:
    row = conn.execute(text("SELECT id FROM pricing_global_settings WHERE id = 1")).fetchone()
    if row is not None:
        return
    cols = _table_columns(engine, "pricing_global_settings")
    wa_col = WHATSAPP_SURVEY_FEE_PENCE_COLUMN
    if wa_col not in cols:
        raise RuntimeError(f"pricing_global_settings missing required column {wa_col}")
    logger.warning("schema_hotfix_seed_pricing_global_settings")
    conn.execute(
        text(
            f"""
            INSERT INTO pricing_global_settings (
                id, fx_aud_multiplier, fx_cad_multiplier, fx_usd_multiplier,
                connection_fee_pence, connection_fee_label, connection_fee_enabled,
                interview_per_min_pence, {wa_col}, wa_survey_extra_pence,
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
    _reconcile_pricing_wa_fee_columns(engine)
    ensure_schema_hotfixes()
    with engine.begin() as conn:
        insp = inspect(engine)
        if _table_exists(insp, "pricing_global_settings"):
            _seed_pricing_global_settings(conn, engine)
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
        ("pricing_global_settings", WHATSAPP_SURVEY_FEE_PENCE_COLUMN, "INTEGER NOT NULL DEFAULT 50"),
        ("org_custom_pricing", "wa_survey_extra_pence", "INTEGER NULL"),
        ("org_custom_pricing", WHATSAPP_SURVEY_FEE_PENCE_COLUMN, "INTEGER NULL"),
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
        _run_pricing_bootstrap_after_migrations()
        return

    settings = get_settings()
    logger.info("database_migrations_start")
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(alembic_ini))
        cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(cfg, "head")
        logger.info("database_migrations_applied")
    except Exception as exc:
        logger.exception("database_migrations_failed: %s", exc)
    try:
        ensure_pricing_schema()
        logger.info("database_migrations_schema_hotfix_ok")
    except Exception as exc:
        logger.exception("database_migrations_schema_hotfix_failed: %s", exc)
    _run_pricing_bootstrap_after_migrations()
    logger.info("database_migrations_complete")


def _run_pricing_bootstrap_after_migrations() -> None:
    from app.services.pricing_bootstrap_service import bootstrap_pricing_on_startup

    try:
        with get_sessionmaker()() as db:
            bootstrap_pricing_on_startup(db)
    except Exception as exc:
        logger.exception("pricing_bootstrap_after_migrations_failed: %s", exc)


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
