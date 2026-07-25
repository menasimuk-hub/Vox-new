"""Private packages: create org-only plans, multi-org assign, resolve rates with defaults."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FEEDBACK_SERVICE_CODE, FeedbackPackage
from app.models.expo import EXPO_SERVICE_CODE, ExpoPackage
from app.models.org_package_assignment import OrgPackageAssignment, PlanUnitRate
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.plan_price import PlanPrice
from app.services.billing_currency import SUPPORTED_CURRENCIES, normalize_currency
from app.services.plan_admin_service import PlanAdminError, PlanAdminService
from app.services.plan_price_service import PlanPriceService

PRIVATE_SERVICE_KINDS = ("voxbulk", "customer_feedback", "expo")
CORE_CF_INTERVALS = frozenset({"monthly", "yearly"})
EXPO_INTERVALS = frozenset({"one_time", "yearly"})


class PrivatePackagesError(ValueError):
    pass


class PrivatePackagesService:
    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _normalize_interval(service_kind: str, raw: Any) -> str:
        value = str(raw or "").strip().lower()
        if service_kind == EXPO_SERVICE_CODE:
            if value in EXPO_INTERVALS:
                return value
            return "one_time"
        if value in CORE_CF_INTERVALS:
            return value
        return "monthly"

    @staticmethod
    def get_assignment(db: Session, org_id: str, service_kind: str) -> OrgPackageAssignment | None:
        return db.execute(
            select(OrgPackageAssignment).where(
                OrgPackageAssignment.org_id == org_id,
                OrgPackageAssignment.service_kind == service_kind,
                OrgPackageAssignment.is_active.is_(True),
            )
        ).scalar_one_or_none()

    @staticmethod
    def get_private_plan_for_org(db: Session, org_id: str, service_kind: str) -> Plan | None:
        row = PrivatePackagesService.get_assignment(db, org_id, service_kind)
        if row is None:
            return None
        plan = db.get(Plan, row.plan_id)
        if plan is None or not plan.is_active or not getattr(plan, "is_private", False):
            return None
        return plan

    @staticmethod
    def list_private_packages(db: Session, *, service_kind: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
        q = select(Plan).where(Plan.is_private.is_(True)).order_by(Plan.sort_order.asc(), Plan.name.asc())
        if service_kind:
            q = q.where(Plan.service_kind == service_kind)
        if active_only:
            q = q.where(Plan.is_active.is_(True))
        plans = list(db.execute(q).scalars().all())
        return [PrivatePackagesService.package_to_dict(db, p) for p in plans]

    @staticmethod
    def package_to_dict(db: Session, plan: Plan) -> dict[str, Any]:
        base = PlanAdminService.plan_to_dict(plan)
        base["is_private"] = True
        prices = {row.currency: PlanPriceService.price_to_dict(row) for row in PlanPriceService.list_for_plan(db, plan.id)}
        unit_rates = {
            row.currency: {
                "currency": row.currency,
                "connection_fee_minor": row.connection_fee_minor,
                "interview_per_min_minor": row.interview_per_min_minor,
                "wa_package_fee_minor": row.wa_package_fee_minor,
                "wa_extra_minor": row.wa_extra_minor,
                "cv_scan_fee_minor": row.cv_scan_fee_minor,
            }
            for row in db.execute(select(PlanUnitRate).where(PlanUnitRate.plan_id == plan.id)).scalars().all()
        }
        for c in SUPPORTED_CURRENCIES:
            prices.setdefault(c, {"currency": c, "monthly_price_minor": None, "yearly_price_minor": None, "per_min_minor": 0, "extra_per_min_minor": 0})
            unit_rates.setdefault(
                c,
                {
                    "currency": c,
                    "connection_fee_minor": None,
                    "interview_per_min_minor": None,
                    "wa_package_fee_minor": None,
                    "wa_extra_minor": None,
                    "cv_scan_fee_minor": None,
                },
            )
        assignments = list(
            db.execute(
                select(OrgPackageAssignment, Organisation)
                .join(Organisation, Organisation.id == OrgPackageAssignment.org_id)
                .where(OrgPackageAssignment.plan_id == plan.id, OrgPackageAssignment.is_active.is_(True))
            ).all()
        )
        orgs = [{"org_id": a.org_id, "org_name": o.name, "assignment_id": a.id} for a, o in assignments]
        meta: dict[str, Any] = {}
        if plan.service_kind == FEEDBACK_SERVICE_CODE:
            pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
            if pkg:
                meta = {
                    "max_locations": pkg.max_locations,
                    "wa_units_included": pkg.wa_units_included,
                    "web_units_included": pkg.web_units_included,
                    "promo_message_cost_minor": pkg.promo_message_cost_minor,
                    "package_id": pkg.id,
                }
        if plan.service_kind == EXPO_SERVICE_CODE:
            pkg = db.execute(select(ExpoPackage).where(ExpoPackage.plan_id == plan.id)).scalar_one_or_none()
            if pkg:
                meta = {
                    "duration_days": pkg.duration_days,
                    "tier": pkg.tier,
                    "max_booths": pkg.max_booths,
                    "max_assets": pkg.max_assets,
                    "package_id": pkg.id,
                }
        return {**base, "prices": prices, "unit_rates": unit_rates, "orgs": orgs, "org_ids": [x["org_id"] for x in orgs], **meta}

    @staticmethod
    def defaults_payload(db: Session) -> dict[str, Any]:
        """Default list prices + unit rates to prefill the create form."""
        prices: dict[str, Any] = {}
        unit_rates: dict[str, Any] = {}
        for currency in SUPPORTED_CURRENCIES:
            unit = PlanPriceService.get_currency_settings(db, currency)
            unit_rates[currency] = {
                "connection_fee_minor": int(unit.connection_fee_minor or 0),
                "interview_per_min_minor": int(unit.interview_per_min_minor or 0),
                "wa_package_fee_minor": int(unit.wa_package_fee_minor or 0),
                "wa_extra_minor": int(unit.wa_extra_minor or 0),
                "cv_scan_fee_minor": int(unit.cv_scan_fee_minor or 0),
            }
            prices[currency] = {
                "monthly_price_minor": None,
                "yearly_price_minor": None,
                "per_min_minor": int(unit.interview_per_min_minor or 0),
                "extra_per_min_minor": int(unit.interview_per_min_minor or 0),
            }
        return {"supported_currencies": list(SUPPORTED_CURRENCIES), "prices": prices, "unit_rates": unit_rates}

    @staticmethod
    def create_package(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        kind = str(payload.get("service_kind") or "voxbulk").strip()
        if kind not in PRIVATE_SERVICE_KINDS:
            raise PrivatePackagesError(f"Unsupported service_kind: {kind}")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise PrivatePackagesError("Package name is required")
        try:
            code = PlanAdminService.normalize_code(str(payload.get("code") or f"private_{kind}_{name}"))
        except PlanAdminError as exc:
            raise PrivatePackagesError(str(exc)) from exc
        if not code.startswith("private_"):
            code = f"private_{code}"
        if db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none():
            code = f"{code}_{uuid.uuid4().hex[:6]}"

        now = PrivatePackagesService._now()
        defaults = PrivatePackagesService.defaults_payload(db)
        interval = PrivatePackagesService._normalize_interval(kind, payload.get("interval"))
        plan = Plan(
            id=str(uuid.uuid4()),
            code=code[:50],
            name=name,
            price_gbp_pence=int(payload.get("price_gbp_pence") or 0),
            interval=interval,
            description=str(payload.get("description") or "").strip() or f"Private {kind} package",
            features_json=json.dumps(payload["features"]) if isinstance(payload.get("features"), list) else None,
            calls_included=int(payload.get("calls_included") or payload.get("minutes_included") or 0),
            whatsapp_included=int(payload.get("whatsapp_included") or payload.get("wa_units_included") or 0),
            cv_scans_included=int(payload.get("cv_scans_included") or 0),
            per_min_pence=int(payload.get("per_min_pence") or 0),
            overage_per_min_pence=int(payload.get("extra_per_min_pence") or payload.get("overage_per_min_pence") or 0),
            service_kind=kind,
            is_private=True,
            is_enterprise=True,
            is_active=bool(payload.get("is_active", True)),
            is_featured=False,
            sort_order=int(payload.get("sort_order") or 900),
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        db.flush()

        if kind == FEEDBACK_SERVICE_CODE:
            db.add(
                FeedbackPackage(
                    id=str(uuid.uuid4()),
                    plan_id=plan.id,
                    market_zone="gb",
                    max_locations=int(payload.get("max_locations") or 1),
                    wa_units_included=int(payload.get("wa_units_included") or payload.get("whatsapp_included") or 100),
                    web_units_included=int(payload.get("web_units_included") or 100),
                    promo_message_cost_minor=int(payload.get("promo_message_cost_minor") or 5),
                    display_order=int(payload.get("sort_order") or 900),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
        if kind == EXPO_SERVICE_CODE:
            days = max(1, int(payload.get("duration_days") or 1))
            db.add(
                ExpoPackage(
                    id=str(uuid.uuid4()),
                    plan_id=plan.id,
                    market_zone="all",
                    tier=str(payload.get("tier") or f"day{days}")[:32],
                    duration_days=days,
                    max_booths=int(payload.get("max_booths") or 1),
                    max_assets=int(payload.get("max_assets") or 5),
                    lead_scoring_enabled=bool(payload.get("lead_scoring_enabled", True)),
                    display_order=int(payload.get("sort_order") or 900),
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )

        PrivatePackagesService._upsert_prices(db, plan.id, payload.get("prices") or defaults["prices"], defaults["prices"])
        PrivatePackagesService._upsert_unit_rates(db, plan.id, payload.get("unit_rates") or defaults["unit_rates"], defaults["unit_rates"])
        org_ids = payload.get("org_ids") or []
        if isinstance(org_ids, list) and org_ids:
            PrivatePackagesService.set_orgs(db, plan.id, org_ids, apply_subscription=True)
        else:
            db.commit()
        return PrivatePackagesService.package_to_dict(db, plan)

    @staticmethod
    def update_package(db: Session, plan_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        plan = db.get(Plan, plan_id)
        if plan is None or not getattr(plan, "is_private", False):
            raise PrivatePackagesError("Private package not found")
        now = PrivatePackagesService._now()
        if payload.get("name") is not None:
            plan.name = str(payload["name"]).strip() or plan.name
        if "is_active" in payload:
            plan.is_active = bool(payload["is_active"])
        if "description" in payload:
            plan.description = str(payload.get("description") or "") or None
        if isinstance(payload.get("features"), list):
            plan.features_json = json.dumps([str(x) for x in payload["features"]])
        if "interval" in payload and payload.get("interval") is not None:
            plan.interval = PrivatePackagesService._normalize_interval(
                str(plan.service_kind or "voxbulk"),
                payload.get("interval"),
            )
        for field, key in (
            ("calls_included", "calls_included"),
            ("calls_included", "minutes_included"),
            ("whatsapp_included", "whatsapp_included"),
            ("cv_scans_included", "cv_scans_included"),
            ("sort_order", "sort_order"),
        ):
            if key in payload and payload[key] is not None:
                setattr(plan, field, int(payload[key] or 0))
        plan.updated_at = now
        db.add(plan)

        if plan.service_kind == FEEDBACK_SERVICE_CODE:
            pkg = db.execute(select(FeedbackPackage).where(FeedbackPackage.plan_id == plan.id)).scalar_one_or_none()
            if pkg:
                if "max_locations" in payload:
                    pkg.max_locations = int(payload["max_locations"] or 1)
                if "wa_units_included" in payload:
                    pkg.wa_units_included = int(payload["wa_units_included"] or 0)
                    plan.whatsapp_included = pkg.wa_units_included
                if "web_units_included" in payload:
                    pkg.web_units_included = int(payload["web_units_included"] or 0)
                if "is_active" in payload:
                    pkg.is_active = bool(payload["is_active"])
                pkg.updated_at = now
                db.add(pkg)

        if plan.service_kind == EXPO_SERVICE_CODE:
            pkg = db.execute(select(ExpoPackage).where(ExpoPackage.plan_id == plan.id)).scalar_one_or_none()
            if pkg:
                if "duration_days" in payload:
                    pkg.duration_days = max(1, int(payload["duration_days"] or 1))
                if "max_booths" in payload:
                    pkg.max_booths = int(payload["max_booths"] or 1)
                if "max_assets" in payload:
                    pkg.max_assets = int(payload["max_assets"] or 5)
                if "is_active" in payload:
                    pkg.is_active = bool(payload["is_active"])
                pkg.updated_at = now
                db.add(pkg)

        defaults = PrivatePackagesService.defaults_payload(db)
        if payload.get("prices") is not None:
            PrivatePackagesService._upsert_prices(db, plan.id, payload["prices"], defaults["prices"])
        if payload.get("unit_rates") is not None:
            PrivatePackagesService._upsert_unit_rates(db, plan.id, payload["unit_rates"], defaults["unit_rates"])
        if "org_ids" in payload and isinstance(payload.get("org_ids"), list):
            PrivatePackagesService.set_orgs(db, plan.id, payload["org_ids"], apply_subscription=True)
        else:
            db.commit()
        db.refresh(plan)
        return PrivatePackagesService.package_to_dict(db, plan)

    @staticmethod
    def _upsert_prices(db: Session, plan_id: str, prices: dict[str, Any], defaults: dict[str, Any]) -> None:
        now = PrivatePackagesService._now()
        for currency in SUPPORTED_CURRENCIES:
            row_in = prices.get(currency) if isinstance(prices, dict) else None
            if not isinstance(row_in, dict):
                row_in = {}
            def_row = defaults.get(currency) or {}
            monthly = row_in.get("monthly_price_minor", def_row.get("monthly_price_minor"))
            yearly = row_in.get("yearly_price_minor", def_row.get("yearly_price_minor"))
            per_min = row_in.get("per_min_minor", def_row.get("per_min_minor"))
            extra = row_in.get("extra_per_min_minor", def_row.get("extra_per_min_minor"))
            existing = PlanPriceService.get_price(db, plan_id, currency)
            if existing is None:
                existing = PlanPrice(id=str(uuid.uuid4()), plan_id=plan_id, currency=currency, created_at=now, updated_at=now)
            existing.monthly_price_minor = None if monthly is None or monthly == "" else max(0, int(monthly))
            existing.yearly_price_minor = None if yearly is None or yearly == "" else max(0, int(yearly))
            existing.per_min_minor = max(0, int(per_min or 0))
            existing.extra_per_min_minor = max(0, int(extra or 0))
            existing.updated_at = now
            db.add(existing)
        db.flush()

    @staticmethod
    def _upsert_unit_rates(db: Session, plan_id: str, unit_rates: dict[str, Any], defaults: dict[str, Any]) -> None:
        now = PrivatePackagesService._now()
        for currency in SUPPORTED_CURRENCIES:
            row_in = unit_rates.get(currency) if isinstance(unit_rates, dict) else None
            if not isinstance(row_in, dict):
                row_in = {}
            def_row = defaults.get(currency) or {}
            existing = db.execute(
                select(PlanUnitRate).where(PlanUnitRate.plan_id == plan_id, PlanUnitRate.currency == currency)
            ).scalar_one_or_none()
            if existing is None:
                existing = PlanUnitRate(id=str(uuid.uuid4()), plan_id=plan_id, currency=currency, created_at=now, updated_at=now)

            def pick(key: str) -> int | None:
                if key in row_in and row_in[key] is not None and row_in[key] != "":
                    return max(0, int(row_in[key]))
                if key in def_row and def_row[key] is not None:
                    return max(0, int(def_row[key]))
                return None

            existing.connection_fee_minor = pick("connection_fee_minor")
            existing.interview_per_min_minor = pick("interview_per_min_minor")
            existing.wa_package_fee_minor = pick("wa_package_fee_minor")
            existing.wa_extra_minor = pick("wa_extra_minor")
            existing.cv_scan_fee_minor = pick("cv_scan_fee_minor")
            existing.updated_at = now
            db.add(existing)
        db.flush()

    @staticmethod
    def set_orgs(db: Session, plan_id: str, org_ids: list[Any], *, apply_subscription: bool = True) -> dict[str, Any]:
        plan = db.get(Plan, plan_id)
        if plan is None or not getattr(plan, "is_private", False):
            raise PrivatePackagesError("Private package not found")
        kind = str(plan.service_kind or "voxbulk")
        wanted = {str(x).strip() for x in org_ids if str(x).strip()}
        now = PrivatePackagesService._now()

        existing = list(db.execute(select(OrgPackageAssignment).where(OrgPackageAssignment.plan_id == plan_id)).scalars().all())
        existing_by_org = {a.org_id: a for a in existing}

        # Deactivate removals
        for a in existing:
            if a.org_id not in wanted:
                a.is_active = False
                a.updated_at = now
                db.add(a)

        for org_id in wanted:
            org = db.get(Organisation, org_id)
            if org is None:
                raise PrivatePackagesError(f"Organisation not found: {org_id}")
            # One active assignment per org+service — clear other private plans for this service
            others = list(
                db.execute(
                    select(OrgPackageAssignment).where(
                        OrgPackageAssignment.org_id == org_id,
                        OrgPackageAssignment.service_kind == kind,
                        OrgPackageAssignment.plan_id != plan_id,
                    )
                ).scalars().all()
            )
            for o in others:
                o.is_active = False
                o.updated_at = now
                db.add(o)

            row = existing_by_org.get(org_id)
            if row is None:
                # Also check if org already has inactive row we can revive? create new
                row = OrgPackageAssignment(
                    id=str(uuid.uuid4()),
                    org_id=org_id,
                    plan_id=plan_id,
                    service_kind=kind,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.is_active = True
                row.plan_id = plan_id
                row.service_kind = kind
                row.updated_at = now
                db.add(row)

            if apply_subscription:
                PrivatePackagesService._apply_subscription(db, org_id=org_id, plan=plan)

        db.commit()
        return PrivatePackagesService.package_to_dict(db, plan)

    @staticmethod
    def _apply_subscription(db: Session, *, org_id: str, plan: Plan) -> None:
        kind = str(plan.service_kind or "voxbulk")
        try:
            if kind == "voxbulk":
                from app.services.gocardless_service import BillingService

                BillingService.change_plan(db, org_id=org_id, plan_id=plan.id)
            elif kind == FEEDBACK_SERVICE_CODE:
                from app.services.customer_feedback.billing_service import FeedbackBillingService

                FeedbackBillingService.admin_assign_plan(db, org_id=org_id, plan_id=plan.id, status="active")
        except Exception:
            # Assignment row still saved; subscription apply best-effort
            pass

    @staticmethod
    def deactivate_package(db: Session, plan_id: str) -> dict[str, Any]:
        return PrivatePackagesService.update_package(db, plan_id, {"is_active": False, "org_ids": []})

    @staticmethod
    def assignments_for_org(db: Session, org_id: str) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(OrgPackageAssignment, Plan)
                .join(Plan, Plan.id == OrgPackageAssignment.plan_id)
                .where(OrgPackageAssignment.org_id == org_id, OrgPackageAssignment.is_active.is_(True))
            ).all()
        )
        out = []
        for a, plan in rows:
            out.append(
                {
                    "assignment_id": a.id,
                    "service_kind": a.service_kind,
                    "plan_id": plan.id,
                    "plan_code": plan.code,
                    "plan_name": plan.name,
                    "is_private": bool(getattr(plan, "is_private", False)),
                }
            )
        return out
