"""Smart Card QR leads list + KPI summary."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.smart_card import SmartCardLead, SmartCardRepresentative, SmartCardSession
from app.services.org_rbac import OrgRbacService, can_view_all_campaigns
from app.services.smart_card.company_service import SmartCardEntitlementService

UK = ZoneInfo("Europe/London")


class SmartCardResultsError(ValueError):
    pass


class SmartCardResultsService:
    @staticmethod
    def _rep_scope(db: Session, *, org_id: str, user_id: str) -> list[str] | None:
        """None = all reps; else list of representative ids."""
        role = OrgRbacService.role_for(db, org_id=org_id, user_id=user_id)
        if can_view_all_campaigns(role):
            return None
        rows = (
            db.execute(
                select(SmartCardRepresentative.id).where(
                    SmartCardRepresentative.org_id == org_id,
                    SmartCardRepresentative.linked_user_id == user_id,
                )
            )
            .scalars()
            .all()
        )
        return [str(x) for x in rows]

    @staticmethod
    def list_leads(db: Session, *, org_id: str, user_id: str) -> list[dict[str, Any]]:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        stmt = select(SmartCardLead).where(SmartCardLead.org_id == org_id)
        if scope is not None:
            if not scope:
                return []
            stmt = stmt.where(SmartCardLead.representative_id.in_(scope))
        stmt = stmt.order_by(SmartCardLead.created_at.desc()).limit(500)
        leads = db.execute(stmt).scalars().all()
        out = []
        for lead in leads:
            rep = db.get(SmartCardRepresentative, lead.representative_id)
            out.append(
                {
                    "id": lead.id,
                    "representative_id": lead.representative_id,
                    "representative_name": rep.name if rep else None,
                    "name": lead.name,
                    "company": lead.company,
                    "visitor_phone": lead.visitor_phone,
                    "visitor_email": lead.visitor_email,
                    "interest": lead.interest,
                    "buying_timeline": lead.buying_timeline,
                    "lead_score": lead.lead_score,
                    "ai_summary": lead.ai_summary,
                    "suggested_follow_up": lead.suggested_follow_up,
                    "follow_up_status": lead.follow_up_status,
                    "channel": lead.channel,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                }
            )
        return out

    @staticmethod
    def update_lead(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        lead_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        lead = db.execute(
            select(SmartCardLead).where(SmartCardLead.id == lead_id, SmartCardLead.org_id == org_id)
        ).scalar_one_or_none()
        if lead is None:
            raise SmartCardResultsError("Lead not found")
        if scope is not None and lead.representative_id not in scope:
            raise SmartCardResultsError("Lead not found")
        if "follow_up_status" in payload:
            st = str(payload.get("follow_up_status") or "").strip().lower()
            if st in {"open", "done", "ignored"}:
                lead.follow_up_status = st
        lead.updated_at = datetime.utcnow()
        db.add(lead)
        db.flush()
        items = SmartCardResultsService.list_leads(db, org_id=org_id, user_id=user_id)
        return next((x for x in items if x["id"] == lead_id), {"id": lead_id})

    @staticmethod
    def customer_summary(db: Session, *, org_id: str, user_id: str) -> dict[str, Any]:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        now_uk = datetime.now(UK)
        today_start = datetime(now_uk.year, now_uk.month, now_uk.day)
        yesterday_start = today_start - timedelta(days=1)
        week_start = today_start - timedelta(days=6)
        month_start = today_start.replace(day=1)

        def _lead_q():
            q = select(SmartCardLead).where(SmartCardLead.org_id == org_id)
            if scope is not None:
                if not scope:
                    return None
                q = q.where(SmartCardLead.representative_id.in_(scope))
            return q

        base = _lead_q()
        if base is None:
            leads: list[SmartCardLead] = []
        else:
            leads = list(db.execute(base).scalars().all())

        def _in_range(dt: datetime | None, start: datetime, end: datetime | None = None) -> bool:
            if dt is None:
                return False
            # store UTC naive; compare as naive UK midnight approx
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            if dt < start:
                return False
            if end is not None and dt >= end:
                return False
            return True

        scans_q = select(func.coalesce(func.sum(SmartCardRepresentative.scan_count), 0)).where(
            SmartCardRepresentative.org_id == org_id
        )
        if scope is not None:
            if scope:
                scans_q = scans_q.where(SmartCardRepresentative.id.in_(scope))
            else:
                scans_total = 0
                return {
                    "scans": 0,
                    "scans_today": 0,
                    "leads": 0,
                    "leads_today": 0,
                    "hot": 0,
                    "warm": 0,
                    "cold": 0,
                    "need_follow_up": 0,
                    "leads_this_week": 0,
                    "leads_this_month": 0,
                    "daily": [],
                    "seat_quantity": SmartCardEntitlementService.seat_quantity(db, org_id),
                    "active_reps": 0,
                    "mode": SmartCardEntitlementService.access_mode(db, org_id),
                }
        scans_total = int(db.execute(scans_q).scalar() or 0)

        sess_today = select(func.count()).select_from(SmartCardSession).where(
            SmartCardSession.org_id == org_id,
            SmartCardSession.created_at >= yesterday_start,  # rough
        )
        # Better: UK day boundaries as naive UTC approx
        sess_today = select(func.count()).select_from(SmartCardSession).where(
            SmartCardSession.org_id == org_id,
            SmartCardSession.created_at >= today_start,
        )
        if scope is not None:
            sess_today = sess_today.where(SmartCardSession.representative_id.in_(scope))
        scans_today = int(db.execute(sess_today).scalar() or 0)

        leads_today = sum(1 for L in leads if _in_range(L.created_at, today_start))
        leads_week = sum(1 for L in leads if _in_range(L.created_at, week_start))
        leads_month = sum(1 for L in leads if _in_range(L.created_at, month_start))
        hot = sum(1 for L in leads if (L.lead_score or "") == "hot")
        warm = sum(1 for L in leads if (L.lead_score or "") == "warm")
        cold = sum(1 for L in leads if (L.lead_score or "") == "cold")
        need = sum(1 for L in leads if (L.follow_up_status or "open") == "open" and (L.lead_score or "") == "hot")

        daily = []
        for i in range(7):
            day = today_start - timedelta(days=6 - i)
            day_end = day + timedelta(days=1)
            daily.append(
                {
                    "day": day.strftime("%a"),
                    "scans": int(
                        db.execute(
                            select(func.count())
                            .select_from(SmartCardSession)
                            .where(
                                SmartCardSession.org_id == org_id,
                                SmartCardSession.created_at >= day,
                                SmartCardSession.created_at < day_end,
                                *(
                                    [SmartCardSession.representative_id.in_(scope)]
                                    if scope is not None
                                    else []
                                ),
                            )
                        ).scalar()
                        or 0
                    ),
                    "leads": sum(1 for L in leads if _in_range(L.created_at, day, day_end)),
                    "hot": sum(
                        1
                        for L in leads
                        if _in_range(L.created_at, day, day_end) and (L.lead_score or "") == "hot"
                    ),
                }
            )

        return {
            "scans": scans_total,
            "scans_today": scans_today,
            "leads": len(leads),
            "leads_today": leads_today,
            "leads_this_week": leads_week,
            "leads_this_month": leads_month,
            "hot": hot,
            "warm": warm,
            "cold": cold,
            "need_follow_up": need,
            "daily": daily,
            "seat_quantity": SmartCardEntitlementService.seat_quantity(db, org_id),
            "active_reps": SmartCardEntitlementService.active_rep_count(db, org_id),
            "mode": SmartCardEntitlementService.access_mode(db, org_id),
        }
