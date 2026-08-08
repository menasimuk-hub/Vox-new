"""Public Smart Card engagement events (clicks, file opens) for KPIs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardEngagementEvent, SmartCardRepresentative

logger = logging.getLogger(__name__)

ALLOWED_EVENT_TYPES = frozenset(
    {
        "social_instagram",
        "social_linkedin",
        "social_facebook",
        "social_x",
        "social_tiktok",
        "website",
        "tel",
        "mailto",
        "maps",
        "save_contact",
        "whatsapp",
        "share",
        "web_survey",
        "file_open",
    }
)

# Soft rate limit: max events per token (rep) in a short window
_RATE_WINDOW_SEC = 60
_RATE_MAX = 40


class SmartCardEngagementError(ValueError):
    pass


class SmartCardEngagementService:
    @staticmethod
    def normalize_event_type(raw: str | None) -> str:
        v = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "instagram": "social_instagram",
            "linkedin": "social_linkedin",
            "facebook": "social_facebook",
            "twitter": "social_x",
            "x": "social_x",
            "tiktok": "social_tiktok",
            "phone": "tel",
            "call": "tel",
            "email": "mailto",
            "vcf": "save_contact",
            "contact": "save_contact",
            "wa": "whatsapp",
        }
        v = aliases.get(v, v)
        if v not in ALLOWED_EVENT_TYPES:
            raise SmartCardEngagementError("Unsupported event type")
        return v

    @staticmethod
    def record(
        db: Session,
        *,
        rep: SmartCardRepresentative,
        event_type: str,
        lead_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> SmartCardEngagementEvent:
        et = SmartCardEngagementService.normalize_event_type(event_type)
        since = datetime.utcnow() - timedelta(seconds=_RATE_WINDOW_SEC)
        recent = int(
            db.execute(
                select(func.count())
                .select_from(SmartCardEngagementEvent)
                .where(
                    SmartCardEngagementEvent.representative_id == rep.id,
                    SmartCardEngagementEvent.created_at >= since,
                )
            ).scalar()
            or 0
        )
        if recent >= _RATE_MAX:
            raise SmartCardEngagementError("Too many events — try again shortly")

        row = SmartCardEngagementEvent(
            org_id=rep.org_id,
            representative_id=rep.id,
            lead_id=(str(lead_id).strip() or None) if lead_id else None,
            event_type=et,
            meta_json=json.dumps(meta) if meta else None,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def counts_for(
        db: Session,
        *,
        org_id: str,
        representative_ids: list[str] | None = None,
    ) -> dict[str, int]:
        stmt = (
            select(SmartCardEngagementEvent.event_type, func.count())
            .where(SmartCardEngagementEvent.org_id == org_id)
            .group_by(SmartCardEngagementEvent.event_type)
        )
        if representative_ids is not None:
            if not representative_ids:
                return {}
            stmt = stmt.where(SmartCardEngagementEvent.representative_id.in_(representative_ids))
        rows = db.execute(stmt).all()
        return {str(et): int(n or 0) for et, n in rows}

    @staticmethod
    def engagement_summary(counts: dict[str, int]) -> dict[str, Any]:
        social = sum(
            counts.get(k, 0)
            for k in (
                "social_instagram",
                "social_linkedin",
                "social_facebook",
                "social_x",
                "social_tiktok",
            )
        )
        return {
            "social_clicks": social,
            "website_clicks": int(counts.get("website", 0)),
            "tel_clicks": int(counts.get("tel", 0)),
            "mailto_clicks": int(counts.get("mailto", 0)),
            "save_contact": int(counts.get("save_contact", 0)),
            "whatsapp_clicks": int(counts.get("whatsapp", 0)),
            "share_clicks": int(counts.get("share", 0)),
            "file_opens": int(counts.get("file_open", 0)),
            "maps_clicks": int(counts.get("maps", 0)),
            "web_survey_clicks": int(counts.get("web_survey", 0)),
            "engagement_total": int(sum(counts.values())),
            "by_type": dict(counts),
        }
