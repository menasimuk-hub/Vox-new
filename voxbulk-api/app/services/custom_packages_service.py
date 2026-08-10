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
        rows = list(
            db.execute(
                select(CustomPackageOrgAssignment, Organisation)
                .join(Organisation, Organisation.id == CustomPackageOrgAssignment.org_id)
                .where(
                    CustomPackageOrgAssignment.custom_package_id == pkg.id,
                    CustomPackageOrgAssignment.is_active.is_(True),
                )
            ).all()
        )
        orgs = []
        for assignment, org in rows:
            from app.services.billing_currency import resolve_org_currency

            try:
                preferred = resolve_org_currency(db, org)
            except Exception:
                preferred = getattr(org, "billing_currency", None) or "GBP"
            orgs.append(
                {
                    "org_id": org.id,
                    "org_name": org.name,
                    "assignment_id": assignment.id,
                    "preferred_currency": str(preferred or "GBP").upper(),
                    "currency_mismatch": str(preferred or "GBP").upper() != str(pkg.currency or "GBP").upper(),
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
