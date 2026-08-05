"""Smart Card QR leads list + KPI summary."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.smart_card import (
    SmartCardLead,
    SmartCardQuestionTemplate,
    SmartCardRepresentative,
    SmartCardResponse,
    SmartCardSession,
    SmartCardVoiceNoteJob,
)
from app.services.org_rbac import OrgRbacService, can_view_all_campaigns
from app.services.smart_card.company_service import SmartCardEntitlementService

UK = ZoneInfo("Europe/London")
_REPO_ROOT = Path(__file__).resolve().parents[3]


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
    def _assert_rep_allowed(scope: list[str] | None, representative_id: str | None) -> None:
        if scope is None:
            return
        rid = str(representative_id or "").strip()
        if not rid or rid not in scope:
            raise SmartCardResultsError("Lead not found")

    @staticmethod
    def _lead_row(db: Session, lead: SmartCardLead) -> dict[str, Any]:
        rep = db.get(SmartCardRepresentative, lead.representative_id)
        consent = str(lead.consent or "").strip().lower()
        catalogue_requested = bool(consent) and consent not in {"no", "n", "false", "0", "no thanks"}
        products: list[str] = []
        if lead.assets_sent_json:
            try:
                parsed = json.loads(lead.assets_sent_json)
                if isinstance(parsed, dict):
                    products = [
                        str(p.get("name") or "").strip()
                        for p in (parsed.get("products") or [])
                        if isinstance(p, dict) and str(p.get("name") or "").strip()
                    ]
            except (TypeError, ValueError):
                products = []
        if products:
            catalogue_requested = True
        return {
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
            "catalogue_requested": catalogue_requested,
            "catalogue_products": products,
            "business_card_url": (
                f"/smart-card/results/leads/{lead.id}/card-image" if lead.business_card_path else None
            ),
            "created_at": lead.created_at.isoformat() if lead.created_at else None,
        }

    @staticmethod
    def list_leads(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        representative_id: str | None = None,
    ) -> list[dict[str, Any]]:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        stmt = select(SmartCardLead).where(SmartCardLead.org_id == org_id)
        if scope is not None:
            if not scope:
                return []
            stmt = stmt.where(SmartCardLead.representative_id.in_(scope))
        rid = str(representative_id or "").strip() or None
        if rid:
            if scope is not None and rid not in scope:
                return []
            stmt = stmt.where(SmartCardLead.representative_id == rid)
        # Include preview test leads (tagged) so dashboard testing is visible.
        stmt = stmt.order_by(SmartCardLead.created_at.desc()).limit(500)
        leads = db.execute(stmt).scalars().all()
        preview_session_ids: set[str] = set()
        session_ids = [str(L.session_id) for L in leads if L.session_id]
        if session_ids:
            preview_session_ids = {
                str(s.id)
                for s in db.execute(
                    select(SmartCardSession).where(
                        SmartCardSession.id.in_(session_ids),
                        SmartCardSession.is_preview.is_(True),
                    )
                )
                .scalars()
                .all()
            }
        out = []
        for lead in leads:
            row = SmartCardResultsService._lead_row(db, lead)
            row["is_preview"] = bool(lead.session_id and str(lead.session_id) in preview_session_ids)
            out.append(row)
        return out

    @staticmethod
    def get_lead(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        lead_id: str,
    ) -> dict[str, Any]:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        lead = db.execute(
            select(SmartCardLead).where(SmartCardLead.id == lead_id, SmartCardLead.org_id == org_id)
        ).scalar_one_or_none()
        if lead is None:
            raise SmartCardResultsError("Lead not found")
        SmartCardResultsService._assert_rep_allowed(scope, lead.representative_id)
        data = SmartCardResultsService._lead_row(db, lead)
        is_preview = False
        if lead.session_id:
            sess = db.get(SmartCardSession, lead.session_id)
            is_preview = bool(sess and sess.is_preview)
        data["is_preview"] = is_preview
        data["answers"] = SmartCardResultsService._answers_for_session(
            db, org_id=org_id, session_id=lead.session_id
        )
        return data

    @staticmethod
    def _question_labels(db: Session) -> tuple[dict[str, str], dict[str, str]]:
        labels = {
            "contact": "Contact",
            "contact_web": "Contact",
            "contact_manual": "Contact",
            "contact_card_only": "Business card",
            "interest": "Interest",
            "role": "Role",
            "timeline": "Buying timeline",
            "follow_up": "Follow-up",
            "consent_info": "Consent",
            "open_feedback": "Anything else",
        }
        prompts = dict(labels)
        try:
            rows = db.execute(select(SmartCardQuestionTemplate)).scalars().all()
            for row in rows:
                key = str(row.question_key or "").strip()
                if not key:
                    continue
                label = str(row.label or "").strip()
                prompt = str(row.prompt or "").strip()
                if label:
                    labels[key] = label
                if prompt:
                    prompts[key] = prompt
        except Exception:
            pass
        return labels, prompts

    @staticmethod
    def _answers_for_session(db: Session, *, org_id: str, session_id: str | None) -> list[dict[str, Any]]:
        if not session_id:
            return []
        rows = (
            db.execute(
                select(SmartCardResponse)
                .where(
                    SmartCardResponse.session_id == session_id,
                    SmartCardResponse.org_id == org_id,
                )
                .order_by(SmartCardResponse.created_at.asc())
            )
            .scalars()
            .all()
        )
        labels, prompts = SmartCardResultsService._question_labels(db)
        jobs = {
            str(j.id): j
            for j in db.execute(
                select(SmartCardVoiceNoteJob).where(
                    SmartCardVoiceNoteJob.org_id == org_id,
                    SmartCardVoiceNoteJob.session_id == session_id,
                )
            )
            .scalars()
            .all()
        }
        # Fallback: match unused completed jobs with storage to voice answers missing voice_job_id
        unused_jobs = [
            j
            for j in jobs.values()
            if str(j.status or "") == "completed" and str(j.storage_path or "").strip()
        ]
        used_job_ids = {
            str(getattr(r, "voice_job_id", None) or "").strip()
            for r in rows
            if getattr(r, "voice_job_id", None)
        }
        unused_jobs = [j for j in unused_jobs if str(j.id) not in used_job_ids]

        answers: list[dict[str, Any]] = []
        for r in rows:
            key = str(r.question_key or "")
            src = str(getattr(r, "answer_source", None) or "text").strip().lower() or "text"
            job_id = str(getattr(r, "voice_job_id", None) or "").strip() or None
            original = str(getattr(r, "original_text", None) or r.answer_text or "").strip() or None
            english = str(getattr(r, "answer_text_en", None) or "").strip() or None
            if src == "voice" and not job_id and unused_jobs:
                # Heuristic: attach next unused job whose transcript matches original/answer
                matched = None
                for j in unused_jobs:
                    tr = str(j.transcript or "").strip()
                    if tr and (
                        tr == (original or "")
                        or tr == str(r.answer_text or "").strip()
                        or tr == (english or "")
                    ):
                        matched = j
                        break
                if matched is None and unused_jobs:
                    matched = unused_jobs[0]
                if matched is not None:
                    job_id = str(matched.id)
                    unused_jobs = [j for j in unused_jobs if j.id != matched.id]
                    if not original and matched.transcript:
                        original = str(matched.transcript).strip()
            audio_url = None
            detected_language = None
            low_confidence = False
            if src == "voice" and job_id:
                job = jobs.get(job_id)
                if job:
                    if str(job.storage_path or "").strip():
                        audio_url = f"/smart-card/results/voice-notes/{job_id}/audio"
                    detected_language = str(getattr(job, "detected_language", None) or "") or None
                    low_confidence = bool(getattr(job, "low_confidence", False))
            answers.append(
                {
                    "question_key": key,
                    "question_label": labels.get(key, key.replace("_", " ").title()),
                    "question_prompt": prompts.get(key) or labels.get(key) or key,
                    "answer_text": r.answer_text,
                    "original_text": original,
                    "answer_text_en": english or r.answer_text,
                    "answer_source": src,
                    "audio_url": audio_url,
                    "detected_language": detected_language,
                    "low_confidence": low_confidence,
                }
            )
        return answers

    @staticmethod
    def resolve_voice_audio_path(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        job_id: str,
    ) -> Path | None:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        job = db.execute(
            select(SmartCardVoiceNoteJob).where(
                SmartCardVoiceNoteJob.id == job_id,
                SmartCardVoiceNoteJob.org_id == org_id,
            )
        ).scalar_one_or_none()
        if job is None or not str(job.storage_path or "").strip():
            return None
        session = db.get(SmartCardSession, job.session_id)
        if session is None or session.org_id != org_id:
            return None
        if scope is not None and str(session.representative_id) not in scope:
            return None
        rel = str(job.storage_path).strip().replace("\\", "/")
        if ".." in rel.split("/"):
            return None
        abs_path = (_REPO_ROOT / rel).resolve()
        try:
            abs_path.relative_to((_REPO_ROOT / "data").resolve())
        except ValueError:
            return None
        return abs_path if abs_path.is_file() else None

    @staticmethod
    def resolve_lead_card_path(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        lead_id: str,
    ) -> Path | None:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        lead = db.execute(
            select(SmartCardLead).where(SmartCardLead.id == lead_id, SmartCardLead.org_id == org_id)
        ).scalar_one_or_none()
        if lead is None or not lead.business_card_path:
            return None
        SmartCardResultsService._assert_rep_allowed(scope, lead.representative_id)
        rel = str(lead.business_card_path).strip().replace("\\", "/")
        if ".." in rel.split("/"):
            return None
        abs_path = (_REPO_ROOT / rel).resolve()
        try:
            abs_path.relative_to((_REPO_ROOT / "data").resolve())
        except ValueError:
            return None
        return abs_path if abs_path.is_file() else None

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
        SmartCardResultsService._assert_rep_allowed(scope, lead.representative_id)
        if "follow_up_status" in payload:
            st = str(payload.get("follow_up_status") or "").strip().lower()
            if st in {"open", "done", "ignored"}:
                lead.follow_up_status = st
        lead.updated_at = datetime.utcnow()
        db.add(lead)
        db.flush()
        return SmartCardResultsService.get_lead(db, org_id=org_id, user_id=user_id, lead_id=lead_id)

    @staticmethod
    def customer_summary(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        representative_id: str | None = None,
    ) -> dict[str, Any]:
        scope = SmartCardResultsService._rep_scope(db, org_id=org_id, user_id=user_id)
        rid = str(representative_id or "").strip() or None
        if rid and scope is not None and rid not in scope:
            rid = None

        now_uk = datetime.now(UK)
        today_start = datetime(now_uk.year, now_uk.month, now_uk.day)
        week_start = today_start - timedelta(days=6)
        month_start = today_start.replace(day=1)

        def _lead_q():
            q = select(SmartCardLead).where(SmartCardLead.org_id == org_id)
            if scope is not None:
                if not scope:
                    return None
                q = q.where(SmartCardLead.representative_id.in_(scope))
            if rid:
                q = q.where(SmartCardLead.representative_id == rid)
            return q

        base = _lead_q()
        if base is None:
            leads: list[SmartCardLead] = []
        else:
            leads = list(db.execute(base).scalars().all())

        # Include preview test leads in KPIs so dashboard testing is visible.
        def _in_range(dt: datetime | None, start: datetime, end: datetime | None = None) -> bool:
            if dt is None:
                return False
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            if dt < start:
                return False
            if end is not None and dt >= end:
                return False
            return True

        empty = {
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
            "by_representative": [],
            "seat_quantity": SmartCardEntitlementService.seat_quantity(db, org_id),
            "active_reps": 0,
            "mode": SmartCardEntitlementService.access_mode(db, org_id),
        }

        scans_q = select(func.coalesce(func.sum(SmartCardRepresentative.scan_count), 0)).where(
            SmartCardRepresentative.org_id == org_id
        )
        if scope is not None:
            if not scope:
                return empty
            scans_q = scans_q.where(SmartCardRepresentative.id.in_(scope))
        if rid:
            scans_q = scans_q.where(SmartCardRepresentative.id == rid)
        scans_total = int(db.execute(scans_q).scalar() or 0)

        sess_today = select(func.count()).select_from(SmartCardSession).where(
            SmartCardSession.org_id == org_id,
            SmartCardSession.created_at >= today_start,
        )
        if scope is not None:
            sess_today = sess_today.where(SmartCardSession.representative_id.in_(scope))
        if rid:
            sess_today = sess_today.where(SmartCardSession.representative_id == rid)
        scans_today = int(db.execute(sess_today).scalar() or 0)

        leads_today = sum(1 for L in leads if _in_range(L.created_at, today_start))
        leads_week = sum(1 for L in leads if _in_range(L.created_at, week_start))
        leads_month = sum(1 for L in leads if _in_range(L.created_at, month_start))
        hot = sum(1 for L in leads if (L.lead_score or "") == "hot")
        warm = sum(1 for L in leads if (L.lead_score or "") == "warm")
        cold = sum(1 for L in leads if (L.lead_score or "") == "cold")
        need = sum(
            1 for L in leads if (L.follow_up_status or "open") == "open" and (L.lead_score or "") == "hot"
        )

        daily = []
        for i in range(7):
            day = today_start - timedelta(days=6 - i)
            day_end = day + timedelta(days=1)
            sess_filters = [
                SmartCardSession.org_id == org_id,
                SmartCardSession.created_at >= day,
                SmartCardSession.created_at < day_end,
            ]
            if scope is not None:
                sess_filters.append(SmartCardSession.representative_id.in_(scope))
            if rid:
                sess_filters.append(SmartCardSession.representative_id == rid)
            daily.append(
                {
                    "day": day.strftime("%a"),
                    "scans": int(
                        db.execute(
                            select(func.count()).select_from(SmartCardSession).where(*sess_filters)
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

        lead_count_by_rep: dict[str, int] = {}
        for L in leads:
            key = str(L.representative_id or "")
            if not key:
                continue
            lead_count_by_rep[key] = lead_count_by_rep.get(key, 0) + 1

        reps_stmt = select(SmartCardRepresentative).where(
            SmartCardRepresentative.org_id == org_id,
            SmartCardRepresentative.status != "archived",
        )
        if scope is not None:
            reps_stmt = reps_stmt.where(SmartCardRepresentative.id.in_(scope))
        if rid:
            reps_stmt = reps_stmt.where(SmartCardRepresentative.id == rid)
        reps_stmt = reps_stmt.order_by(SmartCardRepresentative.name.asc())
        reps = list(db.execute(reps_stmt).scalars().all())
        by_representative = [
            {
                "id": r.id,
                "name": r.name,
                "scan_count": int(r.scan_count or 0),
                "lead_count": int(lead_count_by_rep.get(str(r.id), 0)),
            }
            for r in reps
        ]

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
            "by_representative": by_representative,
            "seat_quantity": SmartCardEntitlementService.seat_quantity(db, org_id),
            "active_reps": SmartCardEntitlementService.active_rep_count(db, org_id),
            "mode": SmartCardEntitlementService.access_mode(db, org_id),
        }
