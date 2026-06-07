"""Admin observability for WA Survey adaptive sessions (P6)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession, SurveySessionAnswer, SurveySessionDecision
from app.services.survey_flow_constants import RULE_AI_PICKER_FALLBACK
from app.services.survey_outcome_delivery_schema import loads_outcome_delivery
from app.services.survey_picker_settings_service import SurveyPickerSettingsService
from app.services.survey_session_service import SurveySessionService


def _decision_context(row: SurveySessionDecision) -> dict[str, Any]:
    try:
        data = json.loads(row.context_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _session_to_summary(session: SurveySession) -> dict[str, Any]:
    delivery = loads_outcome_delivery(session.outcome_delivery_json)
    return {
        "id": session.id,
        "order_id": session.order_id,
        "recipient_id": session.recipient_id,
        "org_id": session.org_id,
        "status": session.status,
        "flow_mode": session.flow_mode,
        "current_step": session.current_step,
        "current_node_key": session.current_node_key,
        "outcome_key": session.outcome_key,
        "picker_invocation_count": int(session.picker_invocation_count or 0),
        "question_visits": int(session.question_visits or 0),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "outcome_delivery": delivery,
    }


def _answer_to_dict(row: SurveySessionAnswer) -> dict[str, Any]:
    return {
        "sequence": row.sequence,
        "step_index": row.step_index,
        "step_role": row.step_role,
        "node_key": row.node_key,
        "question_text": row.question_text,
        "raw_value": row.raw_value,
        "normalized_value": row.normalized_value,
        "reply_type": row.reply_type,
        "answered_at": row.answered_at.isoformat() if row.answered_at else None,
    }


def _decision_to_dict(row: SurveySessionDecision) -> dict[str, Any]:
    return {
        "sequence": row.sequence,
        "decision_kind": row.decision_kind,
        "rule_key": row.rule_key,
        "picker": row.picker,
        "from_step": row.from_step,
        "to_step": row.to_step,
        "from_role": row.from_role,
        "to_role": row.to_role,
        "reason": row.reason,
        "context": _decision_context(row),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


class SurveyWaObservabilityService:
    @staticmethod
    def list_sessions(
        db: Session,
        *,
        order_id: str | None = None,
        org_id: str | None = None,
        survey_type_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        q = select(SurveySession).order_by(SurveySession.updated_at.desc())
        if order_id:
            q = q.where(SurveySession.order_id == order_id)
        if org_id:
            q = q.where(SurveySession.org_id == org_id)
        if survey_type_id:
            q = q.where(SurveySession.survey_type_id == survey_type_id)
        if status:
            q = q.where(SurveySession.status == status)
        rows = list(db.execute(q.limit(max(1, min(limit, 200)))).scalars())
        return {
            "sessions": [_session_to_summary(r) for r in rows],
            "count": len(rows),
        }

    @staticmethod
    def get_session_detail(db: Session, session_id: str) -> dict[str, Any] | None:
        session = db.get(SurveySession, session_id)
        if session is None:
            return None
        recipient = db.get(ServiceOrderRecipient, session.recipient_id)
        order = db.get(ServiceOrder, session.order_id)
        answers = SurveySessionService.list_answers(db, session_id)
        decisions = SurveySessionService.list_decisions(db, session_id)
        from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

        voice_notes = [
            SurveyWaVoiceNoteService.job_to_dict(job)
            for job in SurveyWaVoiceNoteService.list_jobs_for_recipient(db, session.recipient_id)
        ]
        picker_debug = [
            _decision_to_dict(d)
            for d in decisions
            if d.decision_kind in {"branch_picker_invoke", "branch_picker_result"}
        ]
        return {
            "session": _session_to_summary(session),
            "recipient": {
                "id": recipient.id if recipient else None,
                "name": recipient.name if recipient else None,
                "phone": recipient.phone if recipient else None,
                "status": recipient.status if recipient else None,
            },
            "order": {
                "id": order.id if order else None,
                "title": order.title if order else None,
                "status": order.status if order else None,
            },
            "answers": [_answer_to_dict(a) for a in answers],
            "voice_notes": voice_notes,
            "decisions": [_decision_to_dict(d) for d in decisions],
            "picker_debug": picker_debug,
            "branch_path": [
                {"rule_key": d.rule_key, "to_role": d.to_role, "decision_kind": d.decision_kind}
                for d in decisions
                if d.decision_kind in {"branch_take", "branch_evaluate", "advance_linear"}
            ],
        }

    @staticmethod
    def overview(
        db: Session,
        *,
        order_id: str | None = None,
        org_id: str | None = None,
        survey_type_id: str | None = None,
        since_days: int = 7,
    ) -> dict[str, Any]:
        since = datetime.utcnow() - timedelta(days=max(1, min(since_days, 90)))
        base = select(SurveySession).where(SurveySession.created_at >= since)
        if order_id:
            base = base.where(SurveySession.order_id == order_id)
        if org_id:
            base = base.where(SurveySession.org_id == org_id)
        if survey_type_id:
            base = base.where(SurveySession.survey_type_id == survey_type_id)

        sessions = list(db.execute(base).scalars())
        session_ids = [s.id for s in sessions]

        by_status: dict[str, int] = {}
        by_flow_mode: dict[str, int] = {}
        by_outcome: dict[str, int] = {}
        text_fallback_count = 0
        template_send_failure_count = 0
        delivery_failure_count = 0

        for s in sessions:
            by_status[s.status] = by_status.get(s.status, 0) + 1
            by_flow_mode[s.flow_mode] = by_flow_mode.get(s.flow_mode, 0) + 1
            if s.outcome_key:
                by_outcome[s.outcome_key] = by_outcome.get(s.outcome_key, 0) + 1
            delivery = loads_outcome_delivery(s.outcome_delivery_json)
            if delivery.get("sent_at"):
                if delivery.get("used_text_fallback"):
                    text_fallback_count += 1
                if delivery.get("template_send_failed"):
                    template_send_failure_count += 1
                if not delivery.get("ok"):
                    delivery_failure_count += 1

        picker_invocations = sum(int(s.picker_invocation_count or 0) for s in sessions)
        ai_picker_fallback_count = 0
        branch_rule_counts: dict[str, int] = {}

        if session_ids:
            dec_rows = list(
                db.execute(
                    select(SurveySessionDecision).where(SurveySessionDecision.session_id.in_(session_ids))
                ).scalars()
            )
            for d in dec_rows:
                if d.rule_key == RULE_AI_PICKER_FALLBACK:
                    ai_picker_fallback_count += 1
                if d.decision_kind in {"branch_take", "advance_linear"}:
                    key = str(d.rule_key or "unknown")
                    branch_rule_counts[key] = branch_rule_counts.get(key, 0) + 1

        top_branches = sorted(branch_rule_counts.items(), key=lambda x: -x[1])[:15]

        picker_settings = SurveyPickerSettingsService.get_settings(db)

        return {
            "since": since.isoformat(),
            "filters": {
                "order_id": order_id,
                "org_id": org_id,
                "survey_type_id": survey_type_id,
                "since_days": since_days,
            },
            "session_count": len(sessions),
            "sessions_by_status": by_status,
            "sessions_by_flow_mode": by_flow_mode,
            "outcome_counts": by_outcome,
            "text_fallback_count": text_fallback_count,
            "template_send_failure_count": template_send_failure_count,
            "delivery_failure_count": delivery_failure_count,
            "picker_invocation_count": picker_invocations,
            "ai_picker_fallback_count": ai_picker_fallback_count,
            "top_branch_rule_keys": [{"rule_key": k, "count": v} for k, v in top_branches],
            "picker": {
                "platform_enabled": SurveyPickerSettingsService.is_platform_picker_enabled(db),
                "kill_switch": bool(picker_settings.get("kill_switch")),
                "max_calls_per_session": picker_settings.get("max_calls_per_session"),
            },
        }
