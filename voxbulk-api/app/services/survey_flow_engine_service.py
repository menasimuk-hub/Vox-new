"""Deterministic graph runtime for WA Survey sessions (P2)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession, SurveySessionAnswer
from app.services.survey_flow_compiler_service import index_snapshot
from app.services.survey_flow_condition_service import evaluate_condition
from app.services.survey_flow_config_service import get_flow_snapshot
from app.services.survey_flow_constants import (
    ACTION_SEND_TEMPLATE,
    ACTION_SEND_TEXT,
    DECISION_BRANCH_EVALUATE,
    DECISION_BRANCH_TAKE,
    DECISION_OUTCOME_ACTION,
    DECISION_OUTCOME_REACHED,
    FLOW_MODE_GRAPH,
    NODE_TYPE_OUTCOME,
    NODE_TYPE_QUESTION,
    OUTCOME_KEYS,
    RULE_BRANCH_DEFAULT,
    RULE_GRAPH_SEND,
    RULE_GRAPH_START,
)
from app.services.survey_session_service import (
    DECISION_RECORD_ANSWER,
    DECISION_SEND_QUESTION,
    DECISION_START,
    SurveySessionService,
)
from app.services.wa_template_privacy import normalize_privacy_mode

logger = logging.getLogger(__name__)


class SurveyFlowEngineService:
    @staticmethod
    def load_indexed(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        snap = get_flow_snapshot(config)
        if not snap:
            raise ValueError("Missing flow_snapshot on order config")
        return snap, index_snapshot(snap)

    @staticmethod
    def start_graph_session(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        config: dict[str, Any],
    ) -> tuple[SurveySession, dict[str, Any], str]:
        existing = SurveySessionService.get_active_by_recipient(db, recipient.id)
        snap, idx = SurveyFlowEngineService.load_indexed(config)
        entry = str(snap.get("entry_node_key") or "")
        node = idx["nodes"].get(entry)
        if not node:
            raise ValueError(f"Invalid entry_node_key: {entry}")

        if existing and str(existing.status) == "active":
            q = SurveyFlowEngineService._question_for_node(node)
            body = SurveyFlowEngineService._format_node_question(q, session=existing, snap=snap)
            return existing, q, body

        privacy_raw = config.get("privacy_mode")
        if config.get("anonymous_responses") in (True, "true", "1", 1):
            privacy_raw = "on"
        now = datetime.utcnow()
        mq = int(snap.get("max_question_visits") or config.get("page_count") or 6)
        session = SurveySession(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=order.org_id,
            channel="whatsapp",
            status="active",
            flow_mode=FLOW_MODE_GRAPH,
            current_step=1,
            total_steps=mq,
            current_node_key=entry,
            question_visits=0,
            page_roles_json=json.dumps(config.get("page_roles") or [], ensure_ascii=False),
            flow_definition_id=str(config.get("flow_definition_id") or "") or None,
            flow_snapshot_json=json.dumps(snap, ensure_ascii=False),
            survey_type_id=str(config.get("survey_type_id") or "") or None,
            privacy_mode=normalize_privacy_mode(privacy_raw),
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(session)
        db.flush()

        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_START,
            rule_key=RULE_GRAPH_START,
            from_step=None,
            to_step=1,
            from_role=None,
            to_role=str(node.get("step_role") or entry),
            reason="Graph WA survey session opened.",
            context={"entry_node_key": entry, "flow_mode": FLOW_MODE_GRAPH},
        )
        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_SEND_QUESTION,
            rule_key=RULE_GRAPH_SEND,
            from_step=None,
            to_step=1,
            from_role=None,
            to_role=str(node.get("step_role") or entry),
            reason="First graph question dispatched.",
            context={"node_key": entry},
        )
        db.commit()
        db.refresh(session)
        q = SurveyFlowEngineService._question_for_node(node)
        body = SurveyFlowEngineService._format_node_question(q, session=session, snap=snap)
        return session, q, body

    @staticmethod
    def _question_for_node(node: dict[str, Any]) -> dict[str, Any]:
        q = node.get("question")
        if isinstance(q, dict):
            return q
        return {
            "text": node.get("title") or node.get("step_role") or "Question",
            "reply_type": "text",
            "options": [],
            "step_role": node.get("step_role"),
        }

    @staticmethod
    def _format_node_question(question: dict[str, Any], *, session: SurveySession, snap: dict[str, Any]) -> str:
        from app.services.survey_whatsapp_conversation_service import format_question_message

        visit = int(session.question_visits or 0) + 1
        total = int(snap.get("max_question_visits") or session.total_steps or 1)
        return format_question_message(question, index=visit, total=total)

    @staticmethod
    def record_answer_and_resolve(
        db: Session,
        *,
        session: SurveySession,
        config: dict[str, Any],
        current_node_key: str,
        question: dict[str, Any],
        raw_body: str,
    ) -> dict[str, Any]:
        snap, idx = SurveyFlowEngineService.load_indexed(config)
        if session.flow_snapshot_json:
            try:
                snap = json.loads(session.flow_snapshot_json)
                idx = index_snapshot(snap)
            except Exception:
                pass

        from app.services.survey_whatsapp_conversation_service import match_answer

        normalized = match_answer(raw_body, question)
        visit_num = int(session.question_visits or 0) + 1
        step_role = str(question.get("step_role") or current_node_key)

        seq = SurveySessionService._next_answer_sequence(db, session.id)
        now = datetime.utcnow()
        answer_row = SurveySessionAnswer(
            session_id=session.id,
            sequence=seq,
            step_index=visit_num,
            step_role=step_role,
            node_key=current_node_key,
            question_text=str(question.get("text") or "").strip() or None,
            raw_value=str(raw_body or "").strip(),
            normalized_value=normalized,
            reply_type=str(question.get("reply_type") or "").strip() or None,
            template_id=int(question["template_id"]) if question.get("template_id") else None,
            answered_at=now,
            created_at=now,
        )
        db.add(answer_row)
        session.question_visits = visit_num
        session.updated_at = now
        db.add(session)
        db.flush()

        answers = SurveySessionService.list_answers(db, session.id)
        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_RECORD_ANSWER,
            rule_key="graph.record_answer",
            from_step=visit_num,
            to_step=visit_num,
            from_role=step_role,
            to_role=step_role,
            reason="Inbound answer stored.",
            context={"node_key": current_node_key, "normalized_value": normalized},
        )

        mq = int(snap.get("max_question_visits") or session.total_steps or 6)
        if visit_num >= mq:
            fallback = str(snap.get("fallback_outcome_key") or "neutral")
            return SurveyFlowEngineService._resolve_outcome(
                db,
                session=session,
                snap=snap,
                idx=idx,
                outcome_node_key=f"outcome_{fallback}",
                rule_key="graph.max_visits",
                config=config,
            )

        edges = idx["edges_by_from"].get(current_node_key, [])
        matched_edge = None
        for edge in edges:
            cond = edge.get("condition_json")
            if cond is None:
                continue
            SurveySessionService._append_decision(
                db,
                session,
                decision_kind=DECISION_BRANCH_EVALUATE,
                rule_key=str(edge.get("rule_key") or "branch.eval"),
                from_step=visit_num,
                to_step=None,
                from_role=step_role,
                to_role=None,
                reason="Evaluating branch condition.",
                context={"edge": edge, "condition": cond},
            )
            if evaluate_condition(cond, last_answer=answer_row, answers=answers):
                matched_edge = edge
                break

        if matched_edge is None:
            defaults = [e for e in edges if e.get("condition_json") is None]
            matched_edge = defaults[0] if defaults else None

        if not matched_edge:
            fallback = str(snap.get("fallback_outcome_key") or "neutral")
            return SurveyFlowEngineService._resolve_outcome(
                db,
                session=session,
                snap=snap,
                idx=idx,
                outcome_node_key=f"outcome_{fallback}",
                rule_key=RULE_BRANCH_DEFAULT,
                config=config,
            )

        to_key = str(matched_edge.get("to_node_key") or "")
        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_BRANCH_TAKE,
            rule_key=str(matched_edge.get("rule_key") or RULE_BRANCH_DEFAULT),
            from_step=visit_num,
            to_step=visit_num + 1,
            from_role=step_role,
            to_role=to_key,
            reason="Branch edge selected.",
            context={"from_node_key": current_node_key, "to_node_key": to_key},
        )

        return SurveyFlowEngineService._advance_to_node(
            db,
            session=session,
            snap=snap,
            idx=idx,
            to_node_key=to_key,
            config=config,
        )

    @staticmethod
    def _advance_to_node(
        db: Session,
        *,
        session: SurveySession,
        snap: dict[str, Any],
        idx: dict[str, Any],
        to_node_key: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        node = idx["nodes"].get(to_node_key)
        if not node:
            fallback = str(snap.get("fallback_outcome_key") or "neutral")
            return SurveyFlowEngineService._resolve_outcome(
                db,
                session=session,
                snap=snap,
                idx=idx,
                outcome_node_key=f"outcome_{fallback}",
                rule_key="graph.missing_node",
                config=config,
            )
        ntype = str(node.get("node_type") or "")
        if ntype == NODE_TYPE_QUESTION:
            session.current_node_key = to_node_key
            session.current_step = int(session.question_visits or 0) + 1
            session.updated_at = datetime.utcnow()
            db.add(session)
            SurveySessionService._append_decision(
                db,
                session,
                decision_kind=DECISION_SEND_QUESTION,
                rule_key=RULE_GRAPH_SEND,
                from_step=int(session.question_visits or 0),
                to_step=session.current_step,
                from_role=None,
                to_role=str(node.get("step_role") or to_node_key),
                reason="Next graph question.",
                context={"node_key": to_node_key},
            )
            q = SurveyFlowEngineService._question_for_node(node)
            body = SurveyFlowEngineService._format_node_question(q, session=session, snap=snap)
            return {
                "action": "send_question",
                "node_key": to_node_key,
                "question": q,
                "body": body,
                "completed": False,
            }
        if ntype == NODE_TYPE_OUTCOME:
            return SurveyFlowEngineService._resolve_outcome(
                db,
                session=session,
                snap=snap,
                idx=idx,
                outcome_node_key=to_node_key,
                rule_key="graph.outcome_node",
                config=config,
            )
        fallback = str(snap.get("fallback_outcome_key") or "neutral")
        return SurveyFlowEngineService._resolve_outcome(
            db,
            session=session,
            snap=snap,
            idx=idx,
            outcome_node_key=f"outcome_{fallback}",
            rule_key="graph.unknown_node_type",
            config=config,
        )

    @staticmethod
    def _resolve_outcome(
        db: Session,
        *,
        session: SurveySession,
        snap: dict[str, Any],
        idx: dict[str, Any],
        outcome_node_key: str,
        rule_key: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        node = idx["nodes"].get(outcome_node_key) or {}
        outcome_key = str(node.get("outcome_key") or outcome_node_key.replace("outcome_", ""))
        if outcome_key not in OUTCOME_KEYS:
            outcome_key = str(snap.get("fallback_outcome_key") or "neutral")

        outcome_cfg = idx["outcomes_by_node"].get(outcome_node_key) or idx["outcomes_by_key"].get(outcome_key) or {}
        template_send = outcome_cfg.get("template_send")
        session.outcome_key = outcome_key
        session.current_node_key = outcome_node_key
        session.status = "completed"
        session.completed_at = datetime.utcnow()
        session.updated_at = datetime.utcnow()
        db.add(session)

        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_OUTCOME_REACHED,
            rule_key=rule_key,
            from_step=int(session.question_visits or 0),
            to_step=None,
            from_role=None,
            to_role=outcome_key,
            reason="Outcome node reached.",
            context={"outcome_node_key": outcome_node_key},
        )

        action_type = str(outcome_cfg.get("action_type") or ACTION_SEND_TEXT)
        message_body = str(outcome_cfg.get("message_body") or "Thank you for your feedback.")

        SurveySessionService._append_decision(
            db,
            session,
            decision_kind=DECISION_OUTCOME_ACTION,
            rule_key=f"outcome.{outcome_key}",
            from_step=None,
            to_step=None,
            from_role=None,
            to_role=outcome_key,
            reason="Outcome action resolved.",
            context={
                "action_type": action_type,
                "template_id": outcome_cfg.get("template_id"),
                "has_template_send": bool(template_send),
            },
        )

        return {
            "action": "complete",
            "completed": True,
            "outcome_key": outcome_key,
            "body": message_body,
            "message_body": message_body,
            "action_type": action_type,
            "template_id": outcome_cfg.get("template_id"),
            "template_send": template_send,
        }
