"""Sales Hub promo benefits, commission tiers, partner terms, and package prices by currency."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.services.billing_currency import (
    SUPPORTED_CURRENCIES,
    currency_for_country_code,
    currency_symbol,
    money_display,
    normalize_currency,
)

SERVICE_IDS = ("ai_interview", "wa_survey", "customer_feedback", "voxbulk_expo")

SERVICE_META: dict[str, dict[str, Any]] = {
    "ai_interview": {
        "name": "AI Interview Screening",
        "service_kind": "interview",
        "options": [
            {"kind": "fixed_topup", "label": "Fixed top-up amount", "unit": "minor"},
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
        ],
    },
    "wa_survey": {
        "name": "WA Survey / AI Call Survey",
        "service_kind": "survey",
        "options": [
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
            {"kind": "fixed_topup", "label": "Fixed top-up amount", "unit": "minor"},
            {"kind": "free_days", "label": "Free trial days", "unit": "days", "default": 14},
        ],
    },
    "customer_feedback": {
        "name": "Customer Feedback",
        "service_kind": "feedback",
        "options": [
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
            {"kind": "free_days", "label": "Free days from 1st scan", "unit": "days", "default": 15},
        ],
    },
    "voxbulk_expo": {
        "name": "Voxbulk Expo",
        "service_kind": "expo",
        "options": [
            {"kind": "free_package_days", "label": "Free package days", "unit": "days", "default": 3},
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
        ],
    },
}

SERVICE_KIND_BY_ID = {sid: meta["service_kind"] for sid, meta in SERVICE_META.items()}
DEFAULT_VOUCHER_MINOR = 2000


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def currency_of_rep(rep) -> str:
    stored = normalize_currency(getattr(rep, "currency", None) or "")
    if getattr(rep, "currency", None) and str(getattr(rep, "currency") or "").strip().upper() in SUPPORTED_CURRENCIES:
        return stored
    return currency_for_country_code(getattr(rep, "country", None))


def sync_rep_currency(rep) -> str:
    cur = currency_for_country_code(getattr(rep, "country", None))
    rep.currency = cur
    return cur


def default_promo_benefits(*, voucher_enabled: bool = True, voucher_minor: int = DEFAULT_VOUCHER_MINOR) -> dict[str, Any]:
    services = {}
    for sid in SERVICE_IDS:
        opts = SERVICE_META[sid]["options"]
        first = opts[0]
        services[sid] = {
            "enabled": False,
            "kind": first["kind"],
            "value": int(first.get("default") or (DEFAULT_VOUCHER_MINOR if first["kind"] == "fixed_topup" else 0)),
        }
    return {
        "wallet_voucher": {"enabled": bool(voucher_enabled), "amount_minor": int(voucher_minor or DEFAULT_VOUCHER_MINOR)},
        "services": services,
        "usage_limit": None,
        "expires_at": None,
    }


def default_commission_tiers(*, month2_pct: float = 15.0) -> list[dict[str, Any]]:
    return [
        {"month": 2, "enabled": True, "kind": "percent", "value": float(month2_pct)},
        {"month": 3, "enabled": False, "kind": "percent", "value": float(month2_pct)},
        {"month": 4, "enabled": False, "kind": "percent", "value": float(month2_pct)},
    ]


def default_partner_terms(*, discount_percent: float = 0.0, billing: str = "customer_pays") -> dict[str, Any]:
    mode = str(billing or "customer_pays").strip().lower()
    if mode not in {"invoice_partner", "customer_pays"}:
        mode = "customer_pays"
    return {"discount_percent": float(discount_percent or 0), "billing": mode}


def parse_promo_benefits(rep) -> dict[str, Any]:
    raw = _loads(getattr(rep, "promo_benefits_json", None), None)
    if isinstance(raw, dict) and "wallet_voucher" in raw:
        base = default_promo_benefits()
        base["wallet_voucher"].update(raw.get("wallet_voucher") or {})
        services = dict(base["services"])
        incoming = raw.get("services") or {}
        if isinstance(incoming, dict):
            for sid in SERVICE_IDS:
                if sid in incoming and isinstance(incoming[sid], dict):
                    services[sid] = {**services[sid], **incoming[sid]}
        base["services"] = services
        if "usage_limit" in raw:
            base["usage_limit"] = raw.get("usage_limit")
        if "expires_at" in raw:
            base["expires_at"] = raw.get("expires_at")
        return base
    # Legacy: always £20 / 20 local voucher
    return default_promo_benefits(voucher_enabled=True, voucher_minor=DEFAULT_VOUCHER_MINOR)


def parse_commission_tiers(rep) -> list[dict[str, Any]]:
    raw = _loads(getattr(rep, "commission_tiers_json", None), None)
    if isinstance(raw, list) and raw:
        by_month = {int(t.get("month") or 0): t for t in raw if isinstance(t, dict)}
        out = []
        for month in (2, 3, 4):
            t = by_month.get(month) or {"month": month, "enabled": False, "kind": "percent", "value": 15}
            out.append(
                {
                    "month": month,
                    "enabled": bool(t.get("enabled")),
                    "kind": "fixed" if str(t.get("kind") or "").lower() == "fixed" else "percent",
                    "value": float(t.get("value") or 0),
                }
            )
        return out
    # Legacy from commission_type / pct / fixed
    from app.services.sales_payout_service import (
        COMMISSION_TYPE_FIXED,
        COMMISSION_TYPE_MONTH2,
        COMMISSION_TYPE_PERCENT,
        SalesPayoutService,
    )

    ctype = SalesPayoutService.commission_type_of(rep)
    pct = float(getattr(rep, "commission_pct", None) or 15)
    fixed = int(getattr(rep, "commission_fixed_minor", None) or 0)
    if ctype == COMMISSION_TYPE_MONTH2:
        return default_commission_tiers(month2_pct=pct)
    # percent/fixed → treat as partner-style next payment; still expose month2 slot for UI consistency
    kind = "fixed" if ctype == COMMISSION_TYPE_FIXED else "percent"
    value = fixed if kind == "fixed" else pct
    return [
        {"month": 2, "enabled": ctype == COMMISSION_TYPE_MONTH2, "kind": kind, "value": value},
        {"month": 3, "enabled": False, "kind": "percent", "value": pct},
        {"month": 4, "enabled": False, "kind": "percent", "value": pct},
    ]


def parse_partner_terms(rep) -> dict[str, Any]:
    raw = _loads(getattr(rep, "partner_terms_json", None), None)
    if isinstance(raw, dict):
        return default_partner_terms(
            discount_percent=raw.get("discount_percent"),
            billing=raw.get("billing"),
        )
    return default_partner_terms()


def normalize_promo_benefits(payload: Any) -> dict[str, Any]:
    base = default_promo_benefits(voucher_enabled=False, voucher_minor=DEFAULT_VOUCHER_MINOR)
    if not isinstance(payload, dict):
        return base
    wv = payload.get("wallet_voucher") if isinstance(payload.get("wallet_voucher"), dict) else {}
    base["wallet_voucher"] = {
        "enabled": bool(wv.get("enabled")),
        "amount_minor": max(0, int(wv.get("amount_minor") or DEFAULT_VOUCHER_MINOR)),
    }
    services = {}
    incoming = payload.get("services") if isinstance(payload.get("services"), dict) else {}
    for sid in SERVICE_IDS:
        src = incoming.get(sid) if isinstance(incoming.get(sid), dict) else {}
        allowed = {o["kind"] for o in SERVICE_META[sid]["options"]}
        kind = str(src.get("kind") or SERVICE_META[sid]["options"][0]["kind"])
        if kind not in allowed:
            kind = SERVICE_META[sid]["options"][0]["kind"]
        services[sid] = {
            "enabled": bool(src.get("enabled")),
            "kind": kind,
            "value": float(src.get("value") or 0),
        }
    base["services"] = services
    ul = payload.get("usage_limit")
    base["usage_limit"] = None if ul in (None, "", 0, "0") else max(1, int(ul))
    exp = payload.get("expires_at")
    base["expires_at"] = str(exp).strip() if exp else None
    return base


def normalize_commission_tiers(payload: Any) -> list[dict[str, Any]]:
    base = default_commission_tiers()
    if not isinstance(payload, list):
        return base
    by_month = {int(t.get("month") or 0): t for t in payload if isinstance(t, dict)}
    out = []
    for month in (2, 3, 4):
        t = by_month.get(month) or {}
        kind = "fixed" if str(t.get("kind") or "").lower() == "fixed" else "percent"
        out.append(
            {
                "month": month,
                "enabled": bool(t.get("enabled")),
                "kind": kind,
                "value": float(t.get("value") or 0),
            }
        )
    return out


def normalize_partner_terms(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return default_partner_terms()
    return default_partner_terms(
        discount_percent=payload.get("discount_percent"),
        billing=payload.get("billing"),
    )


def set_promo_benefits(rep, payload: Any) -> dict[str, Any]:
    data = normalize_promo_benefits(payload)
    rep.promo_benefits_json = _dumps(data)
    return data


def set_commission_tiers(rep, payload: Any) -> list[dict[str, Any]]:
    data = normalize_commission_tiers(payload)
    rep.commission_tiers_json = _dumps(data)
    # Keep legacy columns in sync with first enabled tier (or month 2).
    primary = next((t for t in data if t["enabled"]), data[0])
    if primary["kind"] == "fixed":
        rep.commission_type = "fixed"
        rep.commission_fixed_minor = int(round(float(primary["value"])))
        rep.commission_pct = float(data[0]["value"] if data[0]["kind"] == "percent" else getattr(rep, "commission_pct", 15) or 15)
    else:
        # If only month 2 (or monthly tiers) — month2; if partner uses next-payment percent they set commission_type separately
        enabled_months = [t["month"] for t in data if t["enabled"]]
        if enabled_months and set(enabled_months) <= {2, 3, 4}:
            rep.commission_type = "month2"
        rep.commission_pct = float(primary["value"])
        rep.commission_fixed_minor = 0
    return data


def set_partner_terms(rep, payload: Any) -> dict[str, Any]:
    data = normalize_partner_terms(payload)
    rep.partner_terms_json = _dumps(data)
    return data


def benefit_summaries(benefits: dict[str, Any], *, currency: str = "GBP") -> list[str]:
    lines: list[str] = []
    wv = benefits.get("wallet_voucher") or {}
    if wv.get("enabled"):
        lines.append(f"Wallet voucher {money_display(int(wv.get('amount_minor') or 0), currency)}")
    for sid in SERVICE_IDS:
        svc = (benefits.get("services") or {}).get(sid) or {}
        if not svc.get("enabled"):
            continue
        name = SERVICE_META[sid]["name"]
        kind = str(svc.get("kind") or "")
        val = float(svc.get("value") or 0)
        if kind == "percent_discount":
            lines.append(f"{name}: {val:g}% discount")
        elif kind == "fixed_topup":
            lines.append(f"{name}: {money_display(int(round(val)), currency)} top-up")
        elif kind == "free_days":
            lines.append(f"{name}: {int(val)} free days")
        elif kind == "free_package_days":
            lines.append(f"{name}: {int(val)} free package days")
        else:
            lines.append(f"{name}: {kind} {val:g}")
    return lines


def commission_summary(tiers: list[dict[str, Any]], *, currency: str = "GBP", partner: bool = False, partner_terms: dict | None = None) -> str:
    enabled = [t for t in tiers if t.get("enabled")]
    if partner:
        pt = partner_terms or {}
        bits = []
        if enabled:
            t = enabled[0]
            if t["kind"] == "fixed":
                bits.append(f"Next payment · {money_display(int(round(t['value'])), currency)}")
            else:
                bits.append(f"Next payment · {float(t['value']):g}%")
        if pt.get("discount_percent"):
            bits.append(f"Partner discount {float(pt['discount_percent']):g}%")
        return " · ".join(bits) or "No commission"
    if not enabled:
        return "No commission tiers"
    parts = []
    for t in enabled:
        if t["kind"] == "fixed":
            parts.append(f"M{t['month']} {money_display(int(round(t['value'])), currency)}")
        else:
            parts.append(f"M{t['month']} {float(t['value']):g}%")
    return " · ".join(parts)


def packages_for_currency(db: Session, currency: str) -> list[dict[str, Any]]:
    """Live package list prices for a currency (Interview / Survey / Feedback / Expo)."""
    cur = normalize_currency(currency)
    out: list[dict[str, Any]] = []
    try:
        from app.models.plan import Plan
        from app.services.plan_price_service import PlanPriceService
        from sqlalchemy import select

        plans = db.execute(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.name.asc())).scalars().all()
        family_map = {
            "interview": "ai_interview",
            "ai_interview": "ai_interview",
            "survey": "wa_survey",
            "wa_survey": "wa_survey",
            "feedback": "customer_feedback",
            "customer_feedback": "customer_feedback",
            "expo": "voxbulk_expo",
            "voxbulk": "voxbulk_expo",
        }
        seen_services: set[str] = set()
        for plan in plans:
            code = str(getattr(plan, "code", "") or "").lower()
            product = str(getattr(plan, "product", "") or getattr(plan, "family", "") or "").lower()
            service_id = None
            for key, sid in family_map.items():
                if key in code or key in product:
                    service_id = sid
                    break
            if service_id is None or service_id in seen_services:
                continue
            price = PlanPriceService.get_price(db, plan.id, cur)
            monthly = None
            yearly = None
            if price is not None:
                monthly = getattr(price, "monthly_price_minor", None)
                yearly = getattr(price, "yearly_price_minor", None)
            out.append(
                {
                    "service_id": service_id,
                    "name": SERVICE_META[service_id]["name"],
                    "plan_code": getattr(plan, "code", None),
                    "plan_name": getattr(plan, "name", None),
                    "currency": cur,
                    "symbol": currency_symbol(cur),
                    "monthly_price_minor": monthly,
                    "yearly_price_minor": yearly,
                    "monthly_display": money_display(monthly, cur) if monthly is not None else None,
                    "yearly_display": money_display(yearly, cur) if yearly is not None else None,
                    "list_price_minor": monthly if monthly is not None else yearly,
                    "list_price_display": money_display(monthly if monthly is not None else yearly, cur)
                    if (monthly is not None or yearly is not None)
                    else None,
                }
            )
            seen_services.add(service_id)
            if len(seen_services) >= 4:
                break
    except Exception:
        pass

    # Ensure all four services appear even without plans
    have = {p["service_id"] for p in out}
    for sid in SERVICE_IDS:
        if sid not in have:
            out.append(
                {
                    "service_id": sid,
                    "name": SERVICE_META[sid]["name"],
                    "plan_code": None,
                    "plan_name": None,
                    "currency": cur,
                    "symbol": currency_symbol(cur),
                    "monthly_price_minor": None,
                    "yearly_price_minor": None,
                    "monthly_display": None,
                    "yearly_display": None,
                    "list_price_minor": None,
                    "list_price_display": None,
                }
            )
    return out


def service_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": sid,
            "name": meta["name"],
            "service_kind": meta["service_kind"],
            "options": meta["options"],
        }
        for sid, meta in SERVICE_META.items()
    ]


def parse_expires_at(raw: Any) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text.replace("Z", ""))
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
