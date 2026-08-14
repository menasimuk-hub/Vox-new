"""GBP → market FX helpers for Admin catalog pricing (not used at checkout).

Stored ``plan_prices`` / ``pricing_currency_settings`` remain the billing source of truth.
Rates in ``pricing_fx_rates`` only fill unlocked (non-manual) catalog rows when GBP changes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan_price import PricingFxRate, SUPPORTED_CURRENCIES
from app.services.billing_currency import normalize_currency

QUOTE_CURRENCIES = tuple(c for c in SUPPORTED_CURRENCIES if c != "GBP")

# Seeded 2026-08-14 mid-market approx (units of quote per 1 GBP). Used if DB row missing.
DEFAULT_FX_RATES: dict[str, Decimal] = {
    "EUR": Decimal("1.17010000"),
    "USD": Decimal("1.35330000"),
    "CAD": Decimal("1.88350000"),
    "AUD": Decimal("1.91200000"),
}


class PricingFxError(ValueError):
    pass


def commercial_round_minor(raw_minor: Decimal) -> int:
    """Round converted minor units to a commercial shelf price.

    - ≥ 100.00 major → nearest whole unit
    - ≥ 10.00 major → nearest 0.50
    - ≥ 1.00 major → nearest 0.05
    - else → nearest 0.01
    """
    if raw_minor <= 0:
        return 0
    major = raw_minor / Decimal(100)
    if major >= Decimal("100"):
        step = Decimal("1")
    elif major >= Decimal("10"):
        step = Decimal("0.5")
    elif major >= Decimal("1"):
        step = Decimal("0.05")
    else:
        step = Decimal("0.01")
    rounded_major = (major / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
    return int((rounded_major * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class PricingFxService:
    @staticmethod
    def ensure_seeded(db: Session) -> None:
        now = datetime.utcnow()
        created = False
        for quote, rate in DEFAULT_FX_RATES.items():
            row = db.get(PricingFxRate, quote)
            if row is None:
                db.add(
                    PricingFxRate(
                        quote_currency=quote,
                        base_currency="GBP",
                        rate=rate,
                        source="seed_2026-08-14",
                        updated_at=now,
                    )
                )
                created = True
        if created:
            db.commit()

    @staticmethod
    def list_rates(db: Session) -> list[dict[str, Any]]:
        PricingFxService.ensure_seeded(db)
        rows = list(db.execute(select(PricingFxRate).order_by(PricingFxRate.quote_currency.asc())).scalars().all())
        by_quote = {r.quote_currency: r for r in rows}
        out: list[dict[str, Any]] = []
        for quote in QUOTE_CURRENCIES:
            row = by_quote.get(quote)
            if row is None:
                continue
            out.append(
                {
                    "quote_currency": row.quote_currency,
                    "base_currency": row.base_currency or "GBP",
                    "rate": float(row.rate),
                    "rate_display": f"1 GBP = {float(row.rate):.4f} {row.quote_currency}",
                    "source": row.source,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
            )
        return out

    @staticmethod
    def rate_map(db: Session) -> dict[str, Decimal]:
        PricingFxService.ensure_seeded(db)
        rows = list(db.execute(select(PricingFxRate)).scalars().all())
        out = {q: r for q, r in DEFAULT_FX_RATES.items()}
        for row in rows:
            try:
                out[normalize_currency(row.quote_currency)] = Decimal(str(row.rate))
            except Exception:
                continue
        return out

    @staticmethod
    def upsert_rates(db: Session, rates: dict[str, Any]) -> list[dict[str, Any]]:
        """``rates`` is ``{ "EUR": 1.17, ... }`` or list of ``{quote_currency, rate}``."""
        items: list[tuple[str, Decimal]] = []
        if isinstance(rates, dict):
            for key, value in rates.items():
                code = normalize_currency(str(key))
                if code == "GBP":
                    continue
                if code not in QUOTE_CURRENCIES:
                    raise PricingFxError(f"Unsupported FX quote currency: {code}")
                items.append((code, Decimal(str(value))))
        elif isinstance(rates, list):
            for row in rates:
                if not isinstance(row, dict):
                    continue
                code = normalize_currency(str(row.get("quote_currency") or ""))
                if code not in QUOTE_CURRENCIES:
                    raise PricingFxError(f"Unsupported FX quote currency: {code}")
                items.append((code, Decimal(str(row.get("rate")))))
        else:
            raise PricingFxError("rates must be an object or list")

        now = datetime.utcnow()
        for code, rate in items:
            if rate <= 0:
                raise PricingFxError(f"FX rate for {code} must be positive")
            row = db.get(PricingFxRate, code)
            if row is None:
                row = PricingFxRate(quote_currency=code, base_currency="GBP", rate=rate, source="manual", updated_at=now)
            else:
                row.rate = rate
                row.source = "manual"
                row.updated_at = now
            db.add(row)
        db.commit()
        return PricingFxService.list_rates(db)

    @staticmethod
    def convert_gbp_minor(gbp_minor: int | None, quote_currency: str, rates: dict[str, Decimal] | None = None) -> int | None:
        if gbp_minor is None:
            return None
        code = normalize_currency(quote_currency)
        if code == "GBP":
            return int(gbp_minor)
        rate = (rates or {}).get(code)
        if rate is None or rate <= 0:
            return int(gbp_minor)
        raw = Decimal(int(gbp_minor)) * rate
        return commercial_round_minor(raw)

    @staticmethod
    def convert_payload_from_gbp(gbp_payload: dict[str, Any], quote_currency: str, rates: dict[str, Decimal]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key in ("monthly_price_minor", "yearly_price_minor", "per_min_minor", "extra_per_min_minor"):
            if key not in gbp_payload:
                continue
            value = gbp_payload[key]
            if value is None:
                out[key] = None
            else:
                out[key] = PricingFxService.convert_gbp_minor(int(value), quote_currency, rates)
        for key in (
            "connection_fee_minor",
            "interview_per_min_minor",
            "wa_package_fee_minor",
            "wa_extra_minor",
            "cv_scan_fee_minor",
        ):
            if key not in gbp_payload:
                continue
            out[key] = PricingFxService.convert_gbp_minor(int(gbp_payload[key] or 0), quote_currency, rates)
        if "is_active" in gbp_payload:
            out["is_active"] = bool(gbp_payload["is_active"])
        out["manual_override"] = False
        out["_from_fx"] = True
        return out
