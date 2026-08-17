"""Admin package catalog — Core / Customer Feedback / Expo packages with multi-currency prices."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FEEDBACK_SERVICE_CODE, FeedbackPackage
from app.models.expo import EXPO_SERVICE_CODE, ExpoPackage
from app.models.smart_card import SMART_CARD_SERVICE_CODE, SmartCardPackage
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.models.org_package_assignment import PlanUnitRate
from app.services.billing_currency import SUPPORTED_CURRENCIES, normalize_currency
from app.services.plan_admin_service import PlanAdminError, PlanAdminService
from app.services.plan_price_service import PlanPriceError, PlanPriceService
from app.services.pricing_fx_service import PricingFxService

SERVICE_KINDS = ("voxbulk", "customer_feedback", "expo", "smart_card")
_ZONE_SUFFIX_RE = re.compile(r"_(gb|eu|us|ca|au)$", re.IGNORECASE)
_ZONE_CURRENCY = {"gb": "GBP", "eu": "EUR", "us": "USD", "ca": "CAD", "au": "AUD"}
_CURRENCY_ZONE = {v: k for k, v in _ZONE_CURRENCY.items()}

# Public-facing blurbs for empty plan.description (insert-only; never overwrite Admin edits).
_DEFAULT_PLAN_DESCRIPTIONS: dict[str, str] = {
    # Match public-site fallbacks / marketing blurbs (insert-only when plan.description is empty).
    "payg": "Only pay for what you use · no monthly fee",
    "starter": "Best for a single hiring manager or small team trialling AI interviews and WhatsApp surveys.",
    "pro": "Our most popular plan — for growing teams running weekly interview and survey campaigns.",
    "business": "High-volume recruitment and survey operations across multiple hiring managers.",
    "enterprise": "Volume rates · SLA · dedicated support",
    "cf_starter": "Best for a single location getting started with WhatsApp and web feedback.",
    "feedback_starter": "Best for a single location getting started with WhatsApp and web feedback.",
    "cf_growth": "For multi-location teams who want a live dashboard and weekly reporting.",
    "feedback_growth": "For multi-location teams who want a live dashboard and weekly reporting.",
    "cf_pro": "Unlimited feedback across up to 10 locations, with a dedicated account manager.",
    "feedback_pro": "Unlimited feedback across up to 10 locations, with a dedicated account manager.",
    "expo_day1": "Single-day booth QR for small local shows and pop-ups.",
    "expo_day3": "Multi-day booth QR for regional exhibitions and trade fairs.",
    "expo_day7": "Full-week coverage for flagship trade shows, with post-show follow-up and an AI wrap-up report.",
    "sc_monthly": "Pay-monthly seat for reps who want to try Smart Card without a commitment.",
    "sc_yearly": "20% cheaper per seat, with owner visibility across every rep and catalogue matching included.",
}


class PricingPackagesError(ValueError):
    pass


class PricingPackagesService:
    @staticmethod
    def ensure_catalog_copy(db: Session) -> None:
        """Fill empty descriptions and ensure GBP prices / unit rates exist for catalog plans."""
        from app.services.voxbulk_pricing_service import VoxbulkPricingService

        try:
            VoxbulkPricingService.ensure_seeded(db)
        except Exception:
            pass
        PlanPriceService.ensure_seeded(db)
        PricingFxService.ensure_seeded(db)

        plans = list(
            db.execute(
                select(Plan).where(
                    Plan.service_kind.in_(list(SERVICE_KINDS)),
                    Plan.is_private.is_(False),
                )
            )
            .scalars()
            .all()
        )
        now = datetime.utcnow()
        changed = False
        for plan in plans:
            code = str(plan.code or "").strip().lower()
            family = _ZONE_SUFFIX_RE.sub("", code)
            blurb = _DEFAULT_PLAN_DESCRIPTIONS.get(code) or _DEFAULT_PLAN_DESCRIPTIONS.get(family)
            if blurb and not str(plan.description or "").strip():
                plan.description = blurb
                plan.updated_at = now
                db.add(plan)
                changed = True

            if str(plan.service_kind or "") != "voxbulk":
                continue
            # Ensure per-plan WA/CV rows exist (connection stays shared / null).
            unit = PlanPriceService.get_currency_settings(db, "GBP")
            for currency in SUPPORTED_CURRENCIES:
                existing = db.execute(
                    select(PlanUnitRate).where(PlanUnitRate.plan_id == plan.id, PlanUnitRate.currency == currency)
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                cur_settings = PlanPriceService.get_currency_settings(db, currency)
                db.add(
                    PlanUnitRate(
                        id=str(uuid.uuid4()),
                        plan_id=plan.id,
                        currency=currency,
                        connection_fee_minor=None,
                        interview_per_min_minor=None,
                        wa_package_fee_minor=int(cur_settings.wa_package_fee_minor or unit.wa_package_fee_minor or 50),
                        wa_extra_minor=int(cur_settings.wa_extra_minor or unit.wa_extra_minor or 49),
                        cv_scan_fee_minor=int(cur_settings.cv_scan_fee_minor or unit.cv_scan_fee_minor or 75),
                        created_at=now,
                        updated_at=now,
                    )
                )
                changed = True
            # Ensure GBP plan price row exists with AI rates from plan legacy fields if missing.
            gbp = PlanPriceService.get_price(db, plan.id, "GBP")
            if gbp is None and not bool(getattr(plan, "is_enterprise", False)):
                monthly = 0 if str(plan.code or "").lower() == "payg" else plan.price_gbp_pence
                PlanPriceService.upsert_price(
                    db,
                    plan_id=plan.id,
                    currency="GBP",
                    payload={
                        "monthly_price_minor": monthly,
                        "yearly_price_minor": (int(monthly) * 10) if monthly and int(monthly) > 0 else None,
                        "per_min_minor": int(getattr(plan, "per_min_pence", 0) or 0),
                        "extra_per_min_minor": int(plan.overage_per_min_pence or 0),
                        "is_active": bool(plan.is_active),
                    },
                    commit=False,
                    sync_fx=True,
                )
                changed = True
        if changed:
            db.commit()

    @staticmethod
    def list_packages(
        db: Session,
        *,
        service_kind: str | None = None,
        active_only: bool = True,
    ) -> dict[str, Any]:
        PricingPackagesService.ensure_catalog_copy(db)
        kinds = [service_kind] if service_kind else list(SERVICE_KINDS)
        out: dict[str, list[dict[str, Any]]] = {k: [] for k in SERVICE_KINDS}
        for kind in kinds:
            if kind not in SERVICE_KINDS:
                raise PricingPackagesError(f"Unsupported service_kind: {kind}")
            if kind == "voxbulk":
                out[kind] = PricingPackagesService._list_voxbulk(db, active_only=active_only)
            elif kind == "customer_feedback":
                out[kind] = PricingPackagesService._list_feedback(db, active_only=active_only)
            elif kind == "smart_card":
                out[kind] = PricingPackagesService._list_smart_card(db, active_only=active_only)
            else:
                out[kind] = PricingPackagesService._list_expo(db, active_only=active_only)
        return {
            "ok": True,
            "supported_currencies": list(SUPPORTED_CURRENCIES),
            "packages": out if not service_kind else {service_kind: out[service_kind]},
        }

    @staticmethod
    def _prices_map(db: Session, plan_id: str) -> dict[str, dict[str, Any]]:
        prices = {row.currency: PlanPriceService.price_to_dict(row) for row in PlanPriceService.list_for_plan(db, plan_id)}
        for currency in SUPPORTED_CURRENCIES:
            prices.setdefault(
                currency,
                {
                    "currency": currency,
                    "monthly_price_minor": None,
                    "yearly_price_minor": None,
                    "per_min_minor": 0,
                    "extra_per_min_minor": 0,
                },
            )
        return prices

    @staticmethod
    def _unit_rates_map(db: Session, plan_id: str) -> dict[str, dict[str, Any]]:
        rows = list(
            db.execute(select(PlanUnitRate).where(PlanUnitRate.plan_id == plan_id)).scalars().all()
        )
        by_cur = {str(r.currency).upper(): r for r in rows}
        out: dict[str, dict[str, Any]] = {}
        for currency in SUPPORTED_CURRENCIES:
            row = by_cur.get(currency)
            if row is None:
                out[currency] = {
                    "currency": currency,
                    "wa_package_fee_minor": None,
                    "wa_extra_minor": None,
                    "cv_scan_fee_minor": None,
                }
            else:
                out[currency] = {
                    "currency": currency,
                    "wa_package_fee_minor": row.wa_package_fee_minor,
                    "wa_extra_minor": row.wa_extra_minor,
                    "cv_scan_fee_minor": row.cv_scan_fee_minor,
                }
        return out

    @staticmethod
    def _list_voxbulk(db: Session, *, active_only: bool) -> list[dict[str, Any]]:
        q = select(Plan).where(Plan.service_kind == "voxbulk", Plan.is_private.is_(False)).order_by(Plan.sort_order.asc(), Plan.name.asc())
        if active_only:
            q = q.where(Plan.is_active.is_(True))
        rows = list(db.execute(q).scalars().all())
        out = []
        for plan in rows:
            base = PlanAdminService.plan_to_dict(plan)
            out.append(
                {
                    **base,
                    "package_id": None,
                    "prices": PricingPackagesService._prices_map(db, plan.id),
                    "unit_rates": PricingPackagesService._unit_rates_map(db, plan.id),
                }
            )
        return out

    @staticmethod
    def _cf_family_key(code: str) -> str:
        return _ZONE_SUFFIX_RE.sub("", str(code or "").strip().lower())

    @staticmethod
    def _list_feedback(db: Session, *, active_only: bool) -> list[dict[str, Any]]:
        """One admin row per package family — prefer GB zone, assemble multi-currency from siblings."""
        q = (
            select(Plan, FeedbackPackage)
            .join(FeedbackPackage, FeedbackPackage.plan_id == Plan.id)
            .where(Plan.service_kind == FEEDBACK_SERVICE_CODE, Plan.is_private.is_(False))
            .order_by(FeedbackPackage.display_order.asc(), Plan.name.asc())
        )
        if active_only:
            q = q.where(Plan.is_active.is_(True), FeedbackPackage.is_active.is_(True))
        rows = list(db.execute(q).all())
        by_family: dict[str, list[tuple[Plan, FeedbackPackage]]] = {}
        for plan, pkg in rows:
            key = PricingPackagesService._cf_family_key(plan.code)
            by_family.setdefault(key, []).append((plan, pkg))

        out: list[dict[str, Any]] = []
        for family, members in by_family.items():
            primary = next((m for m in members if m[1].market_zone == "gb"), members[0])
            plan, pkg = primary
            prices: dict[str, dict[str, Any]] = {}
            for currency in SUPPORTED_CURRENCIES:
                zone = _CURRENCY_ZONE.get(currency, "gb")
                sibling = next((m for m in members if m[1].market_zone == zone), None)
                target_plan = sibling[0] if sibling else plan
                row = PlanPriceService.get_price(db, target_plan.id, currency)
                if row is None and sibling is None:
                    row = PlanPriceService.get_price(db, plan.id, currency)
                prices[currency] = (
                    PlanPriceService.price_to_dict(row)
                    if row
                    else {
                        "currency": currency,
                        "monthly_price_minor": None,
                        "yearly_price_minor": None,
                        "per_min_minor": 0,
                        "extra_per_min_minor": 0,
                    }
                )
            base = PlanAdminService.plan_to_dict(plan)
            out.append(
                {
                    **base,
                    "code": family if family.startswith("cf_") else plan.code,
                    "package_id": pkg.id,
                    "market_zone": pkg.market_zone,
                    "max_locations": int(pkg.max_locations or 0),
                    "wa_units_included": int(pkg.wa_units_included or 0),
                    "web_units_included": int(pkg.web_units_included or 0),
                    "promo_message_cost_minor": int(pkg.promo_message_cost_minor or 0),
                    "prices": prices,
                    "family_plan_ids": {m[1].market_zone: m[0].id for m in members},
                }
            )
        out.sort(key=lambda x: (int(x.get("sort_order") or 100), str(x.get("name") or "")))
        return out

    @staticmethod
    def _list_expo(db: Session, *, active_only: bool) -> list[dict[str, Any]]:
        q = (
            select(Plan, ExpoPackage)
            .join(ExpoPackage, ExpoPackage.plan_id == Plan.id)
            .where(Plan.service_kind == EXPO_SERVICE_CODE, ExpoPackage.market_zone == "all", Plan.is_private.is_(False))
            .order_by(ExpoPackage.display_order.asc(), Plan.name.asc())
        )
        if active_only:
            q = q.where(Plan.is_active.is_(True), ExpoPackage.is_active.is_(True))
        rows = list(db.execute(q).all())
        out = []
        for plan, pkg in rows:
            base = PlanAdminService.plan_to_dict(plan)
            out.append(
                {
                    **base,
                    "package_id": pkg.id,
                    "market_zone": pkg.market_zone,
                    "tier": pkg.tier,
                    "duration_days": int(pkg.duration_days or 1),
                    "max_booths": int(pkg.max_booths or 1),
                    "max_assets": int(pkg.max_assets or 5),
                    "lead_scoring_enabled": bool(pkg.lead_scoring_enabled),
                    "post_show_followup_enabled": bool(pkg.post_show_followup_enabled),
                    "post_event_survey_enabled": bool(pkg.post_event_survey_enabled),
                    "ai_summary_report_enabled": bool(pkg.ai_summary_report_enabled),
                    "prices": PricingPackagesService._prices_map(db, plan.id),
                }
            )
        return out

    @staticmethod
    def _list_smart_card(db: Session, *, active_only: bool) -> list[dict[str, Any]]:
        q = (
            select(Plan, SmartCardPackage)
            .join(SmartCardPackage, SmartCardPackage.plan_id == Plan.id)
            .where(Plan.service_kind == SMART_CARD_SERVICE_CODE, Plan.is_private.is_(False))
            .order_by(SmartCardPackage.display_order.asc(), Plan.name.asc())
        )
        if active_only:
            q = q.where(Plan.is_active.is_(True), SmartCardPackage.is_active.is_(True))
        rows = list(db.execute(q).all())
        out = []
        for plan, pkg in rows:
            base = PlanAdminService.plan_to_dict(plan)
            out.append(
                {
                    **base,
                    "package_id": pkg.id,
                    "tier": pkg.tier,
                    "monthly_unit_hint_usd_cents": int(pkg.monthly_unit_hint_usd_cents or 500),
                    "prices": PricingPackagesService._prices_map(db, plan.id),
                }
            )
        return out

    @staticmethod
    def get_package(db: Session, plan_id: str) -> dict[str, Any] | None:
        plan = PlanAdminService.get_plan(db, plan_id)
        if plan is None:
            return None
        kind = str(plan.service_kind or "voxbulk")
        items = PricingPackagesService.list_packages(db, service_kind=kind, active_only=False)["packages"][kind]
        return next((x for x in items if x["id"] == plan_id), None)

    @staticmethod
    def create_package(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload.get("service_kind") or "voxbulk").strip()
        if kind not in SERVICE_KINDS:
            raise PricingPackagesError(f"Unsupported service_kind: {kind}")
        now = datetime.utcnow()
        name = str(payload.get("name") or "").strip()
        if not name:
            raise PricingPackagesError("Package name is required")

        if kind == "voxbulk":
            create_payload = {
                **payload,
                "service_kind": "voxbulk",
                "interval": payload.get("interval") or "monthly",
                "is_active": bool(payload.get("is_active", True)),
            }
            try:
                plan = PlanAdminService.create_plan(db, create_payload)
            except PlanAdminError as exc:
                raise PricingPackagesError(str(exc)) from exc
            if payload.get("prices"):
                PricingPackagesService.upsert_prices(db, plan.id, payload["prices"], commit=True)
            if payload.get("unit_rates"):
                PricingPackagesService.upsert_unit_rates(db, plan.id, payload["unit_rates"], commit=True)
            return PricingPackagesService.get_package(db, plan.id)  # type: ignore[return-value]

        if kind == "expo":
            try:
                code = PlanAdminService.normalize_code(str(payload.get("code") or name))
            except PlanAdminError as exc:
                raise PricingPackagesError(str(exc)) from exc
            if not code.startswith("expo_"):
                code = f"expo_{code}"
            existing = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
            if existing is not None:
                raise PricingPackagesError(f"Plan code already exists: {code}")
            days = max(1, int(payload.get("duration_days") or 1))
            tier = str(payload.get("tier") or f"day{days}").strip()[:32]
            plan = Plan(
                id=str(uuid.uuid4()),
                code=code,
                name=name,
                price_gbp_pence=int(payload.get("price_gbp_pence") or 0),
                interval="one_time",
                description=str(payload.get("description") or "").strip() or None,
                features_json=json.dumps(payload["features"]) if isinstance(payload.get("features"), list) else None,
                service_kind=EXPO_SERVICE_CODE,
                is_active=bool(payload.get("is_active", True)),
                is_featured=bool(payload.get("is_featured", False)),
                sort_order=int(payload.get("sort_order") or 100),
                created_at=now,
                updated_at=now,
            )
            db.add(plan)
            db.flush()
            expo_pkg = ExpoPackage(
                id=str(uuid.uuid4()),
                plan_id=plan.id,
                market_zone="all",
                tier=tier,
                duration_days=days,
                max_booths=int(payload.get("max_booths") or 1),
                max_assets=int(payload.get("max_assets") or 5),
                lead_scoring_enabled=bool(payload.get("lead_scoring_enabled", True)),
                post_show_followup_enabled=bool(payload.get("post_show_followup_enabled", False)),
                post_event_survey_enabled=bool(payload.get("post_event_survey_enabled", False)),
                ai_summary_report_enabled=bool(payload.get("ai_summary_report_enabled", False)),
                display_order=int(payload.get("sort_order") or 100),
                is_active=bool(payload.get("is_active", True)),
                created_at=now,
                updated_at=now,
            )
            db.add(expo_pkg)
            db.commit()
            if payload.get("prices"):
                PricingPackagesService.upsert_prices(db, plan.id, payload["prices"], commit=True)
            return PricingPackagesService.get_package(db, plan.id)  # type: ignore[return-value]

        if kind == "smart_card":
            try:
                code = PlanAdminService.normalize_code(str(payload.get("code") or name))
            except PlanAdminError as exc:
                raise PricingPackagesError(str(exc)) from exc
            if not (code.startswith("sc_") or code.startswith("smart_card_")):
                code = f"sc_{code}"
            existing = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
            if existing is not None:
                raise PricingPackagesError(f"Plan code already exists: {code}")
            tier = str(payload.get("tier") or "seat").strip()[:32] or "seat"
            plan = Plan(
                id=str(uuid.uuid4()),
                code=code,
                name=name,
                price_gbp_pence=int(payload.get("price_gbp_pence") or 0),
                interval=str(payload.get("interval") or "yearly"),
                description=str(payload.get("description") or "").strip() or None,
                features_json=json.dumps(payload["features"]) if isinstance(payload.get("features"), list) else None,
                service_kind=SMART_CARD_SERVICE_CODE,
                is_active=bool(payload.get("is_active", True)),
                is_featured=bool(payload.get("is_featured", False)),
                sort_order=int(payload.get("sort_order") or 100),
                created_at=now,
                updated_at=now,
            )
            db.add(plan)
            db.flush()
            sc_pkg = SmartCardPackage(
                id=str(uuid.uuid4()),
                plan_id=plan.id,
                tier=tier,
                monthly_unit_hint_usd_cents=int(payload.get("monthly_unit_hint_usd_cents") or 500),
                display_order=int(payload.get("sort_order") or 100),
                is_active=bool(payload.get("is_active", True)),
                created_at=now,
                updated_at=now,
            )
            db.add(sc_pkg)
            db.commit()
            if payload.get("prices"):
                PricingPackagesService.upsert_prices(db, plan.id, payload["prices"], commit=True)
            return PricingPackagesService.get_package(db, plan.id)  # type: ignore[return-value]

        # customer_feedback — create GB package (+ optional prices); sibling zones get price sync on save
        zone = "gb"
        suffix = uuid.uuid4().hex[:6]
        raw_code = str(payload.get("code") or "").strip().lower()
        family = PricingPackagesService._cf_family_key(raw_code) if raw_code else f"cf_{PlanAdminService.normalize_code(name)}_{suffix}"
        if not family.startswith("cf_"):
            family = f"cf_{family}"
        code = f"{family}_{zone}"
        if db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none():
            code = f"{family}_{suffix}_{zone}"
            family = PricingPackagesService._cf_family_key(code)
        max_order = db.execute(
            select(func.max(FeedbackPackage.display_order)).where(FeedbackPackage.market_zone == zone)
        ).scalar()
        display_order = int(payload.get("sort_order") or (int(max_order or 0) + 10))
        plan = Plan(
            id=str(uuid.uuid4()),
            code=code,
            name=name,
            price_gbp_pence=int(payload.get("price_gbp_pence") or 0),
            interval=str(payload.get("interval") or "monthly"),
            description=str(payload.get("description") or "").strip() or None,
            features_json=json.dumps(payload["features"]) if isinstance(payload.get("features"), list) else None,
            service_kind=FEEDBACK_SERVICE_CODE,
            is_active=bool(payload.get("is_active", True)),
            is_featured=bool(payload.get("is_featured", False)),
            is_enterprise=bool(payload.get("is_enterprise", False)),
            sort_order=display_order,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        db.flush()
        pkg = FeedbackPackage(
            id=str(uuid.uuid4()),
            plan_id=plan.id,
            market_zone=zone,
            max_locations=int(payload.get("max_locations") or 1),
            wa_units_included=int(payload.get("wa_units_included") or 100),
            web_units_included=int(payload.get("web_units_included") or 100),
            promo_message_cost_minor=int(payload.get("promo_message_cost_minor") or 5),
            display_order=display_order,
            is_active=bool(payload.get("is_active", True)),
            created_at=now,
            updated_at=now,
        )
        db.add(pkg)
        db.commit()
        if payload.get("prices"):
            PricingPackagesService.upsert_prices(db, plan.id, payload["prices"], commit=True)
        return PricingPackagesService.get_package(db, plan.id)  # type: ignore[return-value]

    @staticmethod
    def update_package(db: Session, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = PlanAdminService.get_plan(db, plan_id)
        if plan is None:
            raise PricingPackagesError("Package not found")
        kind = str(plan.service_kind or "voxbulk")
        now = datetime.utcnow()

        plan_fields = {
            k: payload[k]
            for k in (
                "name",
                "description",
                "features",
                "interval",
                "calls_included",
                "minutes_included",
                "whatsapp_included",
                "sms_included",
                "cv_scans_included",
                "per_min_pence",
                "extra_per_min_pence",
                "overage_per_min_pence",
                "trial_days_default",
                "sort_order",
                "is_active",
                "is_featured",
                "is_enterprise",
                "price_gbp_pence",
            )
            if k in payload
        }
        if plan_fields:
            try:
                plan = PlanAdminService.update_plan(db, plan, plan_fields)
            except PlanAdminError as exc:
                raise PricingPackagesError(str(exc)) from exc

        if kind == "expo":
            expo_pkg = db.execute(select(ExpoPackage).where(ExpoPackage.plan_id == plan.id)).scalar_one_or_none()
            if expo_pkg is None:
                raise PricingPackagesError("Expo package metadata missing")
            for field, caster in (
                ("duration_days", int),
                ("max_booths", int),
                ("max_assets", int),
                ("tier", str),
            ):
                if field in payload and payload[field] is not None:
                    setattr(expo_pkg, field, caster(payload[field]))
            for flag in (
                "lead_scoring_enabled",
                "post_show_followup_enabled",
                "post_event_survey_enabled",
                "ai_summary_report_enabled",
            ):
                if flag in payload:
                    setattr(expo_pkg, flag, bool(payload[flag]))
            if "is_active" in payload:
                expo_pkg.is_active = bool(payload["is_active"])
            if "sort_order" in payload:
                expo_pkg.display_order = int(payload["sort_order"] or 100)
            expo_pkg.market_zone = "all"
            expo_pkg.updated_at = now
            db.add(expo_pkg)
            db.commit()

        if kind == "smart_card":
            sc_pkg = db.execute(select(SmartCardPackage).where(SmartCardPackage.plan_id == plan.id)).scalar_one_or_none()
            if sc_pkg is None:
                raise PricingPackagesError("Smart Card package metadata missing")
            if "tier" in payload and payload["tier"] is not None:
                sc_pkg.tier = str(payload["tier"]).strip()[:32] or sc_pkg.tier
            if "monthly_unit_hint_usd_cents" in payload and payload["monthly_unit_hint_usd_cents"] is not None:
                sc_pkg.monthly_unit_hint_usd_cents = int(payload["monthly_unit_hint_usd_cents"])
            if "is_active" in payload:
                sc_pkg.is_active = bool(payload["is_active"])
            if "sort_order" in payload:
                sc_pkg.display_order = int(payload["sort_order"] or 100)
            sc_pkg.updated_at = now
            db.add(sc_pkg)
            db.commit()

        if kind == "customer_feedback":
            PricingPackagesService._update_feedback_family(db, plan, payload, now=now)

        if payload.get("prices"):
            PricingPackagesService.upsert_prices(db, plan.id, payload["prices"], commit=True)
        if payload.get("unit_rates") and kind == "voxbulk":
            PricingPackagesService.upsert_unit_rates(db, plan.id, payload["unit_rates"], commit=True)

        item = PricingPackagesService.get_package(db, plan.id)
        if item is None:
            raise PricingPackagesError("Package not found after update")
        return item

    @staticmethod
    def _update_feedback_family(db: Session, plan: Plan, payload: dict[str, Any], *, now: datetime) -> None:
        family = PricingPackagesService._cf_family_key(plan.code)
        members = list(
            db.execute(
                select(Plan, FeedbackPackage)
                .join(FeedbackPackage, FeedbackPackage.plan_id == Plan.id)
                .where(Plan.service_kind == FEEDBACK_SERVICE_CODE)
            ).all()
        )
        targets = [(p, pkg) for p, pkg in members if PricingPackagesService._cf_family_key(p.code) == family]
        if not targets:
            pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
            if pkg:
                targets = [(plan, pkg)]
        for p, pkg in targets:
            if "name" in payload and payload["name"] is not None:
                p.name = str(payload["name"]).strip() or p.name
            if "description" in payload:
                desc = str(payload.get("description") or "").strip()
                p.description = desc or None
            if "features_json" in payload:
                p.features_json = payload.get("features_json")
            if isinstance(payload.get("features"), list):
                p.features_json = json.dumps([str(x).strip() for x in payload["features"] if str(x).strip()]) or None
            if "is_active" in payload:
                active = bool(payload["is_active"])
                p.is_active = active
                pkg.is_active = active
            if "max_locations" in payload:
                pkg.max_locations = int(payload["max_locations"] or 1)
            if "wa_units_included" in payload:
                pkg.wa_units_included = int(payload["wa_units_included"] or 0)
            if "web_units_included" in payload:
                pkg.web_units_included = int(payload["web_units_included"] or 0)
            if "promo_message_cost_minor" in payload:
                pkg.promo_message_cost_minor = int(payload["promo_message_cost_minor"] or 5)
            if "sort_order" in payload:
                order = int(payload["sort_order"] or 100)
                p.sort_order = order
                pkg.display_order = order
            p.updated_at = now
            pkg.updated_at = now
            db.add(p)
            db.add(pkg)
        db.commit()

    @staticmethod
    def upsert_prices(
        db: Session,
        plan_id: str,
        prices: dict[str, Any] | list[dict[str, Any]],
        *,
        commit: bool = True,
    ) -> dict[str, Any]:
        plan = PlanAdminService.get_plan(db, plan_id)
        if plan is None:
            raise PricingPackagesError("Package not found")

        items: list[tuple[str, dict[str, Any]]] = []
        if isinstance(prices, dict):
            for currency, row in prices.items():
                if isinstance(row, dict):
                    items.append((normalize_currency(currency), row))
        elif isinstance(prices, list):
            for row in prices:
                if isinstance(row, dict) and row.get("currency"):
                    items.append((normalize_currency(str(row["currency"])), row))
        else:
            raise PricingPackagesError("prices must be an object or list")

        kind = str(plan.service_kind or "voxbulk")
        gbp_item = next(((c, r) for c, r in items if c == "GBP"), None)
        other_items = [(c, r) for c, r in items if c != "GBP"]

        # Save GBP first so FX can fill unlocked markets.
        if gbp_item is not None:
            currency, row = gbp_item
            payload = {
                k: row[k]
                for k in ("monthly_price_minor", "yearly_price_minor", "per_min_minor", "extra_per_min_minor", "is_active")
                if k in row
            }
            if row.get("force_fx_sync"):
                payload["force_fx_sync"] = True
            try:
                PlanPriceService.upsert_price(db, plan_id=plan.id, currency=currency, payload=payload, commit=False)
            except PlanPriceError as exc:
                raise PricingPackagesError(str(exc)) from exc
            if kind == "customer_feedback":
                PricingPackagesService._sync_feedback_zone_price(db, plan, currency, payload)
                for quote in SUPPORTED_CURRENCIES:
                    if quote == "GBP":
                        continue
                    synced = PlanPriceService.get_price(db, plan.id, quote)
                    if synced is None:
                        continue
                    sibling_payload = {
                        "monthly_price_minor": synced.monthly_price_minor,
                        "yearly_price_minor": synced.yearly_price_minor,
                        "per_min_minor": int(synced.per_min_minor or 0),
                        "extra_per_min_minor": int(synced.extra_per_min_minor or 0),
                        "is_active": bool(synced.is_active),
                        "_from_fx": not bool(getattr(synced, "manual_override", False)),
                        "manual_override": bool(getattr(synced, "manual_override", False)),
                    }
                    PricingPackagesService._sync_feedback_zone_price(db, plan, quote, sibling_payload)

        # Apply non-GBP only when Admin explicitly edited that market (or GBP was not in this save).
        for currency, row in other_items:
            explicit = bool(row.get("manual_override") or row.get("apply") or row.get("_manual_edit"))
            if gbp_item is not None and not explicit:
                existing = PlanPriceService.get_price(db, plan.id, currency)
                if existing is None or not bool(getattr(existing, "manual_override", False)):
                    continue
            payload = {
                k: row[k]
                for k in ("monthly_price_minor", "yearly_price_minor", "per_min_minor", "extra_per_min_minor", "is_active")
                if k in row
            }
            try:
                PlanPriceService.upsert_price(
                    db, plan_id=plan.id, currency=currency, payload=payload, commit=False, sync_fx=False
                )
            except PlanPriceError as exc:
                raise PricingPackagesError(str(exc)) from exc

            if kind == "customer_feedback":
                PricingPackagesService._sync_feedback_zone_price(db, plan, currency, payload)

        if commit:
            db.commit()
        item = PricingPackagesService.get_package(db, plan.id)
        if item is None:
            raise PricingPackagesError("Package not found")
        return item

    @staticmethod
    def upsert_unit_rates(
        db: Session,
        plan_id: str,
        unit_rates: dict[str, Any] | list[dict[str, Any]],
        *,
        commit: bool = True,
        force_fx_sync: bool = False,
    ) -> dict[str, Any]:
        """Upsert per-plan WA/CV unit rates. Connection fee is never stored here for catalog plans."""
        plan = PlanAdminService.get_plan(db, plan_id)
        if plan is None:
            raise PricingPackagesError("Package not found")

        items: list[tuple[str, dict[str, Any]]] = []
        if isinstance(unit_rates, dict):
            for currency, row in unit_rates.items():
                if isinstance(row, dict):
                    items.append((normalize_currency(currency), row))
        elif isinstance(unit_rates, list):
            for row in unit_rates:
                if isinstance(row, dict) and row.get("currency"):
                    items.append((normalize_currency(str(row["currency"])), row))
        else:
            raise PricingPackagesError("unit_rates must be an object or list")

        gbp_item = next(((c, r) for c, r in items if c == "GBP"), None)
        other_items = [(c, r) for c, r in items if c != "GBP"]
        now = datetime.utcnow()

        def write_row(currency: str, row: dict[str, Any], *, from_fx: bool = False) -> None:
            existing = db.execute(
                select(PlanUnitRate).where(PlanUnitRate.plan_id == plan_id, PlanUnitRate.currency == currency)
            ).scalar_one_or_none()
            if existing is None:
                existing = PlanUnitRate(
                    id=str(uuid.uuid4()), plan_id=plan_id, currency=currency, created_at=now, updated_at=now
                )
            for key in ("wa_package_fee_minor", "wa_extra_minor", "cv_scan_fee_minor"):
                if key in row and row[key] is not None and row[key] != "":
                    setattr(existing, key, max(0, int(row[key])))
            # Catalog packages: connection stays shared — leave null
            if str(plan.service_kind or "") == "voxbulk" and not bool(getattr(plan, "is_private", False)):
                existing.connection_fee_minor = None
            existing.updated_at = now
            db.add(existing)

        if gbp_item is not None:
            write_row("GBP", gbp_item[1])
            rates = PricingFxService.rate_map(db)
            gbp_payload = {
                "wa_package_fee_minor": gbp_item[1].get("wa_package_fee_minor"),
                "wa_extra_minor": gbp_item[1].get("wa_extra_minor"),
                "cv_scan_fee_minor": gbp_item[1].get("cv_scan_fee_minor"),
            }
            # Fill unlocked currencies from GBP (skip if Admin sent an explicit edit for that market)
            explicit = {
                c for c, r in other_items if r.get("manual_override") or r.get("_manual_edit") or r.get("apply")
            }
            for quote in SUPPORTED_CURRENCIES:
                if quote == "GBP":
                    continue
                if quote in explicit and not force_fx_sync:
                    continue
                converted = PricingFxService.convert_payload_from_gbp(
                    {k: int(v) for k, v in gbp_payload.items() if v is not None and v != ""},
                    quote,
                    rates,
                )
                write_row(quote, converted, from_fx=True)

        for currency, row in other_items:
            explicit = bool(row.get("manual_override") or row.get("_manual_edit") or row.get("apply"))
            if gbp_item is not None and not explicit and not force_fx_sync:
                continue
            write_row(currency, row)

        if commit:
            db.commit()
        item = PricingPackagesService.get_package(db, plan_id)
        if item is None:
            raise PricingPackagesError("Package not found")
        return item

    @staticmethod
    def _sync_feedback_zone_price(db: Session, plan: Plan, currency: str, payload: dict[str, Any]) -> None:
        zone = _CURRENCY_ZONE.get(normalize_currency(currency))
        if not zone:
            return
        family = PricingPackagesService._cf_family_key(plan.code)
        sibling_code = f"{family}_{zone}"
        sibling = db.execute(select(Plan).where(Plan.code == sibling_code)).scalar_one_or_none()
        if sibling is None or sibling.id == plan.id:
            return
        try:
            PlanPriceService.upsert_price(
                db,
                plan_id=sibling.id,
                currency=currency,
                payload=payload,
                commit=False,
                sync_fx=False,
            )
        except PlanPriceError:
            return

    @staticmethod
    def deactivate_package(db: Session, plan_id: str) -> dict[str, Any]:
        return PricingPackagesService.update_package(db, plan_id, {"is_active": False})
