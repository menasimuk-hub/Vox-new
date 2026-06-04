"""Multi-step WhatsApp survey conversations (intro → questions → closing)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.messaging_log_service import normalize_e164
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_dispatch_service import _first_name, _personalize, _uses_whatsapp
from app.services.survey_flow_config_service import is_graph_flow, is_simulator_dry_run
from app.services.survey_flow_engine_service import SurveyFlowEngineService
from app.services.survey_outcome_send_service import SurveyOutcomeSendService
from app.services.survey_session_service import SurveySessionService
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-wa]"


def is_whatsapp_survey_order(order: ServiceOrder) -> bool:
    if order.service_code != "survey":
        return False
    try:
        config = json.loads(order.config_json or "{}")
        return PlatformCatalogService.resolve_survey_channel(config) == "whatsapp"
    except Exception:
        return False


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _whatsapp_flow(config: dict[str, Any]) -> dict[str, Any]:
    wa = config.get("whatsapp_flow")
    return wa if isinstance(wa, dict) else {}


def _wa_conversation(result: dict[str, Any]) -> dict[str, Any]:
    wa = result.get("wa_conversation")
    return wa if isinstance(wa, dict) else {}


def _save_recipient_result(db: Session, recipient: ServiceOrderRecipient, payload: dict[str, Any]) -> None:
    recipient.result_json = json.dumps(payload, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()


def format_question_message(
    question: dict[str, Any],
    *,
    index: int,
    total: int,
) -> str:
    text = str(question.get("text") or "Question").strip()
    reply_type = str(question.get("reply_type") or "text").strip().lower()
    options = question.get("options") or []
    if not isinstance(options, list):
        options = []

    lines = [f"Question {index} of {total}", text]
    if reply_type in {"text", "long_text", "contact", "date"}:
        lines.append("Reply with your answer.")
    elif options:
        lines.append("Reply with one of:")
        for i, opt in enumerate(options[:12], start=1):
            label = str(opt).strip()
            if label:
                lines.append(f"{i}. {label}")
    else:
        lines.append("Reply with your answer.")
    return "\n".join(lines)


def match_answer(body: str, question: dict[str, Any]) -> str:
    raw = str(body or "").strip()
    if not raw:
        return raw
    options = question.get("options") or []
    if not isinstance(options, list) or not options:
        return raw
    lowered = raw.lower()
    for opt in options:
        label = str(opt).strip()
        if label and lowered == label.lower():
            return label
    m = re.match(r"^(\d+)\b", raw)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(options):
            return str(options[idx]).strip()
    return raw


def _phone_candidates(phone: str) -> set[str]:
    out: set[str] = set()
    raw = str(phone or "").strip()
    if not raw:
        return out
    out.add(raw)
    try:
        out.add(normalize_e164(raw))
    except ValueError:
        pass
    digits = re.sub(r"\D", "", raw)
    if digits:
        out.add(digits)
        if len(digits) >= 10:
            out.add(digits[-10:])
    return {p for p in out if p}


def find_active_recipient(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None = None,
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None]:
    """Find a running WhatsApp survey recipient awaiting a reply."""
    needles = _phone_candidates(from_phone)
    if not needles:
        return None, None

    orders = list(
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.service_code == "survey",
                ServiceOrder.status == "running",
            )
        ).scalars()
    )

    for order in orders:
        if org_id and order.org_id != org_id:
            continue
        if not is_whatsapp_survey_order(order):
            continue
        for recipient in ServiceOrderService.get_recipients(db, order.id):
            if str(recipient.status or "").lower() not in {"sent", "in_progress"}:
                continue
            rec_phones = _phone_candidates(recipient.phone or "")
            if not needles.intersection(rec_phones):
                continue
            conv = _wa_conversation(_recipient_result(recipient))
            step = int(conv.get("step") or 0)
            total = int(conv.get("total") or 0)
            if step >= 1 and step <= max(total, 1):
                return order, recipient
    return None, None


def _send_message(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    body: str,
) -> bool:
    config = _order_config(order)
    if is_simulator_dry_run(config):
        return True
    result = TelnyxMessagingService.send_survey_message(
        db,
        org_id=order.org_id,
        to_number=recipient.phone or "",
        body=body,
        prefer_whatsapp=True,
    )
    try:
        TelnyxMessagingService.log_outbound(
            db,
            org_id=order.org_id,
            to_number=recipient.phone or "",
            from_number=None,
            body=body,
            result=result,
        )
    except Exception:
        pass
    return bool(result.ok)


def send_first_question(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
) -> None:
    flow = _whatsapp_flow(config)
    questions = flow.get("questions") or []
    if not isinstance(questions, list) or not questions:
        return

    if is_graph_flow(config):
        _send_first_question_graph(db, order=order, recipient=recipient, config=config, questions=questions)
        return

    q0 = questions[0] if isinstance(questions[0], dict) else {"text": str(questions[0])}
    body = format_question_message(q0, index=1, total=len(questions))

    payload = _recipient_result(recipient)
    payload["channel"] = "whatsapp"
    payload["wa_conversation"] = {
        "step": 1,
        "total": len(questions),
        "answers": [],
        "started_at": datetime.utcnow().isoformat(),
    }
    session = SurveySessionService.start_linear_session(
        db,
        order=order,
        recipient=recipient,
        config=config,
        question_count=len(questions),
    )
    payload = SurveySessionService.attach_session_to_result(payload, session)
    recipient.status = "in_progress"
    _save_recipient_result(db, recipient, payload)

    if _send_message(db, order=order, recipient=recipient, body=body):
        logger.info("%s first_question_sent order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id)


def _send_first_question_graph(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    questions: list[Any],
) -> None:
    from app.services.survey_flow_config_service import max_question_visits

    session, _q, body = SurveyFlowEngineService.start_graph_session(
        db, order=order, recipient=recipient, config=config
    )
    total = max_question_visits(config)
    payload = _recipient_result(recipient)
    payload["channel"] = "whatsapp"
    payload["wa_conversation"] = {
        "step": 1,
        "total": total,
        "answers": [],
        "started_at": datetime.utcnow().isoformat(),
        "current_node_key": session.current_node_key,
    }
    payload = SurveySessionService.attach_session_to_result(payload, session)
    recipient.status = "in_progress"
    _save_recipient_result(db, recipient, payload)
    if _send_message(db, order=order, recipient=recipient, body=body):
        logger.info("%s graph_first_question order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id)


def _maybe_complete_order(db: Session, order: ServiceOrder) -> None:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    if not recipients:
        return
    terminal = {"completed", "failed", "skipped", "opted_out", "cancelled"}
    if all(str(r.status or "").lower() in terminal for r in recipients):
        order.status = "completed"
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()


def handle_inbound_reply(
    db: Session,
    *,
    from_phone: str,
    body: str,
    org_id: str | None = None,
    log_id: int | None = None,
) -> dict[str, Any]:
    """Advance an active WhatsApp survey when a contact replies."""
    order, recipient = find_active_recipient(db, from_phone=from_phone, org_id=org_id)
    if not order or not recipient:
        return {"handled": False, "reason": "no_active_survey"}

    config = _order_config(order)
    flow = _whatsapp_flow(config)
    questions = [q for q in (flow.get("questions") or []) if isinstance(q, dict)]
    if not questions:
        return {"handled": False, "reason": "no_questions"}

    if is_graph_flow(config):
        return _handle_inbound_reply_graph(
            db,
            order=order,
            recipient=recipient,
            config=config,
            flow=flow,
            questions=questions,
            body=body,
            log_id=log_id,
        )

    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()

    payload = _recipient_result(recipient)
    conv = _wa_conversation(payload)
    step = int(conv.get("step") or 0)
    total = int(conv.get("total") or len(questions))
    answers: list[dict[str, Any]] = list(conv.get("answers") or [])

    if step < 1 or step > total:
        return {"handled": False, "reason": "invalid_step"}

    q_index = step - 1
    question = questions[q_index]
    answer = match_answer(body, question)
    answers.append(
        {
            "question": str(question.get("text") or f"Question {step}"),
            "answer": answer,
            "reply_type": question.get("reply_type"),
        }
    )

    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    if session is None:
        session = SurveySessionService.start_linear_session(
            db,
            order=order,
            recipient=recipient,
            config=config,
            question_count=total,
        )
    SurveySessionService.record_linear_answer(
        db,
        session,
        step_index=step,
        question=question,
        raw_value=str(body or "").strip(),
        normalized_value=answer,
        config=config,
    )

    extracted = [{"question": a["question"], "answer": a["answer"]} for a in answers]
    payload["extracted_answers"] = extracted
    payload["channel"] = "whatsapp"
    conv["answers"] = answers
    payload = SurveySessionService.attach_session_to_result(payload, session)

    if step < total:
        next_q = questions[step]
        next_body = format_question_message(next_q, index=step + 1, total=total)
        conv["step"] = step + 1
        payload["wa_conversation"] = conv
        SurveySessionService.advance_linear(
            db, session, config=config, from_step=step, to_step=step + 1
        )
        recipient.status = "in_progress"
        _save_recipient_result(db, recipient, payload)
        sent = _send_message(db, order=order, recipient=recipient, body=next_body)
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "step": step,
            "next_step": step + 1,
            "sent": sent,
            "log_id": log_id,
        }

    closing_template = str(flow.get("closing") or "Thank you for your feedback.").strip()
    closing = _personalize(
        closing_template,
        first_name=_first_name(recipient.name),
        org_name=org_name,
        organiser=organiser,
    )
    conv["step"] = total + 1
    conv["completed_at"] = datetime.utcnow().isoformat()
    payload["wa_conversation"] = conv
    SurveySessionService.complete_linear(db, session, config=config, final_step=step)
    recipient.status = "completed"
    _save_recipient_result(db, recipient, payload)
    _send_message(db, order=order, recipient=recipient, body=closing)

    report = {}
    try:
        report = json.loads(order.report_json or "{}")
        if not isinstance(report, dict):
            report = {}
    except Exception:
        report = {}
    report["completed"] = int(report.get("completed") or 0) + 1
    order.report_json = json.dumps(report, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()

    _maybe_complete_order(db, order)
    logger.info("%s completed order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id)
    return {
        "handled": True,
        "order_id": order.id,
        "recipient_id": recipient.id,
        "completed": True,
        "log_id": log_id,
    }


def _handle_inbound_reply_graph(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    flow: dict[str, Any],
    questions: list[dict[str, Any]],
    body: str,
    log_id: int | None,
) -> dict[str, Any]:
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()

    payload = _recipient_result(recipient)
    conv = _wa_conversation(payload)
    step = int(conv.get("step") or 0)
    from app.services.survey_flow_config_service import max_question_visits

    total = int(conv.get("total") or max_question_visits(config))
    answers: list[dict[str, Any]] = list(conv.get("answers") or [])

    current_node_key = str(conv.get("current_node_key") or "")
    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    if session and session.current_node_key:
        current_node_key = session.current_node_key

    if not current_node_key:
        return {"handled": False, "reason": "invalid_graph_state"}

    q_index = max(0, step - 1)
    question = questions[q_index] if q_index < len(questions) else {}
    if session and session.flow_snapshot_json:
        try:
            import json as _json

            snap = _json.loads(session.flow_snapshot_json)
            node = {n["node_key"]: n for n in snap.get("nodes") or [] if isinstance(n, dict)}.get(
                current_node_key
            )
            if node and isinstance(node.get("question"), dict):
                question = node["question"]
        except Exception:
            pass

    answer = match_answer(body, question)
    answers.append(
        {
            "question": str(question.get("text") or f"Question {step}"),
            "answer": answer,
            "reply_type": question.get("reply_type"),
            "node_key": current_node_key,
        }
    )

    if session is None:
        session, _, _ = SurveyFlowEngineService.start_graph_session(
            db, order=order, recipient=recipient, config=config
        )

    result = SurveyFlowEngineService.record_answer_and_resolve(
        db,
        session=session,
        config=config,
        current_node_key=current_node_key,
        question=question,
        raw_body=body,
    )

    extracted = [{"question": a["question"], "answer": a["answer"]} for a in answers]
    payload["extracted_answers"] = extracted
    payload["channel"] = "whatsapp"
    conv["answers"] = answers
    payload = SurveySessionService.attach_session_to_result(payload, session)

    if result.get("completed"):
        conv["step"] = total + 1
        conv["completed_at"] = datetime.utcnow().isoformat()
        conv["outcome_key"] = result.get("outcome_key")
        payload["wa_conversation"] = conv
        recipient.status = "completed"
        _save_recipient_result(db, recipient, payload)
        SurveyOutcomeSendService.deliver(
            db,
            order=order,
            recipient=recipient,
            session=session,
            outcome_result=result,
            config=config,
        )
        report = {}
        try:
            report = json.loads(order.report_json or "{}")
            if not isinstance(report, dict):
                report = {}
        except Exception:
            report = {}
        report["completed"] = int(report.get("completed") or 0) + 1
        order.report_json = json.dumps(report, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        _maybe_complete_order(db, order)
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "completed": True,
            "outcome_key": result.get("outcome_key"),
            "log_id": log_id,
        }

    next_body = str(result.get("body") or "")
    conv["step"] = int(session.question_visits or step) + 1
    conv["current_node_key"] = result.get("node_key") or session.current_node_key
    payload["wa_conversation"] = conv
    recipient.status = "in_progress"
    _save_recipient_result(db, recipient, payload)
    sent = _send_message(db, order=order, recipient=recipient, body=next_body)
    return {
        "handled": True,
        "order_id": order.id,
        "recipient_id": recipient.id,
        "step": step,
        "next_step": conv["step"],
        "sent": sent,
        "log_id": log_id,
    }


def bootstrap_after_intro(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
) -> None:
    """After intro is sent, queue the first survey question."""
    if not _uses_whatsapp(config):
        return
    send_first_question(db, order=order, recipient=recipient, config=config)
