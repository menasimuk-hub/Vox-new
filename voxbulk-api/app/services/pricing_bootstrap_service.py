"""Pricing DB schema + default plans/settings bootstrap (idempotent, logged)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.database import ensure_pricing_schema
from app.models.plan import Plan
from app.services.voxbulk_pricing_service import VoxbulkPricingService

logger = logging.getLogger(__name__)

CANONICAL_PLAN_CODES: tuple[str, ...] = ("payg", "starter", "pro", "business", "enterprise")

_BOOTSTRAP_STATE: dict[str, Any] = {
    "ok": False,
    "step": "not_started",
    "error": None,
    "plan_codes": [],
    "settings_ready": False,
}


class PricingBootstrapError(RuntimeError):
    pass


def get_pricing_bootstrap_status() -> dict[str, Any]:
    return dict(_BOOTSTRAP_STATE)


def _set_state(*, ok: bool, step: str, error: str | None = None, plan_codes: list[str] | None = None, settings_ready: bool = False) -> None:
    _BOOTSTRAP_STATE["ok"] = ok
    _BOOTSTRAP_STATE["step"] = step
    _BOOTSTRAP_STATE["error"] = error
    if plan_codes is not None:
        _BOOTSTRAP_STATE["plan_codes"] = plan_codes
    _BOOTSTRAP_STATE["settings_ready"] = settings_ready


def _missing_plan_codes(db: Session) -> list[str]:
    have = set(db.execute(select(Plan.code).where(Plan.code.in_(CANONICAL_PLAN_CODES))).scalars().all())
    return [code for code in CANONICAL_PLAN_CODES if code not in have]


def bootstrap_pricing_on_startup(db: Session) -> dict[str, Any]:
    """Ensure pricing schema, settings row, and canonical VoxBulk plans exist."""
    logger.info("pricing_bootstrap_start")
    _set_state(ok=False, step="start", error=None, plan_codes=[], settings_ready=False)

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            logger.info("pricing_bootstrap_step schema attempt=%s", attempt + 1)
            ensure_pricing_schema()
            _set_state(ok=False, step="schema_ok")
            logger.info("pricing_bootstrap_step schema_ok")

            settings = VoxbulkPricingService.get_settings(db)
            _set_state(ok=False, step="settings_ok", settings_ready=True)
            logger.info("pricing_bootstrap_step settings_ok id=%s wa_extra=%s", settings.id, settings.wa_survey_extra_pence)

            missing_before = _missing_plan_codes(db)
            if missing_before:
                logger.info("pricing_bootstrap_step seed_required missing=%s", ",".join(missing_before))
                VoxbulkPricingService.seed_voxbulk_plans(db)
            else:
                VoxbulkPricingService.ensure_seeded(db)

            missing_after = _missing_plan_codes(db)
            if missing_after:
                raise PricingBootstrapError(f"Missing canonical plans after seed: {missing_after}")

            plan_codes = sorted(
                db.execute(select(Plan.code).where(Plan.code.in_(CANONICAL_PLAN_CODES))).scalars().all()
            )
            _set_state(ok=True, step="complete", error=None, plan_codes=plan_codes, settings_ready=True)
            logger.info(
                "pricing_plans_seeded_on_boot plan_count=%s plans=%s",
                len(plan_codes),
                ",".join(plan_codes),
            )
            return get_pricing_bootstrap_status()
        except (OperationalError, ProgrammingError, PricingBootstrapError) as exc:
            db.rollback()
            last_exc = exc
            logger.warning("pricing_bootstrap_retry attempt=%s step=%s error=%s", attempt + 1, _BOOTSTRAP_STATE["step"], exc)
            ensure_pricing_schema()
        except Exception as exc:
            db.rollback()
            last_exc = exc
            logger.exception("pricing_bootstrap_failed step=%s", _BOOTSTRAP_STATE.get("step"))
            _set_state(ok=False, step=str(_BOOTSTRAP_STATE.get("step") or "failed"), error=str(exc))
            raise

    message = str(last_exc or "Pricing bootstrap failed")
    _set_state(ok=False, step=str(_BOOTSTRAP_STATE.get("step") or "failed"), error=message)
    logger.error("pricing_bootstrap_failed final step=%s error=%s", _BOOTSTRAP_STATE["step"], message)
    raise PricingBootstrapError(message) from last_exc


def ensure_pricing_ready(db: Session) -> None:
    """Raise PricingBootstrapError when bootstrap did not complete."""
    status = get_pricing_bootstrap_status()
    if status.get("ok"):
        return
    logger.info("pricing_bootstrap_lazy_retry previous_step=%s previous_error=%s", status.get("step"), status.get("error"))
    bootstrap_pricing_on_startup(db)
