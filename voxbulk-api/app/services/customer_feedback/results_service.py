"""Customer Feedback results and analytics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackLocation, FeedbackResponse, FeedbackSession, FeedbackSurveyType
from app.services.customer_feedback.location_service import location_to_dict


class FeedbackResultsService:
    @staticmethod
    def customer_results(
        db: Session,
        org_id: str,
        *,
        location_id: str | None = None,
        survey_type_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> dict[str, Any]:
        loc_q = select(FeedbackLocation).where(FeedbackLocation.org_id == org_id)
        locations = list(db.execute(loc_q.order_by(FeedbackLocation.name)).scalars().all())
        resp_q = select(FeedbackResponse).where(FeedbackResponse.org_id == org_id)
        sess_q = select(FeedbackSession).where(FeedbackSession.org_id == org_id)
        if location_id:
            resp_q = resp_q.where(FeedbackResponse.location_id == location_id)
            sess_q = sess_q.where(FeedbackSession.location_id == location_id)
        if survey_type_id:
            resp_q = resp_q.where(FeedbackResponse.survey_type_id == survey_type_id)
        if date_from:
            resp_q = resp_q.where(FeedbackResponse.created_at >= date_from)
            sess_q = sess_q.where(FeedbackSession.started_at >= date_from)
        if date_to:
            resp_q = resp_q.where(FeedbackResponse.created_at <= date_to)
            sess_q = sess_q.where(FeedbackSession.started_at <= date_to)

        responses = list(db.execute(resp_q.order_by(FeedbackResponse.created_at.desc()).limit(500)).scalars().all())
        sessions = list(db.execute(sess_q).scalars().all())
        completed = sum(1 for s in sessions if str(s.status) == "completed")
        rows = []
        for r in responses:
            loc = db.get(FeedbackLocation, r.location_id)
            st = db.get(FeedbackSurveyType, r.survey_type_id)
            rows.append(
                {
                    "id": r.id,
                    "location_id": r.location_id,
                    "location_name": loc.name if loc else None,
                    "survey_type_id": r.survey_type_id,
                    "survey_type_name": st.name if st else None,
                    "question_key": r.question_key,
                    "answer_text": r.answer_text_en or r.answer_text,
                    "original_text": r.original_text,
                    "visitor_language": getattr(
                        db.get(FeedbackSession, r.session_id), "detected_language", None
                    ),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return {
            "ok": True,
            "locations": [location_to_dict(db, loc) for loc in locations],
            "summary": {
                "sessions": len(sessions),
                "completed_sessions": completed,
                "responses": len(responses),
                "total_scans": sum(int(loc.scan_count or 0) for loc in locations),
            },
            "rows": rows,
        }

    @staticmethod
    def admin_results(
        db: Session,
        *,
        org_id: str | None = None,
        location_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        q = select(FeedbackResponse).order_by(FeedbackResponse.created_at.desc()).limit(limit)
        if org_id:
            q = q.where(FeedbackResponse.org_id == org_id)
        if location_id:
            q = q.where(FeedbackResponse.location_id == location_id)
        responses = list(db.execute(q).scalars().all())
        rows = []
        for r in responses:
            loc = db.get(FeedbackLocation, r.location_id)
            rows.append(
                {
                    "id": r.id,
                    "org_id": r.org_id,
                    "location_id": r.location_id,
                    "location_name": loc.name if loc else None,
                    "question_key": r.question_key,
                    "answer_text": r.answer_text_en or r.answer_text,
                    "original_text": r.original_text,
                    "visitor_language": getattr(
                        db.get(FeedbackSession, r.session_id), "detected_language", None
                    ),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return {"ok": True, "rows": rows, "count": len(rows)}
