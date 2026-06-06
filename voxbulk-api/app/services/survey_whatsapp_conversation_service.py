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
from app.services.survey_step_bank_service import normalize_step_role
from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
)
from app.services.survey_flow_config_service import is_graph_flow, is_simulator_dry_run
from app.services.survey_builder_flow_service import (
    SurveyBuilderFlowError,
    _rating_answer_is_low,
    effective_order_config,
    log_builder_step_resolution,
    log_inbound_step_context,
    question_from_tell_us_more_template,
    resolve_conversation_step,
    resolve_next_conversation_step,
    should_use_builder_linear_runtime,
    survey_questions_from_config,
)
from app.services.survey_builder_runtime_service import (
    assert_runtime_template_send,
    has_builder_runtime,
    load_builder_runtime,
    reject_stale_graph_session,
    runtime_low_rating_threshold,
    runtime_tell_us_more_enabled,
)
from app.services.survey_flow_engine_service import SurveyFlowEngineService
from app.services.survey_outcome_send_service import SurveyOutcomeSendService
from app.services.survey_session_service import SurveySessionService
from app.services.survey_whatsapp_inbound_guard import is_duplicate_inbound, mark_inbound_processed
from app.services.telnyx_messaging_service import TelnyxMessageResult, TelnyxMessagingService

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
        raw = data if isinstance(data, dict) else {}
    except Exception:
        raw = {}
    return effective_order_config(raw)


def _question_outbound_body(
    db: Session,
    *,
    config: dict[str, Any],
    question: dict[str, Any],
    recipient: ServiceOrderRecipient,
    index: int,
    total: int,
) -> str:
    """Prefer approved WhatsApp template body — never append generic Option A/B/C for builder flows."""
    variables = _survey_variables(config, recipient)
    if question.get("template_id"):
        preview = survey_template_preview(
            db,
            config=config,
            template_id=question["template_id"],
            recipient=recipient,
        )
        body = str(preview.get("preview_body") or "").strip()
        if body:
            return body
    if should_use_builder_linear_runtime(config):
        raise SurveyBuilderFlowError(
            f"Builder step {index} template_id={question.get('template_id')} has no renderable body"
        )
    return format_question_message(question, index=index, total=total, variables=variables)


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


def _survey_variables(
    config: dict[str, Any],
    recipient: ServiceOrderRecipient | None = None,
    *,
    default_first_name: str = "Alex",
) -> dict[str, str]:
    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
    first = _first_name(recipient.name or "") if recipient else default_first_name
    if not first or first == "there":
        first = default_first_name
    return {
        "first_name": first,
        "clinic_name": org_name,
        "organisation_name": org_name,
        "business_name": org_name,
        "organiser_name": organiser,
        "survey_organiser": organiser,
    }


def survey_template_preview(
    db: Session,
    *,
    config: dict[str, Any],
    template_id: Any,
    recipient: ServiceOrderRecipient | None = None,
) -> dict[str, Any]:
    """Rendered WhatsApp template body + buttons for UI and simulator previews."""
    tid = str(template_id or "").strip()
    if not tid.isdigit():
        return {}
    row = SurveyWhatsappTemplateService.get_template(db, int(tid))
    if row is None:
        return {}
    variables = _survey_variables(config, recipient)
    preview = SurveyWhatsappTemplateService.build_preview(
        db,
        row,
        business_name=variables["organisation_name"],
        first_name=variables["first_name"],
    )
    buttons = preview.get("buttons") or []
    return {
        "template_id": row.id,
        "template_name": row.display_name or row.name,
        "preview_body": str(preview.get("rendered_body") or row.body_preview or "").strip(),
        "footer": str(preview.get("footer") or "").strip(),
        "buttons": buttons,
        "button_labels": [str(b.get("label") or b.get("text") or "") for b in buttons if isinstance(b, dict)],
        "status": str(row.status or "").upper(),
        "step_role": normalize_step_role(row.step_role or ""),
    }


def survey_question_display(
    db: Session,
    *,
    config: dict[str, Any],
    question: dict[str, Any],
    recipient: ServiceOrderRecipient | None,
    index: int,
    total: int,
) -> dict[str, Any]:
    """Prefer saved template preview; fall back to compact free-text for unapproved rows."""
    variables = _survey_variables(config, recipient)
    template_id = question.get("template_id")
    if template_id:
        preview = survey_template_preview(db, config=config, template_id=template_id, recipient=recipient)
        if preview.get("preview_body"):
            step_role = str(question.get("step_role") or preview.get("step_role") or "").strip()
            options = question.get("options") or []
            reply_type = str(question.get("reply_type") or "text").strip().lower()
            if step_role == "rating" or (
                reply_type == "choice" and isinstance(options, list) and len(options) >= 7
            ):
                choice_labels = [str(o) for o in options] if isinstance(options, list) else []
            else:
                choice_labels = preview.get("button_labels") or []
            return {
                **preview,
                "step_role": step_role,
                "reply_type": reply_type,
                "options": choice_labels,
                "body": preview["preview_body"],
                "text": preview["preview_body"],
                "uses_template": True,
            }
    body = format_question_message(question, index=index, total=total, variables=variables)
    return {
        "step_role": str(question.get("step_role") or ""),
        "reply_type": question.get("reply_type"),
        "options": question.get("options") or [],
        "text": _personalize_survey_text(str(question.get("text") or ""), variables),
        "body": body,
        "preview_body": body,
        "uses_template": False,
    }


def _personalize_survey_text(text: str, variables: dict[str, str]) -> str:
    from app.services.survey_whatsapp_template_service import _render_body_text

    raw = str(text or "").strip()
    if not raw:
        return raw
    if "{{" in raw:
        filler = [
            variables.get("first_name") or "there",
            variables.get("organisation_name") or "Your business",
            variables.get("organiser_name") or variables.get("organisation_name") or "there",
        ]
        max_idx = 0
        for match in re.finditer(r"\{\{(\d+)\}\}", raw):
            max_idx = max(max_idx, int(match.group(1)))
        while len(filler) < max_idx:
            filler.append("—")
        return _render_body_text(raw, filler[:max_idx]).strip()
    return _personalize(
        raw,
        first_name=variables.get("first_name") or "there",
        org_name=variables.get("organisation_name") or "Your business",
        organiser=variables.get("organiser_name") or variables.get("organisation_name") or "Your business",
    )


def format_question_message(
    question: dict[str, Any],
    *,
    index: int,
    total: int,
    variables: dict[str, str] | None = None,
    include_progress: bool = False,
) -> str:
    text = _personalize_survey_text(str(question.get("text") or "Question"), variables or {}) if variables else str(
        question.get("text") or "Question"
    ).strip()
    reply_type = str(question.get("reply_type") or "text").strip().lower()
    step_role = str(question.get("step_role") or "").strip().lower()
    options = question.get("options") or []
    if not isinstance(options, list):
        options = []

    lines = [f"Question {index} of {total}", text] if include_progress else [text]
    if reply_type in {"text", "long_text", "contact", "date"}:
        lines.append("Reply with your answer.")
    elif step_role == "rating" or (
        reply_type == "choice" and len(options) >= 7 and all(str(opt).strip().isdigit() for opt in options)
    ):
        low = str(options[0]).strip() if options else "0"
        high = str(options[-1]).strip() if options else "10"
        lines.append(f"Please reply with one number from {low} to {high}.")
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
                ServiceOrder.org_id == scoped_org,
                ServiceOrder.status.in_(("running", "draft")),
            )
        ).scalars()
    )

    for order in orders:
        if not is_whatsapp_survey_order(order):
            continue
        order_config = _order_config(order)
        if str(order.status or "").lower() == "draft" and not order_config.get("wa_builder_test"):
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
            if conv.get("intro_sent_at") and step == 0:
                return order, recipient
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


def _resolve_template_row(db: Session, template_id: Any) -> Any | None:
    try:
        row = SurveyWhatsappTemplateService.get_template(db, int(template_id))
    except (TypeError, ValueError):
        return None
    if row is None or str(row.status or "").upper() != "APPROVED":
        return None
    return row


def _resolve_question_template(
    db: Session,
    config: dict[str, Any],
    question: dict[str, Any] | None,
    *,
    order_id: str | None = None,
    session_id: str | None = None,
    step: int | None = None,
) -> Any:
    """Strict template lookup for builder flows — no step-bank fallback."""
    strict = should_use_builder_linear_runtime(config)
    tid = question.get("template_id") if isinstance(question, dict) else None
    if strict:
        if not tid:
            msg = (
                f"No template_id for step {step} (order={order_id}, session={session_id}); refusing fallback."
            )
            logger.error("%s %s", LOG_PREFIX, msg)
            raise SurveyBuilderFlowError(msg)
        return assert_runtime_template_send(
            db,
            config,
            tid,
            context=f"send_template step={step}",
            order_id=order_id,
            session_id=session_id,
            preview_hash=str(config.get("builder_runtime_hash") or "") or None,
        )
    if tid:
        row = _resolve_template_row(db, tid)
        if row is not None:
            return row
    return None


def _send_whatsapp_template(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    template_row: Any,
    variables: dict[str, str],
    body: str,
) -> TelnyxMessageResult:
    preview = SurveyWhatsappTemplateService.build_preview(
        db,
        template_row,
        business_name=variables.get("organisation_name") or "Your business",
        first_name=variables.get("first_name") or "there",
    )
    template_components = TelnyxWhatsappTemplateSyncService.build_components_for_row(
        template_row,
        variables=variables,
    )
    send_id = send_template_id_for_row(template_row)
    rendered = str(body or preview.get("rendered_body") or template_row.body_preview or "Survey message").strip()
    langs: list[str] = []
    for candidate in (template_row.language, "en_US", "en_GB", "en"):
        code = str(candidate or "").strip()
        if code and code not in langs:
            langs.append(code)
    if not langs:
        langs = ["en_US"]

    result = None
    for lang in langs:
        attempt = TelnyxMessagingService.send_whatsapp(
            db,
            org_id=order.org_id,
            to_number=recipient.phone or "",
            body=rendered,
            template_name=template_row.name,
            template_language=lang,
            template_components=template_components,
        )
        result = attempt
        if attempt.ok:
            return attempt
    if send_id:
        for lang in langs:
            attempt = TelnyxMessagingService.send_whatsapp(
                db,
                org_id=order.org_id,
                to_number=recipient.phone or "",
                body=rendered,
                template_id=send_id,
                template_language=lang,
                template_components=template_components,
            )
            result = attempt
            if attempt.ok:
                return attempt
    return result or TelnyxMessageResult(
        ok=False,
        status="failed",
        detail="WhatsApp template send failed",
        channel="whatsapp",
    )


def _send_message(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    body: str,
    config: dict[str, Any] | None = None,
    question: dict[str, Any] | None = None,
) -> bool:
    config = config or _order_config(order)
    if is_simulator_dry_run(config):
        return True

    variables = _survey_variables(config, recipient)
    template_row = None
    if question and question.get("template_id"):
        template_row = _resolve_question_template(
            db,
            config,
            question,
            order_id=order.id,
            step=int(question.get("sequence", 0)) + 1 if question.get("sequence") is not None else None,
        )
    if template_row is None and question is None:
        wa_template_id = config.get("wa_template_id")
        if wa_template_id:
            template_row = _resolve_template_row(db, wa_template_id)

    if template_row is not None:
        result = _send_whatsapp_template(
            db,
            order=order,
            recipient=recipient,
            template_row=template_row,
            variables=variables,
            body=body,
        )
    else:
        personalized = _personalize_survey_text(body, variables)
        result = TelnyxMessagingService.send_whatsapp(
            db,
            org_id=order.org_id,
            to_number=recipient.phone or "",
            body=personalized,
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
    if not result.ok:
        payload = _recipient_result(recipient)
        payload["error"] = result.detail or result.status
        payload["channel"] = result.channel or "whatsapp"
        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        recipient.status = "failed"
        db.add(recipient)
        db.commit()
    return bool(result.ok)


def send_survey_opening(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
) -> bool:
    """Send the approved start WhatsApp template; first question follows after the recipient replies."""
    if is_simulator_dry_run(config):
        return True
    if _conversation_already_started(recipient):
        return True

    flow = _whatsapp_flow(config)
    questions = flow.get("questions") or []
    total = len(questions) if isinstance(questions, list) else 0
    if is_graph_flow(config):
        from app.services.survey_flow_config_service import max_question_visits

        total = max_question_visits(config)

    variables = _survey_variables(config, recipient)
    template_row = _resolve_template_row(db, config.get("wa_template_id"))
    preview_body = ""
    if template_row is not None:
        preview = SurveyWhatsappTemplateService.build_preview(
            db,
            template_row,
            business_name=variables.get("organisation_name") or "Your business",
            first_name=variables.get("first_name") or "there",
        )
        preview_body = str(preview.get("rendered_body") or template_row.body_preview or "").strip()
    else:
        preview_body = _personalize_survey_text(str(flow.get("intro") or ""), variables)

    sent = _send_message(
        db,
        order=order,
        recipient=recipient,
        body=preview_body or "Tap below to start your survey.",
        config=config,
    )
    if not sent:
        return False

    payload = _recipient_result(recipient)
    payload["channel"] = "whatsapp"
    payload["wa_conversation"] = {
        "step": 0,
        "total": total,
        "answers": [],
        "intro_sent_at": datetime.utcnow().isoformat(),
    }
    recipient.status = "sent"
    _save_recipient_result(db, recipient, payload)
    logger.info("%s opening_sent order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id)
    return True


def send_first_question(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
) -> None:
    conv = _wa_conversation(_recipient_result(recipient))
    awaiting_start = bool(conv.get("intro_sent_at")) and int(conv.get("step") or 0) == 0

    if _conversation_already_started(recipient) and not awaiting_start:
        logger.info(
            "%s send_first_question_skipped order=%s recipient=%s (already started)",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        return

    if not awaiting_start and not is_simulator_dry_run(config) and config.get("wa_template_id"):
        send_survey_opening(db, order=order, recipient=recipient, config=config)
        return

    config = _order_config(order)
    runtime = load_builder_runtime(config)
    if runtime:
        reject_stale_graph_session(
            db,
            recipient_id=recipient.id,
            order_id=order.id,
            runtime=runtime,
        )
    questions = survey_questions_from_config(config)
    if not questions:
        return

    session_existing = SurveySessionService.get_by_recipient(db, recipient.id)
    if is_graph_flow(config) and not should_use_builder_linear_runtime(config):
        _send_first_question_graph(db, order=order, recipient=recipient, config=config, questions=questions)
        return

    if is_graph_flow(config) and should_use_builder_linear_runtime(config):
        logger.error(
            "%s builder_graph_blocked order=%s — stale graph fields were stripped; using builder linear",
            LOG_PREFIX,
            order.id,
        )

    q0 = resolve_conversation_step(
        config,
        1,
        order_id=order.id,
        session_id=session_existing.id if session_existing else None,
    )
    log_builder_step_resolution(
        phase="send_first_question",
        order_id=order.id,
        session_id=session_existing.id if session_existing else None,
        config=config,
        current_step=0,
        next_step=1,
        current_question=None,
        next_question=q0,
        payload_source="builder_step_sequence",
    )
    total = len(questions)
    body = _question_outbound_body(
        db,
        config=config,
        question=q0,
        recipient=recipient,
        index=1,
        total=total,
    )

    payload = _recipient_result(recipient)
    payload["channel"] = "whatsapp"
    payload["wa_conversation"] = {
        "step": 1,
        "total": total,
        "answers": [],
        "started_at": datetime.utcnow().isoformat(),
        "intro_sent_at": conv.get("intro_sent_at"),
        "current_template_id": q0.get("template_id"),
        "current_node_key": q0.get("node_key"),
        "builder_template_ids": config.get("builder_template_ids"),
        "builder_runtime_hash": (runtime or {}).get("hash") or config.get("builder_runtime_hash"),
    }
    session = SurveySessionService.start_linear_session(
        db,
        order=order,
        recipient=recipient,
        config=config,
        question_count=total,
    )
    payload = SurveySessionService.attach_session_to_result(payload, session)
    recipient.status = "in_progress"
    _save_recipient_result(db, recipient, payload)

    if _send_message(db, order=order, recipient=recipient, body=body, config=config, question=q0):
        logger.info(
            "%s first_question_sent order=%s recipient=%s template_id=%s template_name=%s source=builder_step_sequence",
            LOG_PREFIX,
            order.id,
            recipient.id,
            q0.get("template_id"),
            q0.get("template_name"),
        )


def _send_first_question_graph(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    questions: list[Any],
) -> None:
    from app.services.survey_flow_config_service import max_question_visits

    session, q, _body = SurveyFlowEngineService.start_graph_session(
        db, order=order, recipient=recipient, config=config
    )
    total = max_question_visits(config)
    variables = _survey_variables(config, recipient)
    body = format_question_message(q, index=1, total=total, variables=variables)
    conv = _wa_conversation(_recipient_result(recipient))
    payload = _recipient_result(recipient)
    payload["channel"] = "whatsapp"
    payload["wa_conversation"] = {
        "step": 1,
        "total": total,
        "answers": [],
        "started_at": datetime.utcnow().isoformat(),
        "intro_sent_at": conv.get("intro_sent_at"),
        "current_node_key": session.current_node_key,
    }
    payload = SurveySessionService.attach_session_to_result(payload, session)
    recipient.status = "in_progress"
    _save_recipient_result(db, recipient, payload)
    if _send_message(db, order=order, recipient=recipient, body=body, config=config, question=q):
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
        logger.info(
            "%s inbound_no_active_session from=%r org=%s body=%r",
            LOG_PREFIX,
            from_phone,
            org_id,
            str(body or "")[:80],
        )
        return {"handled": False, "reason": "no_active_survey"}

    logger.info(
        "%s inbound_matched order=%s recipient=%s step=%s body=%r",
        LOG_PREFIX,
        order.id,
        recipient.id,
        int(_wa_conversation(_recipient_result(recipient)).get("step") or 0),
        str(body or "")[:80],
    )

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
    runtime = load_builder_runtime(config)
    if runtime:
        reject_stale_graph_session(
            db,
            recipient_id=recipient.id,
            order_id=order.id,
            runtime=runtime,
        )
    questions = survey_questions_from_config(config)
    if not questions:
        logger.error("%s no_questions order=%s — refusing fallback", LOG_PREFIX, order.id)
        return {"handled": False, "reason": "no_questions"}

    session_row = SurveySessionService.get_active_by_recipient(db, recipient.id)
    log_inbound_step_context(
        order_id=order.id,
        session_id=session_row.id if session_row else None,
        recipient_id=recipient.id,
        step=int(_wa_conversation(payload).get("step") or 0),
        body=body,
        survey_type_id=str(config.get("survey_type_id") or "") or None,
    )

    conv = _wa_conversation(payload)
    step = int(conv.get("step") or 0)
    if step == 0 and conv.get("intro_sent_at"):
        send_first_question(db, order=order, recipient=recipient, config=config)
        db.refresh(recipient)
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "started": True,
            "log_id": log_id,
            "inbound_message_id": inbound_message_id,
        }

    flow = _whatsapp_flow(config)
    if is_graph_flow(config) and not should_use_builder_linear_runtime(config):
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
    if is_graph_flow(config) and should_use_builder_linear_runtime(config):
        logger.error(
            "%s builder_graph_blocked_inbound order=%s session=%s — refusing stale graph path",
            LOG_PREFIX,
            order.id,
            session_row.id if session_row else None,
        )

    org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()

    conv = _wa_conversation(payload)
    step = int(conv.get("step") or 0)
    total = int(conv.get("total") or len(questions))
    answers: list[dict[str, Any]] = list(conv.get("answers") or [])
    variables = _survey_variables(config, recipient)

    if step < 1 or step > total:
        return {"handled": False, "reason": "invalid_step"}

    try:
        if conv.get("tell_us_more_pending"):
            variables = _survey_variables(config, recipient)
            question = question_from_tell_us_more_template(
                db,
                config,
                business_name=variables.get("organisation_name") or "Your business",
                first_name=variables.get("first_name") or "Alex",
            )
            if question is None:
                raise SurveyBuilderFlowError("tell_us_more_pending but template missing")
        else:
            question = resolve_conversation_step(
                config,
                step,
                order_id=order.id,
                session_id=session_row.id if session_row else None,
            )
    except SurveyBuilderFlowError as exc:
        logger.error("%s linear_step_resolve_failed order=%s step=%s err=%s", LOG_PREFIX, order.id, step, exc)
        return {"handled": False, "reason": "step_resolve_failed", "detail": str(exc)}

    answer = match_answer(body, question)
    q_display = survey_question_display(
        db,
        config=config,
        question=question,
        recipient=recipient,
        index=step,
        total=total,
    )
    answers.append(
        {
            "step_role": str(question.get("step_role") or ""),
            "question": str(q_display.get("preview_body") or q_display.get("body") or question.get("text") or f"Question {step}"),
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

    if step < total or conv.get("tell_us_more_pending"):
        try:
            if conv.get("tell_us_more_pending"):
                next_step = step + 1
                next_q = resolve_conversation_step(
                    config,
                    next_step,
                    order_id=order.id,
                    session_id=session_row.id if session_row else None,
                )
                payload_source = "builder_step_sequence"
                conv.pop("tell_us_more_pending", None)
            elif (
                should_use_builder_linear_runtime(config)
                and runtime_tell_us_more_enabled(config)
                and not conv.get("tell_us_more_asked")
                and normalize_step_role(str(question.get("step_role") or "")) == "rating"
                and _rating_answer_is_low(answer, threshold=runtime_low_rating_threshold(config))
            ):
                variables = _survey_variables(config, recipient)
                next_q = question_from_tell_us_more_template(
                    db,
                    config,
                    business_name=variables.get("organisation_name") or "Your business",
                    first_name=variables.get("first_name") or "Alex",
                )
                if next_q is None:
                    raise SurveyBuilderFlowError("tell_us_more_template configured but could not resolve")
                next_step = step
                payload_source = "builder_tell_us_more_template"
                conv["tell_us_more_asked"] = True
                conv["tell_us_more_pending"] = True
            else:
                next_step, next_q, payload_source = resolve_next_conversation_step(
                    db,
                    config,
                    current_step=step,
                    answers=answers,
                    conv=conv,
                    order_id=order.id,
                    session_id=session_row.id if session_row else None,
                    business_name=variables.get("organisation_name") or "Your business",
                    first_name=variables.get("first_name") or "Alex",
                )
        except SurveyBuilderFlowError as exc:
            logger.error(
                "%s linear_next_step_failed order=%s step=%s err=%s",
                LOG_PREFIX,
                order.id,
                step + 1,
                exc,
            )
            return {"handled": False, "reason": "next_step_resolve_failed", "detail": str(exc)}
        log_builder_step_resolution(
            phase="send_next_question",
            order_id=order.id,
            session_id=session_row.id if session_row else None,
            config=config,
            current_step=step,
            next_step=next_step,
            current_question=question,
            next_question=next_q,
            payload_source=payload_source,
        )
        next_body = _question_outbound_body(
            db,
            config=config,
            question=next_q,
            recipient=recipient,
            index=next_step,
            total=total,
        )
        conv["step"] = next_step
        conv["current_template_id"] = next_q.get("template_id")
        conv["current_node_key"] = next_q.get("node_key")
        payload["wa_conversation"] = conv
        payload = mark_inbound_processed(
            payload, log_id=log_id, inbound_message_id=inbound_message_id
        )
        if next_step != step:
            SurveySessionService.advance_linear(
                db, session, config=config, from_step=step, to_step=next_step
            )
        recipient.status = "in_progress"
        _save_recipient_result(db, recipient, payload)
        sent = _send_message(
            db, order=order, recipient=recipient, body=next_body, config=config, question=next_q
        )
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "step": step,
            "next_step": next_step,
            "sent": sent,
            "payload_source": payload_source,
            "log_id": log_id,
        }

    closing_template = str(flow.get("closing") or "Thank you for your feedback.").strip()
    if has_builder_runtime(config):
        runtime = load_builder_runtime(config) or {}
        thank_tid = runtime.get("thank_you_template_id")
        if not thank_tid:
            logger.error("%s builder_missing_thank_you order=%s", LOG_PREFIX, order.id)
            return {"handled": False, "reason": "missing_thank_you_template"}
        thank_q = {"template_id": thank_tid, "step_role": "completion", "source": "order.config_json.builder_runtime"}
        try:
            assert_runtime_template_send(
                db,
                config,
                thank_tid,
                context="builder_completion",
                order_id=order.id,
                session_id=session_row.id if session_row else None,
                preview_hash=str(conv.get("builder_runtime_hash") or config.get("builder_runtime_hash") or "") or None,
            )
        except SurveyBuilderFlowError as exc:
            return {"handled": False, "reason": "thank_you_send_blocked", "detail": str(exc)}
        closing_body = _question_outbound_body(
            db,
            config=config,
            question=thank_q,
            recipient=recipient,
            index=len(questions) + 1,
            total=len(questions),
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
        _send_message(
            db,
            order=order,
            recipient=recipient,
            body=closing_body,
            config=config,
            question=thank_q,
        )
    else:
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
    if has_builder_runtime(config):
        logger.error(
            "%s builder_runtime_blocks_graph order=%s recipient=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        return {
            "handled": False,
            "reason": "builder_runtime_blocks_graph",
            "detail": "Graph resolver disabled for builder-selected surveys",
        }

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

    variables = _survey_variables(config, recipient)
    next_node_key = str(result.get("node_key") or session.current_node_key or "")
    next_q: dict[str, Any] = {}
    if session.flow_snapshot_json:
        try:
            snap = json.loads(session.flow_snapshot_json)
            node = {n["node_key"]: n for n in snap.get("nodes") or [] if isinstance(n, dict)}.get(next_node_key)
            if node:
                next_q = SurveyFlowEngineService._question_for_node(node)
        except Exception:
            next_q = {}
    next_step = int(session.question_visits or step) + 1
    next_body = (
        format_question_message(next_q, index=next_step, total=total, variables=variables)
        if next_q
        else str(result.get("body") or "")
    )
    conv["step"] = next_step
    conv["current_node_key"] = next_node_key or session.current_node_key
    payload["wa_conversation"] = conv
    payload = mark_inbound_processed(
        payload, log_id=log_id, inbound_message_id=inbound_message_id
    )
    recipient.status = "in_progress"
    _save_recipient_result(db, recipient, payload)
    sent = _send_message(
        db, order=order, recipient=recipient, body=next_body, config=config, question=next_q or None
    )
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
