"""Products hub catalogue — display metadata and marketing copy only.

Does not mutate prices, allowances, wallet, invoices, or launch billing rates.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackPackage
from app.models.plan import Plan
from app.models.platform_service import PlatformService
from app.services.billing_access_service import BillingAccessService
from app.services.billing_currency import money_display, normalize_currency
from app.services.gocardless_service import BillingService
from app.services.plan_admin_service import PlanAdminError, PlanAdminService
from app.services.platform_catalog_service import PlatformCatalogService

_DENTAL_CODES = frozenset({"practice", "group"})
_CF_CODE_RE = re.compile(r"^cf_(?P<tier>[a-z0-9]+)_(?P<zone>[a-z]{2})$", re.I)

_ZONE_LABELS: dict[str, tuple[str, str]] = {
    "gb": ("GB", "GBP"),
    "eu": ("EU", "EUR"),
    "us": ("US", "USD"),
    "ca": ("CA", "CAD"),
    "au": ("AU", "AUD"),
}

_GROUP_LABELS = {
    "voxbulk": "Core platform",
    "customer_feedback": "Customer Feedback",
    "campaign": "Campaign packs",
}

_CAMPAIGN_TIER: dict[str, str] = {
    "survey": "survey",
    "interview": "interview",
    "interview_ats": "ats",
    "appointments": "appt",
}


class ProductsHubService:
    @staticmethod
    def is_dental_plan(plan: Plan) -> bool:
        kind = str(getattr(plan, "service_kind", None) or "").strip().lower()
        code = str(plan.code or "").strip().lower()
        if kind == "dental":
            return True
        return code in _DENTAL_CODES

    @staticmethod
    def product_line_for_plan(plan: Plan) -> str | None:
        if ProductsHubService.is_dental_plan(plan):
            return None
        kind = str(getattr(plan, "service_kind", None) or "voxbulk").strip().lower()
        code = str(plan.code or "").strip().lower()
        if kind == "customer_feedback" or code.startswith("cf_"):
            return "customer_feedback"
        if kind == "voxbulk" or BillingAccessService.is_valid_core_plan(plan):
            return "voxbulk"
        return None

    @staticmethod
    def decode_cf_code(code: str) -> tuple[str | None, str | None]:
        m = _CF_CODE_RE.match(str(code or "").strip())
        if not m:
            return None, None
        return m.group("tier").lower(), m.group("zone").lower()

    @staticmethod
    def tier_key_for_plan(plan: Plan) -> str:
        line = ProductsHubService.product_line_for_plan(plan)
        code = str(plan.code or "").strip().lower()
        if line == "customer_feedback":
            tier, _ = ProductsHubService.decode_cf_code(code)
            return tier or code
        return code or "plan"

    @staticmethod
    def region_for_plan(plan: Plan, *, fb_pkg: FeedbackPackage | None = None) -> str:
        line = ProductsHubService.product_line_for_plan(plan)
        if line == "customer_feedback":
            _, zone = ProductsHubService.decode_cf_code(plan.code)
            zone = zone or (str(fb_pkg.market_zone).lower() if fb_pkg else None)
            if zone and zone in _ZONE_LABELS:
                return _ZONE_LABELS[zone][0]
        return "Global"

    @staticmethod
    def currency_for_plan(plan: Plan, *, fb_pkg: FeedbackPackage | None = None) -> str:
        line = ProductsHubService.product_line_for_plan(plan)
        if line == "customer_feedback":
            _, zone = ProductsHubService.decode_cf_code(plan.code)
            zone = zone or (str(fb_pkg.market_zone).lower() if fb_pkg else None)
            if zone and zone in _ZONE_LABELS:
                return _ZONE_LABELS[zone][1]
        return "GBP"

    @staticmethod
    def _price_minor_for_display(db: Session, plan: Plan, currency: str) -> int | None:
        from app.services.plan_price_service import PlanPriceService

        code = normalize_currency(currency)
        price_row = PlanPriceService.get_price(db, plan.id, code)
        if price_row and price_row.monthly_price_minor is not None:
            return int(price_row.monthly_price_minor)
        if code == "GBP" and plan.price_gbp_pence is not None:
            return int(plan.price_gbp_pence)
        return None

    @staticmethod
    def limits_summary(plan: Plan, *, fb_pkg: FeedbackPackage | None = None, campaign_desc: str | None = None) -> str:
        line = ProductsHubService.product_line_for_plan(plan)
        if line == "customer_feedback" and fb_pkg is not None:
            web = (
                "Unlimited Web"
                if int(fb_pkg.web_units_included or 0) < 0
                else f"{int(fb_pkg.web_units_included)} Web"
            )
            return f"{int(fb_pkg.wa_units_included or 0)} WhatsApp · {web}"
        if line == "voxbulk":
            parts: list[str] = []
            if int(plan.calls_included or 0):
                parts.append(f"{int(plan.calls_included)} calls")
            if int(plan.whatsapp_included or 0):
                parts.append(f"{int(plan.whatsapp_included)} WhatsApp")
            if int(plan.sms_included or 0):
                parts.append(f"{int(plan.sms_included)} SMS")
            if int(getattr(plan, "cv_scans_included", 0) or 0):
                parts.append(f"{int(plan.cv_scans_included)} CV scans")
            return " · ".join(parts) if parts else "No limits set"
        return str(campaign_desc or "No limits set")

    @staticmethod
    def picker_parts(plan: Plan, *, fb_pkg: FeedbackPackage | None = None) -> dict[str, str]:
        line = ProductsHubService.product_line_for_plan(plan) or "plan"
        group_label = _GROUP_LABELS.get(line, line)
        region = ProductsHubService.region_for_plan(plan, fb_pkg=fb_pkg)
        currency = ProductsHubService.currency_for_plan(plan, fb_pkg=fb_pkg)
        title = str(plan.name or plan.code)
        if line == "voxbulk":
            subtitle = f"{group_label} · Custom" if bool(getattr(plan, "is_enterprise", False)) else f"{group_label} · Global"
        else:
            subtitle = f"{group_label} · {region} ({currency})"
        if line == "voxbulk":
            picker_label = f"{group_label} · {title} · {'Custom' if bool(getattr(plan, 'is_enterprise', False)) else 'Global'}"
        else:
            picker_label = f"{group_label} · {title} · {region} ({currency})"
        return {
            "picker_title": title,
            "picker_subtitle": subtitle,
            "picker_label": picker_label,
        }

    @staticmethod
    def pricing_editor_url(plan: Plan, *, currency: str = "GBP") -> str:
        line = ProductsHubService.product_line_for_plan(plan)
        code = str(plan.code or "")
        if line == "customer_feedback":
            return f"/customer-feedback/packages?currency={normalize_currency(currency)}&plan={code}"
        return f"/pricing/plans?plan={code}"

    @staticmethod
    def preview_urls(plan: Plan) -> dict[str, str]:
        code = str(plan.code or "")
        line = ProductsHubService.product_line_for_plan(plan)
        if line == "customer_feedback":
            return {
                "dashboard": f"/account/feedback/packages?plan={code}",
                "website": f"https://voxbulk.com/pricing?plan={code}&product=feedback",
            }
        return {
            "dashboard": f"/account/packages?plan={code}",
            "website": f"https://voxbulk.com/pricing?plan={code}",
        }

    @staticmethod
    def enrich_plan_row(db: Session, plan: Plan, *, fb_pkg: FeedbackPackage | None = None) -> dict[str, Any] | None:
        line = ProductsHubService.product_line_for_plan(plan)
        if line is None:
            return None
        currency = ProductsHubService.currency_for_plan(plan, fb_pkg=fb_pkg)
        price_minor = ProductsHubService._price_minor_for_display(db, plan, currency)
        base = PlanAdminService.plan_to_dict(plan)
        picker = ProductsHubService.picker_parts(plan, fb_pkg=fb_pkg)
        previews = ProductsHubService.preview_urls(plan)
        return {
            **base,
            **picker,
            "product_line": line,
            "group_label": _GROUP_LABELS[line],
            "tier_key": ProductsHubService.tier_key_for_plan(plan),
            "region": ProductsHubService.region_for_plan(plan, fb_pkg=fb_pkg),
            "currency": currency,
            "price_minor": price_minor,
            "price_display": money_display(price_minor, currency) if price_minor is not None else None,
            "price_gap": False,
            "limits_summary": ProductsHubService.limits_summary(plan, fb_pkg=fb_pkg),
            "pricing_url": ProductsHubService.pricing_editor_url(plan, currency=currency),
            "preview_dashboard_url": previews["dashboard"],
            "preview_website_url": previews["website"],
            "market_zone": str(fb_pkg.market_zone).lower() if fb_pkg else None,
        }

    @staticmethod
    def enrich_campaign_row(svc: PlatformService) -> dict[str, Any]:
        base = PlanAdminService.campaign_to_dict(svc)
        code = str(svc.code or "")
        tier = _CAMPAIGN_TIER.get(code, code)
        return {
            **base,
            "product_line": "campaign",
            "group_label": _GROUP_LABELS["campaign"],
            "tier_key": tier,
            "region": "Global",
            "currency": None,
            "price_minor": None,
            "price_display": None,
            "price_gap": False,
            "limits_summary": str(svc.description or "No limits set"),
            "pricing_url": "/pricing/services",
            "preview_dashboard_url": None,
            "preview_website_url": None,
            "picker_title": str(svc.name or code),
            "picker_subtitle": "Campaign packs · Global",
            "picker_label": f"Campaign packs · {svc.name or code}",
        }

    @staticmethod
    def _apply_price_gaps(rows: list[dict[str, Any]]) -> None:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if row.get("product_type") != "subscription":
                continue
            key = f"{row.get('product_line')}|{row.get('tier_key')}"
            buckets.setdefault(key, []).append(row)
        for group in buckets.values():
            has_real = any(int(r.get("price_minor") or 0) > 0 for r in group)
            for r in group:
                minor = int(r.get("price_minor") or 0)
                r["price_gap"] = bool(has_real and minor <= 0 and not r.get("is_enterprise"))

    @staticmethod
    def list_catalog(db: Session) -> list[dict[str, Any]]:
        BillingService.ensure_default_plans(db)
        PlatformCatalogService.ensure_defaults(db)
        fb_by_plan = {str(p.plan_id): p for p in db.execute(select(FeedbackPackage)).scalars().all()}
        rows: list[dict[str, Any]] = []
        for plan in PlanAdminService.list_plans(db):
            enriched = ProductsHubService.enrich_plan_row(db, plan, fb_pkg=fb_by_plan.get(str(plan.id)))
            if enriched is not None:
                rows.append(enriched)
        for svc in db.execute(select(PlatformService).order_by(PlatformService.sort_order.asc())).scalars().all():
            rows.append(ProductsHubService.enrich_campaign_row(svc))
        ProductsHubService._apply_price_gaps(rows)
        rows.sort(
            key=lambda x: (
                {"voxbulk": 0, "customer_feedback": 1, "campaign": 2}.get(x.get("product_line") or "", 9),
                int(x.get("sort_order") or 100),
                x.get("region") or "",
                x.get("name") or "",
            )
        )
        return rows

    @staticmethod
    def list_assignable_plans(
        db: Session,
        *,
        product_line: str | None = None,
        market_zone: str | None = None,
    ) -> list[dict[str, Any]]:
        zone = str(market_zone or "").strip().lower() or None
        want = str(product_line or "").strip().lower() or None
        out: list[dict[str, Any]] = []
        for row in ProductsHubService.list_catalog(db):
            if row.get("product_type") != "subscription":
                continue
            line = str(row.get("product_line") or "")
            if want in {"core", "voxbulk"} and line != "voxbulk":
                continue
            if want in {"feedback", "customer_feedback"} and line != "customer_feedback":
                continue
            if zone and line == "customer_feedback":
                row_zone = str(row.get("market_zone") or "").lower()
                if row_zone and row_zone != zone:
                    continue
            out.append(
                {
                    "id": row.get("id"),
                    "code": row.get("code"),
                    "name": row.get("name"),
                    "product_line": line,
                    "picker_title": row.get("picker_title"),
                    "picker_subtitle": row.get("picker_subtitle"),
                    "picker_label": row.get("picker_label"),
                    "currency": row.get("currency"),
                    "region": row.get("region"),
                    "price_display": row.get("price_display"),
                    "is_enterprise": bool(row.get("is_enterprise")),
                    "is_active": bool(row.get("is_active")),
                    "market_zone": row.get("market_zone"),
                }
            )
        return out

    @staticmethod
    def update_plan_copy(db: Session, row: Plan, payload: dict[str, Any]) -> Plan:
        """Marketing copy and visibility only — never prices or billing allowances."""
        if payload.get("name") is not None:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise PlanAdminError("Plan name is required")
            row.name = name
        if "description" in payload:
            raw = payload.get("description")
            row.description = None if raw is None else str(raw).strip() or None
        if isinstance(payload.get("features"), list):
            row.features_json = json.dumps([str(x).strip() for x in payload["features"] if str(x).strip()])
        elif payload.get("features_text") is not None:
            features = [ln.strip() for ln in str(payload.get("features_text") or "").splitlines() if ln.strip()]
            row.features_json = json.dumps(features) if features else None
        if payload.get("is_active") is not None:
            row.is_active = bool(payload.get("is_active"))
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
