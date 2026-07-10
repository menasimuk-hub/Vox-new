"""Local Telnyx destination rate card — search, serialize, CSV import."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.telnyx_destination_rate import TelnyxDestinationRate

# 1 minor unit = 1/10000 of major currency (USD: 50 → $0.0050)
RATE_SCALE = 10_000
MAX_IMPORT_BYTES = 45 * 1024 * 1024

_ISO_RE = re.compile(r"^[A-Za-z]{2}$")

# Common calling codes when Telnyx prefix is too long to infer cleanly.
_DIAL_FALLBACK = {
    "GB": "44",
    "US": "1",
    "CA": "1",
    "AU": "61",
    "CN": "86",
    "EG": "20",
    "SA": "966",
    "AE": "971",
    "IN": "91",
    "PS": "970",
    "DE": "49",
    "FR": "33",
    "IE": "353",
    "NZ": "64",
    "PK": "92",
    "BD": "880",
    "PH": "63",
    "NG": "234",
    "ZA": "27",
    "TR": "90",
}


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


def _norm_header(k: str) -> str:
    k = str(k or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "iso": "country_iso",
        "country_code": "country_iso",
        "country_iso_code": "country_iso",
        "iso_code": "country_iso",
        "alpha_2": "country_iso",
        "country": "country_name",
        "country_name": "country_name",
        "destination_country": "country_name",
        "name": "country_name",
        "dial": "dial_code",
        "dial_code": "dial_code",
        "code": "dial_code",
        "prefix": "prefix",
        "destination_prefix": "prefix",
        "npanxx": "prefix",
        "description": "description",
        "destination": "description",
        "destination_name": "description",
        "rate": "rate",
        "rate_per_minute": "rate",
        "price": "rate",
        "amount": "rate",
        "voice_out": "voice_outbound",
        "voice_in": "voice_inbound",
        "sms_out": "sms_outbound",
        "sms_in": "sms_inbound",
        "voice_outbound": "voice_outbound",
        "voice_inbound": "voice_inbound",
        "sms_outbound": "sms_outbound",
        "sms_inbound": "sms_inbound",
        "voice_outbound_per_min": "voice_outbound",
        "voice_inbound_per_min": "voice_inbound",
        "sms_outbound_per_msg": "sms_outbound",
        "sms_inbound_per_msg": "sms_inbound",
        "currency": "currency",
        "notes": "notes",
    }
    return aliases.get(k, k)


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


def _infer_dial(iso: str, prefixes: Iterable[str]) -> str:
    if iso in _DIAL_FALLBACK:
        return _DIAL_FALLBACK[iso]
    # Prefer shortest numeric prefix (often the country calling code).
    cands = sorted({p for p in prefixes if p.isdigit()}, key=lambda p: (len(p), p))
    if not cands:
        return ""
    shortest = cands[0]
    if len(shortest) <= 3:
        return shortest
    # US/CA style 1XXXXXXXXX → 1
    if shortest.startswith("1") and iso in {"US", "CA"}:
        return "1"
    return shortest[:3]


def _is_sms_row(description: str, headers: set[str]) -> bool:
    d = (description or "").lower()
    if "sms" in d or "messaging" in d or "message" in d:
        return True
    if "voice_outbound" not in headers and "sms_outbound" in headers:
        return True
    return False


def _is_inbound_row(description: str) -> bool:
    d = (description or "").lower()
    return "inbound" in d and "outbound" not in d


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
                if len(errors) < 20:
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
        """Import either our compact country CSV or a Telnyx global rate deck.

        Telnyx decks are prefix-level (often 10M+ rows / tens of MB). We aggregate
        to one row per country ISO using the **minimum** outbound rate (Telnyx
        “starting at”) and note the max prefix rate.
        """
        if text is None:
            return {"ok": False, "error": "Empty CSV", "created": 0, "updated": 0, "skipped": 0}
        raw_bytes = len(text.encode("utf-8", errors="ignore")) if isinstance(text, str) else 0
        if raw_bytes > MAX_IMPORT_BYTES:
            return {
                "ok": False,
                "error": f"File too large ({raw_bytes // (1024 * 1024)}MB). Max is {MAX_IMPORT_BYTES // (1024 * 1024)}MB.",
                "created": 0,
                "updated": 0,
                "skipped": 0,
            }

        raw = (text or "").lstrip("\ufeff")
        if not raw.strip():
            return {"ok": False, "error": "Empty CSV", "created": 0, "updated": 0, "skipped": 0}

        # Sniff delimiter (Telnyx is usually comma).
        sample = raw[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(raw), dialect=dialect)
        if not reader.fieldnames:
            return {"ok": False, "error": "CSV missing header row", "created": 0, "updated": 0, "skipped": 0}

        header_map = {h: _norm_header(h) for h in reader.fieldnames}
        norms = set(header_map.values())
        detected_headers = [header_map[h] for h in reader.fieldnames]

        has_iso = "country_iso" in norms
        has_rate = "rate" in norms
        has_prefix = "prefix" in norms
        has_simple_voice = "voice_outbound" in norms
        is_telnyx_deck = has_iso and has_rate and (has_prefix or "description" in norms) and not has_simple_voice

        if not has_iso and not has_simple_voice:
            return {
                "ok": False,
                "error": (
                    "Unrecognised CSV headers. Need either country_iso + voice_outbound, "
                    "or a Telnyx rate deck with Country Code + Rate (+ Prefix). "
                    f"Got: {', '.join(detected_headers[:12])}"
                ),
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "headers": detected_headers[:20],
            }

        # --- Compact country CSV path ---
        if has_simple_voice or (has_iso and not is_telnyx_deck and not has_rate):
            rows: list[dict[str, Any]] = []
            for rec in reader:
                rows.append({header_map[k]: v for k, v in rec.items() if k in header_map})
            result = TelnyxDestinationRateService.upsert_many(db, rows, source=source)
            result["ok"] = True
            result["mode"] = "country_csv"
            result["rows_read"] = len(rows)
            return result

        # --- Telnyx global rate deck: aggregate by country ---
        # Per ISO: track min/max outbound voice (or SMS), name, prefixes
        agg: dict[str, dict[str, Any]] = {}
        rows_read = 0
        skipped = 0

        for rec in reader:
            rows_read += 1
            mapped = {header_map[k]: v for k, v in rec.items() if k in header_map}
            iso = str(mapped.get("country_iso") or "").strip().upper()
            if not _ISO_RE.match(iso):
                skipped += 1
                continue

            rate_minor = _parse_money_to_minor(mapped.get("rate"))
            if rate_minor is None:
                # Some decks put rate in voice_outbound already
                rate_minor = _parse_money_to_minor(mapped.get("voice_outbound"))
            if rate_minor is None:
                skipped += 1
                continue

            name = str(mapped.get("country_name") or iso).strip() or iso
            prefix = str(mapped.get("prefix") or "").strip().lstrip("+").replace(" ", "")
            desc = str(mapped.get("description") or "")
            bucket = agg.setdefault(
                iso,
                {
                    "name": name,
                    "prefixes": set(),
                    "voice_out_min": None,
                    "voice_out_max": None,
                    "voice_in_min": None,
                    "sms_out_min": None,
                    "sms_out_max": None,
                    "count": 0,
                },
            )
            if name and name != iso:
                bucket["name"] = name
            if prefix.isdigit():
                bucket["prefixes"].add(prefix)
            bucket["count"] += 1

            sms = _is_sms_row(desc, norms)
            inbound = _is_inbound_row(desc)

            if sms:
                cur_min = bucket["sms_out_min"]
                cur_max = bucket["sms_out_max"]
                bucket["sms_out_min"] = rate_minor if cur_min is None else min(cur_min, rate_minor)
                bucket["sms_out_max"] = rate_minor if cur_max is None else max(cur_max, rate_minor)
            elif inbound:
                cur = bucket["voice_in_min"]
                bucket["voice_in_min"] = rate_minor if cur is None else min(cur, rate_minor)
            else:
                cur_min = bucket["voice_out_min"]
                cur_max = bucket["voice_out_max"]
                bucket["voice_out_min"] = rate_minor if cur_min is None else min(cur_min, rate_minor)
                bucket["voice_out_max"] = rate_minor if cur_max is None else max(cur_max, rate_minor)

        if not agg:
            return {
                "ok": False,
                "error": (
                    "No country rates found in Telnyx sheet. "
                    f"Read {rows_read} rows, skipped {skipped}. "
                    f"Headers: {', '.join(detected_headers[:12])}"
                ),
                "created": 0,
                "updated": 0,
                "skipped": skipped,
                "rows_read": rows_read,
                "headers": detected_headers[:20],
            }

        upsert_rows: list[dict[str, Any]] = []
        for iso, b in agg.items():
            vo_min = b["voice_out_min"]
            vo_max = b["voice_out_max"]
            note_parts = [f"Telnyx deck: {b['count']} prefixes"]
            if vo_min is not None and vo_max is not None and vo_max != vo_min:
                note_parts.append(
                    f"voice out ${vo_min / RATE_SCALE:.4f}–${vo_max / RATE_SCALE:.4f}/min (showing min)"
                )
            if b["sms_out_min"] is not None and b["sms_out_max"] is not None and b["sms_out_max"] != b["sms_out_min"]:
                note_parts.append(
                    f"SMS ${b['sms_out_min'] / RATE_SCALE:.4f}–${b['sms_out_max'] / RATE_SCALE:.4f}"
                )
            upsert_rows.append(
                {
                    "country_iso": iso,
                    "country_name": b["name"],
                    "dial_code": _infer_dial(iso, b["prefixes"]),
                    "voice_outbound_per_min_minor": vo_min,
                    "voice_inbound_per_min_minor": b["voice_in_min"],
                    "sms_outbound_per_msg_minor": b["sms_out_min"],
                    "currency": "USD",
                    "notes": "; ".join(note_parts),
                }
            )

        result = TelnyxDestinationRateService.upsert_many(db, upsert_rows, source=source)
        result["ok"] = True
        result["mode"] = "telnyx_deck_aggregated"
        result["rows_read"] = rows_read
        result["countries"] = len(upsert_rows)
        result["skipped"] = skipped
        result["message"] = (
            f"Aggregated {rows_read} Telnyx prefix rows → {len(upsert_rows)} countries "
            f"({result.get('created', 0)} new, {result.get('updated', 0)} updated)."
        )
        return result
