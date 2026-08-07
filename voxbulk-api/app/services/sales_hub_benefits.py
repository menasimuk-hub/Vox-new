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

SERVICE_IDS = ("core_package", "ai_interview", "wa_survey", "customer_feedback", "voxbulk_expo", "smart_card")

SERVICE_META: dict[str, dict[str, Any]] = {
    "core_package": {
        "name": "Core package (Starter / Growth)",
        "service_kind": "voxbulk",
        "options": [
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
            {"kind": "free_days", "label": "Free trial days", "unit": "days", "default": 3},
        ],
    },
    "ai_interview": {
        "name": "AI Interview Screening",
        "service_kind": "interview",
        "options": [
            {"kind": "fixed_topup", "label": "Fixed top-up amount", "unit": "minor", "default": 2000},
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
        ],
    },
    "wa_survey": {
        "name": "WA Survey / AI Call Survey",
        "service_kind": "survey",
        "options": [
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
            {"kind": "fixed_topup", "label": "Fixed top-up amount", "unit": "minor", "default": 2000},
            {"kind": "free_days", "label": "Free trial days", "unit": "days", "default": 14},
        ],
    },
    "customer_feedback": {
        "name": "Customer Feedback",
        "service_kind": "feedback",
        "options": [
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
            {"kind": "fixed_topup", "label": "Fixed top-up amount", "unit": "minor", "default": 2000},
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
    "smart_card": {
        "name": "Smart Card QR",
        "service_kind": "smart_card",
        "options": [
            {"kind": "percent_discount", "label": "Percentage discount", "unit": "%", "default": 20},
            {"kind": "fixed_topup", "label": "Fixed top-up amount", "unit": "minor", "default": 2000},
            {"kind": "free_days", "label": "Free trial days", "unit": "days", "default": 14},
        ],
    },
}

SERVICE_KIND_BY_ID = {sid: meta["service_kind"] for sid, meta in SERVICE_META.items()}
DEFAULT_VOUCHER_MINOR = 2000
COMMISSION_MONTHS = (1, 2, 3, 4, 5, 6)
COMMISSION_MODES = frozenset({"commission_only", "one_time_only", "one_time_plus_commission"})
DEFAULT_COMMISSION_MODE = "commission_only"


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
    pct = float(month2_pct)
    return [
        {"month": m, "enabled": m == 2, "kind": "percent", "value": pct}
        for m in COMMISSION_MONTHS
    ]


def normalize_commission_mode(raw: Any) -> str:
    mode = str(raw or DEFAULT_COMMISSION_MODE).strip().lower()
    return mode if mode in COMMISSION_MODES else DEFAULT_COMMISSION_MODE


def parse_commission_mode(rep) -> str:
    return normalize_commission_mode(getattr(rep, "commission_mode", None))


def parse_one_time_bonus_minor(rep) -> int:
    try:
        return max(0, int(getattr(rep, "one_time_bonus_minor", None) or 0))
    except (TypeError, ValueError):
        return 0


def set_commission_extras(rep, *, mode: Any = None, one_time_bonus_minor: Any = None) -> None:
    if mode is not None:
        rep.commission_mode = normalize_commission_mode(mode)
    if one_time_bonus_minor is not None:
        try:
            rep.one_time_bonus_minor = max(0, int(one_time_bonus_minor))
        except (TypeError, ValueError):
            rep.one_time_bonus_minor = 0


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
        for month in COMMISSION_MONTHS:
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
        SalesPayoutService,
    )

    ctype = SalesPayoutService.commission_type_of(rep)
    pct = float(getattr(rep, "commission_pct", None) or 15)
    fixed = int(getattr(rep, "commission_fixed_minor", None) or 0)
    if ctype == COMMISSION_TYPE_MONTH2:
        return default_commission_tiers(month2_pct=pct)
    kind = "fixed" if ctype == COMMISSION_TYPE_FIXED else "percent"
    value = fixed if kind == "fixed" else pct
    out = default_commission_tiers(month2_pct=pct)
    # Partner-style: expose month-1 as the “next payment” slot when using percent/fixed
    out[0] = {"month": 1, "enabled": True, "kind": kind, "value": value}
    for i in range(1, len(out)):
        out[i] = {**out[i], "enabled": False}
    return out


def normalize_commission_tiers(payload: Any) -> list[dict[str, Any]]:
    base = default_commission_tiers()
    if not isinstance(payload, list):
        return base
    by_month = {int(t.get("month") or 0): t for t in payload if isinstance(t, dict)}
    out = []
    for month in COMMISSION_MONTHS:
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


def set_commission_tiers(rep, payload: Any, *, preserve_partner_type: bool = False) -> list[dict[str, Any]]:
    data = normalize_commission_tiers(payload)
    rep.commission_tiers_json = _dumps(data)
    primary = next((t for t in data if t["enabled"]), data[1] if len(data) > 1 else data[0])
    is_partner = str(getattr(rep, "kind", "") or "").lower() == "partner_channel"
    if preserve_partner_type or is_partner:
        # Partners keep percent/fixed “every paid invoice” semantics; tiers are display/secondary
        if primary["kind"] == "fixed":
            rep.commission_type = "fixed"
            rep.commission_fixed_minor = int(round(float(primary["value"])))
        else:
            rep.commission_type = "percent"
            rep.commission_pct = float(primary["value"])
            rep.commission_fixed_minor = 0
        return data
    if primary["kind"] == "fixed":
        rep.commission_type = "fixed"
        rep.commission_fixed_minor = int(round(float(primary["value"])))
        rep.commission_pct = float(
            next((t["value"] for t in data if t["kind"] == "percent"), getattr(rep, "commission_pct", 15) or 15)
        )
    else:
        enabled_months = [t["month"] for t in data if t["enabled"]]
        if enabled_months:
            rep.commission_type = "month2"
        rep.commission_pct = float(primary["value"])
        rep.commission_fixed_minor = 0
    return data


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


def set_partner_terms(rep, payload: Any) -> dict[str, Any]:
    data = normalize_partner_terms(payload)
    rep.partner_terms_json = _dumps(data)
    return data


def benefit_summaries(benefits: dict[str, Any], *, currency: str = "GBP") -> list[str]:
    lines: list[str] = []
    wv = benefits.get("wallet_voucher") or {}
    if wv.get("enabled"):
        lines.append(
            f"Customer signup wallet credit {money_display(int(wv.get('amount_minor') or 0), currency)} "
            "(goes to the customer, not your commission)"
        )
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


def commission_summary(
    tiers: list[dict[str, Any]],
    *,
    currency: str = "GBP",
    partner: bool = False,
    partner_terms: dict | None = None,
    commission_mode: str | None = None,
    one_time_bonus_minor: int | None = None,
) -> str:
    mode = (commission_mode or "commission_only").strip().lower()
    bonus = int(one_time_bonus_minor or 0)
    bonus_bit = ""
    if mode in ("one_time_only", "one_time_plus_commission") and bonus > 0:
        bonus_bit = f"One-time bonus {money_display(bonus, currency)}"

    enabled = [t for t in tiers if t.get("enabled")]
    if partner:
        pt = partner_terms or {}
        bits = []
        if bonus_bit:
            bits.append(bonus_bit)
        if enabled and mode != "one_time_only":
            t = enabled[0]
            if t["kind"] == "fixed":
                bits.append(f"Next payment · {money_display(int(round(t['value'])), currency)}")
            else:
                bits.append(f"Next payment · {float(t['value']):g}%")
        if pt.get("discount_percent"):
            bits.append(f"Partner discount {float(pt['discount_percent']):g}%")
        return " · ".join(bits) or "No commission"
    if mode == "one_time_only":
        return bonus_bit or "One-time bonus only (amount not set)"
    if not enabled:
        return bonus_bit or "No commission tiers"
    parts = []
    if bonus_bit and mode == "one_time_plus_commission":
        parts.append(bonus_bit)
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
            "voxbulk": "core_package",
            "starter": "core_package",
            "growth": "core_package",
            "smart_card": "smart_card",
            "smartcard": "smart_card",
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
            if len(seen_services) >= 5:
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
