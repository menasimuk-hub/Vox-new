from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.country_vat_rate import CountryVatRate
from app.models.organisation import Organisation

_COUNTRY_ALIASES: dict[str, str] = {
    "uk": "GB",
    "u.k.": "GB",
    "united kingdom": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "wales": "GB",
    "uae": "AE",
    "u.a.e.": "AE",
    "united arab emirates": "AE",
    "dubai": "AE",
    "abu dhabi": "AE",
    "saudi arabia": "SA",
    "ksa": "SA",
    "qatar": "QA",
    "bahrain": "BH",
    "kuwait": "KW",
    "oman": "OM",
    "ireland": "IE",
    "republic of ireland": "IE",
    "united states": "US",
    "usa": "US",
    "u.s.a.": "US",
    "canada": "CA",
    "australia": "AU",
    "new zealand": "NZ",
    "singapore": "SG",
}


class CountryVatService:
    @staticmethod
    def resolve_country_code(db: Session, raw: str | None) -> str:
        text = str(raw or "").strip()
        if not text:
            return "GB"
        if len(text) == 2 and text.isalpha():
            return text.upper()
        key = re.sub(r"\s+", " ", text.lower())
        if key in _COUNTRY_ALIASES:
            return _COUNTRY_ALIASES[key]
        rows = db.execute(select(CountryVatRate)).scalars().all()
        for row in rows:
            if row.country_name.strip().lower() == key:
                return row.country_code.upper()
        return "GB"

    @staticmethod
    def resolve_org_country_code(db: Session, org: Organisation | None) -> str:
        if org is None:
            return "GB"
        return CountryVatService.resolve_country_code(db, org.country)

    @staticmethod
    def get_rate(db: Session, country_code: str) -> tuple[float, str]:
        code = str(country_code or "GB").upper()[:2]
        row = db.execute(select(CountryVatRate).where(CountryVatRate.country_code == code)).scalar_one_or_none()
        if row is None or not row.is_enabled:
            fallback = db.execute(select(CountryVatRate).where(CountryVatRate.country_code == "GB")).scalar_one_or_none()
            if fallback and fallback.is_enabled:
                return float(fallback.vat_rate_percent or 0), fallback.country_name
            return 0.0, code
        return float(row.vat_rate_percent or 0), row.country_name

    @staticmethod
    def list_all(db: Session) -> list[CountryVatRate]:
        return list(db.execute(select(CountryVatRate).order_by(CountryVatRate.country_name.asc())).scalars().all())

    @staticmethod
    def upsert(
        db: Session,
        *,
        country_code: str,
        country_name: str,
        vat_rate_percent: float,
        is_enabled: bool = True,
        notes: str | None = None,
    ) -> CountryVatRate:
        from datetime import datetime

        code = str(country_code or "").strip().upper()[:2]
        if len(code) != 2:
            raise ValueError("country_code must be 2 letters")
        row = db.execute(select(CountryVatRate).where(CountryVatRate.country_code == code)).scalar_one_or_none()
        now = datetime.utcnow()
        if row is None:
            row = CountryVatRate(
                country_code=code,
                country_name=str(country_name or code).strip(),
                vat_rate_percent=float(vat_rate_percent or 0),
                is_enabled=bool(is_enabled),
                notes=(notes or "").strip() or None,
                created_at=now,
                updated_at=now,
            )
        else:
            row.country_name = str(country_name or row.country_name).strip()
            row.vat_rate_percent = float(vat_rate_percent or 0)
            row.is_enabled = bool(is_enabled)
            row.notes = (notes or "").strip() or None
            row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete(db: Session, country_code: str) -> bool:
        code = str(country_code or "").strip().upper()[:2]
        row = db.execute(select(CountryVatRate).where(CountryVatRate.country_code == code)).scalar_one_or_none()
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True

    @staticmethod
    def compute_tax(subtotal_pence: int, rate_percent: float) -> int:
        subtotal = max(0, int(subtotal_pence or 0))
        rate = max(0.0, float(rate_percent or 0))
        return int(round(subtotal * rate / 100.0))

    @staticmethod
    def to_dict(row: CountryVatRate) -> dict[str, Any]:
        return {
            "country_code": row.country_code,
            "country_name": row.country_name,
            "vat_rate_percent": float(row.vat_rate_percent or 0),
            "is_enabled": bool(row.is_enabled),
            "notes": row.notes,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
