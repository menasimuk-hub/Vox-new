from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.pricing import OrgCustomPricing, PricingGlobalSettings, TopupTier
from app.models.platform_service import PlatformService, ServicePricingRule
from app.services.platform_catalog_service import PlatformCatalogService

MARKETS = ("gbp", "aud", "cad", "usd")
MARKET_SYMBOLS = {"gbp": "£", "aud": "A$", "cad": "CA$", "usd": "$"}


class VoxbulkPricingError(ValueError):
    pass


class VoxbulkPricingService:
    @staticmethod
    def get_settings(db: Session) -> PricingGlobalSettings:
        row = db.get(PricingGlobalSettings, 1)
        if row is None:
            now = datetime.utcnow()
            row = PricingGlobalSettings(id=1, updated_at=now)
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def fx_multipliers(settings: PricingGlobalSettings) -> dict[str, float]:
        return {
            "gbp": 1.0,
            "aud": float(settings.fx_aud_multiplier or 1.95),
            "cad": float(settings.fx_cad_multiplier or 1.71),
            "usd": float(settings.fx_usd_multiplier or 1.26),
        }

    @staticmethod
    def convert_pence(pence: int | None, market: str, settings: PricingGlobalSettings) -> int | None:
        if pence is None:
            return None
        fx = VoxbulkPricingService.fx_multipliers(settings)
        m = str(market or "gbp").lower()
        return int(round(int(pence) * fx.get(m, 1.0)))

    @staticmethod
    def money_display(pence: int | None, market: str = "gbp", settings: PricingGlobalSettings | None = None) -> str:
        if pence is None:
            return "Custom"
        sym = MARKET_SYMBOLS.get(str(market or "gbp").lower(), "£")
        val = int(pence)
        if settings is not None and market != "gbp":
            val = VoxbulkPricingService.convert_pence(val, market, settings) or 0
        return f"{sym}{(val / 100):.2f}"

    @staticmethod
    def compute_plan_allowances(plan: Plan, settings: PricingGlobalSettings) -> dict[str, Any]:
        price = int(plan.price_gbp_pence or 0)
        per_min = int(getattr(plan, "per_min_pence", 0) or 0)
        extra = int(plan.overage_per_min_pence or 0)
        wa_unit = int(settings.wa_survey_package_fee_pence or 0)
        cv_unit = int(settings.ats_cv_scan_fee_pence or 0)
        mins = price // per_min if per_min > 0 else 0
        wa = price // wa_unit if wa_unit > 0 else 0
        cv = price // cv_unit if cv_unit > 0 else 0
        return {
            "minutes_included": mins,
            "whatsapp_included": wa,
            "cv_scans_included": cv,
            "per_min_pence": per_min,
            "extra_per_min_pence": extra,
            "wa_unit_pence": wa_unit,
            "cv_unit_pence": cv_unit,
            "minutes_formula": f"monthly ÷ cost/min = {price // 100}.{price % 100:02d} ÷ {per_min / 100:.2f}" if per_min else "",
            "wa_formula": f"monthly ÷ WA survey package fee = {price / 100:.2f} ÷ {wa_unit / 100:.2f} = {wa} recipients" if wa_unit else "",
            "cv_formula": f"monthly ÷ CV fee = {price / 100:.2f} ÷ {cv_unit / 100:.2f}" if cv_unit else "",
        }

    @staticmethod
    def apply_plan_allowances(db: Session, plan: Plan, settings: PricingGlobalSettings | None = None) -> Plan:
        if plan.is_enterprise or plan.service_kind != "voxbulk":
            return plan
        settings = settings or VoxbulkPricingService.get_settings(db)
        calc = VoxbulkPricingService.compute_plan_allowances(plan, settings)
        plan.calls_included = int(calc["minutes_included"])
        plan.whatsapp_included = int(calc["whatsapp_included"])
        plan.cv_scans_included = int(calc["cv_scans_included"])
        plan.updated_at = datetime.utcnow()
        db.add(plan)
        return plan

    @staticmethod
    def enrich_plan_dict(plan: Plan, base: dict[str, Any], settings: PricingGlobalSettings) -> dict[str, Any]:
        per_min = int(getattr(plan, "per_min_pence", 0) or 0)
        extra = int(plan.overage_per_min_pence or 0)
        out = {
            **base,
            "per_min_pence": per_min,
            "extra_per_min_pence": extra,
            "wa_unit_pence": int(settings.wa_survey_package_fee_pence or 0),
            "wa_survey_extra_pence": int(settings.wa_survey_extra_pence or 49),
            "cv_unit_pence": int(settings.ats_cv_scan_fee_pence or 0),
        }
        if plan.is_enterprise:
            return out
        calc = VoxbulkPricingService.compute_plan_allowances(plan, settings)
        out.update(calc)
        return out

    @staticmethod
    def plan_to_public_dict(row: Plan, *, market: str = "gbp", settings: PricingGlobalSettings) -> dict[str, Any]:
        fx = VoxbulkPricingService.fx_multipliers(settings)
        m = str(market or "gbp").lower()
        mult = fx.get(m, 1.0)
        per_min = int(getattr(row, "per_min_pence", 0) or row.overage_per_min_pence or 0)
        extra_min = int(row.overage_per_min_pence or 0)
        conn = int(settings.connection_fee_pence or 0) if settings.connection_fee_enabled else 0
        typical_low = conn + per_min * 10
        typical_high = conn + per_min * 15
        price = row.price_gbp_pence
        calc = VoxbulkPricingService.compute_plan_allowances(row, settings) if not row.is_enterprise else {}
        return {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "price_gbp_pence": price,
            "price_display_pence": None if price is None else int(round(price * mult)),
            "price_display": VoxbulkPricingService.money_display(price, m, settings),
            "interval": row.interval,
            "description": row.description,
            "features": VoxbulkPricingService._parse_features(row.features_json),
            "minutes_included": int(calc.get("minutes_included", row.calls_included or 0)),
            "whatsapp_included": int(calc.get("whatsapp_included", row.whatsapp_included or 0)),
            "cv_scans_included": int(calc.get("cv_scans_included", getattr(row, "cv_scans_included", 0) or 0)),
            "per_min_pence": per_min,
            "per_min_display": VoxbulkPricingService.money_display(per_min, m, settings),
            "extra_per_min_pence": extra_min,
            "extra_per_min_display": VoxbulkPricingService.money_display(extra_min, m, settings),
            "wa_unit_pence": int(settings.wa_survey_package_fee_pence or 0),
            "wa_unit_display": VoxbulkPricingService.money_display(int(settings.wa_survey_package_fee_pence or 0), m, settings),
            "wa_survey_extra_pence": int(settings.wa_survey_extra_pence or 49),
            "wa_survey_extra_display": VoxbulkPricingService.money_display(int(settings.wa_survey_extra_pence or 49), m, settings),
            "cv_unit_pence": int(settings.ats_cv_scan_fee_pence or 0),
            "cv_unit_display": VoxbulkPricingService.money_display(int(settings.ats_cv_scan_fee_pence or 0), m, settings),
            "minutes_formula": calc.get("minutes_formula"),
            "wa_formula": calc.get("wa_formula"),
            "cv_formula": calc.get("cv_formula"),
            "connection_fee_pence": conn,
            "connection_fee_display": VoxbulkPricingService.money_display(conn, m, settings),
            "typical_call_low_pence": int(round(typical_low * mult)),
            "typical_call_high_pence": int(round(typical_high * mult)),
            "typical_call_low_display": VoxbulkPricingService.money_display(typical_low, m, settings),
            "typical_call_high_display": VoxbulkPricingService.money_display(typical_high, m, settings),
            "is_featured": bool(getattr(row, "is_featured", False)),
            "is_enterprise": bool(getattr(row, "is_enterprise", False)),
            "is_payg": str(row.code or "").lower() == "payg",
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 100),
            "market": m,
        }

    @staticmethod
    def _parse_features(raw: str | None) -> list[str]:
        if not raw:
            return []
        import json

        try:
            val = json.loads(raw)
            return [str(x) for x in val] if isinstance(val, list) else []
        except Exception:
            return []

    @staticmethod
    def settings_to_dict(row: PricingGlobalSettings) -> dict[str, Any]:
        package_fee = int(row.wa_survey_package_fee_pence or 0)
        extra = int(row.wa_survey_extra_pence or 49)
        return {
            "fx_aud_multiplier": float(row.fx_aud_multiplier),
            "fx_cad_multiplier": float(row.fx_cad_multiplier),
            "fx_usd_multiplier": float(row.fx_usd_multiplier),
            "connection_fee_pence": int(row.connection_fee_pence or 0),
            "connection_fee_label": row.connection_fee_label,
            "connection_fee_enabled": bool(row.connection_fee_enabled),
            "interview_per_min_pence": int(row.interview_per_min_pence or 0),
            "wa_survey_package_fee_pence": package_fee,
            "wa_survey_extra_pence": extra,
            "whatsapp_survey_fee_pence": package_fee,
            "ats_cv_scan_fee_pence": int(row.ats_cv_scan_fee_pence or 0),
            "estimator_default_duration_min": int(row.estimator_default_duration_min or 12),
            "estimator_default_interview_count": int(row.estimator_default_interview_count or 100),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def update_settings(db: Session, payload: dict[str, Any]) -> PricingGlobalSettings:
        row = VoxbulkPricingService.get_settings(db)
        for key in (
            "fx_aud_multiplier",
            "fx_cad_multiplier",
            "fx_usd_multiplier",
            "connection_fee_pence",
            "connection_fee_label",
            "connection_fee_enabled",
            "interview_per_min_pence",
            "wa_survey_package_fee_pence",
            "wa_survey_extra_pence",
            "whatsapp_survey_fee_pence",
            "ats_cv_scan_fee_pence",
            "estimator_default_duration_min",
            "estimator_default_interview_count",
        ):
            if key in payload and payload[key] is not None:
                if key == "whatsapp_survey_fee_pence":
                    row.wa_survey_package_fee_pence = int(payload[key])
                else:
                    setattr(row, key, payload[key])
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def list_topup_tiers(db: Session, *, active_only: bool = False) -> list[TopupTier]:
        q = select(TopupTier).order_by(TopupTier.sort_order.asc(), TopupTier.credit_gbp_pence.asc())
        if active_only:
            q = q.where(TopupTier.is_active.is_(True))
        return list(db.execute(q).scalars().all())

    @staticmethod
    def topup_tier_to_dict(row: TopupTier, *, market: str = "gbp", settings: PricingGlobalSettings | None = None) -> dict[str, Any]:
        settings = settings or None
        credit = int(row.credit_gbp_pence or 0)
        bonus = int(row.bonus_credit_pence or 0)
        total = credit + bonus
        out: dict[str, Any] = {
            "id": row.id,
            "credit_gbp_pence": credit,
            "bonus_credit_pence": bonus,
            "total_credit_pence": total,
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 100),
        }
        if settings is not None:
            out["credit_display"] = VoxbulkPricingService.money_display(credit, market, settings)
            out["total_credit_display"] = VoxbulkPricingService.money_display(total, market, settings)
        return out

    @staticmethod
    def create_topup_tier(db: Session, payload: dict[str, Any]) -> TopupTier:
        now = datetime.utcnow()
        row = TopupTier(
            id=str(uuid.uuid4()),
            credit_gbp_pence=int(payload.get("credit_gbp_pence") or 0),
            bonus_credit_pence=int(payload.get("bonus_credit_pence") or 0),
            is_active=bool(payload.get("is_active", True)),
            sort_order=int(payload.get("sort_order") or 100),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_topup_tier(db: Session, row: TopupTier, payload: dict[str, Any]) -> TopupTier:
        for key in ("credit_gbp_pence", "bonus_credit_pence", "is_active", "sort_order"):
            if key in payload:
                setattr(row, key, payload[key])
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_topup_tier(db: Session, row: TopupTier) -> None:
        db.delete(row)
        db.commit()

    @staticmethod
    def list_custom_pricing(db: Session) -> list[OrgCustomPricing]:
        return list(db.execute(select(OrgCustomPricing).order_by(OrgCustomPricing.updated_at.desc())).scalars().all())

    @staticmethod
    def custom_pricing_to_dict(row: OrgCustomPricing, org: Organisation | None = None) -> dict[str, Any]:
        return {
            "id": row.id,
            "org_id": row.org_id,
            "org_name": org.name if org else None,
            "label": row.label,
            "monthly_price_gbp_pence": row.monthly_price_gbp_pence,
            "per_min_pence": row.per_min_pence,
            "connection_fee_pence": row.connection_fee_pence,
            "minutes_included": row.minutes_included,
            "whatsapp_included": row.whatsapp_included,
            "cv_scans_included": row.cv_scans_included,
            "interview_per_min_pence": row.interview_per_min_pence,
            "wa_survey_package_fee_pence": row.wa_survey_package_fee_pence,
            "wa_survey_extra_pence": row.wa_survey_extra_pence,
            "whatsapp_survey_fee_pence": row.wa_survey_package_fee_pence,
            "ats_cv_scan_fee_pence": row.ats_cv_scan_fee_pence,
            "is_active": bool(row.is_active),
            "notes": row.notes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def create_custom_pricing(db: Session, payload: dict[str, Any]) -> OrgCustomPricing:
        org_id = str(payload.get("org_id") or "").strip()
        if not org_id:
            raise VoxbulkPricingError("org_id is required")
        org = db.get(Organisation, org_id)
        if org is None:
            raise VoxbulkPricingError("Organisation not found")
        now = datetime.utcnow()
        row = OrgCustomPricing(
            id=str(uuid.uuid4()),
            org_id=org_id,
            label=str(payload.get("label") or f"Custom pricing — {org.name}"),
            monthly_price_gbp_pence=payload.get("monthly_price_gbp_pence"),
            per_min_pence=payload.get("per_min_pence"),
            connection_fee_pence=payload.get("connection_fee_pence"),
            minutes_included=payload.get("minutes_included"),
            whatsapp_included=payload.get("whatsapp_included"),
            cv_scans_included=payload.get("cv_scans_included"),
            interview_per_min_pence=payload.get("interview_per_min_pence"),
            wa_survey_package_fee_pence=payload.get("wa_survey_package_fee_pence") or payload.get("whatsapp_survey_fee_pence"),
            wa_survey_extra_pence=payload.get("wa_survey_extra_pence"),
            ats_cv_scan_fee_pence=payload.get("ats_cv_scan_fee_pence"),
            is_active=bool(payload.get("is_active", True)),
            notes=str(payload.get("notes") or "").strip() or None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_custom_pricing(db: Session, row: OrgCustomPricing, payload: dict[str, Any]) -> OrgCustomPricing:
        for key in (
            "label",
            "monthly_price_gbp_pence",
            "per_min_pence",
            "connection_fee_pence",
            "minutes_included",
            "whatsapp_included",
            "cv_scans_included",
            "interview_per_min_pence",
            "wa_survey_package_fee_pence",
            "wa_survey_extra_pence",
            "whatsapp_survey_fee_pence",
            "ats_cv_scan_fee_pence",
            "is_active",
            "notes",
        ):
            if key in payload:
                if key == "whatsapp_survey_fee_pence":
                    row.wa_survey_package_fee_pence = payload[key]
                else:
                    setattr(row, key, payload[key])
        row.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete_custom_pricing(db: Session, row: OrgCustomPricing) -> None:
        db.delete(row)
        db.commit()

    @staticmethod
    def get_org_custom_pricing(db: Session, org_id: str) -> OrgCustomPricing | None:
        return (
            db.execute(
                select(OrgCustomPricing)
                .where(OrgCustomPricing.org_id == org_id, OrgCustomPricing.is_active.is_(True))
                .order_by(OrgCustomPricing.updated_at.desc())
            )
            .scalars()
            .first()
        )

    @staticmethod
    def resolve_rates_for_org(db: Session, org_id: str | None, plan: Plan | None = None) -> dict[str, int]:
        settings = VoxbulkPricingService.get_settings(db)
        custom = VoxbulkPricingService.get_org_custom_pricing(db, org_id) if org_id else None
        per_min = int(custom.per_min_pence if custom and custom.per_min_pence is not None else (getattr(plan, "per_min_pence", None) if plan else None) or (plan.overage_per_min_pence if plan else settings.interview_per_min_pence) or settings.interview_per_min_pence)
        extra_min = int(
            plan.overage_per_min_pence
            if plan and plan.overage_per_min_pence
            else (custom.per_min_pence if custom and custom.per_min_pence is not None else settings.interview_per_min_pence)
        )
        conn = int(
            custom.connection_fee_pence
            if custom and custom.connection_fee_pence is not None
            else (settings.connection_fee_pence if settings.connection_fee_enabled else 0)
        )
        wa_pkg = int(
            custom.wa_survey_package_fee_pence
            if custom and custom.wa_survey_package_fee_pence is not None
            else settings.wa_survey_package_fee_pence
        )
        wa_extra = int(
            custom.wa_survey_extra_pence
            if custom and custom.wa_survey_extra_pence is not None
            else settings.wa_survey_extra_pence
        )
        ats = int(custom.ats_cv_scan_fee_pence if custom and custom.ats_cv_scan_fee_pence is not None else settings.ats_cv_scan_fee_pence)
        interview_per_min = int(
            custom.interview_per_min_pence
            if custom and custom.interview_per_min_pence is not None
            else (getattr(plan, "per_min_pence", None) if plan else None) or (plan.overage_per_min_pence if plan else settings.interview_per_min_pence)
        )
        return {
            "per_min_pence": per_min,
            "extra_per_min_pence": extra_min,
            "interview_per_min_pence": interview_per_min,
            "connection_fee_pence": conn,
            "wa_survey_package_fee_pence": wa_pkg,
            "wa_survey_extra_pence": wa_extra,
            "whatsapp_survey_fee_pence": wa_pkg,
            "ats_cv_scan_fee_pence": ats,
        }

    @staticmethod
    def interview_call_cost_pence(*, per_min_pence: int, duration_min: int, connection_fee_pence: int) -> int:
        return int(connection_fee_pence or 0) + max(int(duration_min or 0), 0) * int(per_min_pence or 0)

    @staticmethod
    def quote_wa_survey_launch(
        *,
        recipient_count: int,
        wa_remaining: int,
        wa_survey_extra_pence: int,
        has_subscription: bool,
    ) -> dict[str, Any]:
        """Price a WA survey launch by recipient allowance + extra rate."""
        count = max(int(recipient_count or 0), 0)
        remaining = max(int(wa_remaining or 0), 0)
        extra_rate = max(int(wa_survey_extra_pence or 0), 0)
        covered = min(remaining, count) if has_subscription else 0
        extra_recipients = max(0, count - covered)
        extra_pence = extra_recipients * extra_rate
        total_pence = extra_pence if has_subscription else count * extra_rate
        return {
            "recipient_count": count,
            "covered_recipients": covered,
            "extra_recipients": extra_recipients,
            "wa_survey_extra_pence": extra_rate,
            "extra_cost_pence": extra_pence,
            "extra_cost_display": VoxbulkPricingService.money_display(extra_pence),
            "total_pence": total_pence,
            "total_gbp": VoxbulkPricingService.money_display(total_pence),
            "pricing_source": "wa_survey_extra",
        }

    @staticmethod
    def quote_phone_survey_launch(
        db: Session,
        *,
        org_id: str,
        recipient_count: int,
        duration_min: int | None = None,
    ) -> dict[str, Any]:
        settings = VoxbulkPricingService.get_settings(db)
        rates = VoxbulkPricingService.resolve_rates_for_org(db, org_id)
        duration = max(int(duration_min or settings.estimator_default_duration_min or 12), 1)
        per_call = VoxbulkPricingService.interview_call_cost_pence(
            per_min_pence=int(rates["interview_per_min_pence"]),
            duration_min=duration,
            connection_fee_pence=int(rates["connection_fee_pence"]),
        )
        count = max(int(recipient_count or 0), 0)
        total = per_call * count
        return {
            "recipient_count": count,
            "duration_minutes": duration,
            "per_call_pence": per_call,
            "per_call_display": VoxbulkPricingService.money_display(per_call),
            "total_pence": total,
            "total_gbp": VoxbulkPricingService.money_display(total),
            "pricing_source": "interview_per_minute",
        }

    @staticmethod
    def estimate_interview_batch(
        *,
        per_min_pence: int,
        duration_min: int,
        interview_count: int,
        connection_fee_pence: int,
        market: str = "gbp",
        settings: PricingGlobalSettings,
    ) -> dict[str, Any]:
        per_call = VoxbulkPricingService.interview_call_cost_pence(
            per_min_pence=per_min_pence,
            duration_min=duration_min,
            connection_fee_pence=connection_fee_pence,
        )
        total = per_call * max(int(interview_count or 0), 0)
        m = str(market or "gbp").lower()
        return {
            "per_call_pence": per_call,
            "per_call_display": VoxbulkPricingService.money_display(per_call, m, settings),
            "total_pence": total,
            "total_display": VoxbulkPricingService.money_display(total, m, settings),
            "duration_min": duration_min,
            "interview_count": interview_count,
        }

    @staticmethod
    def topup_breakdown(
        *,
        credit_pence: int,
        settings: PricingGlobalSettings,
        per_min_pence: int | None = None,
        market: str = "gbp",
    ) -> dict[str, Any]:
        per_min = int(per_min_pence or settings.interview_per_min_pence or 35)
        conn = int(settings.connection_fee_pence or 0) if settings.connection_fee_enabled else 0
        avg_duration = int(settings.estimator_default_duration_min or 12)
        per_interview = VoxbulkPricingService.interview_call_cost_pence(
            per_min_pence=per_min, duration_min=avg_duration, connection_fee_pence=conn
        )
        wa_fee = int(settings.wa_survey_package_fee_pence or 50)
        ats_fee = int(settings.ats_cv_scan_fee_pence or 75)
        credit = max(int(credit_pence or 0), 0)
        interviews = per_interview > 0 and credit // per_interview or 0
        wa_surveys = wa_fee > 0 and credit // wa_fee or 0
        cv_scans = ats_fee > 0 and credit // ats_fee or 0
        call_minutes = per_min > 0 and max(0, (credit - conn * interviews)) // per_min if interviews else (per_min > 0 and credit // per_min or 0)
        m = str(market or "gbp").lower()
        return {
            "credit_pence": credit,
            "credit_display": VoxbulkPricingService.money_display(credit, m, settings),
            "estimated_interviews": int(interviews),
            "estimated_wa_survey_recipients": int(wa_surveys),
            "estimated_cv_scans": int(cv_scans),
            "estimated_call_minutes": int(call_minutes),
            "avg_call_duration_min": avg_duration,
        }

    @staticmethod
    def public_pricing_payload(db: Session, *, market: str = "gbp", org_id: str | None = None) -> dict[str, Any]:
        settings = VoxbulkPricingService.get_settings(db)
        from app.services.plan_admin_service import PlanAdminService

        plans = [p for p in PlanAdminService.list_plans(db, active_only=True) if getattr(p, "service_kind", "") == "voxbulk"]
        if not plans:
            plans = PlanAdminService.list_plans(db, active_only=True)
        custom = VoxbulkPricingService.get_org_custom_pricing(db, org_id) if org_id else None
        rates = VoxbulkPricingService.resolve_rates_for_org(db, org_id, plan=None)
        m = str(market or "gbp").lower()
        fx = VoxbulkPricingService.fx_multipliers(settings)
        plan_rows = [VoxbulkPricingService.plan_to_public_dict(p, market=m, settings=settings) for p in plans if p.is_active]
        tiers = [
            VoxbulkPricingService.topup_tier_to_dict(t, market=m, settings=settings)
            for t in VoxbulkPricingService.list_topup_tiers(db, active_only=True)
        ]
        services = {
            "interview_per_min_pence": rates["interview_per_min_pence"],
            "interview_per_min_display": VoxbulkPricingService.money_display(rates["interview_per_min_pence"], m, settings),
            "connection_fee_pence": rates["connection_fee_pence"],
            "connection_fee_display": VoxbulkPricingService.money_display(rates["connection_fee_pence"], m, settings),
            "connection_fee_label": settings.connection_fee_label,
            "connection_fee_enabled": bool(settings.connection_fee_enabled),
            "wa_survey_package_fee_pence": rates["wa_survey_package_fee_pence"],
            "wa_survey_package_fee_display": VoxbulkPricingService.money_display(rates["wa_survey_package_fee_pence"], m, settings),
            "wa_survey_extra_pence": rates["wa_survey_extra_pence"],
            "wa_survey_extra_display": VoxbulkPricingService.money_display(rates["wa_survey_extra_pence"], m, settings),
            "whatsapp_survey_fee_pence": rates["wa_survey_package_fee_pence"],
            "whatsapp_survey_display": VoxbulkPricingService.money_display(rates["wa_survey_package_fee_pence"], m, settings),
            "ats_cv_scan_fee_pence": rates["ats_cv_scan_fee_pence"],
            "ats_cv_scan_display": VoxbulkPricingService.money_display(rates["ats_cv_scan_fee_pence"], m, settings),
        }
        return {
            "market": m,
            "currency_symbol": MARKET_SYMBOLS.get(m, "£"),
            "fx_multipliers": fx,
            "settings": VoxbulkPricingService.settings_to_dict(settings),
            "plans": plan_rows,
            "services": services,
            "topup_tiers": tiers,
            "estimator_defaults": {
                "duration_min": int(settings.estimator_default_duration_min or 12),
                "interview_count": int(settings.estimator_default_interview_count or 100),
            },
            "custom_pricing_active": custom is not None,
        }

    @staticmethod
    def deposit_wallet(db: Session, org: Organisation, amount_pence: int) -> Organisation:
        amt = max(int(amount_pence or 0), 0)
        org.wallet_balance_pence = int(org.wallet_balance_pence or 0) + amt
        db.commit()
        db.refresh(org)
        return org

    @staticmethod
    def _upsert_voxbulk_plan(db: Session, s: dict[str, Any], *, settings: PricingGlobalSettings, now: datetime) -> None:
        existing = db.execute(select(Plan).where(Plan.code == s["code"])).scalar_one_or_none()
        if existing is not None:
            existing.name = s["name"]
            existing.price_gbp_pence = s["price_gbp_pence"]
            existing.per_min_pence = int(s.get("per_min_pence") or 0)
            existing.overage_per_min_pence = int(s.get("extra_per_min_pence") or 0)
            existing.is_featured = bool(s.get("is_featured"))
            existing.is_enterprise = bool(s.get("is_enterprise"))
            existing.service_kind = "voxbulk"
            existing.sort_order = int(s["sort_order"])
            existing.is_active = bool(s.get("is_active", True))
            existing.updated_at = now
            if not existing.is_enterprise:
                VoxbulkPricingService.apply_plan_allowances(db, existing, settings)
            return
        row = Plan(
            id=str(uuid.uuid4()),
            code=s["code"],
            name=s["name"],
            price_gbp_pence=s["price_gbp_pence"],
            interval="monthly",
            description=s.get("description"),
            features_json=None,
            calls_included=0,
            whatsapp_included=0,
            sms_included=0,
            cv_scans_included=0,
            per_min_pence=int(s.get("per_min_pence") or 0),
            overage_per_min_pence=int(s.get("extra_per_min_pence") or 0),
            trial_days_default=14,
            service_kind="voxbulk",
            is_active=bool(s.get("is_active", True)),
            is_featured=bool(s.get("is_featured")),
            is_enterprise=bool(s.get("is_enterprise")),
            sort_order=int(s["sort_order"]),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        if not row.is_enterprise:
            VoxbulkPricingService.apply_plan_allowances(db, row, settings)

    @staticmethod
    def ensure_payg_plan(db: Session) -> Plan | None:
        settings = VoxbulkPricingService.get_settings(db)
        per_min = int(settings.interview_per_min_pence or 35)
        now = datetime.utcnow()
        VoxbulkPricingService._upsert_voxbulk_plan(
            db,
            {
                "code": "payg",
                "name": "Pay as you go",
                "description": "No monthly subscription — top up your wallet and pay per interview, survey, or CV scan.",
                "price_gbp_pence": 0,
                "per_min_pence": per_min,
                "extra_per_min_pence": per_min,
                "sort_order": 5,
            },
            settings=settings,
            now=now,
        )
        db.commit()
        return db.execute(select(Plan).where(Plan.code == "payg")).scalar_one_or_none()

    @staticmethod
    def seed_voxbulk_plans(db: Session) -> None:
        """Ensure VoxBulk Pay-as-you-go, Starter/Pro/Business/Enterprise plans exist."""
        VoxbulkPricingService.get_settings(db)
        PlatformCatalogService.ensure_defaults(db)
        now = datetime.utcnow()
        settings = VoxbulkPricingService.get_settings(db)
        per_min = int(settings.interview_per_min_pence or 35)
        seeds = [
            {
                "code": "payg",
                "name": "Pay as you go",
                "description": "No monthly subscription — top up your wallet and pay per interview, survey, or CV scan.",
                "price_gbp_pence": 0,
                "per_min_pence": per_min,
                "extra_per_min_pence": per_min,
                "sort_order": 5,
            },
            {"code": "starter", "name": "Starter", "price_gbp_pence": 5900, "per_min_pence": 32, "extra_per_min_pence": 35, "sort_order": 10},
            {"code": "pro", "name": "Pro", "price_gbp_pence": 12900, "per_min_pence": 30, "extra_per_min_pence": 32, "is_featured": True, "sort_order": 20},
            {"code": "business", "name": "Business", "price_gbp_pence": 24900, "per_min_pence": 25, "extra_per_min_pence": 28, "sort_order": 30},
            {"code": "enterprise", "name": "Enterprise", "price_gbp_pence": None, "per_min_pence": 0, "extra_per_min_pence": 0, "is_enterprise": True, "sort_order": 40},
        ]
        for s in seeds:
            VoxbulkPricingService._upsert_voxbulk_plan(db, s, settings=settings, now=now)
        default_tiers = [
            (1000, 0, 10),
            (5000, 500, 20),
            (10000, 1500, 30),
            (25000, 5000, 40),
        ]
        existing_tiers = VoxbulkPricingService.list_topup_tiers(db)
        if not existing_tiers:
            for credit, bonus, order in default_tiers:
                db.add(
                    TopupTier(
                        id=str(uuid.uuid4()),
                        credit_gbp_pence=credit,
                        bonus_credit_pence=bonus,
                        is_active=True,
                        sort_order=order,
                        created_at=now,
                        updated_at=now,
                    )
                )
        db.commit()

    @staticmethod
    def ensure_seeded(db: Session) -> None:
        settings = VoxbulkPricingService.get_settings(db)
        voxbulk_plans = db.execute(select(Plan).where(Plan.service_kind == "voxbulk")).scalars().first()
        if voxbulk_plans is None:
            VoxbulkPricingService.seed_voxbulk_plans(db)
        elif not VoxbulkPricingService.list_topup_tiers(db):
            now = datetime.utcnow()
            for credit, bonus, order in [(1000, 0, 10), (5000, 500, 20), (10000, 1500, 30), (25000, 5000, 40)]:
                db.add(
                    TopupTier(
                        id=str(uuid.uuid4()),
                        credit_gbp_pence=credit,
                        bonus_credit_pence=bonus,
                        is_active=True,
                        sort_order=order,
                        created_at=now,
                        updated_at=now,
                    )
                )
            db.commit()
        VoxbulkPricingService.ensure_payg_plan(db)
