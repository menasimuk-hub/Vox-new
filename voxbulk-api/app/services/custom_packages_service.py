"""Custom multi-service packages — Admin CRUD (Phase 1). Entitlement/overage metering comes later."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.custom_package import CustomPackage, CustomPackageOrgAssignment
from app.models.organisation import Organisation
from app.services.billing_currency import CURRENCY_SYMBOLS, SUPPORTED_CURRENCIES, normalize_currency

INTERVALS = frozenset({"monthly", "yearly"})
STATUSES = frozenset({"draft", "active", "inactive"})
CORE_ALLOWLIST = ("GB", "AU", "CA", "USA")
MODULE_KEYS = ("customer_feedback", "core", "smart_card", "expo", "survey")


class CustomPackagesError(ValueError):
    pass


def _now() -> datetime:
    return datetime.utcnow()


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def default_modules() -> dict[str, Any]:
    return {
        "customer_feedback": {
            "enabled": False,
            "max_locations": 1,
            "wa_units_included": 100,
            "web_units_included": 100,
            "wa_extra_minor": 0,
            "web_extra_minor": 0,
            "notes": "",
            "ai_followback": {
                "minutes_included": 0,
                "connection_fee_minor": 0,
                "per_min_minor": 0,
            },
        },
        "core": {
            "enabled": False,
            "minutes_included": 0,
            "whatsapp_included": 0,
            "cv_scans_included": 0,
            "per_min_minor": 0,
            "overage_per_min_minor": 0,
            "unit_rates": {
                "connection_fee_minor": 0,
                "interview_per_min_minor": 0,
                "wa_package_fee_minor": 0,
                "wa_extra_minor": 0,
                "cv_scan_fee_minor": 0,
            },
        },
        "smart_card": {
            "enabled": False,
            "seats": 1,
            "per_seat_minor": 0,
        },
        "expo": {
            "enabled": False,
            "duration_days": 1,
            "max_booths": 1,
            "max_assets": 5,
            "max_categories": 1,
            "lead_scoring_enabled": False,
            "post_show_followup_enabled": False,
            "post_event_survey_enabled": False,
            "ai_summary_report_enabled": False,
        },
        "survey": {
            "enabled": False,
            "max_active_campaigns": 5,
            "whatsapp_recipients_included": 500,
            "call_minutes_included": 100,
            "wa_extra_minor": 0,
            "call_overage_per_min_minor": 0,
            "connection_fee_minor": 0,
        },
    }


def default_allowlist() -> dict[str, Any]:
    return {"mode": "default", "core": ["GB", "AU", "CA", "USA"], "extra": []}


def _merge_modules(raw: Any) -> dict[str, Any]:
    base = default_modules()
    if not isinstance(raw, dict):
        return base
    for key in MODULE_KEYS:
        incoming = raw.get(key)
        if not isinstance(incoming, dict):
            continue
        merged = {**base[key], **incoming}
        if key == "customer_feedback" and isinstance(incoming.get("ai_followback"), dict):
            merged["ai_followback"] = {**base[key]["ai_followback"], **incoming["ai_followback"]}
        if key == "core" and isinstance(incoming.get("unit_rates"), dict):
            merged["unit_rates"] = {**base[key]["unit_rates"], **incoming["unit_rates"]}
        merged["enabled"] = bool(incoming.get("enabled", merged.get("enabled")))
        base[key] = merged
    return base


def _merge_allowlist(raw: Any) -> dict[str, Any]:
    base = default_allowlist()
    if not isinstance(raw, dict):
        return base
    mode = str(raw.get("mode") or "default").strip().lower()
    base["mode"] = "custom" if mode == "custom" else "default"
    core = raw.get("core")
    if isinstance(core, list):
        cleaned = []
        for item in core:
            code = str(item or "").strip().upper()
            if code == "US":
                code = "USA"
            if code in CORE_ALLOWLIST and code not in cleaned:
                cleaned.append(code)
        base["core"] = cleaned
    extra = raw.get("extra")
    if isinstance(extra, list):
        cleaned_extra = []
        for item in extra:
            code = str(item or "").strip().upper()[:8]
            if code and code not in CORE_ALLOWLIST and code not in cleaned_extra:
                cleaned_extra.append(code)
        base["extra"] = cleaned_extra
    return base


def _slug_code(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().upper()).strip("-")
    slug = (slug or "PKG")[:24]
    return f"PKG-{slug}-{uuid.uuid4().hex[:4].upper()}"


class CustomPackagesService:
    @staticmethod
    def enabled_service_keys(modules: dict[str, Any]) -> list[str]:
        out = []
        for key in MODULE_KEYS:
            mod = modules.get(key) if isinstance(modules, dict) else None
            if isinstance(mod, dict) and mod.get("enabled"):
                out.append(key)
        return out

    @staticmethod
    def package_to_dict(db: Session, pkg: CustomPackage) -> dict[str, Any]:
        modules = _merge_modules(_loads(pkg.modules_json, {}))
        allowlist = _merge_allowlist(_loads(pkg.allowlist_json, {}))
        # Avoid JOIN on org_id — MySQL collation can differ until 0243 migration runs.
        assignments = list(
            db.execute(
                select(CustomPackageOrgAssignment).where(
                    CustomPackageOrgAssignment.custom_package_id == pkg.id,
                    CustomPackageOrgAssignment.is_active.is_(True),
                )
            ).scalars().all()
        )
        org_ids = [a.org_id for a in assignments]
        orgs_by_id: dict[str, Organisation] = {}
        if org_ids:
            for org in db.execute(select(Organisation).where(Organisation.id.in_(org_ids))).scalars().all():
                orgs_by_id[str(org.id)] = org
        orgs = []
        for assignment in assignments:
            org = orgs_by_id.get(str(assignment.org_id))
            if org is None:
                orgs.append(
                    {
                        "org_id": assignment.org_id,
                        "org_name": assignment.org_id,
                        "assignment_id": assignment.id,
                        "preferred_currency": "USD",
                        "currency_mismatch": False,
                    }
                )
                continue
            from app.services.billing_currency import resolve_org_currency

            try:
                preferred = resolve_org_currency(db, org)
            except Exception:
                preferred = getattr(org, "billing_currency", None) or "USD"
            orgs.append(
                {
                    "org_id": org.id,
                    "org_name": org.name,
                    "assignment_id": assignment.id,
                    "preferred_currency": str(preferred or "USD").upper(),
                    "currency_mismatch": str(preferred or "USD").upper() != str(pkg.currency or "USD").upper(),
                }
            )
        country_count = 0
        if allowlist.get("mode") == "custom":
            country_count = len(allowlist.get("core") or []) + len(allowlist.get("extra") or [])
        return {
            "id": pkg.id,
            "name": pkg.name,
            "code": pkg.code,
            "interval": pkg.interval,
            "currency": pkg.currency,
            "currency_symbol": CURRENCY_SYMBOLS.get(pkg.currency, pkg.currency),
            "price_minor": int(pkg.price_minor or 0),
            "status": pkg.status,
            "admin_notes": pkg.admin_notes,
            "modules": modules,
            "enabled_services": CustomPackagesService.enabled_service_keys(modules),
            "allowlist": allowlist,
            "allowlist_country_count": country_count if allowlist.get("mode") == "custom" else None,
            "internal_cost_notes": pkg.internal_cost_notes,
            "org_ids": [o["org_id"] for o in orgs],
            "orgs": orgs,
            "org_count": len(orgs),
            "created_at": pkg.created_at.isoformat() if pkg.created_at else None,
            "updated_at": pkg.updated_at.isoformat() if pkg.updated_at else None,
        }

    @staticmethod
    def list_packages(
        db: Session,
        *,
        status: str | None = None,
        active_only: bool = False,
        q: str | None = None,
        service: str | None = None,
        org_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = select(CustomPackage).order_by(CustomPackage.updated_at.desc())
        if status and status in STATUSES:
            query = query.where(CustomPackage.status == status)
        elif active_only:
            query = query.where(CustomPackage.status == "active")
        packages = list(db.execute(query).scalars().all())
        items = [CustomPackagesService.package_to_dict(db, p) for p in packages]
        needle = (q or "").strip().lower()
        if needle:
            filtered = []
            for item in items:
                hay = f"{item.get('name') or ''} {item.get('code') or ''}".lower()
                org_hay = " ".join(f"{o.get('org_name') or ''} {o.get('org_id') or ''}" for o in item.get("orgs") or []).lower()
                if needle in hay or needle in org_hay:
                    filtered.append(item)
            items = filtered
        if service and service in MODULE_KEYS:
            items = [i for i in items if service in (i.get("enabled_services") or [])]
        if org_id:
            items = [i for i in items if org_id in (i.get("org_ids") or [])]
        return items

    @staticmethod
    def get_package(db: Session, package_id: str) -> dict[str, Any]:
        pkg = db.get(CustomPackage, package_id)
        if pkg is None:
            raise CustomPackagesError("Custom package not found")
        return CustomPackagesService.package_to_dict(db, pkg)

    @staticmethod
    def _normalize_payload(payload: dict[str, Any], *, existing: CustomPackage | None = None) -> dict[str, Any]:
        name = str(payload.get("name") or (existing.name if existing else "")).strip()
        if not name:
            raise CustomPackagesError("Name is required")
        interval = str(payload.get("interval") or (existing.interval if existing else "monthly")).strip().lower()
        if interval not in INTERVALS:
            raise CustomPackagesError("Interval must be monthly or yearly")
        currency = normalize_currency(payload.get("currency") or (existing.currency if existing else "GBP"))
        if currency not in SUPPORTED_CURRENCIES:
            raise CustomPackagesError(f"Currency must be one of {', '.join(SUPPORTED_CURRENCIES)}")
        status = str(payload.get("status") or (existing.status if existing else "draft")).strip().lower()
        if status not in STATUSES:
            raise CustomPackagesError("Status must be draft, active, or inactive")
        price_raw = payload.get("price_minor")
        if price_raw is None and existing is not None:
            price_minor = int(existing.price_minor or 0)
        else:
            try:
                price_minor = max(0, int(price_raw or 0))
            except (TypeError, ValueError) as exc:
                raise CustomPackagesError("price_minor must be an integer") from exc
        code = str(payload.get("code") or (existing.code if existing else "")).strip().upper()
        if not code:
            code = _slug_code(name)
        modules = _merge_modules(payload.get("modules") if "modules" in payload else (None if existing is None else _loads(existing.modules_json, {})))
        allowlist = _merge_allowlist(
            payload.get("allowlist") if "allowlist" in payload else (None if existing is None else _loads(existing.allowlist_json, {}))
        )
        notes = payload.get("admin_notes")
        if notes is None and existing is not None:
            notes = existing.admin_notes
        else:
            notes = (str(notes).strip() or None) if notes is not None else None
        internal = payload.get("internal_cost_notes")
        if internal is None and existing is not None:
            internal = existing.internal_cost_notes
        else:
            internal = (str(internal).strip() or None) if internal is not None else None
        org_ids = payload.get("org_ids")
        if org_ids is None and existing is None:
            org_ids = []
        elif org_ids is None:
            org_ids = None  # leave unchanged on update
        elif not isinstance(org_ids, list):
            raise CustomPackagesError("org_ids must be a list")
        else:
            org_ids = [str(x).strip() for x in org_ids if str(x).strip()]
        return {
            "name": name,
            "code": code,
            "interval": interval,
            "currency": currency,
            "price_minor": price_minor,
            "status": status,
            "admin_notes": notes,
            "modules": modules,
            "allowlist": allowlist,
            "internal_cost_notes": internal,
            "org_ids": org_ids,
        }

    @staticmethod
    def _ensure_unique_code(db: Session, code: str, *, exclude_id: str | None = None) -> None:
        q = select(CustomPackage).where(CustomPackage.code == code)
        if exclude_id:
            q = q.where(CustomPackage.id != exclude_id)
        if db.execute(q).scalar_one_or_none() is not None:
            raise CustomPackagesError(f"Package code already exists: {code}")

    @staticmethod
    def set_orgs(db: Session, package_id: str, org_ids: list[str]) -> None:
        pkg = db.get(CustomPackage, package_id)
        if pkg is None:
            raise CustomPackagesError("Custom package not found")
        wanted = []
        seen = set()
        for oid in org_ids:
            if oid in seen:
                continue
            seen.add(oid)
            org = db.get(Organisation, oid)
            if org is None:
                raise CustomPackagesError(f"Organisation not found: {oid}")
            wanted.append(oid)

        existing = list(
            db.execute(select(CustomPackageOrgAssignment).where(CustomPackageOrgAssignment.custom_package_id == package_id)).scalars().all()
        )
        by_org = {row.org_id: row for row in existing}
        keep = set(wanted)
        for row in existing:
            if row.org_id not in keep:
                db.delete(row)

        for oid in wanted:
            conflict = db.execute(
                select(CustomPackageOrgAssignment).where(
                    CustomPackageOrgAssignment.org_id == oid,
                    CustomPackageOrgAssignment.custom_package_id != package_id,
                )
            ).scalar_one_or_none()
            if conflict is not None:
                # Move org to this package (one custom package per org)
                conflict.custom_package_id = package_id
                conflict.is_active = True
                conflict.updated_at = _now()
                continue
            row = by_org.get(oid)
            if row is None:
                db.add(
                    CustomPackageOrgAssignment(
                        id=str(uuid.uuid4()),
                        custom_package_id=package_id,
                        org_id=oid,
                        is_active=True,
                        created_at=_now(),
                        updated_at=_now(),
                    )
                )
            else:
                row.is_active = True
                row.updated_at = _now()

    @staticmethod
    def create_package(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        data = CustomPackagesService._normalize_payload(payload)
        CustomPackagesService._ensure_unique_code(db, data["code"])
        now = _now()
        pkg = CustomPackage(
            id=str(uuid.uuid4()),
            name=data["name"],
            code=data["code"],
            interval=data["interval"],
            currency=data["currency"],
            price_minor=data["price_minor"],
            status=data["status"],
            admin_notes=data["admin_notes"],
            modules_json=_dumps(data["modules"]),
            allowlist_json=_dumps(data["allowlist"]),
            internal_cost_notes=data["internal_cost_notes"],
            created_at=now,
            updated_at=now,
        )
        db.add(pkg)
        db.flush()
        CustomPackagesService.set_orgs(db, pkg.id, data["org_ids"] or [])
        CustomPackagesService.ensure_billing_plan(db, pkg)
        db.commit()
        db.refresh(pkg)
        return CustomPackagesService.package_to_dict(db, pkg)

    @staticmethod
    def update_package(db: Session, package_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        pkg = db.get(CustomPackage, package_id)
        if pkg is None:
            raise CustomPackagesError("Custom package not found")
        data = CustomPackagesService._normalize_payload(payload, existing=pkg)
        if data["code"] != pkg.code:
            CustomPackagesService._ensure_unique_code(db, data["code"], exclude_id=pkg.id)
            pkg.code = data["code"]
        pkg.name = data["name"]
        pkg.interval = data["interval"]
        pkg.currency = data["currency"]
        pkg.price_minor = data["price_minor"]
        pkg.status = data["status"]
        pkg.admin_notes = data["admin_notes"]
        pkg.modules_json = _dumps(data["modules"])
        pkg.allowlist_json = _dumps(data["allowlist"])
        pkg.internal_cost_notes = data["internal_cost_notes"]
        pkg.updated_at = _now()
        if data["org_ids"] is not None:
            CustomPackagesService.set_orgs(db, pkg.id, data["org_ids"])
        CustomPackagesService.ensure_billing_plan(db, pkg)
        db.commit()
        db.refresh(pkg)
        return CustomPackagesService.package_to_dict(db, pkg)

    @staticmethod
    def duplicate_package(db: Session, package_id: str) -> dict[str, Any]:
        src = CustomPackagesService.get_package(db, package_id)
        payload = {
            "name": f"{src['name']} (copy)",
            "code": "",
            "interval": src["interval"],
            "currency": src["currency"],
            "price_minor": src["price_minor"],
            "status": "draft",
            "admin_notes": src.get("admin_notes"),
            "modules": src.get("modules"),
            "allowlist": src.get("allowlist"),
            "internal_cost_notes": src.get("internal_cost_notes"),
            "org_ids": [],
        }
        return CustomPackagesService.create_package(db, payload)

    @staticmethod
    def deactivate_package(db: Session, package_id: str) -> dict[str, Any]:
        pkg = db.get(CustomPackage, package_id)
        if pkg is None:
            raise CustomPackagesError("Custom package not found")
        pkg.status = "inactive"
        pkg.updated_at = _now()
        for row in db.execute(
            select(CustomPackageOrgAssignment).where(CustomPackageOrgAssignment.custom_package_id == package_id)
        ).scalars().all():
            row.is_active = False
            row.updated_at = _now()
        db.commit()
        db.refresh(pkg)
        return CustomPackagesService.package_to_dict(db, pkg)

    @staticmethod
    def get_for_org(db: Session, org_id: str) -> dict[str, Any] | None:
        row = db.execute(
            select(CustomPackageOrgAssignment).where(
                CustomPackageOrgAssignment.org_id == org_id,
                CustomPackageOrgAssignment.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        pkg = db.get(CustomPackage, row.custom_package_id)
        if pkg is None or pkg.status != "active":
            return None
        return CustomPackagesService.package_to_dict(db, pkg)

    @staticmethod
    def get_row_for_org(db: Session, org_id: str) -> CustomPackage | None:
        row = db.execute(
            select(CustomPackageOrgAssignment).where(
                CustomPackageOrgAssignment.org_id == org_id,
                CustomPackageOrgAssignment.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        pkg = db.get(CustomPackage, row.custom_package_id)
        if pkg is None or pkg.status != "active":
            return None
        return pkg

    @staticmethod
    def billing_plan_code(package_code: str) -> str:
        return f"cpkg-{str(package_code or '').strip().lower()}"[:50]

    @staticmethod
    def ensure_billing_plan(
        db: Session,
        pkg: CustomPackage,
    ):
        """Create/update a private Plan + PlanPrice so GC/Stripe subscription checkout can reuse Core payment APIs.

        PlanPrice is written only for the package's single deal currency (no cross-currency seeding).
        """
        from app.models.plan import Plan
        from app.models.plan_price import PlanPrice
        from app.services.plan_price_service import PlanPriceService

        code = CustomPackagesService.billing_plan_code(pkg.code)
        plan = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
        now = _now()
        currency = normalize_currency(pkg.currency)
        amount = max(0, int(pkg.price_minor or 0))
        interval = "yearly" if str(pkg.interval or "").lower() == "yearly" else "monthly"
        active = str(pkg.status or "").lower() == "active"

        if plan is None:
            plan = Plan(
                id=str(uuid.uuid4()),
                code=code,
                name=str(pkg.name or "Private package")[:255],
                description=f"Private package ({pkg.code})",
                price_gbp_pence=amount if currency == "GBP" else None,
                interval=interval,
                features_json="[]",
                service_kind="voxbulk",
                is_private=True,
                is_active=active,
                is_enterprise=False,
                sort_order=9500,
                created_at=now,
                updated_at=now,
            )
            db.add(plan)
            db.flush()
        else:
            plan.name = str(pkg.name or plan.name)[:255]
            plan.interval = interval
            plan.is_private = True
            plan.is_active = active
            plan.service_kind = "voxbulk"
            if currency == "GBP":
                plan.price_gbp_pence = amount
            plan.updated_at = now

        row = PlanPriceService.get_price(db, plan.id, currency)
        if row is None:
            row = PlanPrice(
                id=str(uuid.uuid4()),
                plan_id=plan.id,
                currency=currency,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        if interval == "yearly":
            row.yearly_price_minor = amount
            if row.monthly_price_minor is None:
                row.monthly_price_minor = amount
        else:
            row.monthly_price_minor = amount
            if row.yearly_price_minor is None:
                row.yearly_price_minor = amount * 12
        row.is_active = True
        row.updated_at = now

        # Disable leftover cross-seeded prices in other currencies on this shadow plan.
        for other in db.execute(
            select(PlanPrice).where(PlanPrice.plan_id == plan.id, PlanPrice.currency != currency)
        ).scalars().all():
            if other.is_active:
                other.is_active = False
                other.updated_at = now

        db.flush()
        return plan

    @staticmethod
    def assert_checkout_allowed(db: Session, org: Organisation | None, plan) -> None:
        """Raise CustomPackagesError when locked org currency mismatches the private deal currency."""
        from app.models.plan import Plan
        from app.services.billing_currency import billing_currency_is_locked, resolve_org_currency
        from app.services.plan_price_service import PlanPriceService

        if plan is None or not isinstance(plan, Plan):
            return
        code = str(plan.code or "").strip().lower()
        if not code.startswith("cpkg-"):
            return
        if org is None:
            return
        deal = PlanPriceService._custom_package_plan_currency(db, plan)
        if not deal:
            return
        org_currency = resolve_org_currency(db, org, persist=False)
        if billing_currency_is_locked(db, org) and org_currency != deal:
            raise CustomPackagesError(
                f"This private package is priced in {deal}, but your organisation billing currency "
                f"is locked to {org_currency}. Ask your account manager to align the deal currency."
            )

    @staticmethod
    def _money_display(minor: int, currency: str) -> str:
        from app.services.billing_currency import CURRENCY_SYMBOLS

        sym = CURRENCY_SYMBOLS.get(currency, currency + " ")
        return f"{sym}{(int(minor or 0) / 100):,.2f}"

    @staticmethod
    def _usage_row(
        *,
        module: str,
        key: str,
        label: str,
        used: int,
        included: int,
        unit: str,
    ) -> dict[str, Any]:
        used_n = max(0, int(used or 0))
        included_n = max(0, int(included or 0))
        remaining = max(0, included_n - used_n) if included_n > 0 else None
        pct = round((used_n / included_n) * 100, 1) if included_n > 0 else 0.0
        return {
            "module": module,
            "key": key,
            "label": label,
            "used": used_n,
            "included": included_n,
            "remaining": remaining,
            "unit": unit,
            "pct_used": pct,
        }

    @staticmethod
    def org_dashboard_payload(db: Session, org_id: str) -> dict[str, Any] | None:
        """Customer-facing Private package page payload (assigned + active only)."""
        pkg_row = CustomPackagesService.get_row_for_org(db, org_id)
        if pkg_row is None:
            return None
        pkg = CustomPackagesService.package_to_dict(db, pkg_row)

        modules = pkg.get("modules") or {}
        currency = str(pkg.get("currency") or "USD")
        interval = str(pkg.get("interval") or "monthly")
        price_minor = int(pkg.get("price_minor") or 0)

        org = db.get(Organisation, org_id)
        from app.services.billing_currency import (
            billing_currency_is_locked,
            normalize_currency,
            resolve_org_currency,
        )

        deal_currency = normalize_currency(currency)
        currency_mismatch = False
        payment_block_reason = None
        if org is not None:
            if not billing_currency_is_locked(db, org):
                # New / unlocked profile: align billing currency to the deal.
                org.billing_currency = deal_currency
                db.add(org)
            else:
                org_currency = resolve_org_currency(db, org, persist=False)
                if org_currency != deal_currency:
                    currency_mismatch = True
                    payment_block_reason = (
                        f"This private package is priced in {deal_currency}, but your organisation "
                        f"billing currency is locked to {org_currency}. Ask your account manager to align the deal."
                    )

        billing_plan = CustomPackagesService.ensure_billing_plan(db, pkg_row)
        db.commit()

        # Live usage where meters already exist (Phase B will sync package caps into them).
        core_used = {"calls": 0, "whatsapp": 0, "cv": 0}
        feedback_used = {"wa": 0, "web": 0}
        try:
            from app.services.usage_wallet_service import UsageWalletService

            period = UsageWalletService.get_current(db, org_id)
            if period is not None:
                core_used["calls"] = int(getattr(period, "calls_used", 0) or 0)
                core_used["whatsapp"] = int(getattr(period, "whatsapp_used", 0) or 0)
                core_used["cv"] = int(getattr(period, "cv_scans_used", 0) or 0)
        except Exception:
            pass
        try:
            from app.services.customer_feedback.billing_service import FeedbackBillingService

            fb = FeedbackBillingService.get_current_usage(db, org_id)
            if isinstance(fb, dict):
                feedback_used["wa"] = int(fb.get("wa_units_used") or 0)
                feedback_used["web"] = int(fb.get("web_units_used") or 0)
            elif fb is not None:
                feedback_used["wa"] = int(getattr(fb, "wa_units_used", 0) or 0)
                feedback_used["web"] = int(getattr(fb, "web_units_used", 0) or 0)
        except Exception:
            pass

        usage_rows: list[dict[str, Any]] = []
        cf = modules.get("customer_feedback") or {}
        if cf.get("enabled"):
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="customer_feedback",
                    key="locations",
                    label="Feedback locations",
                    used=0,
                    included=int(cf.get("max_locations") or 0),
                    unit="venues",
                )
            )
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="customer_feedback",
                    key="wa_units",
                    label="Feedback WhatsApp units",
                    used=feedback_used["wa"],
                    included=int(cf.get("wa_units_included") or 0),
                    unit="units",
                )
            )
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="customer_feedback",
                    key="web_units",
                    label="Feedback web / scan units",
                    used=feedback_used["web"],
                    included=int(cf.get("web_units_included") or 0),
                    unit="units",
                )
            )
            ai = cf.get("ai_followback") or {}
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="customer_feedback",
                    key="ai_followback_mins",
                    label="AI follow-back minutes",
                    used=0,
                    included=int(ai.get("minutes_included") or 0),
                    unit="min",
                )
            )

        core = modules.get("core") or {}
        if core.get("enabled"):
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="core",
                    key="minutes",
                    label="Core / interview minutes",
                    used=core_used["calls"],
                    included=int(core.get("minutes_included") or 0),
                    unit="min",
                )
            )
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="core",
                    key="whatsapp",
                    label="Core WhatsApp",
                    used=core_used["whatsapp"],
                    included=int(core.get("whatsapp_included") or 0),
                    unit="msgs",
                )
            )
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="core",
                    key="cv_scans",
                    label="CV scans",
                    used=core_used["cv"],
                    included=int(core.get("cv_scans_included") or 0),
                    unit="scans",
                )
            )

        survey = modules.get("survey") or {}
        if survey.get("enabled"):
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="survey",
                    key="campaigns",
                    label="Active survey campaigns",
                    used=0,
                    included=int(survey.get("max_active_campaigns") or 0),
                    unit="campaigns",
                )
            )
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="survey",
                    key="recipients",
                    label="Survey WhatsApp recipients",
                    used=core_used["whatsapp"],
                    included=int(survey.get("whatsapp_recipients_included") or 0),
                    unit="recipients",
                )
            )
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="survey",
                    key="call_minutes",
                    label="Survey call minutes",
                    used=core_used["calls"],
                    included=int(survey.get("call_minutes_included") or 0),
                    unit="min",
                )
            )

        sc = modules.get("smart_card") or {}
        if sc.get("enabled"):
            seats_used = 0
            try:
                from app.models.smart_card import SmartCardCompany, SmartCardRepresentative
                from sqlalchemy import func

                company = db.execute(
                    select(SmartCardCompany).where(SmartCardCompany.org_id == org_id).limit(1)
                ).scalar_one_or_none()
                if company is not None:
                    seats_used = int(
                        db.scalar(
                            select(func.count())
                            .select_from(SmartCardRepresentative)
                            .where(SmartCardRepresentative.company_id == company.id)
                        )
                        or 0
                    )
            except Exception:
                seats_used = 0
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="smart_card",
                    key="seats",
                    label="Smart Card seats",
                    used=seats_used,
                    included=int(sc.get("seats") or 0),
                    unit="seats",
                )
            )

        expo = modules.get("expo") or {}
        if expo.get("enabled"):
            usage_rows.append(
                CustomPackagesService._usage_row(
                    module="expo",
                    key="booths",
                    label="Expo booths",
                    used=0,
                    included=int(expo.get("max_booths") or 0),
                    unit="booths",
                )
            )

        # Payment: subscribed to this private package plan (not any other Core plan).
        mandate_active = False
        payment_method_label = None
        try:
            from app.models.subscription import Subscription

            sub = db.execute(
                select(Subscription).where(Subscription.org_id == org_id).limit(1)
            ).scalar_one_or_none()
            if sub is not None and str(sub.plan_id or "") == str(billing_plan.id):
                status = str(sub.status or "").lower()
                mandate_active = status in {
                    "active",
                    "trial",
                    "trialing",
                    "pending_first_payment",
                    "past_due",
                }
                provider = str(getattr(sub, "payment_provider", None) or "").lower()
                if "gocardless" in provider or provider == "gc":
                    payment_method_label = "GoCardless Direct Debit"
                elif provider in {"stripe", "airwallex"}:
                    payment_method_label = "Card on file"
                else:
                    payment_method_label = "Payment method on file"
        except Exception:
            pass

        payment_options: dict[str, Any] = {}
        try:
            from app.services.payment_provider_router import PaymentProviderRouter

            payment_options = PaymentProviderRouter.subscription_options(db, org)
        except Exception:
            payment_options = {
                "gocardless_available": False,
                "stripe_available": False,
                "airwallex_available": False,
                "primary_provider": "gocardless",
            }

        from datetime import timedelta

        next_billing_date = None
        try:
            raw = pkg.get("updated_at") or pkg.get("created_at")
            if isinstance(raw, str) and raw:
                base = datetime.fromisoformat(raw.replace("Z", ""))
            else:
                base = _now()
            delta = timedelta(days=365) if interval == "yearly" else timedelta(days=30)
            next_billing_date = (base + delta).date().isoformat()
        except Exception:
            next_billing_date = (_now() + timedelta(days=30)).date().isoformat()

        payment_status = "mandate_ready" if mandate_active else "setup_required"
        billing_interval = "yearly" if interval == "yearly" else "monthly"
        can_checkout = bool(
            payment_options.get("gocardless_available") or payment_options.get("stripe_available")
        )
        can_setup_payment = (
            payment_status == "setup_required"
            and can_checkout
            and price_minor > 0
            and not currency_mismatch
        )

        return {
            "assigned": True,
            "package": {
                "id": pkg["id"],
                "name": pkg["name"],
                "code": pkg["code"],
                "interval": interval,
                "currency": currency,
                "currency_symbol": pkg.get("currency_symbol"),
                "price_minor": price_minor,
                "price_display": CustomPackagesService._money_display(price_minor, currency),
                "status": pkg["status"],
                "enabled_services": pkg.get("enabled_services") or [],
                "modules": modules,
                "allowlist": pkg.get("allowlist"),
                "allowlist_country_count": pkg.get("allowlist_country_count"),
            },
            "billing": {
                "interval": interval,
                "billing_interval": billing_interval,
                "currency": currency,
                "amount_next_payment_minor": price_minor,
                "amount_next_payment_display": CustomPackagesService._money_display(price_minor, currency),
                "next_billing_date": next_billing_date,
                "payment_status": payment_status,
                "payment_method_label": payment_method_label,
                "can_setup_payment": can_setup_payment,
                "currency_mismatch": currency_mismatch,
                "payment_block_reason": payment_block_reason,
                "billing_plan_id": billing_plan.id,
                "payment_options": payment_options,
                "setup_path": "/account/private-package",
            },
            "usage": {
                "rows": usage_rows,
                "period_note": "Included amounts are from your private package. Usage meters sync as you use each service.",
            },
            "extras": {
                "estimated_minor": 0,
                "estimated_display": CustomPackagesService._money_display(0, currency),
                "note": "Extra usage after allowance will appear on your next monthly invoice.",
            },
        }
