from __future__ import annotations

from sqlalchemy import text

from app.core.database import ensure_pricing_schema, get_engine, get_sessionmaker, _table_columns
from app.core.pricing_schema import (
    WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN,
    WHATSAPP_SURVEY_FEE_PENCE_COLUMN,
)
from app.services.pricing_bootstrap_service import CANONICAL_PLAN_CODES, bootstrap_pricing_on_startup, get_pricing_bootstrap_status
from app.services.voxbulk_pricing_service import VoxbulkPricingService


def test_reconcile_legacy_wa_package_fee_column():
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS pricing_global_settings"))
        conn.execute(
            text(
                """
                CREATE TABLE pricing_global_settings (
                    id INTEGER PRIMARY KEY,
                    fx_aud_multiplier FLOAT NOT NULL DEFAULT 1.95,
                    fx_cad_multiplier FLOAT NOT NULL DEFAULT 1.71,
                    fx_usd_multiplier FLOAT NOT NULL DEFAULT 1.26,
                    connection_fee_pence INTEGER NOT NULL DEFAULT 200,
                    connection_fee_label VARCHAR(255) NOT NULL DEFAULT 'fee',
                    connection_fee_enabled INTEGER NOT NULL DEFAULT 1,
                    interview_per_min_pence INTEGER NOT NULL DEFAULT 35,
                    wa_survey_package_fee_pence INTEGER NOT NULL DEFAULT 150,
                    wa_survey_extra_pence INTEGER NOT NULL DEFAULT 49,
                    ats_cv_scan_fee_pence INTEGER NOT NULL DEFAULT 75,
                    estimator_default_duration_min INTEGER NOT NULL DEFAULT 12,
                    estimator_default_interview_count INTEGER NOT NULL DEFAULT 100,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(text("INSERT INTO pricing_global_settings (id) VALUES (1)"))

    ensure_pricing_schema()
    cols = _table_columns(engine, "pricing_global_settings")
    assert WHATSAPP_SURVEY_FEE_PENCE_COLUMN in cols
    assert WA_SURVEY_PACKAGE_FEE_LEGACY_COLUMN not in cols

    with get_sessionmaker()() as db:
        row = VoxbulkPricingService.get_settings(db)
        assert row.wa_survey_package_fee_pence == 150


def test_run_database_migrations_bootstraps_pricing():
    ensure_pricing_schema()
    with get_sessionmaker()() as db:
        bootstrap_pricing_on_startup(db)
    status = get_pricing_bootstrap_status()
    assert status["ok"] is True, status
    assert status["step"] == "complete"
    assert set(status["plan_codes"]) == set(CANONICAL_PLAN_CODES)

    with get_sessionmaker()() as db:
        again = bootstrap_pricing_on_startup(db)
        assert again["ok"] is True
        assert set(again["plan_codes"]) == set(CANONICAL_PLAN_CODES)


def test_update_settings_wa_package_fee_not_overwritten_by_stale_alias():
    ensure_pricing_schema()
    with get_sessionmaker()() as db:
        row = VoxbulkPricingService.get_settings(db)
        row.wa_survey_package_fee_pence = 50
        db.commit()

        updated = VoxbulkPricingService.update_settings(
            db,
            {
                "wa_survey_package_fee_pence": 75,
                "whatsapp_survey_fee_pence": 50,
            },
        )
        assert updated.wa_survey_package_fee_pence == 75

        reloaded = VoxbulkPricingService.get_settings(db)
        assert reloaded.wa_survey_package_fee_pence == 75
        out = VoxbulkPricingService.settings_to_dict(reloaded)
        assert out["wa_survey_package_fee_pence"] == 75
        assert out["whatsapp_survey_fee_pence"] == 75
