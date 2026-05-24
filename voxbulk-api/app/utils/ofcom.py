from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session


UK_TZ = ZoneInfo("Europe/London")


@dataclass(frozen=True)
class OfcomWindow:
    start: time
    end: time


DEFAULT_CALL_WINDOW = OfcomWindow(start=time(8, 0), end=time(21, 0))


def now_uk() -> datetime:
    """Return timezone-aware current time in the UK (Europe/London)."""
    return datetime.now(tz=UK_TZ)


def is_within_calling_window(dt: datetime, window: OfcomWindow = DEFAULT_CALL_WINDOW) -> bool:
    """
    Minimal utility for UK calling-time checks.

    TODO: Replace with Ofcom-compliant policy rules (weekends, consent, opt-outs, quiet hours, etc.).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UK_TZ)
    local = dt.astimezone(UK_TZ)
    t = local.time()
    return window.start <= t <= window.end


def _parse_hhmm(value: str, default: time) -> time:
    raw = str(value or "").strip()
    if not raw or ":" not in raw:
        return default
    try:
        hour, minute = raw.split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return default


def is_weekend_uk(dt: datetime) -> bool:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UK_TZ)
    return dt.astimezone(UK_TZ).weekday() >= 5


def resolve_org_call_window(db: Session, org_id: str | None, *, now: datetime | None = None) -> OfcomWindow:
    """Effective calling window for an organisation (intersected with UK platform floor)."""
    now = now or now_uk()
    if not org_id:
        return DEFAULT_CALL_WINDOW

    from app.models.organisation_ai_config import OrganisationComplianceConfig

    row = db.execute(
        select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)
    ).scalar_one_or_none()
    if row is None:
        return DEFAULT_CALL_WINDOW

    try:
        windows = json.loads(row.outbound_call_windows_json or "{}")
    except Exception:
        windows = {}

    block_key = "weekend" if is_weekend_uk(now) else "weekdays"
    block = windows.get(block_key) or windows.get("weekdays") or {}
    org_start = _parse_hhmm(str(block.get("start") or "09:00"), time(9, 0))
    org_end = _parse_hhmm(str(block.get("end") or "18:00"), time(18, 0))

    eff_start = max(org_start, DEFAULT_CALL_WINDOW.start)
    eff_end = min(org_end, DEFAULT_CALL_WINDOW.end)
    if eff_start > eff_end:
        return DEFAULT_CALL_WINDOW
    return OfcomWindow(start=eff_start, end=eff_end)


def org_calling_allowed(
    db: Session,
    org_id: str | None,
    *,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """Return whether outbound survey calls are allowed now for this organisation."""
    now = now or now_uk()

    if org_id:
        from app.models.organisation_ai_config import OrganisationComplianceConfig

        row = db.execute(
            select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)
        ).scalar_one_or_none()
        if row is not None and not row.weekend_allowed and is_weekend_uk(now):
            return False, "Organisation does not allow weekend calling"

    window = resolve_org_call_window(db, org_id, now=now)
    if not is_within_calling_window(now, window):
        return False, "Outside organisation calling hours"
    return True, None
