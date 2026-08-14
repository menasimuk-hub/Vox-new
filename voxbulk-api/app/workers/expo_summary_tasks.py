"""Celery beat: Expo visitor day/end summaries + identity purge."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.models.expo import (
    ExpoBooth,
    ExpoExhibition,
    ExpoLead,
    ExpoVisitorSummarySend,
)
from app.services.expo.expo_email_service import ExpoEmailService, _parse_offer_config
from app.services.expo.visitor_identity_service import ExpoVisitorIdentityService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _local_tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(str(name or "Europe/London").strip() or "Europe/London")
    except Exception:
        return ZoneInfo("Europe/London")


def _stand_row(db, lead: ExpoLead, booth: ExpoBooth) -> dict[str, Any]:
    offer = _parse_offer_config(getattr(booth, "offer_config_json", None))
    assets_raw = lead.assets_sent_json or ""
    asset_list = "—"
    try:
        import json

        parsed = json.loads(assets_raw) if assets_raw else []
        if isinstance(parsed, list) and parsed:
            asset_list = ", ".join(
                str(a.get("title") or a.get("purpose") or "File") for a in parsed if isinstance(a, dict)
            )
    except Exception:
        pass
    return {
        "company_name": booth.company_display_name or booth.name,
        "booth_name": booth.name or booth.booth_code or "",
        "contact_email": ExpoEmailService._booth_contact_email(booth) or "—",
        "asset_list": asset_list,
        "catalogue_requested": bool(lead.offer_sent_at or lead.consent_acknowledged),
        "offer_interested": bool(getattr(lead, "offer_interested", False)),
        "offer_title": (offer or {}).get("title"),
        "offer_claim_url": (offer or {}).get("claim_url"),
    }


@celery_app.task(name="expo.purge_expired_visitor_identities")
def purge_expired_visitor_identities() -> dict[str, Any]:
    with get_sessionmaker()() as db:
        n = ExpoVisitorIdentityService.purge_expired(db)
        return {"purged": n}


def _lead_local_date(created_at: datetime | None, tz: ZoneInfo):
    """Visit calendar day in the exhibition timezone (created_at is stored UTC-naive)."""
    if created_at is None:
        return None
    try:
        naive = created_at.replace(tzinfo=None) if getattr(created_at, "tzinfo", None) else created_at
        return naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).date()
    except Exception:
        try:
            return created_at.date()
        except Exception:
            return None


@celery_app.task(name="expo.send_visitor_day_summaries")
def send_visitor_day_summaries() -> dict[str, Any]:
    """Hourly: at most one visit summary email per visitor per exhibition, ever.

    - Daily (local 20:00): only leads created that local calendar day, and only if
      this visitor has never received a summary for this exhibition.
    - Final (within 26h of ends_on): all stands, but still only if never emailed.
    - Ended exhibitions are marked status=ended so the final window cannot re-open.
    """
    sent_daily = 0
    sent_final = 0
    marked_ended = 0
    with get_sessionmaker()() as db:
        try:
            now_utc = datetime.utcnow()
            exhibitions = db.execute(
                select(ExpoExhibition).where(ExpoExhibition.status == "active")
            ).scalars().all()
            for exhibition in exhibitions:
                tz = _local_tz(getattr(exhibition, "timezone", None))
                local_now = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz)
                local_date = local_now.date().isoformat()
                # Daily window: local 20:00–21:00 — only stands visited that local day
                if local_now.hour == 20:
                    sent_daily += _send_for_exhibition(
                        db,
                        exhibition=exhibition,
                        tz=tz,
                        summary_date=local_date,
                        is_final=False,
                        day_filter=local_now.date(),
                    )
                # Final: exhibition ended within last 26h (only if never emailed this visitor)
                ends = exhibition.ends_on
                if ends is not None:
                    ends_naive = ends.replace(tzinfo=None) if ends.tzinfo else ends
                    if ends_naive <= now_utc and ends_naive >= now_utc - timedelta(hours=26):
                        sent_final += _send_for_exhibition(
                            db,
                            exhibition=exhibition,
                            tz=tz,
                            summary_date=local_date,
                            is_final=True,
                            day_filter=None,
                        )
                    # Close the exhibition once it has ended so finals cannot re-fire later.
                    if ends_naive <= now_utc - timedelta(hours=1):
                        exhibition.status = "ended"
                        db.add(exhibition)
                        marked_ended += 1
            db.commit()
            return {"daily": sent_daily, "final": sent_final, "marked_ended": marked_ended}
        except Exception:
            logger.exception("expo_send_visitor_day_summaries_failed")
            db.rollback()
            return {"daily": sent_daily, "final": sent_final, "marked_ended": marked_ended, "error": True}


def _visitor_summary_already_sent(db, *, exhibition_id: str, visitor_email: str) -> bool:
    """One summary email per visitor per exhibition — never again on later calendar days."""
    email = str(visitor_email or "").strip().lower()
    if not email:
        return True
    return (
        db.execute(
            select(ExpoVisitorSummarySend.id).where(
                ExpoVisitorSummarySend.exhibition_id == exhibition_id,
                ExpoVisitorSummarySend.visitor_email == email,
            ).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _send_for_exhibition(
    db,
    *,
    exhibition: ExpoExhibition,
    tz: ZoneInfo,
    summary_date: str,
    is_final: bool,
    day_filter,
) -> int:
    leads = (
        db.execute(
            select(ExpoLead).where(
                ExpoLead.exhibition_id == exhibition.id,
                ExpoLead.visitor_email.isnot(None),
            )
        )
        .scalars()
        .all()
    )
    by_email: dict[str, list[ExpoLead]] = {}
    for lead in leads:
        email = str(lead.visitor_email or "").strip().lower()
        if not email or "@" not in email or email.endswith("@expo.local"):
            continue
        if day_filter is not None:
            visit_day = _lead_local_date(lead.created_at, tz)
            if visit_day is None or visit_day != day_filter:
                continue
        by_email.setdefault(email, []).append(lead)

    sent = 0
    for email, email_leads in by_email.items():
        if _visitor_summary_already_sent(db, exhibition_id=exhibition.id, visitor_email=email):
            continue
        stands: list[dict[str, Any]] = []
        first_name = "there"
        seen_booths: set[str] = set()
        for lead in email_leads:
            if lead.booth_id in seen_booths:
                continue
            booth = db.get(ExpoBooth, lead.booth_id)
            if booth is None or getattr(booth, "is_preview_draft", False):
                continue
            seen_booths.add(lead.booth_id)
            stands.append(_stand_row(db, lead, booth))
            if lead.name:
                first_name = str(lead.name).split()[0]
        if not stands:
            continue
        variables = ExpoEmailService.build_day_summary_variables(
            first_name=first_name,
            exhibition_name=exhibition.name or "the exhibition",
            venue=str(exhibition.venue or ""),
            summary_date=summary_date,
            is_final=is_final,
            stands=stands,
        )
        ok = ExpoEmailService.send_visitor_day_summary(db, to_email=email, variables=variables)
        if ok:
            db.add(
                ExpoVisitorSummarySend(
                    id=str(uuid.uuid4()),
                    exhibition_id=exhibition.id,
                    visitor_email=email,  # already lowercased
                    summary_date=summary_date,
                    is_final=is_final,
                    sent_at=datetime.utcnow(),
                )
            )
            db.flush()
            sent += 1
    return sent
