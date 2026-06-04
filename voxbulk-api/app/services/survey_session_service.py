"""WA Survey session persistence — P1 linear flow with structured answers and decision log."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession, SurveySessionAnswer, SurveySessionDecision
from app.services.survey_step_bank_service import normalize_step_role
from app.services.wa_template_privacy import normalize_privacy_mode

logger = logging.getLogger(__name__)

FLOW_MODE_LINEAR = "linear"
PICKER_DETERMINISTIC = "deterministic"
SESSION_ACTIVE = "active"
SESSION_COMPLETED = "completed"

DECISION_START = "start_session"
DECISION_SEND_QUESTION = "send_question"
DECISION_RECORD_ANSWER = "record_answer"
DECISION_ADVANCE_LINEAR = "advance_linear"
DECISION_COMPLETE = "complete_session"

RULE_LINEAR_START = "linear.start"
RULE_LINEAR_SEND = "linear.send_question"
RULE_LINEAR_ADVANCE = "linear.advance"
RULE_LINEAR_COMPLETE = "linear.complete"


def _middle_page_roles(config: dict[str, Any], *, question_count: int) -> list[str]:
    flow = config.get("whatsapp_flow")
    wa_flow = flow if isinstance(flow, dict) else {}
    roles_raw = wa_flow.get("page_roles") or config.get("page_roles") or []
    if not isinstance(roles_raw, list):
        roles_raw = []
    middle = [
        normalize_step_role(str(r))
        for r in roles_raw
        if normalize_step_role(str(r)) not in {"start", "completion"}
    ]
    if middle:
        return middle[:question_count]
    return [f"question_{i}" for i in range(1, question_count + 1)]


def resolve_step_role(
    config: dict[str, Any],
    *,
    step_index: int,
    question_count: int,
    question: dict[str, Any] | None = None,
) -> str:
    """Map 1-based question step to a normalized step_role / node role."""
    middle = _middle_page_roles(config, question_count=question_count)
    if 1 <= step_index <= len(middle):
        return middle[step_index - 1]
    if question and question.get("step_role"):
        return normalize_step_role(str(question["step_role"]))
    reply = str((question or {}).get("reply_type") or "").strip().lower()
    aliases = {
        "rating": "rating",
        "true_false": "yes_no",
        "choice": "abc_choice",
        "long_text": "reason",
        "text": "follow_up",
    }
    return aliases.get(reply, f"question_{step_index}")


def build_node_key(step_role: str, step_index: int) -> str:
    role = normalize_step_role(step_role)
    return f"{role}@{step_index}"


class SurveySessionService:
    @staticmethod
    def get_by_recipient(db: Session, recipient_id: str) -> SurveySession | None:
        return db.execute(
            select(SurveySession).where(SurveySession.recipient_id == recipient_id)
        ).scalar_one_or_none()

    @staticmethod
    def get_active_by_recipient(db: Session, recipient_id: str) -> SurveySession | None:
        row = SurveySessionService.get_by_recipient(db, recipient_id)
        if row and str(row.status or "").lower() == SESSION_ACTIVE:
            return row
        return None

    @staticmethod
    def _next_answer_sequence(db: Session, session_id: str) -> int:
        current = db.execute(
            select(func.coalesce(func.max(SurveySessionAnswer.sequence), 0)).where(
                SurveySessionAnswer.session_id == session_id
            )
        ).scalar_one()
        return int(current or 0) + 1

    @staticmethod
    def _next_decision_sequence(db: Session, session_id: str) -> int:
        current = db.execute(
            select(func.coalesce(func.max(SurveySessionDecision.sequence), 0)).where(
                SurveySessionDecision.session_id == session_id
            )
        ).scalar_one()
        return int(current or 0) + 1

    @staticmethod
    def start_linear_session(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        config: dict[str, Any],
        question_count: int,
    ) -> SurveySession:
        existing = SurveySessionService.get_by_recipient(db, recipient.id)
        if existing and str(existing.status or "").lower() == SESSION_ACTIVE:
            return existing

        if existing and str(existing.status or "").lower() != SESSION_ACTIVE:
            logger.warning(
                "survey_session already exists for recipient=%s status=%s; reusing row",
                recipient.id,
                existing.status,
            )
            return existing

        middle_roles = _middle_page_roles(config, question_count=question_count)
        page_roles_snapshot = middle_roles
        flow = config.get("whatsapp_flow")
        if isinstance(flow, dict) and isinstance(flow.get("page_roles"), list):
            page_roles_snapshot = flow["page_roles"]

        privacy_raw = config.get("privacy_mode")
        if config.get("anonymous_responses") in (True, "true", "1", 1):
            privacy_raw = "on"
        privacy = normalize_privacy_mode(privacy_raw)
        now = datetime.utcnow()
        session = SurveySession(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=order.org_id,
            channel="whatsapp",
            status=SESSION_ACTIVE,
            flow_mode=FLOW_MODE_LINEAR,
            current_step=1,
            total_steps=question_count,
            page_roles_json=json.dumps(page_roles_snapshot, ensure_ascii=False),
            survey_type_id=str(config.get("survey_type_id") or "") or None,
            privacy_mode=privacy,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.flush()

        first_role = resolve_step_role(config, step_index=1, question_count=question_count)
        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_START,
            rule_key=RULE_LINEAR_START,
            from_step=None,
            to_step=1,
            from_role=None,
            to_role=first_role,
            reason="Linear WA survey session opened after intro.",
            context={"question_count": question_count, "flow_mode": FLOW_MODE_LINEAR},
        )
        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_SEND_QUESTION,
            rule_key=RULE_LINEAR_SEND,
            from_step=None,
            to_step=1,
            from_role=None,
            to_role=first_role,
            reason="First survey question dispatched.",
        )
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def record_linear_answer(
        db: Session,
        session: SurveySession,
        *,
        step_index: int,
        question: dict[str, Any],
        raw_value: str,
        normalized_value: str,
        config: dict[str, Any],
    ) -> SurveySessionAnswer:
        step_role = resolve_step_role(
            config,
            step_index=step_index,
            question_count=session.total_steps,
            question=question,
        )
        seq = SurveySessionService._next_answer_sequence(db, session.id)
        now = datetime.utcnow()
        row = SurveySessionAnswer(
            session_id=session.id,
            sequence=seq,
            step_index=step_index,
            step_role=step_role,
            node_key=build_node_key(step_role, step_index),
            question_text=str(question.get("text") or "").strip() or None,
            raw_value=raw_value,
            normalized_value=normalized_value,
            reply_type=str(question.get("reply_type") or "").strip() or None,
            template_id=int(question["template_id"]) if question.get("template_id") else None,
            answered_at=now,
            created_at=now,
        )
        db.add(row)
        db.flush()

        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_RECORD_ANSWER,
            rule_key="linear.record_answer",
            from_step=step_index,
            to_step=step_index,
            from_role=step_role,
            to_role=step_role,
            reason="Inbound answer stored.",
            context={
                "answer_sequence": seq,
                "node_key": row.node_key,
                "normalized_value": normalized_value,
            },
        )
        return row

    @staticmethod
    def advance_linear(
        db: Session,
        session: SurveySession,
        *,
        config: dict[str, Any],
        from_step: int,
        to_step: int,
    ) -> None:
        from_role = resolve_step_role(config, step_index=from_step, question_count=session.total_steps)
        to_role = resolve_step_role(config, step_index=to_step, question_count=session.total_steps)
        session.current_step = to_step
        session.updated_at = datetime.utcnow()
        db.add(session)

        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_ADVANCE_LINEAR,
            rule_key=RULE_LINEAR_ADVANCE,
            from_step=from_step,
            to_step=to_step,
            from_role=from_role,
            to_role=to_role,
            reason="Linear flow: advance to next question.",
        )
        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_SEND_QUESTION,
            rule_key=RULE_LINEAR_SEND,
            from_step=from_step,
            to_step=to_step,
            from_role=from_role,
            to_role=to_role,
            reason="Next survey question dispatched.",
        )

    @staticmethod
    def complete_linear(
        db: Session,
        session: SurveySession,
        *,
        config: dict[str, Any],
        final_step: int,
    ) -> None:
        from_role = resolve_step_role(config, step_index=final_step, question_count=session.total_steps)
        now = datetime.utcnow()
        session.status = SESSION_COMPLETED
        session.current_step = final_step
        session.completed_at = now
        session.updated_at = now
        db.add(session)

        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_COMPLETE,
            rule_key=RULE_LINEAR_COMPLETE,
            from_step=final_step,
            to_step=None,
            from_role=from_role,
            to_role="completion",
            reason="All questions answered; closing message sent.",
        )

    @staticmethod
    def attach_session_to_result(payload: dict[str, Any], session: SurveySession) -> dict[str, Any]:
        """Mirror session id on result_json for backward-compatible debugging."""
        conv = payload.get("wa_conversation")
        if not isinstance(conv, dict):
            conv = {}
        conv["survey_session_id"] = session.id
        conv["flow_mode"] = session.flow_mode
        if session.current_node_key:
            conv["current_node_key"] = session.current_node_key
        if session.outcome_key:
            conv["outcome_key"] = session.outcome_key
        payload["wa_conversation"] = conv
        payload["survey_session_id"] = session.id
        return payload

    @staticmethod
    def list_answers(db: Session, session_id: str) -> list[SurveySessionAnswer]:
        return list(
            db.execute(
                select(SurveySessionAnswer)
                .where(SurveySessionAnswer.session_id == session_id)
                .order_by(SurveySessionAnswer.sequence.asc())
            ).scalars()
        )

    @staticmethod
    def list_decisions(db: Session, session_id: str) -> list[SurveySessionDecision]:
        return list(
            db.execute(
                select(SurveySessionDecision)
                .where(SurveySessionDecision.session_id == session_id)
                .order_by(SurveySessionDecision.sequence.asc())
            ).scalars()
        )

    @staticmethod
    def _append_decision(
        db: Session,
        session: SurveySession,
        *,
        decision_kind: str,
        rule_key: str,
        from_step: int | None,
        to_step: int | None,
        from_role: str | None,
        to_role: str | None,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> SurveySessionDecision:
        seq = SurveySessionService._next_decision_sequence(db, session.id)
        now = datetime.utcnow()
        row = SurveySessionDecision(
            session_id=session.id,
            sequence=seq,
            decision_kind=decision_kind,
            rule_key=rule_key,
            picker=PICKER_DETERMINISTIC,
            from_step=from_step,
            to_step=to_step,
            from_role=from_role,
            to_role=to_role,
            reason=reason,
            context_json=json.dumps(context, ensure_ascii=False) if context else None,
            decided_at=now,
            created_at=now,
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def answers_as_extracted(session_id: str, db: Session) -> list[dict[str, Any]]:
        """Shape compatible with result_json extracted_answers / reporting."""
        rows = SurveySessionService.list_answers(db, session_id)
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "question": row.question_text or row.step_role,
                    "answer": row.normalized_value or row.raw_value or "",
                    "step_role": row.step_role,
                    "step_index": row.step_index,
                    "node_key": row.node_key,
                    "reply_type": row.reply_type,
                }
            )
        return out
