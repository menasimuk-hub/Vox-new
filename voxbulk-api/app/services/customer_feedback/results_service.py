"""Customer Feedback results and analytics."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    FeedbackLocation,
    FeedbackResponse,
    FeedbackSession,
    FeedbackSurveyType,
)
from app.services.customer_feedback.feedback_results_aggregate import (
    build_aggregates,
    build_open_comments,
    build_respondents,
    build_weekly_trend,
    compute_summary,
    load_template_index,
    survey_types_for_locations,
    template_meta,
)
from app.services.customer_feedback.feedback_results_export import (
    build_feedback_results_csv,
    build_feedback_results_pdf,
)
from app.services.customer_feedback.feedback_insights_service import FeedbackInsightsService
from app.services.customer_feedback.location_service import location_to_dict

_UK = ZoneInfo("Europe/London")


def resolve_feedback_results_window(
    *,
    period: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Return naive UTC bounds for results queries (matches stored DateTime.utcnow columns)."""

    def _parse_day(raw: str | None) -> date | None:
        text = str(raw or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _start_of_day_utc(d: date) -> datetime:
        return datetime.combine(d, time.min, tzinfo=_UK).astimezone(timezone.utc).replace(tzinfo=None)

    def _end_of_day_utc(d: date) -> datetime:
        return datetime.combine(d, time.max, tzinfo=_UK).astimezone(timezone.utc).replace(tzinfo=None)

    from_day = _parse_day(date_from)
    to_day = _parse_day(date_to)
    if from_day or to_day:
        start = _start_of_day_utc(from_day) if from_day else None
        end = _end_of_day_utc(to_day) if to_day else None
        return start, end

    key = str(period or "").strip().lower().replace("-", "_")
    if key in {"", "all", "all_time"}:
        return None, None

    now_uk = datetime.now(_UK)
    today = now_uk.date()
    if key == "this_week":
        monday = today - timedelta(days=today.weekday())
        return _start_of_day_utc(monday), None
    if key == "last_7_days":
        return _start_of_day_utc(today - timedelta(days=6)), _end_of_day_utc(today)
    if key == "last_14_days":
        return _start_of_day_utc(today - timedelta(days=13)), _end_of_day_utc(today)
    if key == "last_30_days":
        return _start_of_day_utc(today - timedelta(days=29)), _end_of_day_utc(today)
    if key == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        last_sunday = this_monday - timedelta(days=1)
        return _start_of_day_utc(last_monday), _end_of_day_utc(last_sunday)
    return None, None


class FeedbackResultsService:
    @staticmethod
    def _load_scoped_data(
        db: Session,
        org_id: str,
        *,
        location_id: str | None = None,
        survey_type_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        response_limit: int = 5000,
        row_limit: int = 500,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        loc_q = select(FeedbackLocation).where(FeedbackLocation.org_id == org_id)
        if created_by_user_id:
            loc_q = loc_q.where(FeedbackLocation.created_by_user_id == created_by_user_id)
        if location_id:
            loc_q = loc_q.where(FeedbackLocation.id == location_id)
        locations = list(db.execute(loc_q.order_by(FeedbackLocation.name)).scalars().all())
        location_ids = {loc.id for loc in locations}

        resp_q = select(FeedbackResponse).where(FeedbackResponse.org_id == org_id)
        sess_q = select(FeedbackSession).where(FeedbackSession.org_id == org_id)
        if location_id:
            resp_q = resp_q.where(FeedbackResponse.location_id == location_id)
            sess_q = sess_q.where(FeedbackSession.location_id == location_id)
        elif location_ids:
            resp_q = resp_q.where(FeedbackResponse.location_id.in_(location_ids))
            sess_q = sess_q.where(FeedbackSession.location_id.in_(location_ids))
        if survey_type_id:
            resp_q = resp_q.where(FeedbackResponse.survey_type_id == survey_type_id)
        if date_from:
            resp_q = resp_q.where(FeedbackResponse.created_at >= date_from)
            sess_q = sess_q.where(FeedbackSession.started_at >= date_from)
        if date_to:
            resp_q = resp_q.where(FeedbackResponse.created_at <= date_to)
            sess_q = sess_q.where(FeedbackSession.started_at <= date_to)

        all_responses = list(
            db.execute(resp_q.order_by(FeedbackResponse.created_at.desc()).limit(response_limit)).scalars().all()
        )
        sessions = list(db.execute(sess_q).scalars().all())
        sessions_by_id = {s.id: s for s in sessions}
        locations_by_id = {loc.id: loc for loc in locations}
        survey_type_ids = {str(r.survey_type_id) for r in all_responses}
        survey_type_ids.update(str(loc.survey_type_id) for loc in locations)
        templates = load_template_index(db, survey_type_ids=survey_type_ids)

        responses_by_session: dict[str, list[FeedbackResponse]] = {}
        for resp in all_responses:
            responses_by_session.setdefault(resp.session_id, []).append(resp)

        from app.services.customer_feedback.feedback_voice_note_service import (
            attach_voice_fields,
            jobs_by_response_ids,
        )

        voice_jobs = jobs_by_response_ids(
            db,
            org_id=org_id,
            response_ids=[str(r.id) for r in all_responses],
        )

        table_rows = all_responses[:row_limit]
        flat_rows = []
        for r in table_rows:
            loc = locations_by_id.get(r.location_id)
            st = db.get(FeedbackSurveyType, r.survey_type_id)
            sess = sessions_by_id.get(r.session_id)
            question_label, _ = template_meta(
                templates,
                survey_type_id=str(r.survey_type_id),
                question_key=str(r.question_key),
            )
            row = {
                "id": r.id,
                "session_id": r.session_id,
                "location_id": r.location_id,
                "location_name": loc.name if loc else None,
                "survey_type_id": r.survey_type_id,
                "survey_type_name": st.name if st else None,
                "question_key": r.question_key,
                "question": question_label,
                "answer_text": r.answer_text_en or r.answer_text,
                "original_text": r.original_text,
                "answer_text_en": r.answer_text_en or r.answer_text,
                "translated_text": r.answer_text_en or r.answer_text,
                "translation_status": getattr(r, "translation_status", None),
                "transcription_status": getattr(r, "transcription_status", None),
                "detected_language": getattr(r, "detected_language", None),
                "answer_source": getattr(r, "answer_source", None) or "text",
                "visitor_phone": sess.visitor_phone if sess else None,
                "visitor_language": getattr(sess, "detected_language", None) if sess else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            if str(row["answer_source"]).lower() in {"voice", "voice_note"}:
                attach_voice_fields(row, response_id=str(r.id), jobs=voice_jobs)
            flat_rows.append(row)

        aggregates = build_aggregates(all_responses, templates)
        respondents = build_respondents(
            sessions,
            responses_by_session,
            templates,
            locations_by_id,
            voice_jobs_by_response=voice_jobs,
        )
        from app.services.customer_feedback.feedback_ai_followup_service import (
            attach_ai_followup_to_feedback_respondents,
        )

        respondents = attach_ai_followup_to_feedback_respondents(db, respondents)
        summary = compute_summary(
            sessions=sessions,
            responses=all_responses,
            locations=locations,
            respondents=respondents,
            location_id=location_id,
        )
        weekly_trend = build_weekly_trend(sessions, responses_by_session)
        open_comments = build_open_comments(
            all_responses,
            templates,
            themes=[],
            voice_jobs_by_response=voice_jobs,
        )

        return {
            "locations": locations,
            "locations_by_id": locations_by_id,
            "sessions": sessions,
            "all_responses": all_responses,
            "aggregates": aggregates,
            "respondents": respondents,
            "summary": summary,
            "weekly_trend": weekly_trend,
            "open_comments": open_comments,
            "templates": templates,
            "rows": flat_rows,
            "survey_types": survey_types_for_locations(db, locations),
            "voice_jobs_by_response": voice_jobs,
        }

    @staticmethod
    def customer_results(
        db: Session,
        org_id: str,
        *,
        location_id: str | None = None,
        survey_type_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        data = FeedbackResultsService._load_scoped_data(
            db,
            org_id,
            location_id=location_id,
            survey_type_id=survey_type_id,
            date_from=date_from,
            date_to=date_to,
            created_by_user_id=created_by_user_id,
        )
        loc = data["locations_by_id"].get(location_id) if location_id else None
        return {
            "ok": True,
            "location_name": loc.name if loc else None,
            "locations": [location_to_dict(db, loc) for loc in data["locations"]],
            "survey_types": data["survey_types"],
            "summary": data["summary"],
            "aggregates": data["aggregates"],
            "weekly_trend": data["weekly_trend"],
            "respondents": data["respondents"],
            "open_comments": data["open_comments"],
            "rows": data["rows"],
        }

    @staticmethod
    def customer_insights(
        db: Session,
        org_id: str,
        *,
        location_id: str | None = None,
        survey_type_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        force: bool = False,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        data = FeedbackResultsService._load_scoped_data(
            db,
            org_id,
            location_id=location_id,
            survey_type_id=survey_type_id,
            date_from=date_from,
            date_to=date_to,
            created_by_user_id=created_by_user_id,
        )
        voice_jobs = data.get("voice_jobs_by_response") or {}
        open_comments = build_open_comments(
            data["all_responses"],
            data["templates"],
            themes=[],
            voice_jobs_by_response=voice_jobs,
        )
        ai = FeedbackInsightsService.get_or_generate(
            db,
            org_id,
            location_id=location_id,
            summary=data["summary"],
            aggregates=data["aggregates"],
            open_comments=open_comments,
            force=force,
        )
        if ai.get("themes"):
            open_comments = build_open_comments(
                data["all_responses"],
                data["templates"],
                themes=ai.get("themes") if isinstance(ai.get("themes"), list) else [],
                voice_jobs_by_response=voice_jobs,
            )
        return {"ok": True, "ai": ai, "open_comments": open_comments}

    @staticmethod
    def resolve_voice_audio_path(db: Session, *, org_id: str, job_id: str):
        from app.services.customer_feedback.feedback_voice_note_service import resolve_voice_audio_path as _resolve

        return _resolve(db, org_id=org_id, job_id=job_id)

    @staticmethod
    def export_payload(
        db: Session,
        org_id: str,
        *,
        location_id: str | None = None,
        survey_type_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        include_ai: bool = True,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        results = FeedbackResultsService.customer_results(
            db,
            org_id,
            location_id=location_id,
            survey_type_id=survey_type_id,
            date_from=date_from,
            date_to=date_to,
            created_by_user_id=created_by_user_id,
        )
        if include_ai:
            insights = FeedbackResultsService.customer_insights(
                db,
                org_id,
                location_id=location_id,
                survey_type_id=survey_type_id,
                date_from=date_from,
                date_to=date_to,
                created_by_user_id=created_by_user_id,
            )
            results["ai"] = insights.get("ai")
            results["open_comments"] = insights.get("open_comments") or results.get("open_comments")
        return results

    @staticmethod
    def mark_session_opened(db: Session, org_id: str, session_id: str) -> dict[str, Any]:
        sess = db.get(FeedbackSession, session_id)
        if not sess or str(sess.org_id) != str(org_id):
            raise LookupError("Feedback session not found")
        if sess.dashboard_opened_at is None:
            sess.dashboard_opened_at = datetime.utcnow()
            db.add(sess)
            db.commit()
            db.refresh(sess)
        opened = sess.dashboard_opened_at
        return {
            "ok": True,
            "session_id": sess.id,
            "opened_at": opened.isoformat() if opened else None,
        }

    @staticmethod
    def customer_compare(
        db: Session,
        org_id: str,
        *,
        location_ids: list[str],
    ) -> dict[str, Any]:
        from app.services.customer_feedback.feedback_results_compare import compare_locations

        return compare_locations(db, org_id, location_ids)

    @staticmethod
    def export_csv(
        db: Session,
        org_id: str,
        *,
        location_id: str | None = None,
        survey_type_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        created_by_user_id: str | None = None,
    ) -> str:
        payload = FeedbackResultsService.export_payload(
            db,
            org_id,
            location_id=location_id,
            survey_type_id=survey_type_id,
            date_from=date_from,
            date_to=date_to,
            include_ai=False,
            created_by_user_id=created_by_user_id,
        )
        return build_feedback_results_csv(payload)

    @staticmethod
    def export_pdf(
        db: Session,
        org_id: str,
        *,
        location_id: str | None = None,
        survey_type_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        created_by_user_id: str | None = None,
    ) -> bytes:
        payload = FeedbackResultsService.export_payload(
            db,
            org_id,
            location_id=location_id,
            survey_type_id=survey_type_id,
            date_from=date_from,
            date_to=date_to,
            include_ai=True,
            created_by_user_id=created_by_user_id,
        )
        return build_feedback_results_pdf(payload)

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
                    "answer_text_en": r.answer_text_en or r.answer_text,
                    "translated_text": r.answer_text_en or r.answer_text,
                    "translation_status": getattr(r, "translation_status", None),
                    "transcription_status": getattr(r, "transcription_status", None),
                    "detected_language": getattr(r, "detected_language", None),
                    "visitor_language": getattr(
                        db.get(FeedbackSession, r.session_id), "detected_language", None
                    ),
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
            )
        return {"ok": True, "rows": rows, "count": len(rows)}
