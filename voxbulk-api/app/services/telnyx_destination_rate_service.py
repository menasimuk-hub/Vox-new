"""Local Telnyx destination rate card — search, serialize, CSV import."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.telnyx_destination_rate import TelnyxDestinationRate

# 1 minor unit = 1/10000 of major currency (USD: 50 → $0.0050)
RATE_SCALE = 10_000

_ISO_RE = re.compile(r"^[A-Za-z]{2}$")


def _money(minor: int | None, currency: str = "USD") -> dict[str, Any] | None:
    if minor is None:
        return None
    major = float(minor) / RATE_SCALE
    return {
        "minor": int(minor),
        "amount": major,
        "display": f"${major:.4f}".rstrip("0").rstrip(".") if currency.upper() == "USD" else f"{major:.4f} {currency}",
        "currency": currency.upper(),
    }


def _parse_money_to_minor(raw: Any) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"n/a", "na", "-", "null", "none"}:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return int(round(float(s) * RATE_SCALE))
    except (TypeError, ValueError):
        return None


def serialize_rate(row: TelnyxDestinationRate) -> dict[str, Any]:
    cur = (row.currency or "USD").upper()
    return {
        "country_iso": row.country_iso,
        "country_name": row.country_name,
        "dial_code": row.dial_code or "",
        "currency": cur,
        "voice_outbound": _money(row.voice_outbound_per_min_minor, cur),
        "voice_inbound": _money(row.voice_inbound_per_min_minor, cur),
        "sms_outbound": _money(row.sms_outbound_per_msg_minor, cur),
        "sms_inbound": _money(row.sms_inbound_per_msg_minor, cur),
        "notes": row.notes,
        "source": row.source,
        "is_placeholder": (row.source or "").lower() == "seed",
        "updated_at": row.updated_at.isoformat() + "Z" if row.updated_at else None,
    }


class TelnyxDestinationRateService:
    @staticmethod
    def get(db: Session, iso: str) -> TelnyxDestinationRate | None:
        code = str(iso or "").strip().upper()
        if not _ISO_RE.match(code):
            return None
        return db.get(TelnyxDestinationRate, code)

    @staticmethod
    def search(db: Session, q: str | None = None, *, limit: int = 40) -> list[TelnyxDestinationRate]:
        lim = max(1, min(int(limit or 40), 200))
        stmt = select(TelnyxDestinationRate).order_by(TelnyxDestinationRate.country_name)
        term = str(q or "").strip()
        if term:
            like = f"%{term}%"
            iso = term.upper()
            clauses = [
                TelnyxDestinationRate.country_name.ilike(like),
                TelnyxDestinationRate.country_iso.ilike(like),
                TelnyxDestinationRate.dial_code.ilike(like.lstrip("+")),
            ]
            if _ISO_RE.match(iso):
                clauses.insert(0, TelnyxDestinationRate.country_iso == iso)
            stmt = stmt.where(or_(*clauses))
        return list(db.scalars(stmt.limit(lim)).all())

    @staticmethod
    def map_for_isos(db: Session, isos: list[str]) -> dict[str, dict[str, Any]]:
        codes = sorted({str(i or "").strip().upper() for i in isos if _ISO_RE.match(str(i or "").strip())})
        if not codes:
            return {}
        rows = list(db.scalars(select(TelnyxDestinationRate).where(TelnyxDestinationRate.country_iso.in_(codes))).all())
        return {r.country_iso: serialize_rate(r) for r in rows}

    @staticmethod
    def upsert_many(
        db: Session,
        rows: list[dict[str, Any]],
        *,
        source: str = "csv_import",
        commit: bool = True,
    ) -> dict[str, Any]:
        now = datetime.utcnow()
        created = 0
        updated = 0
        skipped = 0
        errors: list[str] = []

        for i, raw in enumerate(rows):
            iso = str(raw.get("country_iso") or raw.get("iso") or "").strip().upper()
            if not _ISO_RE.match(iso):
                skipped += 1
                errors.append(f"row {i + 1}: invalid ISO")
                continue
            name = str(raw.get("country_name") or raw.get("name") or iso).strip() or iso
            dial = str(raw.get("dial_code") or raw.get("code") or "").strip().lstrip("+").replace(" ", "")
            currency = str(raw.get("currency") or "USD").strip().upper() or "USD"
            notes = raw.get("notes")
            notes_s = str(notes).strip() if notes is not None and str(notes).strip() else None

            vo = _parse_money_to_minor(raw.get("voice_outbound") if "voice_outbound" in raw else raw.get("voice_outbound_per_min"))
            vi = _parse_money_to_minor(raw.get("voice_inbound") if "voice_inbound" in raw else raw.get("voice_inbound_per_min"))
            so = _parse_money_to_minor(raw.get("sms_outbound") if "sms_outbound" in raw else raw.get("sms_outbound_per_msg"))
            si = _parse_money_to_minor(raw.get("sms_inbound") if "sms_inbound" in raw else raw.get("sms_inbound_per_msg"))

            # Also accept already-minor integer columns from API
            if vo is None and raw.get("voice_outbound_per_min_minor") is not None:
                try:
                    vo = int(raw["voice_outbound_per_min_minor"])
                except (TypeError, ValueError):
                    vo = None
            if vi is None and raw.get("voice_inbound_per_min_minor") is not None:
                try:
                    vi = int(raw["voice_inbound_per_min_minor"])
                except (TypeError, ValueError):
                    vi = None
            if so is None and raw.get("sms_outbound_per_msg_minor") is not None:
                try:
                    so = int(raw["sms_outbound_per_msg_minor"])
                except (TypeError, ValueError):
                    so = None
            if si is None and raw.get("sms_inbound_per_msg_minor") is not None:
                try:
                    si = int(raw["sms_inbound_per_msg_minor"])
                except (TypeError, ValueError):
                    si = None

            row = db.get(TelnyxDestinationRate, iso)
            if row is None:
                row = TelnyxDestinationRate(country_iso=iso, created_at=now)
                db.add(row)
                created += 1
            else:
                updated += 1

            row.country_name = name
            if dial:
                row.dial_code = dial
            row.currency = currency
            if vo is not None:
                row.voice_outbound_per_min_minor = vo
            if vi is not None:
                row.voice_inbound_per_min_minor = vi
            if so is not None:
                row.sms_outbound_per_msg_minor = so
            if si is not None:
                row.sms_inbound_per_msg_minor = si
            if notes_s is not None:
                row.notes = notes_s
            row.source = source
            row.updated_at = now

        if commit:
            db.commit()
        else:
            db.flush()

        return {
            "ok": True,
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors[:20],
        }

    @staticmethod
    def import_csv(db: Session, text: str, *, source: str = "csv_import") -> dict[str, Any]:
        raw = (text or "").lstrip("\ufeff").strip()
        if not raw:
            return {"ok": False, "error": "Empty CSV", "created": 0, "updated": 0, "skipped": 0}

        reader = csv.DictReader(io.StringIO(raw))
        if not reader.fieldnames:
            return {"ok": False, "error": "CSV missing header row", "created": 0, "updated": 0, "skipped": 0}

        # Normalize headers
        def _norm_key(k: str) -> str:
            k = str(k or "").strip().lower().replace(" ", "_").replace("-", "_")
            aliases = {
                "iso": "country_iso",
                "country": "country_name",
                "name": "country_name",
                "dial": "dial_code",
                "code": "dial_code",
                "voice_out": "voice_outbound",
                "voice_in": "voice_inbound",
                "sms_out": "sms_outbound",
                "sms_in": "sms_inbound",
                "voice_outbound_per_min": "voice_outbound",
                "voice_inbound_per_min": "voice_inbound",
                "sms_outbound_per_msg": "sms_outbound",
                "sms_inbound_per_msg": "sms_inbound",
            }
            return aliases.get(k, k)

        rows: list[dict[str, Any]] = []
        for rec in reader:
            rows.append({_norm_key(k): v for k, v in rec.items()})

        result = TelnyxDestinationRateService.upsert_many(db, rows, source=source)
        result["ok"] = True
        return result
