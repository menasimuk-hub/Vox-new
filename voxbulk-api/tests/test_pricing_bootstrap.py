from __future__ import annotations

from app.core.database import get_sessionmaker, run_database_migrations
from app.services.pricing_bootstrap_service import CANONICAL_PLAN_CODES, get_pricing_bootstrap_status


def test_run_database_migrations_bootstraps_pricing():
    run_database_migrations()
    status = get_pricing_bootstrap_status()
    assert status["ok"] is True, status
    assert status["step"] == "complete"
    assert set(status["plan_codes"]) == set(CANONICAL_PLAN_CODES)

    with get_sessionmaker()() as db:
        from app.services.pricing_bootstrap_service import bootstrap_pricing_on_startup

        again = bootstrap_pricing_on_startup(db)
        assert again["ok"] is True
        assert set(again["plan_codes"]) == set(CANONICAL_PLAN_CODES)
