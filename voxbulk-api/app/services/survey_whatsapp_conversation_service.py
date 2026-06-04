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
from app.services.survey_whatsapp_inbound_guard import is_duplicate_inbound, mark_inbound_processed
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)
LOG_PREFIX = "[survey-wa]"

from app.services.uk_compliance_opt_out import PECR_STOP_RE as SURVEY_WA_OPT_OUT_RE


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


def is_survey_wa_opt_out_message(body: str) -> bool:
    return bool(SURVEY_WA_OPT_OUT_RE.match(str(body or "").strip()))


def _conversation_already_started(recipient: ServiceOrderRecipient) -> bool:
    """True when the first survey question was already queued or answers exist."""
    conv = _wa_conversation(_recipient_result(recipient))
    step = int(conv.get("step") or 0)
    if step >= 1:
        return True
    if conv.get("started_at"):
        return True
    answers = conv.get("answers")
    return isinstance(answers, list) and len(answers) > 0


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
    """Find a running WhatsApp survey recipient awaiting a reply (scoped to org_id)."""
    scoped_org = str(org_id or "").strip()
    if not scoped_org:
        return None, None

    needles = _phone_candidates(from_phone)
    if not needles:
        return None, None

    orders = list(
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.service_code == "survey",
                ServiceOrder.status == "running",
                ServiceOrder.org_id == scoped_org,
            )
        ).scalars()
    )

    for order in orders:
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


def find_survey_recipient_for_opt_out(
    db: Session,
    *,
    from_phone: str,
    org_id: str,
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None]:
    """Latest running WA survey recipient for this phone in org (for STOP handling)."""
    scoped_org = str(org_id or "").strip()
    if not scoped_org:
        return None, None
    needles = _phone_candidates(from_phone)
    if not needles:
        return None, None

    orders = list(
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.service_code == "survey",
                ServiceOrder.status == "running",
                ServiceOrder.org_id == scoped_org,
            )
        ).scalars()
    )
    best: tuple[ServiceOrder, ServiceOrderRecipient] | None = None
    for order in orders:
        if not is_whatsapp_survey_order(order):
            continue
        for recipient in ServiceOrderService.get_recipients(db, order.id):
            if str(recipient.status or "").lower() in {"opted_out", "completed", "cancelled"}:
                continue
            rec_phones = _phone_candidates(recipient.phone or "")
            if needles.intersection(rec_phones):
                best = (order, recipient)
    return best if best else (None, None)


def handle_survey_wa_opt_out(
    db: Session,
    *,
    from_phone: str,
    body: str,
    org_id: str,
    log_id: int | None = None,
    inbound_message_id: str | None = None,
) -> dict[str, Any]:
    """Record org-level opt-out; do not treat keyword as a survey answer."""
    from app.services.org_opt_out_service import OrgOptOutService
    from app.services.survey_voice_agent_service import mark_recipient_opted_out

    scoped_org = str(org_id or "").strip()
    if not scoped_org:
        return {"handled": False, "reason": "missing_org_id"}

    order, recipient = find_survey_recipient_for_opt_out(db, from_phone=from_phone, org_id=scoped_org)
    try:
        OrgOptOutService.add_opt_out(
            db,
            org_id=scoped_org,
            phone=from_phone,
            contact_name=recipient.name if recipient else None,
            reason="whatsapp_keyword_opt_out",
        )
    except Exception:
        logger.exception("%s opt_out_org_record_failed org=%s", LOG_PREFIX, scoped_org)

    if recipient and order:
        payload = _recipient_result(recipient)
        if is_duplicate_inbound(payload, log_id=log_id, inbound_message_id=inbound_message_id):
            return {
                "handled": True,
                "duplicate": True,
                "opted_out": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
            }
        mark_recipient_opted_out(
            db,
            recipient,
            reason="whatsapp_keyword_opt_out",
            source_text=body,
        )
        db.refresh(recipient)
        payload = mark_inbound_processed(
            _recipient_result(recipient),
            log_id=log_id,
            inbound_message_id=inbound_message_id,
        )
        payload["wa_conversation"] = _wa_conversation(payload)
        payload["wa_conversation"]["opted_out_at"] = datetime.utcnow().isoformat()
        _save_recipient_result(db, recipient, payload)
        confirm = "You have been unsubscribed from survey messages. Reply START if this was a mistake."
        _send_message(db, order=order, recipient=recipient, body=confirm)
        from app.services.uk_compliance_audit_service import UkComplianceAuditService

        UkComplianceAuditService.record(
            db,
            event_type="opt_out.received",
            org_id=scoped_org,
            order_id=order.id,
            detail={"channel": "whatsapp", "workflow": "survey", "recipient_id": recipient.id},
        )
        logger.info(
            "%s opt_out order=%s recipient=%s org=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            scoped_org,
        )
        return {
            "handled": True,
            "opted_out": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "log_id": log_id,
        }

    logger.info("%s opt_out_no_active_recipient org=%s phone=%r", LOG_PREFIX, scoped_org, from_phone)
    return {"handled": True, "opted_out": True, "org_id": scoped_org, "log_id": log_id}


def try_handle_survey_whatsapp_inbound(
    db: Session,
    *,
    from_phone: str,
    body: str,
    org_id: str,
    log_id: int | None = None,
    inbound_message_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Survey-only WA inbound entry. Returns None when the message is not for survey WA
    (caller may route to interview/sales). Interview booking must not receive survey replies.
    """
    scoped_org = str(org_id or "").strip()
    if not scoped_org:
        return {"handled": False, "reason": "missing_org_id"}

    if is_survey_wa_opt_out_message(body):
        return handle_survey_wa_opt_out(
            db,
            from_phone=from_phone,
            body=body,
            org_id=scoped_org,
            log_id=log_id,
            inbound_message_id=inbound_message_id,
        )

    order, recipient = find_active_recipient(db, from_phone=from_phone, org_id=scoped_org)
    if not order or not recipient:
        return None

    return handle_inbound_reply(
        db,
        from_phone=from_phone,
        body=body,
        org_id=scoped_org,
        log_id=log_id,
        inbound_message_id=inbound_message_id,
    )


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
    if _conversation_already_started(recipient):
        logger.info(
            "%s send_first_question_skipped order=%s recipient=%s (already started)",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        return

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
    inbound_message_id: str | None = None,
) -> dict[str, Any]:
    """Advance an active WhatsApp survey when a contact replies."""
    order, recipient = find_active_recipient(db, from_phone=from_phone, org_id=org_id)
    if not order or not recipient:
        return {"handled": False, "reason": "no_active_survey"}

    payload = _recipient_result(recipient)
    if is_duplicate_inbound(payload, log_id=log_id, inbound_message_id=inbound_message_id):
        logger.info(
            "%s duplicate_inbound_skipped order=%s recipient=%s log_id=%s message_id=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            log_id,
            inbound_message_id,
        )
        return {
            "handled": True,
            "duplicate": True,
            "skipped": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "log_id": log_id,
            "inbound_message_id": inbound_message_id,
        }

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
            inbound_message_id=inbound_message_id,
        )

    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()

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
        payload = mark_inbound_processed(
            payload, log_id=log_id, inbound_message_id=inbound_message_id
        )
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
    payload = mark_inbound_processed(
        payload, log_id=log_id, inbound_message_id=inbound_message_id
    )
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
    inbound_message_id: str | None = None,
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
        payload = mark_inbound_processed(
            payload, log_id=log_id, inbound_message_id=inbound_message_id
        )
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
    payload = mark_inbound_processed(
        payload, log_id=log_id, inbound_message_id=inbound_message_id
    )
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
        "inbound_message_id": inbound_message_id,
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
    if _conversation_already_started(recipient):
        logger.info(
            "%s bootstrap_skipped order=%s recipient=%s (conversation already started)",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        return
    send_first_question(db, order=order, recipient=recipient, config=config)
