"""Per-currency plan and service pricing — the single source of truth for VoxBulk prices.

Admin sets explicit prices for each currency (GBP, USD, CAD, AUD). There is no FX conversion:
each market price is a deliberate commercial decision. GBP rows are seeded from the legacy
GBP plan fields the first time the service runs.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice, PricingCurrencySettings
from app.services.billing_currency import (
    SUPPORTED_CURRENCIES,
    money_display,
    normalize_currency,
    resolve_org_currency,
)


class PlanPriceError(ValueError):
    pass


class PlanPriceService:
    # ------------------------------------------------------------------ currency unit rates

    @staticmethod
    def get_currency_settings(db: Session, currency: str) -> PricingCurrencySettings:
        code = normalize_currency(currency)
        row = db.get(PricingCurrencySettings, code)
        if row is None:
            row = PlanPriceService._seed_currency_settings(db, code)
        return row

    @staticmethod
    def _seed_currency_settings(db: Session, currency: str) -> PricingCurrencySettings:
        """Seed unit rates. GBP comes from legacy global settings; other currencies start at GBP
        face value and must be reviewed by the admin."""
        defaults = {"connection_fee": 200, "interview_per_min": 35, "wa_package_fee": 50, "wa_extra": 49, "cv_scan_fee": 75}
        try:
            from app.models.pricing import PricingGlobalSettings

            legacy = db.get(PricingGlobalSettings, 1)
            if legacy is not None:
                defaults = {
                    "connection_fee": int(legacy.connection_fee_pence or 200) if legacy.connection_fee_enabled else 0,
                    "interview_per_min": int(legacy.interview_per_min_pence or 35),
                    "wa_package_fee": int(legacy.wa_survey_package_fee_pence or 50),
                    "wa_extra": int(legacy.wa_survey_extra_pence or 49),
                    "cv_scan_fee": int(legacy.ats_cv_scan_fee_pence or 75),
                }
        except Exception:
            pass
        row = PricingCurrencySettings(
            currency=normalize_currency(currency),
            connection_fee_minor=defaults["connection_fee"],
            interview_per_min_minor=defaults["interview_per_min"],
            wa_package_fee_minor=defaults["wa_package_fee"],
            wa_extra_minor=defaults["wa_extra"],
            cv_scan_fee_minor=defaults["cv_scan_fee"],
            is_active=True,
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def currency_settings_to_dict(row: PricingCurrencySettings) -> dict[str, Any]:
        c = row.currency
        return {
            "currency": c,
            "connection_fee_minor": int(row.connection_fee_minor or 0),
            "connection_fee_display": money_display(int(row.connection_fee_minor or 0), c),
            "interview_per_min_minor": int(row.interview_per_min_minor or 0),
            "interview_per_min_display": money_display(int(row.interview_per_min_minor or 0), c),
            "wa_package_fee_minor": int(row.wa_package_fee_minor or 0),
            "wa_package_fee_display": money_display(int(row.wa_package_fee_minor or 0), c),
            "wa_extra_minor": int(row.wa_extra_minor or 0),
            "wa_extra_display": money_display(int(row.wa_extra_minor or 0), c),
            "cv_scan_fee_minor": int(row.cv_scan_fee_minor or 0),
            "cv_scan_fee_display": money_display(int(row.cv_scan_fee_minor or 0), c),
            "is_active": bool(row.is_active),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def update_currency_settings(db: Session, currency: str, payload: dict[str, Any]) -> PricingCurrencySettings:
        row = PlanPriceService.get_currency_settings(db, currency)
        for key in (
            "connection_fee_minor",
            "interview_per_min_minor",
            "wa_package_fee_minor",
            "wa_extra_minor",
            "cv_scan_fee_minor",
        ):
            if key in payload and payload[key] is not None:
                value = int(payload[key])
                if value < 0:
                    raise PlanPriceError(f"{key} cannot be negative")
                setattr(row, key, value)
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    # ------------------------------------------------------------------ plan prices

    @staticmethod
    def list_for_plan(db: Session, plan_id: str) -> list[PlanPrice]:
        return list(
            db.execute(select(PlanPrice).where(PlanPrice.plan_id == plan_id).order_by(PlanPrice.currency.asc()))
            .scalars()
            .all()
        )

    @staticmethod
    def get_price(db: Session, plan_id: str, currency: str) -> PlanPrice | None:
        return db.execute(
            select(PlanPrice).where(PlanPrice.plan_id == plan_id, PlanPrice.currency == normalize_currency(currency))
        ).scalar_one_or_none()

    @staticmethod
    def price_to_dict(row: PlanPrice) -> dict[str, Any]:
        c = row.currency
        return {
            "id": row.id,
            "plan_id": row.plan_id,
            "currency": c,
            "monthly_price_minor": row.monthly_price_minor,
            "monthly_price_display": money_display(row.monthly_price_minor, c),
            "per_min_minor": int(row.per_min_minor or 0),
            "per_min_display": money_display(int(row.per_min_minor or 0), c),
            "extra_per_min_minor": int(row.extra_per_min_minor or 0),
            "extra_per_min_display": money_display(int(row.extra_per_min_minor or 0), c),
            "is_active": bool(row.is_active),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def upsert_price(db: Session, *, plan_id: str, currency: str, payload: dict[str, Any]) -> PlanPrice:
        plan = db.get(Plan, plan_id)
        if plan is None:
            raise PlanPriceError("Plan not found")
        code = normalize_currency(currency)
        row = PlanPriceService.get_price(db, plan_id, code)
        now = datetime.utcnow()
        if row is None:
            row = PlanPrice(id=str(uuid.uuid4()), plan_id=plan_id, currency=code, created_at=now, updated_at=now)
        if "monthly_price_minor" in payload:
            value = payload["monthly_price_minor"]
            row.monthly_price_minor = None if value is None else max(0, int(value))
        for key in ("per_min_minor", "extra_per_min_minor"):
            if key in payload and payload[key] is not None:
                value = int(payload[key])
                if value < 0:
                    raise PlanPriceError(f"{key} cannot be negative")
                setattr(row, key, value)
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def ensure_seeded(db: Session) -> None:
        """Create GBP price rows from legacy plan GBP fields, and currency settings for all markets."""
        for currency in SUPPORTED_CURRENCIES:
            PlanPriceService.get_currency_settings(db, currency)
        plans = list(db.execute(select(Plan).where(Plan.service_kind == "voxbulk")).scalars().all())
        now = datetime.utcnow()
        created = False
        for plan in plans:
            existing = PlanPriceService.get_price(db, plan.id, "GBP")
            if existing is not None:
                continue
            db.add(
                PlanPrice(
                    id=str(uuid.uuid4()),
                    plan_id=plan.id,
                    currency="GBP",
                    monthly_price_minor=plan.price_gbp_pence,
                    per_min_minor=int(getattr(plan, "per_min_pence", 0) or 0),
                    extra_per_min_minor=int(plan.overage_per_min_pence or 0),
                    is_active=bool(plan.is_active),
                    created_at=now,
                    updated_at=now,
                )
            )
            created = True
        if created:
            db.commit()

    # ------------------------------------------------------------------ rate resolution

    @staticmethod
    def rates_for_org(db: Session, org: Organisation | None, *, plan: Plan | None = None) -> dict[str, Any]:
        """Resolve the effective billing currency + unit rates for an org.

        Org custom pricing (enterprise) overrides are applied on top of the currency defaults.
        """
        currency = resolve_org_currency(db, org)
        unit = PlanPriceService.get_currency_settings(db, currency)
        plan_price = PlanPriceService.get_price(db, plan.id, currency) if plan is not None else None

        per_min = int(plan_price.per_min_minor or 0) if plan_price else 0
        extra_per_min = int(plan_price.extra_per_min_minor or 0) if plan_price else 0
        monthly = plan_price.monthly_price_minor if plan_price else (plan.price_gbp_pence if plan is not None and currency == "GBP" else None)
        if per_min <= 0:
            per_min = int(unit.interview_per_min_minor or 0)
        if extra_per_min <= 0:
            extra_per_min = per_min

        rates: dict[str, Any] = {
            "currency": currency,
            "monthly_price_minor": monthly,
            "per_min_minor": per_min,
            "extra_per_min_minor": extra_per_min,
            "connection_fee_minor": int(unit.connection_fee_minor or 0),
            "interview_per_min_minor": per_min if plan_price else int(unit.interview_per_min_minor or 0),
            "wa_package_fee_minor": int(unit.wa_package_fee_minor or 0),
            "wa_extra_minor": int(unit.wa_extra_minor or 0),
            "cv_scan_fee_minor": int(unit.cv_scan_fee_minor or 0),
        }

        # Enterprise org-specific overrides (stored in GBP-era pence; only applied for GBP orgs)
        if org is not None and currency == "GBP":
            try:
                from app.services.voxbulk_pricing_service import VoxbulkPricingService

                custom = VoxbulkPricingService.get_org_custom_pricing(db, org.id)
            except Exception:
                custom = None
            if custom is not None:
                if custom.per_min_pence is not None:
                    rates["per_min_minor"] = int(custom.per_min_pence)
                    rates["interview_per_min_minor"] = int(custom.per_min_pence)
                if custom.connection_fee_pence is not None:
                    rates["connection_fee_minor"] = int(custom.connection_fee_pence)
                if custom.wa_survey_package_fee_pence is not None:
                    rates["wa_package_fee_minor"] = int(custom.wa_survey_package_fee_pence)
                if custom.wa_survey_extra_pence is not None:
                    rates["wa_extra_minor"] = int(custom.wa_survey_extra_pence)
                if custom.ats_cv_scan_fee_pence is not None:
                    rates["cv_scan_fee_minor"] = int(custom.ats_cv_scan_fee_pence)

        rates["display"] = {
            "monthly_price": money_display(rates["monthly_price_minor"], currency),
            "per_min": money_display(rates["per_min_minor"], currency),
            "extra_per_min": money_display(rates["extra_per_min_minor"], currency),
            "connection_fee": money_display(rates["connection_fee_minor"], currency),
            "wa_package_fee": money_display(rates["wa_package_fee_minor"], currency),
            "wa_extra": money_display(rates["wa_extra_minor"], currency),
            "cv_scan_fee": money_display(rates["cv_scan_fee_minor"], currency),
        }
        return rates

    @staticmethod
    def plan_public_dict(db: Session, plan: Plan, *, currency: str) -> dict[str, Any]:
        """Public plan payload priced in a single explicit currency."""
        code = normalize_currency(currency)
        price = PlanPriceService.get_price(db, plan.id, code)
        unit = PlanPriceService.get_currency_settings(db, code)
        monthly = price.monthly_price_minor if price else (plan.price_gbp_pence if code == "GBP" else None)
        per_min = int(price.per_min_minor or 0) if price else (int(getattr(plan, "per_min_pence", 0) or 0) if code == "GBP" else 0)
        extra_min = int(price.extra_per_min_minor or 0) if price else (int(plan.overage_per_min_pence or 0) if code == "GBP" else 0)
        wa_unit = int(unit.wa_package_fee_minor or 0)
        cv_unit = int(unit.cv_scan_fee_minor or 0)
        is_enterprise = bool(getattr(plan, "is_enterprise", False))
        monthly_int = int(monthly or 0)
        minutes_inc = monthly_int // per_min if per_min > 0 and not is_enterprise else 0
        wa_inc = monthly_int // wa_unit if wa_unit > 0 and not is_enterprise else 0
        cv_inc = monthly_int // cv_unit if cv_unit > 0 and not is_enterprise else 0
        import json as _json

        try:
            features = _json.loads(plan.features_json) if plan.features_json else []
            features = [str(x) for x in features] if isinstance(features, list) else []
        except Exception:
            features = []
        return {
            "id": plan.id,
            "code": plan.code,
            "name": plan.name,
            "currency": code,
            "monthly_price_minor": monthly,
            "monthly_price_display": money_display(monthly, code),
            "price_display": money_display(monthly, code),
            "interval": plan.interval,
            "description": plan.description,
            "features": features,
            "minutes_included": minutes_inc,
            "whatsapp_included": wa_inc,
            "cv_scans_included": cv_inc,
            "per_min_minor": per_min,
            "per_min_display": money_display(per_min, code),
            "extra_per_min_minor": extra_min,
            "extra_per_min_display": money_display(extra_min, code),
            "wa_unit_minor": wa_unit,
            "wa_unit_display": money_display(wa_unit, code),
            "wa_extra_minor": int(unit.wa_extra_minor or 0),
            "wa_extra_display": money_display(int(unit.wa_extra_minor or 0), code),
            "cv_unit_minor": cv_unit,
            "cv_unit_display": money_display(cv_unit, code),
            "connection_fee_minor": int(unit.connection_fee_minor or 0),
            "connection_fee_display": money_display(int(unit.connection_fee_minor or 0), code),
            "is_featured": bool(getattr(plan, "is_featured", False)),
            "is_enterprise": is_enterprise,
            "is_payg": str(plan.code or "").lower() == "payg",
            "is_active": bool(plan.is_active),
            "sort_order": int(plan.sort_order or 100),
            "priced": price is not None or code == "GBP",
        }
