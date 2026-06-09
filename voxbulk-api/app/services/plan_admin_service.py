from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.plan import Plan
from app.models.platform_service import PlatformService
from app.models.subscription import Subscription
from app.services.gocardless_service import BillingService
from app.services.platform_catalog_service import PlatformCatalogService

_CODE_RE = re.compile(r"[^a-z0-9_]+")


class PlanAdminError(ValueError):
    pass


class PlanAdminService:
    @staticmethod
    def normalize_code(raw: str) -> str:
        code = _CODE_RE.sub("_", str(raw or "").strip().lower()).strip("_")
        if len(code) < 2:
            raise PlanAdminError("Plan code must be at least 2 characters")
        return code[:50]

    @staticmethod
    def parse_features(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            val = json.loads(raw)
            return [str(x) for x in val] if isinstance(val, list) else []
        except Exception:
            return []

    @staticmethod
    def plan_to_dict(row: Plan) -> dict[str, Any]:
        return {
            "product_type": "subscription",
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "price_gbp_pence": int(row.price_gbp_pence) if row.price_gbp_pence is not None else None,
            "interval": row.interval,
            "description": row.description,
            "features": PlanAdminService.parse_features(row.features_json),
            "features_json": row.features_json,
            "calls_included": int(row.calls_included or 0),
            "minutes_included": int(row.calls_included or 0),
            "whatsapp_included": int(row.whatsapp_included or 0),
            "sms_included": int(row.sms_included or 0),
            "cv_scans_included": int(getattr(row, "cv_scans_included", 0) or 0),
            "per_min_pence": int(getattr(row, "per_min_pence", 0) or 0),
            "extra_per_min_pence": int(row.overage_per_min_pence or 0),
            "overage_per_min_pence": int(row.overage_per_min_pence or 0),
            "trial_days_default": int(row.trial_days_default or 0),
            "service_kind": row.service_kind,
            "is_featured": bool(getattr(row, "is_featured", False)),
            "is_enterprise": bool(getattr(row, "is_enterprise", False)),
            "is_active": bool(row.is_active),
            "sort_order": int(row.sort_order or 100),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def campaign_to_dict(svc: PlatformService, *, rules_count: int = 0) -> dict[str, Any]:
        return {
            "product_type": "campaign",
            "id": svc.id,
            "code": svc.code,
            "name": svc.name,
            "description": svc.description,
            "service_kind": svc.service_kind,
            "is_active": bool(svc.is_active),
            "sort_order": int(svc.sort_order or 100),
            "pricing_rules_count": rules_count,
            "created_at": svc.created_at.isoformat() if svc.created_at else None,
            "updated_at": svc.updated_at.isoformat() if svc.updated_at else None,
        }

    @staticmethod
    def list_plans(db: Session, *, active_only: bool = False) -> list[Plan]:
        BillingService.ensure_default_plans(db)
        q = select(Plan).order_by(Plan.sort_order.asc(), Plan.price_gbp_pence.asc())
        if active_only:
            q = q.where(Plan.is_active.is_(True))
        return list(db.execute(q).scalars().all())

    @staticmethod
    def list_unified_products(db: Session) -> list[dict[str, Any]]:
        plans = PlanAdminService.list_plans(db)
        PlatformCatalogService.ensure_defaults(db)
        services = db.execute(select(PlatformService).order_by(PlatformService.sort_order.asc())).scalars().all()
        out: list[dict[str, Any]] = [PlanAdminService.plan_to_dict(p) for p in plans]
        for svc in services:
            out.append(PlanAdminService.campaign_to_dict(svc))
        out.sort(key=lambda x: (0 if x["product_type"] == "subscription" else 1, int(x.get("sort_order") or 100), x.get("name") or ""))
        return out

    @staticmethod
    def get_plan(db: Session, plan_id: str) -> Plan | None:
        return db.execute(select(Plan).where(Plan.id == plan_id)).scalar_one_or_none()

    @staticmethod
    def create_plan(db: Session, payload: dict[str, Any]) -> Plan:
        BillingService.ensure_default_plans(db)
        code = PlanAdminService.normalize_code(str(payload.get("code") or ""))
        existing = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
        if existing is not None:
            raise PlanAdminError(f"Plan code already exists: {code}")
        name = str(payload.get("name") or "").strip()
        if not name:
            raise PlanAdminError("Plan name is required")
        now = datetime.utcnow()
        features = payload.get("features")
        features_json = None
        if isinstance(features, list):
            features_json = json.dumps([str(x) for x in features])
        price_raw = payload.get("price_gbp_pence")
        price_val = None if price_raw is None or payload.get("is_enterprise") else int(price_raw or 0)
        row = Plan(
            id=str(uuid.uuid4()),
            code=code,
            name=name,
            price_gbp_pence=price_val,
            interval=str(payload.get("interval") or "monthly").strip(),
            description=str(payload.get("description") or "").strip() or None,
            features_json=features_json,
            calls_included=int(payload.get("calls_included") or payload.get("minutes_included") or 0),
            whatsapp_included=int(payload.get("whatsapp_included") or 0),
            sms_included=int(payload.get("sms_included") or 0),
            cv_scans_included=int(payload.get("cv_scans_included") or 0),
            per_min_pence=int(payload.get("per_min_pence") or 0),
            overage_per_min_pence=int(payload.get("extra_per_min_pence") or payload.get("overage_per_min_pence") or 0),
            trial_days_default=int(payload.get("trial_days_default") or 0),
            service_kind=str(payload.get("service_kind") or "voxbulk").strip(),
            is_active=bool(payload.get("is_active", True)),
            is_featured=bool(payload.get("is_featured", False)),
            is_enterprise=bool(payload.get("is_enterprise", False)),
            sort_order=int(payload.get("sort_order") or 100),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_plan(db: Session, row: Plan, payload: dict[str, Any]) -> Plan:
        if payload.get("name") is not None:
            row.name = str(payload.get("name") or "").strip() or row.name
        if "price_gbp_pence" in payload:
            raw = payload.get("price_gbp_pence")
            row.price_gbp_pence = None if raw is None else int(raw or 0)
        if payload.get("interval") is not None:
            row.interval = str(payload.get("interval") or "monthly").strip()
        if "description" in payload:
            raw = payload.get("description")
            row.description = None if raw is None else str(raw)
        if isinstance(payload.get("features"), list):
            row.features_json = json.dumps([str(x) for x in payload["features"]])
        if payload.get("calls_included") is not None or payload.get("minutes_included") is not None:
            row.calls_included = int(payload.get("calls_included") if payload.get("calls_included") is not None else payload.get("minutes_included") or 0)
        for field in (
            "whatsapp_included",
            "sms_included",
            "cv_scans_included",
            "trial_days_default",
            "sort_order",
        ):
            if payload.get(field) is not None:
                setattr(row, field, int(payload.get(field) or 0))
        if payload.get("per_min_pence") is not None:
            row.per_min_pence = int(payload.get("per_min_pence") or 0)
        if payload.get("extra_per_min_pence") is not None or payload.get("overage_per_min_pence") is not None:
            row.overage_per_min_pence = int(
                payload.get("extra_per_min_pence")
                if payload.get("extra_per_min_pence") is not None
                else payload.get("overage_per_min_pence") or 0
            )
        if payload.get("service_kind") is not None:
            row.service_kind = str(payload.get("service_kind") or "voxbulk").strip()
        if payload.get("is_active") is not None:
            row.is_active = bool(payload.get("is_active"))
        if payload.get("is_featured") is not None:
            row.is_featured = bool(payload.get("is_featured"))
        if payload.get("is_enterprise") is not None:
            row.is_enterprise = bool(payload.get("is_enterprise"))
            if row.is_enterprise and "price_gbp_pence" not in payload:
                row.price_gbp_pence = None
        row.updated_at = datetime.utcnow()
        if row.service_kind == "voxbulk" and not row.is_enterprise:
            from app.services.voxbulk_pricing_service import VoxbulkPricingService

            VoxbulkPricingService.apply_plan_allowances(db, row)
        else:
            db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def duplicate_plan(db: Session, row: Plan) -> Plan:
        suffix = 1
        base = f"{row.code}_copy"
        code = base
        while db.execute(select(Plan.id).where(Plan.code == code)).scalar_one_or_none() is not None:
            suffix += 1
            code = f"{base}{suffix}"
        now = datetime.utcnow()
        dup = Plan(
            id=str(uuid.uuid4()),
            code=code,
            name=f"{row.name} (copy)",
            price_gbp_pence=int(row.price_gbp_pence or 0),
            interval=row.interval,
            description=row.description,
            features_json=row.features_json,
            calls_included=int(row.calls_included or 0),
            whatsapp_included=int(row.whatsapp_included or 0),
            sms_included=int(row.sms_included or 0),
            overage_per_min_pence=int(row.overage_per_min_pence or 0),
            trial_days_default=int(row.trial_days_default or 0),
            service_kind=row.service_kind,
            is_active=False,
            sort_order=int(row.sort_order or 100) + 1,
            created_at=now,
            updated_at=now,
        )
        db.add(dup)
        db.commit()
        db.refresh(dup)
        return dup

    @staticmethod
    def delete_plan(db: Session, row: Plan) -> None:
        n = db.execute(select(func.count()).select_from(Subscription).where(Subscription.plan_id == row.id)).scalar_one()
        if int(n or 0) > 0:
            raise PlanAdminError("Cannot delete — organisations are subscribed to this plan. Stop it instead.")
        db.delete(row)
        db.commit()

    @staticmethod
    def set_active(db: Session, row: Plan, active: bool) -> Plan:
        row.is_active = bool(active)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
