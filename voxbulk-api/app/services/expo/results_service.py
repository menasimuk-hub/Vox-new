"""Expo lead results — customer dashboard summary/leads/export, and admin platform overview."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoExhibition, ExpoLead, ExpoSession

_EMPTY_SUMMARY: dict[str, Any] = {
    "ok": True,
    "scans": 0,
    "sessions_started": 0,
    "completed_leads": 0,
    "hot": 0,
    "warm": 0,
    "cold": 0,
    "offers_sent": 0,
}


class ExpoResultsService:
    @staticmethod
    def _booth_ids_for_org(
        db: Session,
        org_id: str,
        *,
        booth_id: str | None = None,
        created_by_user_id: str | None = None,
    ) -> list[str]:
        q = select(ExpoBooth.id).where(ExpoBooth.org_id == org_id)
        if booth_id:
            q = q.where(ExpoBooth.id == booth_id)
        if created_by_user_id:
            q = q.where(ExpoBooth.created_by_user_id == created_by_user_id)
        return [row[0] for row in db.execute(q).all()]

    @staticmethod
    def customer_summary(
        db: Session,
        org_id: str,
        *,
        booth_id: str | None = None,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        booth_ids = ExpoResultsService._booth_ids_for_org(
            db, org_id, booth_id=booth_id, created_by_user_id=created_by_user_id
        )
        if not booth_ids:
            return dict(_EMPTY_SUMMARY)

        scans = int(
            db.execute(
                select(func.coalesce(func.sum(ExpoBooth.scan_count), 0)).where(ExpoBooth.id.in_(booth_ids))
            ).scalar()
            or 0
        )
        sessions_started = int(
            db.execute(
                select(func.count()).select_from(ExpoSession).where(ExpoSession.booth_id.in_(booth_ids))
            ).scalar()
            or 0
        )
        leads = db.execute(select(ExpoLead).where(ExpoLead.booth_id.in_(booth_ids))).scalars().all()

        return {
            "ok": True,
            "scans": scans,
            "sessions_started": sessions_started,
            "completed_leads": sum(1 for lead in leads if lead.lead_score),
            "hot": sum(1 for lead in leads if lead.lead_score == "hot"),
            "warm": sum(1 for lead in leads if lead.lead_score == "warm"),
            "cold": sum(1 for lead in leads if lead.lead_score == "cold"),
            "offers_sent": sum(1 for lead in leads if lead.offer_sent_at is not None),
        }

    @staticmethod
    def customer_leads(
        db: Session,
        org_id: str,
        *,
        booth_id: str | None = None,
        score: str | None = None,
        created_by_user_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        booth_ids = ExpoResultsService._booth_ids_for_org(
            db, org_id, booth_id=booth_id, created_by_user_id=created_by_user_id
        )
        if not booth_ids:
            return []

        q = select(ExpoLead).where(ExpoLead.booth_id.in_(booth_ids))
        if score:
            q = q.where(ExpoLead.lead_score == str(score).strip().lower())
        capped = max(1, min(int(limit or 200), 5000))
        rows = db.execute(q.order_by(ExpoLead.created_at.desc()).limit(capped)).scalars().all()

        booths = {
            b.id: b for b in db.execute(select(ExpoBooth).where(ExpoBooth.id.in_(booth_ids))).scalars().all()
        }
        return [ExpoResultsService._lead_to_dict(lead, booths.get(lead.booth_id)) for lead in rows]

    @staticmethod
    def _lead_to_dict(lead: ExpoLead, booth: ExpoBooth | None) -> dict[str, Any]:
        try:
            assets_sent = json.loads(lead.assets_sent_json or "[]")
            if not isinstance(assets_sent, list):
                assets_sent = []
        except (json.JSONDecodeError, TypeError):
            assets_sent = []
        return {
            "id": lead.id,
            "booth_id": lead.booth_id,
            "booth_name": booth.name if booth else None,
            "exhibition_id": lead.exhibition_id,
            "name": lead.name,
            "company": lead.company,
            "visitor_phone": lead.visitor_phone,
            "visitor_email": lead.visitor_email,
            "interest": lead.interest,
            "buying_timeline": lead.buying_timeline,
            "lead_score": lead.lead_score,
            "consent_acknowledged": lead.consent_acknowledged,
            "offer_sent_at": lead.offer_sent_at.isoformat() if lead.offer_sent_at else None,
            "assets_sent": assets_sent,
            "follow_up_status": lead.follow_up_status,
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        }

    @staticmethod
    def export_csv(
        db: Session,
        org_id: str,
        *,
        booth_id: str | None = None,
        created_by_user_id: str | None = None,
    ) -> str:
        leads = ExpoResultsService.customer_leads(
            db, org_id, booth_id=booth_id, created_by_user_id=created_by_user_id, limit=5000
        )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "Name",
                "Company",
                "Phone",
                "Email",
                "Interest",
                "Timeline",
                "Score",
                "Consent",
                "Booth",
                "Assets sent",
                "Created at",
            ]
        )
        for lead in leads:
            writer.writerow(
                [
                    lead.get("name") or "",
                    lead.get("company") or "",
                    lead.get("visitor_phone") or "",
                    lead.get("visitor_email") or "",
                    lead.get("interest") or "",
                    lead.get("buying_timeline") or "",
                    lead.get("lead_score") or "",
                    "Yes" if lead.get("consent_acknowledged") else "No",
                    lead.get("booth_name") or "",
                    ", ".join(lead.get("assets_sent") or []),
                    lead.get("created_at") or "",
                ]
            )
        return buf.getvalue()

    @staticmethod
    def admin_overview(db: Session) -> dict[str, Any]:
        booths_total = int(db.execute(select(func.count()).select_from(ExpoBooth)).scalar() or 0)
        exhibitions_total = int(db.execute(select(func.count()).select_from(ExpoExhibition)).scalar() or 0)
        orgs_with_expo = int(
            db.execute(select(func.count(func.distinct(ExpoBooth.org_id)))).scalar() or 0
        )
        scans = int(db.execute(select(func.coalesce(func.sum(ExpoBooth.scan_count), 0))).scalar() or 0)
        leads_total = int(db.execute(select(func.count()).select_from(ExpoLead)).scalar() or 0)
        hot = int(
            db.execute(select(func.count()).select_from(ExpoLead).where(ExpoLead.lead_score == "hot")).scalar()
            or 0
        )
        warm = int(
            db.execute(select(func.count()).select_from(ExpoLead).where(ExpoLead.lead_score == "warm")).scalar()
            or 0
        )
        cold = int(
            db.execute(select(func.count()).select_from(ExpoLead).where(ExpoLead.lead_score == "cold")).scalar()
            or 0
        )
        return {
            "ok": True,
            "booths_total": booths_total,
            "exhibitions_total": exhibitions_total,
            "orgs_with_expo": orgs_with_expo,
            "scans": scans,
            "leads_total": leads_total,
            "hot": hot,
            "warm": warm,
            "cold": cold,
        }
