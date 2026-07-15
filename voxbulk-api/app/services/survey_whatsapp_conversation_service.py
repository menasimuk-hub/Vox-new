"""Multi-step WhatsApp survey conversations (intro → questions → closing)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.services.messaging_log_service import normalize_e164
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService
from app.services.survey_dispatch_service import _first_name, _personalize, _uses_whatsapp
from app.services.survey_step_bank_service import normalize_step_role
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateService,
    resolve_sendable_template_row,
    template_row_must_send_as_session_text,
    template_row_needs_meta_approval,
)
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
)
from app.services.survey_flow_config_service import is_graph_flow, is_simulator_dry_run
from app.services.survey_wa_pacing_service import PACING_BRANCH, PACING_STEP, pause_before_outbound
from app.services.survey_builder_flow_service import (
    SurveyBuilderFlowError,
    effective_order_config,
    is_low_answer_for_tell_us_more,
    is_tell_us_more_branch_question,
    is_tell_us_more_trigger_question,
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
    tell_us_more_blocks_vague_followup,
)
from app.services.survey_wa_inbound_parse_service import (
    NormalizedWaInboundReply,
    START_ACTION,
    detect_start_action,
    detect_start_matcher,
    log_normalized_inbound,
    matches_start_trigger,
    parse_telnyx_wa_inbound_record,
    welcome_start_triggers_from_config,
)
from app.services.survey_flow_engine_service import SurveyFlowEngineService
from app.services.survey_outcome_send_service import SurveyOutcomeSendService
from app.services.survey_session_service import SurveySessionService
# WA_FINAL_FEEDBACK_YES_NO_ACTIVE — optional closing yes/no gate before open-text prompt.
from app.services.survey_wa_final_feedback_service import (
    begin_final_feedback_open_text,
    begin_final_feedback_yes_no,
    build_final_feedback_open_text_question,
    build_final_feedback_yes_no_question,
    closing_uses_yes_no_gate,
    final_feedback_settings,
    is_awaiting_final_feedback,
    log_final_feedback,
    mark_final_feedback_skipped,
    parse_final_feedback_yes_no,
    persist_final_feedback_text,
    persist_final_feedback_yes_no,
    runtime_final_feedback_enabled,
    is_bare_yes_no_reply,
)
from app.services.survey_wa_open_text_state import (
    is_awaiting_tell_us_more_reply,
    is_awaiting_vague_followup_reply,
    is_buttonless_open_text_question,
    mark_survey_started,
    mark_tell_us_more_answered,
    mark_tell_us_more_fired_for_step,
    mark_tell_us_more_prompt_sent,
    mark_vague_followup_answered,
    mark_vague_followup_prompt_sent,
    tell_us_more_already_fired_for_step,
)
from app.services.survey_wa_vague_negative_followup_service import (
    evaluate_vague_negative_followup,
    generate_followup_text,
    is_whatsapp_service_window_open,
    log_vague_negative_decision,
    merge_elaboration_into_answers,
    parse_auto_followup_from_question,
    should_ask_vague_negative_followup,
)
from app.services.survey_wa_test_mode_service import (
    log_first_question_resolution,
    log_inbound_normalized,
    log_lookup_result,
    log_start_detection,
    log_survey_test,
    log_wa_test_mode,
    resolve_trace_id,
)
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


def _order_config(order: ServiceOrder, db: Session | None = None) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        raw = data if isinstance(data, dict) else {}
    except Exception:
        raw = {}
    config = effective_order_config(raw)
    if db is not None:
        from app.services.survey_builder_runtime_service import hydrate_missing_tell_us_more_on_config

        config = hydrate_missing_tell_us_more_on_config(db, config)
    return config


def _question_outbound_body(
    db: Session,
    *,
    config: dict[str, Any],
    question: dict[str, Any],
    recipient: ServiceOrderRecipient,
    index: int,
    total: int,
    org_id: str | None = None,
) -> str:
    """Prefer approved WhatsApp template body — never append generic Option A/B/C for builder flows."""
    variables = _survey_variables(config, recipient, db=db, org_id=org_id)
    if question.get("template_id"):
        preview = survey_template_preview(
            db,
            config=config,
            template_id=question["template_id"],
            recipient=recipient,
            org_id=org_id,
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


def _save_recipient_result(
    db: Session,
    recipient: ServiceOrderRecipient,
    payload: dict[str, Any],
    *,
    enqueue_translation: bool = False,
) -> None:
    recipient.result_json = json.dumps(payload, ensure_ascii=False)
    recipient.updated_at = datetime.utcnow()
    db.add(recipient)
    db.commit()
    # Always sweep for untranslated text answers: this is idempotent and cheap
    # (it only enqueues non-English, not-yet-translated typed answers), so it
    # covers every save path — mid-survey, tell-us-more, and final feedback.
    _enqueue_text_answer_translation(recipient, payload)


def _enqueue_text_answer_translation(recipient: ServiceOrderRecipient, payload: dict[str, Any]) -> None:
    conv = payload.get("wa_conversation") if isinstance(payload.get("wa_conversation"), dict) else {}
    answers = conv.get("answers") if isinstance(conv.get("answers"), list) else []
    if not answers:
        return
    from app.services.survey_wa_translation_service import SurveyWaTranslationService

    for idx, answer in enumerate(answers):
        if not isinstance(answer, dict):
            continue
        # Voice notes are translated by the voice-note pipeline after transcription.
        if str(answer.get("answer_source") or "") == "voice_note":
            continue
        # Skip answers already translated (or confirmed English).
        if str(answer.get("translation_status") or "") in {"completed", "not_needed"}:
            continue
        if str(answer.get("translated_text") or "").strip():
            continue
        text = str(answer.get("answer") or answer.get("answer_text") or "").strip()
        if not text:
            continue
        if not SurveyWaTranslationService.needs_translation(text, answer.get("detected_language")):
            continue
        SurveyWaTranslationService.enqueue_answer_translation(recipient.id, answer_index=idx)


def _survey_variables(
    config: dict[str, Any],
    recipient: ServiceOrderRecipient | None = None,
    *,
    db: Session | None = None,
    org_id: str | None = None,
    default_first_name: str = "Alex",
) -> dict[str, str]:
    if db is not None and org_id:
        from app.services.survey_wa_org_context_service import resolve_survey_organisation_name

        org_name = resolve_survey_organisation_name(db, org_id=str(org_id), config=config)
    else:
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
    org_id: str | None = None,
) -> dict[str, Any]:
    """Rendered WhatsApp template body + buttons for UI and simulator previews."""
    tid = str(template_id or "").strip()
    if not tid.isdigit():
        return {}
    row = SurveyWhatsappTemplateService.get_template(db, int(tid))
    if row is None:
        return {}
    variables = _survey_variables(config, recipient, db=db, org_id=org_id)
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
    org_id: str | None = None,
) -> dict[str, Any]:
    """Prefer saved template preview; fall back to compact free-text for unapproved rows."""
    variables = _survey_variables(config, recipient, db=db, org_id=org_id)
    template_id = question.get("template_id")
    if template_id:
        preview = survey_template_preview(
            db, config=config, template_id=template_id, recipient=recipient, org_id=org_id
        )
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
    if is_buttonless_open_text_question(question):
        lines.append("Reply with text or a voice note.")
    elif reply_type in {"text", "long_text", "contact", "date"}:
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


def _inbound_record_from_reply(reply: NormalizedWaInboundReply) -> dict[str, Any] | None:
    fields = reply.extracted_fields if isinstance(reply.extracted_fields, dict) else {}
    record = fields.get("inbound_record")
    return record if isinstance(record, dict) else None


def _try_voice_note_reply(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    payload: dict[str, Any],
    conv: dict[str, Any],
    question: dict[str, Any] | None,
    reply: NormalizedWaInboundReply,
    inbound_message_id: str | None,
    log_id: int | None,
    session_id: str | None,
    answer_context: str,
    step_index: int,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    from app.services.survey_wa_open_text_service import VOICE_NOTE_FALLBACK_MESSAGE, merge_voice_metadata
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    if not SurveyWaVoiceNoteService.is_inbound_voice(reply):
        return None

    result = SurveyWaVoiceNoteService.prepare_voice_answer(
        db,
        order=order,
        recipient=recipient,
        payload=payload,
        conv=conv,
        question=question,
        reply=reply,
        inbound_message_id=inbound_message_id,
        log_id=log_id,
        session_id=session_id,
        answer_context=answer_context,
        step_index=step_index,
        record=_inbound_record_from_reply(reply),
        config=config,
    )
    if result is None:
        return None
    if result.get("rejected"):
        sent = _send_freeform_whatsapp(
            db,
            order=order,
            recipient=recipient,
            body=str(result.get("fallback_message") or VOICE_NOTE_FALLBACK_MESSAGE),
        )
        return {"handled": True, "voice_rejected": True, "sent": sent, "reason": result.get("reason")}
    if result.get("duplicate"):
        duplicate_result: dict[str, Any] = {
            "handled": True,
            "duplicate": True,
            "voice_note": True,
            "job_id": result.get("job_id"),
        }
        if result.get("accepted"):
            duplicate_result["accepted"] = True
            duplicate_result["answer"] = result.get("answer")
            duplicate_result["transcript_ready"] = result.get("transcript_ready")
        return duplicate_result
    if result.get("accepted") and answer_context == "followup":
        answer_entry = dict(result.get("answer") or {})
        answers = list(conv.get("answers") or [])
        if answers and isinstance(answer_entry, dict):
            answers[-1] = merge_voice_metadata(answers[-1], answer_entry)
            text = str(answer_entry.get("answer_text") or answer_entry.get("answer") or "").strip()
            if text:
                merge_elaboration_into_answers(answers, text)
            conv["answers"] = answers
        result["answers"] = answers
    return result


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


def _is_awaiting_start(conv: dict[str, Any], recipient: ServiceOrderRecipient) -> bool:
    step = int(conv.get("step") or 0)
    if step != 0:
        return False
    if conv.get("intro_sent_at"):
        return True
    return str(recipient.status or "").lower() in {"sent", "in_progress"}


def _coerce_inbound_reply(body: str, inbound_reply: NormalizedWaInboundReply | None) -> NormalizedWaInboundReply:
    if inbound_reply is not None:
        return inbound_reply
    text = str(body or "").strip()
    reply = NormalizedWaInboundReply(
        raw_text=text,
        normalized_answer=text,
        button_text=text,
    )
    reply.normalized_action = detect_start_action(reply)
    return reply


def _is_valid_start_action(
    reply: NormalizedWaInboundReply,
    config: dict[str, Any],
    *,
    awaiting_start: bool,
) -> bool:
    if not awaiting_start:
        return False
    extra = welcome_start_triggers_from_config(config)
    action, _matcher = detect_start_matcher(reply, extra_triggers=extra)
    if action == START_ACTION:
        return True
    # Welcome template only exposes Start/quick-reply — structured button tap on step 0 counts.
    if reply.button_title or reply.button_id or reply.button_payload:
        return True
    if reply.message_type in {"button", "interactive", "quick_reply"} and (
        reply.button_title or reply.button_id or reply.button_payload
    ):
        return True
    return matches_start_trigger(reply.raw_text or reply.normalized_answer, extra)


def _log_start_transition_failure(
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    reply: NormalizedWaInboundReply,
    conv: dict[str, Any],
    session_id: str | None,
) -> None:
    logger.error(
        "%s awaiting_start_unparsed order=%s recipient=%s session=%s conv_step=%s "
        "raw_text=%r button_title=%r button_id=%r button_payload=%r message_type=%s fields=%s",
        LOG_PREFIX,
        order.id,
        recipient.id,
        session_id,
        int(conv.get("step") or 0),
        reply.raw_text[:120],
        reply.button_title[:80],
        reply.button_id[:80],
        reply.button_payload[:80],
        reply.message_type,
        reply.extracted_fields,
    )


def find_active_recipient(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None = None,
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None]:
    """Find a running WhatsApp survey recipient awaiting a reply (scoped to org_id)."""
    order, recipient, _via = find_active_recipient_for_inbound(
        db, from_phone=from_phone, org_id=org_id
    )
    return order, recipient


def _match_recipient_conversation(
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    *,
    session_step: int | None = None,
) -> bool:
    if str(recipient.status or "").lower() not in {"sent", "in_progress"}:
        return False
    conv = _wa_conversation(_recipient_result(recipient))
    step = int(conv.get("step") or 0)
    total = int(conv.get("total") or 0)
    if session_step is not None and int(session_step) == 0:
        return step == 0 or bool(conv.get("intro_sent_at"))
    if step == 0 and str(recipient.status or "").lower() in {"sent", "in_progress"}:
        return True
    if conv.get("intro_sent_at") and step == 0:
        return True
    if step >= 1 and step <= max(total, 1):
        return True
    return False


def _find_active_recipient_in_org(
    db: Session,
    *,
    org_id: str,
    needles: set[str],
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None]:
    orders = list(
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.service_code == "survey",
                ServiceOrder.org_id == org_id,
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
            rec_phones = _phone_candidates(recipient.phone or "")
            if not needles.intersection(rec_phones):
                continue
            if _match_recipient_conversation(order, recipient):
                return order, recipient
    return None, None


def _find_active_recipient_by_session_phone(
    db: Session,
    *,
    needles: set[str],
    org_id: str | None = None,
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None]:
    stmt = (
        select(SurveySession, ServiceOrder, ServiceOrderRecipient)
        .join(ServiceOrderRecipient, ServiceOrderRecipient.id == SurveySession.recipient_id)
        .join(ServiceOrder, ServiceOrder.id == SurveySession.order_id)
        .where(
            SurveySession.status == "active",
            ServiceOrder.service_code == "survey",
            ServiceOrder.status.in_(("running", "draft")),
        )
        .order_by(SurveySession.updated_at.desc())
    )
    if org_id:
        stmt = stmt.where(SurveySession.org_id == org_id)

    for session, order, recipient in db.execute(stmt).all():
        if not is_whatsapp_survey_order(order):
            continue
        order_config = _order_config(order)
        if str(order.status or "").lower() == "draft" and not order_config.get("wa_builder_test"):
            continue
        rec_phones = _phone_candidates(recipient.phone or "")
        if not needles.intersection(rec_phones):
            continue
        if _match_recipient_conversation(order, recipient, session_step=int(session.current_step or 0)):
            return order, recipient
    return None, None


def _log_active_recipient_miss(
    *,
    from_phone: str,
    org_id: str | None,
    needles: set[str],
) -> None:
    logger.info(
        "%s active_recipient_miss from_phone=%r org_id=%s needle_count=%s needles=%s",
        LOG_PREFIX,
        from_phone,
        org_id,
        len(needles),
        sorted(needles)[:5],
    )


def log_welcome_sent_without_active_session(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None,
) -> bool:
    """Return True when a recent welcome exists for this phone but no active session row."""
    needles = _phone_candidates(from_phone)
    if not needles:
        return False
    rows = db.execute(
        select(ServiceOrder, ServiceOrderRecipient)
        .join(ServiceOrderRecipient, ServiceOrderRecipient.order_id == ServiceOrder.id)
        .where(
            ServiceOrder.service_code == "survey",
            ServiceOrder.status.in_(("running", "draft")),
        )
        .order_by(ServiceOrder.updated_at.desc())
    ).all()
    for order, recipient in rows:
        if not is_whatsapp_survey_order(order):
            continue
        rec_phones = _phone_candidates(recipient.phone or "")
        if not needles.intersection(rec_phones):
            continue
        conv = _wa_conversation(_recipient_result(recipient))
        if not conv.get("intro_sent_at"):
            continue
        if int(conv.get("step") or 0) > 0:
            continue
        session = SurveySessionService.get_active_by_recipient(db, recipient.id)
        if session is None:
            logger.error(
                "%s welcome_sent_but_no_active_session order=%s recipient=%s org_id=%s "
                "from_phone=%r recipient_status=%s conv_step=%s",
                LOG_PREFIX,
                order.id,
                recipient.id,
                org_id,
                from_phone,
                recipient.status,
                int(conv.get("step") or 0),
            )
            return True
    return False


def find_awaiting_welcome_recipient(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None = None,
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None]:
    """Latest running survey recipient with welcome sent, step 0, matching phone."""
    needles = _phone_candidates(from_phone)
    if not needles:
        return None, None
    scoped_org = str(org_id or "").strip()
    rows = db.execute(
        select(ServiceOrder, ServiceOrderRecipient)
        .join(ServiceOrderRecipient, ServiceOrderRecipient.order_id == ServiceOrder.id)
        .where(
            ServiceOrder.service_code == "survey",
            ServiceOrder.status.in_(("running", "draft")),
        )
        .order_by(ServiceOrder.updated_at.desc())
    ).all()
    for order, recipient in rows:
        if scoped_org and str(order.org_id) != scoped_org:
            continue
        if not is_whatsapp_survey_order(order):
            continue
        order_config = _order_config(order)
        if str(order.status or "").lower() == "draft" and not order_config.get("wa_builder_test"):
            continue
        rec_phones = _phone_candidates(recipient.phone or "")
        if not needles.intersection(rec_phones):
            continue
        conv = _wa_conversation(_recipient_result(recipient))
        if not conv.get("intro_sent_at"):
            continue
        if int(conv.get("step") or 0) != 0:
            continue
        if str(recipient.status or "").lower() not in {"sent", "in_progress", "pending"}:
            continue
        return order, recipient
    return None, None


def phone_in_recent_survey_welcome_flow(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None = None,
) -> bool:
    order, recipient = find_awaiting_welcome_recipient(db, from_phone=from_phone, org_id=org_id)
    return order is not None and recipient is not None


def recover_survey_session_from_welcome(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
) -> SurveySession | None:
    """Recreate awaiting-start session when welcome exists but session row is missing/broken."""
    if not has_builder_runtime(config):
        log_survey_test(
            "error",
            order=order,
            recipient=recipient,
            config=config,
            handler="survey_whatsapp_conversation_service.recover_survey_session_from_welcome",
            result="fail",
            reason="builder_runtime_missing",
        )
        return None
    try:
        session = SurveySessionService.ensure_awaiting_start_session(
            db,
            order=order,
            recipient=recipient,
            config=config,
        )
    except Exception as exc:
        log_survey_test(
            "error",
            order=order,
            recipient=recipient,
            config=config,
            handler="survey_whatsapp_conversation_service.recover_survey_session_from_welcome",
            result="fail",
            reason="session_recovery_failed",
            extra={"error": str(exc)},
        )
        return None
    logger.info(
        "%s survey_session_recovered_from_welcome order=%s recipient=%s session_id=%s",
        LOG_PREFIX,
        order.id,
        recipient.id,
        session.id,
    )
    log_survey_test(
        "session_created",
        order=order,
        recipient=recipient,
        session=session,
        config=config,
        handler="survey_whatsapp_conversation_service.recover_survey_session_from_welcome",
        result="ok",
        reason="survey_session_recovered_from_welcome",
        current_step=0,
    )
    return session


def _diagnose_inbound_lookup(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None,
    order: ServiceOrder | None,
    recipient: ServiceOrderRecipient | None,
    match_via: str | None,
) -> str:
    if not order or not recipient:
        if not _phone_candidates(from_phone):
            return "phone_mismatch"
        welcome_order, welcome_recipient = find_awaiting_welcome_recipient(
            db, from_phone=from_phone, org_id=org_id
        )
        if welcome_order and welcome_recipient:
            session = SurveySessionService.get_active_by_recipient(db, welcome_recipient.id)
            if session is None:
                return "recipient_found_no_session"
            if str(session.status or "").lower() != "active":
                return "session_found_wrong_status"
        return "no_recipient_for_phone"
    config = _order_config(order)
    if not load_builder_runtime(config):
        return "builder_runtime_missing"
    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    if session is None:
        return "recipient_found_no_session"
    if str(session.status or "").lower() != "active":
        return "session_found_wrong_status"
    conv = _wa_conversation(_recipient_result(recipient))
    if int(conv.get("step") or 0) == 0 and not conv.get("intro_sent_at"):
        return "awaiting_start_missing"
    if org_id and str(order.org_id) != str(org_id) and match_via == "session_phone_cross_org":
        return "org_mismatch"
    return "session_found_ok"


def find_active_recipient_for_inbound(
    db: Session,
    *,
    from_phone: str,
    org_id: str | None = None,
) -> tuple[ServiceOrder | None, ServiceOrderRecipient | None, str | None]:
    """Resolve active survey recipient for inbound; returns (order, recipient, match_via)."""
    scoped_org = str(org_id or "").strip()
    needles = _phone_candidates(from_phone)
    if not needles:
        _log_active_recipient_miss(from_phone=from_phone, org_id=scoped_org or None, needles=needles)
        return None, None, None

    try:
        normalized_phone = normalize_e164(from_phone)
    except ValueError:
        normalized_phone = str(from_phone or "").strip()

    logger.info(
        "%s active_recipient_lookup from_phone=%r normalized=%r org_id=%s needles=%s",
        LOG_PREFIX,
        from_phone,
        normalized_phone,
        scoped_org or None,
        sorted(needles)[:5],
    )
    log_survey_test(
        "lookup_started",
        phone=from_phone,
        org_id=scoped_org or None,
        handler="survey_whatsapp_conversation_service.find_active_recipient_for_inbound",
        result="pending",
        extra={"needles": sorted(needles)[:5]},
    )

    if scoped_org:
        order, recipient = _find_active_recipient_in_org(db, org_id=scoped_org, needles=needles)
        if order and recipient:
            session = SurveySessionService.get_active_by_recipient(db, recipient.id)
            logger.info(
                "%s active_recipient_matched via=org_recipient order=%s recipient=%s session_id=%s",
                LOG_PREFIX,
                order.id,
                recipient.id,
                session.id if session else None,
            )
            cfg = _order_config(order)
            log_lookup_result(
                trace_id=resolve_trace_id(config=cfg, recipient=recipient),
                order=order,
                recipient=recipient,
                session=session,
                config=cfg,
                reason=_diagnose_inbound_lookup(
                    db,
                    from_phone=from_phone,
                    org_id=scoped_org,
                    order=order,
                    recipient=recipient,
                    match_via="org_recipient",
                ),
                handler="survey_whatsapp_conversation_service.find_active_recipient_for_inbound",
                phone=from_phone,
                org_id=scoped_org,
                extra={"match_via": "org_recipient"},
            )
            return order, recipient, "org_recipient"

    order, recipient = _find_active_recipient_by_session_phone(
        db, needles=needles, org_id=scoped_org or None
    )
    if order and recipient:
        session = SurveySessionService.get_active_by_recipient(db, recipient.id)
        logger.info(
            "%s active_recipient_matched via=session_phone order=%s recipient=%s session_id=%s org_id=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            session.id if session else None,
            order.org_id,
        )
        return order, recipient, "session_phone"

    if scoped_org:
        order, recipient = _find_active_recipient_by_session_phone(db, needles=needles, org_id=None)
        if order and recipient:
            session = SurveySessionService.get_active_by_recipient(db, recipient.id)
            logger.warning(
                "%s active_recipient_matched via=session_phone_cross_org webhook_org=%s order_org=%s "
                "recipient=%s session_id=%s",
                LOG_PREFIX,
                scoped_org,
                order.org_id,
                recipient.id,
                session.id if session else None,
            )
            return order, recipient, "session_phone_cross_org"

    log_welcome_sent_without_active_session(db, from_phone=from_phone, org_id=scoped_org or None)
    _log_active_recipient_miss(from_phone=from_phone, org_id=scoped_org or None, needles=needles)
    reason = _diagnose_inbound_lookup(
        db,
        from_phone=from_phone,
        org_id=scoped_org or None,
        order=None,
        recipient=None,
        match_via=None,
    )
    welcome_order, welcome_recipient = find_awaiting_welcome_recipient(
        db, from_phone=from_phone, org_id=scoped_org or None
    )
    cfg = _order_config(welcome_order) if welcome_order else None
    log_lookup_result(
        trace_id=resolve_trace_id(config=cfg, recipient=welcome_recipient),
        order=welcome_order,
        recipient=welcome_recipient,
        session=SurveySessionService.get_active_by_recipient(db, welcome_recipient.id)
        if welcome_recipient
        else None,
        config=cfg,
        reason=reason,
        handler="survey_whatsapp_conversation_service.find_active_recipient_for_inbound",
        phone=from_phone,
        org_id=scoped_org or None,
    )
    return None, None, None


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

    logger.info(
        "%s opt_out_no_active_recipient org=%s phone_hash=%s",
        LOG_PREFIX,
        scoped_org,
        hashlib.sha256((from_phone or "").encode()).hexdigest()[:12] if from_phone else "",
    )
    return {"handled": True, "opted_out": True, "org_id": scoped_org, "log_id": log_id}


def try_handle_survey_whatsapp_inbound(
    db: Session,
    *,
    from_phone: str,
    body: str,
    org_id: str,
    log_id: int | None = None,
    inbound_message_id: str | None = None,
    inbound_reply: NormalizedWaInboundReply | None = None,
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

    order, recipient, _via = find_active_recipient_for_inbound(
        db, from_phone=from_phone, org_id=scoped_org
    )
    if not order or not recipient:
        welcome_order, welcome_recipient = find_awaiting_welcome_recipient(
            db, from_phone=from_phone, org_id=scoped_org
        )
        if welcome_order and welcome_recipient:
            config = _order_config(welcome_order)
            trace_id = resolve_trace_id(config=config, recipient=welcome_recipient)
            log_survey_test(
                "inbound_received",
                trace_id=trace_id,
                order=welcome_order,
                recipient=welcome_recipient,
                config=config,
                phone=from_phone,
                org_id=scoped_org,
                handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
                result="recover",
                reason="recipient_found_no_session",
                extra={"body": str(body or "")[:120]},
            )
            if inbound_reply is not None:
                log_inbound_normalized(
                    trace_id=trace_id,
                    config=config,
                    order=welcome_order,
                    recipient=welcome_recipient,
                    session=None,
                    raw_body=str(body or ""),
                    message_type=inbound_reply.message_type,
                    button_title=inbound_reply.button_title,
                    button_id=inbound_reply.button_id,
                    normalized_text=inbound_reply.normalized_answer,
                    normalized_action=inbound_reply.normalized_action,
                    handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
                )
            session = SurveySessionService.get_active_by_recipient(db, welcome_recipient.id)
            if session is None:
                session = recover_survey_session_from_welcome(
                    db,
                    order=welcome_order,
                    recipient=welcome_recipient,
                    config=config,
                )
            if session is not None:
                order, recipient = welcome_order, welcome_recipient
            elif log_welcome_sent_without_active_session(db, from_phone=from_phone, org_id=scoped_org):
                log_survey_test(
                    "fallback_blocked",
                    trace_id=trace_id,
                    order=welcome_order,
                    recipient=welcome_recipient,
                    config=config,
                    phone=from_phone,
                    org_id=scoped_org,
                    handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
                    result="fail",
                    reason="welcome_sent_but_no_active_session",
                )
                return {
                    "handled": False,
                    "reason": "welcome_sent_but_no_active_session",
                    "org_id": scoped_org,
                    "from_phone": from_phone,
                    "trace_id": trace_id,
                }
        elif log_welcome_sent_without_active_session(db, from_phone=from_phone, org_id=scoped_org):
            log_vague_negative_decision(
                "try_handle_no_recipient",
                handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
                extra={"from_phone": from_phone, "body": str(body or "")[:120], "reason": "welcome_sent_but_no_active_session"},
            )
            return {
                "handled": False,
                "reason": "welcome_sent_but_no_active_session",
                "org_id": scoped_org,
                "from_phone": from_phone,
            }
        log_vague_negative_decision(
            "try_handle_no_recipient",
            handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
            extra={"from_phone": from_phone, "body": str(body or "")[:120], "reason": "no_active_survey_recipient"},
        )
        return None

    config = _order_config(order)
    trace_id = resolve_trace_id(config=config, recipient=recipient)
    log_survey_test(
        "inbound_received",
        trace_id=trace_id,
        order=order,
        recipient=recipient,
        config=config,
        phone=from_phone,
        org_id=scoped_org,
        handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
        result="ok",
        extra={"body": str(body or "")[:120]},
    )
    if inbound_reply is not None:
        session_row = SurveySessionService.get_active_by_recipient(db, recipient.id)
        log_inbound_normalized(
            trace_id=trace_id,
            config=config,
            order=order,
            recipient=recipient,
            session=session_row,
            raw_body=str(body or ""),
            message_type=inbound_reply.message_type,
            button_title=inbound_reply.button_title,
            button_id=inbound_reply.button_id,
            normalized_text=inbound_reply.normalized_answer,
            normalized_action=inbound_reply.normalized_action,
            handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
        )

    log_vague_negative_decision(
        "try_handle_dispatch",
        order_id=order.id,
        recipient_id=recipient.id,
        handler="survey_whatsapp_conversation_service.try_handle_survey_whatsapp_inbound",
        extra={"body": str(body or "")[:120], "log_id": log_id},
    )
    return handle_inbound_reply(
        db,
        from_phone=from_phone,
        body=body,
        org_id=scoped_org,
        log_id=log_id,
        inbound_message_id=inbound_message_id,
        inbound_reply=inbound_reply,
    )


def _resolve_template_row(db: Session, template_id: Any) -> Any | None:
    try:
        row = SurveyWhatsappTemplateService.get_template(db, int(template_id))
    except (TypeError, ValueError):
        return None
    if row is None:
        return None
    if template_row_needs_meta_approval(row):
        return resolve_sendable_template_row(db, row)
    return row


def _is_branch_system_template(question: dict[str, Any] | None) -> bool:
    """Final-feedback / tell-us-more templates sit outside builder step_sequence."""
    if not isinstance(question, dict):
        return False
    role = str(question.get("step_role") or "").strip().lower()
    return role in {"final_feedback_yes_no", "final_feedback_text", "tell_us_more", "reason"}


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
    if strict and _is_branch_system_template(question):
        if tid:
            row = _resolve_template_row(db, tid)
            if row is not None:
                return row
        msg = (
            f"Branch template missing or unapproved for step_role={question.get('step_role') if isinstance(question, dict) else None} "
            f"(order={order_id}, session={session_id})"
        )
        logger.error("%s %s", LOG_PREFIX, msg)
        raise SurveyBuilderFlowError(msg)
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
    sendable = resolve_sendable_template_row(db, template_row) or template_row
    preview = SurveyWhatsappTemplateService.build_preview(
        db,
        sendable,
        business_name=variables.get("organisation_name") or "Your business",
        first_name=variables.get("first_name") or "there",
    )
    template_components = TelnyxWhatsappTemplateSyncService.build_components_for_row(
        sendable,
        variables=variables,
        db=db,
    )
    from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

    send_id = WaTemplateProfilePushService.send_template_id_for_active_profile(
        db,
        sendable,
        org_id=order.org_id,
        service_code="survey",
    )
    rendered = str(body or preview.get("rendered_body") or sendable.body_preview or "Survey message").strip()
    langs: list[str] = []
    for candidate in (sendable.language, "en_US", "en_GB", "en"):
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
            template_name=sendable.name,
            template_language=lang,
            template_components=template_components,
            meter_usage=False,
            service_code="survey",
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
                meter_usage=False,
                service_code="survey",
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
    pacing: str | None = None,
    template_row: Any | None = None,
) -> bool:
    config = config or _order_config(order)
    if is_simulator_dry_run(config):
        return True

    pause_before_outbound(
        pacing=pacing,
        order_id=str(order.id),
        recipient_id=str(recipient.id),
        skip=False,
    )

    variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
    resolved_template = template_row
    if resolved_template is None and question and question.get("template_id"):
        resolved_template = _resolve_question_template(
            db,
            config,
            question,
            order_id=order.id,
            step=int(question.get("sequence", 0)) + 1 if question.get("sequence") is not None else None,
        )
    if resolved_template is None and question is None and template_row is None:
        wa_template_id = config.get("wa_template_id")
        if wa_template_id:
            resolved_template = _resolve_template_row(db, wa_template_id)

    use_row = resolved_template
    session_text_only = is_tell_us_more_branch_question(question) or (
        use_row is not None and template_row_must_send_as_session_text(use_row)
    )
    if use_row is not None and template_row_needs_meta_approval(use_row) and not session_text_only:
        use_row = resolve_sendable_template_row(db, use_row)
        if use_row is None:
            logger.error(
                "%s template_not_sendable_on_meta order=%s recipient=%s template_id=%s",
                LOG_PREFIX,
                order.id,
                recipient.id,
                getattr(resolved_template, "id", None),
            )
            result = TelnyxMessageResult(
                ok=False,
                status="failed",
                detail="WhatsApp template not approved on Meta",
                channel="whatsapp",
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
            return False

    if use_row is not None and template_row_needs_meta_approval(use_row) and not session_text_only:
        # Buttoned welcome/middle templates only — tell-us-more, closing, thank-you stay session text.
        result = _send_whatsapp_template(
            db,
            order=order,
            recipient=recipient,
            template_row=use_row,
            variables=variables,
            body=body,
        )
    else:
        # Buttonless templates (thank_you, tell_us_more, etc.) are session free-form text —
        # no Meta approval required once the customer has replied (24h window).
        personalized = _personalize_survey_text(body, variables)
        if use_row is not None and not personalized:
            preview = SurveyWhatsappTemplateService.build_preview(
                db,
                use_row,
                business_name=variables.get("organisation_name") or "Your business",
                first_name=variables.get("first_name") or "there",
            )
            personalized = str(preview.get("rendered_body") or use_row.body_preview or body).strip()
        result = TelnyxMessagingService.send_whatsapp(
            db,
            org_id=order.org_id,
            to_number=recipient.phone or "",
            body=personalized,
            meter_usage=False,
            service_code="survey",
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


def _log_opening_session(
    event: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    session: SurveySession | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    awaiting = (
        SurveySessionService.flow_snapshot_awaiting_start(session) if session is not None else None
    )
    logger.info(
        "survey_opening_session_%s order_id=%s recipient_id=%s session_id=%s session_status=%s "
        "current_step=%s flow_mode=%s awaiting_start=%s trace_id=%s extra=%s",
        event,
        order.id,
        recipient.id,
        session.id if session else None,
        session.status if session else None,
        int(session.current_step or 0) if session else None,
        session.flow_mode if session else None,
        awaiting,
        resolve_trace_id(config=config, recipient=recipient),
        extra or {},
    )


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
    builder_questions = survey_questions_from_config(config)
    if builder_questions:
        total = len(builder_questions)

    question_count = total or len(builder_questions)
    if question_count < 1:
        logger.error(
            "%s opening_no_questions order=%s recipient=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        _log_opening_session(
            "missing",
            order=order,
            recipient=recipient,
            config=config,
            extra={"reason": "no_questions"},
        )
        return False

    _log_opening_session(
        "ensure_begin",
        order=order,
        recipient=recipient,
        config=config,
        extra={"question_count": question_count},
    )

    try:
        session = SurveySessionService.ensure_awaiting_start_session(
            db,
            order=order,
            recipient=recipient,
            config=config,
            question_count=question_count,
        )
    except Exception as exc:
        logger.error(
            "%s awaiting_start_session_failed order=%s recipient=%s err=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
            exc,
        )
        _log_opening_session(
            "missing",
            order=order,
            recipient=recipient,
            config=config,
            extra={"reason": "ensure_failed", "error": str(exc)},
        )
        return False

    db.refresh(session)
    _log_opening_session(
        "ensure_result",
        order=order,
        recipient=recipient,
        config=config,
        session=session,
        extra={"ensure_called": True},
    )

    verified = SurveySessionService.get_active_by_recipient(db, recipient.id)
    if verified is None or not verified.id:
        _log_opening_session(
            "missing",
            order=order,
            recipient=recipient,
            config=config,
            session=session,
            extra={"reason": "not_active_after_ensure"},
        )
        return False

    session = verified
    db.refresh(session)

    payload_pre = SurveySessionService.attach_session_to_result(_recipient_result(recipient), session)
    _save_recipient_result(db, recipient, payload_pre)
    db.refresh(session)

    _log_opening_session(
        "commit_ok",
        order=order,
        recipient=recipient,
        config=config,
        session=session,
        extra={"recipient_status_before_welcome": recipient.status},
    )

    logger.info(
        "%s awaiting_start_session_committed session_id=%s order=%s recipient=%s phone=%s step=0",
        LOG_PREFIX,
        session.id,
        order.id,
        recipient.id,
        recipient.phone,
    )
    log_wa_test_mode(
        "session_created",
        order=order,
        recipient=recipient,
        config=config,
        session=session,
        current_step=0,
    )
    log_survey_test(
        "session_committed",
        order=order,
        recipient=recipient,
        session=session,
        config=config,
        handler="survey_whatsapp_conversation_service.send_survey_opening",
        result="ok",
        current_step=0,
    )

    variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
    from app.services.survey_system_template_service import SurveySystemTemplateService

    template_row = SurveySystemTemplateService.resolve_order_welcome_template_row(db, config)

    preview_body = ""
    if template_row is not None:
        sendable = resolve_sendable_template_row(db, template_row) or template_row
        preview = SurveyWhatsappTemplateService.build_preview(
            db,
            sendable,
            business_name=variables.get("organisation_name") or "Your business",
            first_name=variables.get("first_name") or "there",
        )
        preview_body = str(preview.get("rendered_body") or sendable.body_preview or "").strip()
        template_row = sendable
    else:
        preview_body = _personalize_survey_text(str(flow.get("intro") or ""), variables)
        logger.error(
            "%s welcome_template_not_sendable order=%s recipient=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        _log_opening_session(
            "missing",
            order=order,
            recipient=recipient,
            config=config,
            session=session,
            extra={"reason": "welcome_template_not_sendable"},
        )
        return False

    sent = _send_message(
        db,
        order=order,
        recipient=recipient,
        body=preview_body or "Tap below to start your survey.",
        config=config,
        template_row=template_row,
    )
    if not sent:
        _log_opening_session(
            "missing",
            order=order,
            recipient=recipient,
            config=config,
            session=session,
            extra={"reason": "welcome_send_failed"},
        )
        return False

    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    if session is None or not session.id:
        _log_opening_session(
            "missing",
            order=order,
            recipient=recipient,
            config=config,
            extra={"reason": "session_lost_after_welcome_send"},
        )
        return False

    payload = _recipient_result(recipient)
    payload["channel"] = "whatsapp"
    payload["wa_conversation"] = {
        "step": 0,
        "total": total,
        "answers": [],
        "intro_sent_at": datetime.utcnow().isoformat(),
        "awaiting_start": True,
    }
    payload = SurveySessionService.attach_session_to_result(payload, session)
    recipient.status = "sent"
    _save_recipient_result(db, recipient, payload)
    logger.info(
        "%s opening_sent order=%s recipient=%s session_id=%s awaiting_start=true",
        LOG_PREFIX,
        order.id,
        recipient.id,
        session.id,
    )
    welcome_name = str(template_row.name or template_row.display_name or "") if template_row else None
    log_wa_test_mode(
        "welcome_sent",
        order=order,
        recipient=recipient,
        config=config,
        session=session,
        current_step=0,
        next_template_id=config.get("wa_template_id"),
        next_template_name=welcome_name,
    )
    return True


def send_first_question(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
) -> dict[str, Any]:
    conv = _wa_conversation(_recipient_result(recipient))
    awaiting_start = bool(conv.get("intro_sent_at")) and int(conv.get("step") or 0) == 0

    if _conversation_already_started(recipient) and not awaiting_start:
        logger.info(
            "%s send_first_question_skipped order=%s recipient=%s (already started)",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        return {"sent": False, "skipped": True, "reason": "already_started"}

    if not awaiting_start and not is_simulator_dry_run(config) and config.get("wa_template_id"):
        send_survey_opening(db, order=order, recipient=recipient, config=config)
        return {"sent": False, "reason": "opening_sent_first"}

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
        logger.error("%s send_first_question_no_questions order=%s", LOG_PREFIX, order.id)
        return {"sent": False, "reason": "no_questions"}

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
        org_id=str(order.org_id),
    )
    template_row = None
    try:
        template_row = _resolve_question_template(
            db,
            config,
            q0,
            order_id=order.id,
            session_id=session_existing.id if session_existing else None,
            step=1,
        )
    except SurveyBuilderFlowError as exc:
        log_first_question_resolution(
            trace_id=resolve_trace_id(config=config, recipient=recipient),
            order=order,
            recipient=recipient,
            config=config,
            session=session_existing,
            question=q0,
            template_row=None,
            handler="survey_whatsapp_conversation_service.send_first_question",
            phase="first_question_send_attempt",
            failure_reason=str(exc),
        )
        return {"sent": False, "reason": "template_resolve_failed", "detail": str(exc)}

    log_first_question_resolution(
        trace_id=resolve_trace_id(config=config, recipient=recipient),
        order=order,
        recipient=recipient,
        config=config,
        session=session_existing,
        question=q0,
        template_row=template_row,
        handler="survey_whatsapp_conversation_service.send_first_question",
        phase="first_question_send_attempt",
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
    mark_survey_started(payload["wa_conversation"])
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

    if _send_message(db, order=order, recipient=recipient, body=body, config=config, question=q0, pacing=PACING_STEP):
        logger.info(
            "%s first_question_sent order=%s recipient=%s template_id=%s template_name=%s source=builder_step_sequence",
            LOG_PREFIX,
            order.id,
            recipient.id,
            q0.get("template_id"),
            q0.get("template_name"),
        )
        log_first_question_resolution(
            trace_id=resolve_trace_id(config=config, recipient=recipient),
            order=order,
            recipient=recipient,
            config=config,
            session=session,
            question=q0,
            template_row=template_row,
            handler="survey_whatsapp_conversation_service.send_first_question",
            phase="first_question_sent",
        )
        return {
            "sent": True,
            "template_id": q0.get("template_id"),
            "template_name": q0.get("template_name"),
            "step": 1,
        }
    log_first_question_resolution(
        trace_id=resolve_trace_id(config=config, recipient=recipient),
        order=order,
        recipient=recipient,
        config=config,
        session=session,
        question=q0,
        template_row=template_row,
        handler="survey_whatsapp_conversation_service.send_first_question",
        phase="first_question_send_attempt",
        failure_reason="send_failed",
    )
    logger.error(
        "%s first_question_send_failed order=%s recipient=%s template_id=%s",
        LOG_PREFIX,
        order.id,
        recipient.id,
        q0.get("template_id"),
    )
    return {
        "sent": False,
        "reason": "send_failed",
        "template_id": q0.get("template_id"),
        "template_name": q0.get("template_name"),
    }


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
    variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
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
    if _send_message(db, order=order, recipient=recipient, body=body, config=config, question=q, pacing=PACING_STEP):
        logger.info("%s graph_first_question order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id)


def _maybe_complete_order(db: Session, order: ServiceOrder) -> None:
    recipients = ServiceOrderService.get_recipients(db, order.id)
    if not recipients:
        return
    terminal = {"completed", "failed", "skipped", "opted_out", "cancelled"}
    if all(str(r.status or "").lower() in terminal for r in recipients):
        from app.services.crm_deal_survey_automation_service import survey_crm_automation_blocks_auto_complete

        if survey_crm_automation_blocks_auto_complete(order):
            return
        order.status = "completed"
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        try:
            from app.services.billing_reconciliation_service import BillingReconciliationService

            BillingReconciliationService.on_order_terminal(db, order, trigger="completion")
        except Exception:
            logger.exception("billing_reconciliation_complete_failed order_id=%s", order.id)


def _send_freeform_whatsapp(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    body: str,
    pacing: str | None = None,
    config: dict[str, Any] | None = None,
) -> bool:
    """Send a plain WhatsApp session message (requires open 24h customer service window)."""
    text = str(body or "").strip()
    if not text:
        return False
    cfg = config if config is not None else _order_config(order)
    pause_before_outbound(
        pacing=pacing,
        order_id=str(order.id),
        recipient_id=str(recipient.id),
        skip=is_simulator_dry_run(cfg),
    )
    result = TelnyxMessagingService.send_whatsapp(
        db,
        org_id=order.org_id,
        to_number=recipient.phone or "",
        body=text,
        meter_usage=False,
        service_code="survey",
    )
    try:
        TelnyxMessagingService.log_outbound(
            db,
            org_id=order.org_id,
            to_number=recipient.phone or "",
            from_number=None,
            body=text,
            result=result,
        )
    except Exception:
        pass
    return bool(result.ok)


def _complete_linear_survey_thank_you(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    flow: dict[str, Any],
    questions: list[dict[str, Any]],
    conv: dict[str, Any],
    payload: dict[str, Any],
    session: SurveySession | None,
    step: int,
    total: int,
    org_name: str,
    organiser: str,
    log_id: int | None,
    inbound_message_id: str | None,
) -> dict[str, Any]:
    """Send thank-you template/text and mark recipient completed."""
    db.refresh(recipient)
    try:
        live_payload = _recipient_result(recipient)
        live_conv = live_payload.get("wa_conversation") if isinstance(live_payload.get("wa_conversation"), dict) else {}
    except Exception:
        live_conv = conv if isinstance(conv, dict) else {}
    if str(recipient.status or "").lower() == "completed" and live_conv.get("completed_at"):
        logger.info(
            "%s thank_you_skipped_already_completed order=%s recipient=%s",
            LOG_PREFIX,
            order.id,
            recipient.id,
        )
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "completed": True,
            "duplicate_thank_you_skipped": True,
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
                session_id=session.id if session else None,
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
            org_id=str(order.org_id),
        )
        conv["step"] = total + 1
        conv["completed_at"] = datetime.utcnow().isoformat()
        payload["wa_conversation"] = conv
        payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
        if session is not None:
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
            pacing=PACING_STEP,
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
        payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
        if session is not None:
            SurveySessionService.complete_linear(db, session, config=config, final_step=step)
        recipient.status = "completed"
        _save_recipient_result(db, recipient, payload)
        _send_message(db, order=order, recipient=recipient, body=closing, config=config, pacing=PACING_STEP)

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

    from app.services.crm_unhappy_task_service import maybe_post_survey_crm_actions

    maybe_post_survey_crm_actions(db, order, recipient)

    try:
        from app.services.survey_ai_followup_service import schedule_wa_if_eligible

        schedule_wa_if_eligible(db, order=order, recipient=recipient)
    except Exception:
        logger.exception("%s ai_followup_schedule_failed order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id)

    from app.workers.survey_wa_recommendations_tasks import enqueue_survey_recommendations

    enqueue_survey_recommendations(order.id)

    _maybe_complete_order(db, order)
    logger.info("%s completed order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id)
    thank_template_id = None
    thank_template_name = None
    if has_builder_runtime(config):
        runtime = load_builder_runtime(config) or {}
        thank_template_id = runtime.get("thank_you_template_id")
        thank_row = _resolve_template_row(db, thank_template_id) if thank_template_id else None
        if thank_row is not None:
            thank_template_name = str(thank_row.display_name or thank_row.name or "")
    log_wa_test_mode(
        "completed",
        order=order,
        recipient=recipient,
        config=config,
        session=session,
        current_step=step,
        next_template_id=thank_template_id,
        next_template_name=thank_template_name,
    )
    log_final_feedback(
        "transition_to_thank_you",
        order_id=order.id,
        recipient_id=recipient.id,
        handler="survey_whatsapp_conversation_service._complete_linear_survey_thank_you",
        extra={"step": step, "final_feedback_done": conv.get("final_feedback_done")},
    )
    return {
        "handled": True,
        "order_id": order.id,
        "recipient_id": recipient.id,
        "completed": True,
        "log_id": log_id,
    }


def _open_text_closing_step(question: dict[str, Any] | None, *, conv: dict[str, Any]) -> bool:
    role = normalize_step_role(str((question or {}).get("step_role") or ""))
    return role in {"reason", "tell_us_more", "final_feedback_text"}


def _send_final_feedback_open_text_prompt(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    conv: dict[str, Any],
    payload: dict[str, Any],
    total: int,
    log_id: int | None,
    inbound_message_id: str | None,
) -> dict[str, Any]:
    settings = final_feedback_settings(config)
    begin_final_feedback_open_text(conv)
    conv.pop("tell_us_more_pending", None)
    payload["wa_conversation"] = conv
    payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
    _save_recipient_result(db, recipient, payload)
    open_text_q = build_final_feedback_open_text_question(settings, db=db, config=config)
    open_text_body = format_question_message(
        open_text_q,
        index=total,
        total=total,
        variables=_survey_variables(config, recipient, db=db, org_id=str(order.org_id)),
    )
    sent = _send_message(
        db,
        order=order,
        recipient=recipient,
        body=open_text_body,
        config=config,
        question=open_text_q,
        pacing=PACING_BRANCH,
    )
    log_final_feedback(
        "bare_yes_open_text_prompt_sent",
        order_id=order.id,
        recipient_id=recipient.id,
        handler="survey_whatsapp_conversation_service._send_final_feedback_open_text_prompt",
        extra={"sent": sent},
    )
    return {
        "handled": True,
        "order_id": order.id,
        "recipient_id": recipient.id,
        "final_feedback": "awaiting_open_text",
        "sent": sent,
        "log_id": log_id,
    }


def _try_bare_yes_no_open_question_gate(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    flow: dict[str, Any],
    questions: list[dict[str, Any]],
    conv: dict[str, Any],
    payload: dict[str, Any],
    session: SurveySession | None,
    step: int,
    total: int,
    org_name: str,
    organiser: str,
    question: dict[str, Any],
    effective_body: str,
    log_id: int | None,
    inbound_message_id: str | None,
) -> dict[str, Any] | None:
    if not _open_text_closing_step(question, conv=conv):
        return None
    choice = is_bare_yes_no_reply(effective_body)
    if not choice:
        return None
    if choice == "Yes":
        return _send_final_feedback_open_text_prompt(
            db,
            order=order,
            recipient=recipient,
            config=config,
            conv=conv,
            payload=payload,
            total=total,
            log_id=log_id,
            inbound_message_id=inbound_message_id,
        )
    settings = final_feedback_settings(config)
    mark_final_feedback_skipped(payload, reason="user_declined")
    conv = payload["wa_conversation"]
    conv["final_feedback_done"] = True
    conv.pop("tell_us_more_pending", None)
    payload["wa_conversation"] = conv
    payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
    _save_recipient_result(db, recipient, payload)
    log_final_feedback(
        "bare_no_skip_to_thank_you",
        order_id=order.id,
        recipient_id=recipient.id,
        handler="survey_whatsapp_conversation_service._try_bare_yes_no_open_question_gate",
    )
    return _complete_linear_survey_thank_you(
        db,
        order=order,
        recipient=recipient,
        config=config,
        flow=flow,
        questions=questions,
        conv=conv,
        payload=payload,
        session=session,
        step=step,
        total=total,
        org_name=org_name,
        organiser=organiser,
        log_id=log_id,
        inbound_message_id=inbound_message_id,
    )


def _handle_final_feedback_inbound(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    flow: dict[str, Any],
    questions: list[dict[str, Any]],
    conv: dict[str, Any],
    payload: dict[str, Any],
    session: SurveySession | None,
    step: int,
    total: int,
    org_name: str,
    organiser: str,
    reply: NormalizedWaInboundReply,
    body: str,
    log_id: int | None,
    inbound_message_id: str | None,
) -> dict[str, Any]:
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    settings = final_feedback_settings(config)
    effective_body = reply.normalized_answer or str(body or "").strip()

    if conv.get("awaiting_final_feedback_yes_no") and SurveyWaVoiceNoteService.is_inbound_voice(reply):
        persist_final_feedback_yes_no(payload, choice="Yes", settings=settings)
        conv = payload["wa_conversation"]
        begin_final_feedback_open_text(conv)
        payload["wa_conversation"] = conv
        log_final_feedback(
            "yes_no_voice_treated_as_yes_open_text",
            order_id=order.id,
            recipient_id=recipient.id,
            handler="survey_whatsapp_conversation_service._handle_final_feedback_inbound",
        )
    elif conv.get("awaiting_final_feedback_yes_no"):
        choice = parse_final_feedback_yes_no(effective_body)
        if not choice:
            retry_q = build_final_feedback_yes_no_question(settings, db=db, config=config)
            retry_body = format_question_message(
                retry_q,
                index=total,
                total=total,
                variables=_survey_variables(config, recipient, db=db, org_id=str(order.org_id)),
            )
            _send_message(
                db,
                order=order,
                recipient=recipient,
                body=retry_body,
                config=config,
                question=retry_q,
                pacing=PACING_STEP,
            )
            return {
                "handled": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
                "final_feedback": "yes_no_retry",
                "log_id": log_id,
            }
        persist_final_feedback_yes_no(payload, choice=choice, settings=settings)
        conv = payload["wa_conversation"]
        if choice == "No":
            mark_final_feedback_skipped(payload, reason="user_declined")
            conv = payload["wa_conversation"]
            conv["final_feedback_done"] = True
            payload["wa_conversation"] = conv
            payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
            _save_recipient_result(db, recipient, payload)
            log_final_feedback(
                "yes_no_declined_skip_to_thank_you",
                order_id=order.id,
                recipient_id=recipient.id,
                handler="survey_whatsapp_conversation_service._handle_final_feedback_inbound",
            )
            return _complete_linear_survey_thank_you(
                db,
                order=order,
                recipient=recipient,
                config=config,
                flow=flow,
                questions=questions,
                conv=conv,
                payload=payload,
                session=session,
                step=step,
                total=total,
                org_name=org_name,
                organiser=organiser,
                log_id=log_id,
                inbound_message_id=inbound_message_id,
            )
        begin_final_feedback_open_text(conv)
        payload["wa_conversation"] = conv
        payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
        _save_recipient_result(db, recipient, payload)
        open_text_q = build_final_feedback_open_text_question(settings, db=db, config=config)
        open_text_body = format_question_message(
            open_text_q,
            index=total,
            total=total,
            variables=_survey_variables(config, recipient, db=db, org_id=str(order.org_id)),
        )
        sent = _send_message(
            db,
            order=order,
            recipient=recipient,
            body=open_text_body,
            config=config,
            question=open_text_q,
            pacing=PACING_BRANCH,
        )
        log_final_feedback(
            "yes_no_accepted_open_text_prompt_sent",
            order_id=order.id,
            recipient_id=recipient.id,
            handler="survey_whatsapp_conversation_service._handle_final_feedback_inbound",
            extra={"sent": sent},
        )
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "final_feedback": "awaiting_open_text",
            "sent": sent,
            "log_id": log_id,
        }

    if conv.get("awaiting_final_feedback_text"):
        voice = _try_voice_note_reply(
            db,
            order=order,
            recipient=recipient,
            payload=payload,
            conv=conv,
            question={"reply_type": "long_text", "step_role": "final_feedback_text"},
            reply=reply,
            inbound_message_id=inbound_message_id,
            log_id=log_id,
            session_id=session.id if session else None,
            answer_context="final_feedback",
            step_index=step,
            config=config,
        )
        if voice and voice.get("voice_rejected"):
            return {
                "handled": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
                "voice_note": True,
                "voice_rejected": True,
                "log_id": log_id,
            }
        if voice and voice.get("accepted"):
            answer_entry = dict(voice.get("answer") or {})
            text = str(answer_entry.get("answer_text") or answer_entry.get("answer") or "").strip()
            persist_final_feedback_text(
                payload,
                text=text,
                settings=settings,
                voice_answer=answer_entry,
            )
            conv = payload["wa_conversation"]
            conv["final_feedback_done"] = True
            conv.pop("awaiting_final_feedback_text", None)
            conv.pop("final_feedback_text_deadline", None)
            payload["wa_conversation"] = conv
            payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
            _save_recipient_result(db, recipient, payload)
            db.refresh(recipient)
            if str(recipient.status or "").lower() == "completed":
                return {
                    "handled": True,
                    "order_id": order.id,
                    "recipient_id": recipient.id,
                    "completed": True,
                    "final_feedback": "voice_completed",
                    "log_id": log_id,
                }
            return _complete_linear_survey_thank_you(
                db,
                order=order,
                recipient=recipient,
                config=config,
                flow=flow,
                questions=questions,
                conv=conv,
                payload=payload,
                session=session,
                step=step,
                total=total,
                org_name=org_name,
                organiser=organiser,
                log_id=log_id,
                inbound_message_id=inbound_message_id,
            )

        text = effective_body.strip()
        if not text:
            return {"handled": False, "reason": "final_feedback_text_empty"}
        bare_choice = is_bare_yes_no_reply(text)
        if bare_choice == "No":
            mark_final_feedback_skipped(payload, reason="user_declined")
            conv = payload["wa_conversation"]
            conv["final_feedback_done"] = True
            conv.pop("awaiting_final_feedback_text", None)
            conv.pop("final_feedback_text_deadline", None)
            payload["wa_conversation"] = conv
            payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
            _save_recipient_result(db, recipient, payload)
            return _complete_linear_survey_thank_you(
                db,
                order=order,
                recipient=recipient,
                config=config,
                flow=flow,
                questions=questions,
                conv=conv,
                payload=payload,
                session=session,
                step=step,
                total=total,
                org_name=org_name,
                organiser=organiser,
                log_id=log_id,
                inbound_message_id=inbound_message_id,
            )
        if bare_choice == "Yes":
            open_text_q = build_final_feedback_open_text_question(settings, db=db, config=config)
            open_text_body = format_question_message(
                open_text_q,
                index=total,
                total=total,
                variables=_survey_variables(config, recipient, db=db, org_id=str(order.org_id)),
            )
            begin_final_feedback_open_text(conv)
            payload["wa_conversation"] = conv
            _send_message(
                db,
                order=order,
                recipient=recipient,
                body=open_text_body,
                config=config,
                question=open_text_q,
                pacing=PACING_BRANCH,
            )
            return {
                "handled": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
                "final_feedback": "open_text_reprompt",
                "log_id": log_id,
            }
        persist_final_feedback_text(payload, text=text, settings=settings)
        conv = payload["wa_conversation"]
        conv["final_feedback_done"] = True
        conv.pop("awaiting_final_feedback_text", None)
        conv.pop("final_feedback_text_deadline", None)
        payload["wa_conversation"] = conv
        log_final_feedback(
            "open_text_saved",
            order_id=order.id,
            recipient_id=recipient.id,
            handler="survey_whatsapp_conversation_service._handle_final_feedback_inbound",
            extra={"text_len": len(text)},
        )
        payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
        _save_recipient_result(db, recipient, payload)
        return _complete_linear_survey_thank_you(
            db,
            order=order,
            recipient=recipient,
            config=config,
            flow=flow,
            questions=questions,
            conv=conv,
            payload=payload,
            session=session,
            step=step,
            total=total,
            org_name=org_name,
            organiser=organiser,
            log_id=log_id,
            inbound_message_id=inbound_message_id,
        )

    return {"handled": False, "reason": "final_feedback_state_invalid"}


def handle_inbound_reply(
    db: Session,
    *,
    from_phone: str,
    body: str,
    org_id: str | None = None,
    log_id: int | None = None,
    inbound_message_id: str | None = None,
    inbound_reply: NormalizedWaInboundReply | None = None,
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

    reply = _coerce_inbound_reply(body, inbound_reply)
    if not reply.sender_phone:
        reply.sender_phone = str(from_phone or "")

    logger.info(
        "%s inbound_matched order=%s recipient=%s step=%s body=%r action=%s button_title=%r button_id=%r",
        LOG_PREFIX,
        order.id,
        recipient.id,
        int(_wa_conversation(_recipient_result(recipient)).get("step") or 0),
        str(body or "")[:80],
        reply.normalized_action,
        reply.button_title[:80] if reply.button_title else "",
        reply.button_id[:80] if reply.button_id else "",
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

    config = _order_config(order, db)
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
    awaiting_start = _is_awaiting_start(conv, recipient)
    if awaiting_start:
        log_normalized_inbound(
            reply,
            phase="awaiting_start_inbound",
            order_id=order.id,
            session_id=session_row.id if session_row else None,
            conv_step=step,
            awaiting_start=True,
        )
        extra_triggers = welcome_start_triggers_from_config(config)
        _action, start_matcher = detect_start_matcher(reply, extra_triggers=extra_triggers)
        if not _is_valid_start_action(reply, config, awaiting_start=True):
            log_start_detection(
                trace_id=resolve_trace_id(config=config, recipient=recipient),
                config=config,
                order=order,
                recipient=recipient,
                session=session_row,
                detected=False,
                matcher=None,
                handler="survey_whatsapp_conversation_service.handle_inbound_reply",
                reply_summary={
                    "raw_body": str(body or "")[:120],
                    "button_title": reply.button_title,
                    "button_id": reply.button_id,
                    "normalized_text": reply.normalized_answer,
                    "normalized_action": reply.normalized_action,
                },
            )
            _log_start_transition_failure(
                order=order,
                recipient=recipient,
                reply=reply,
                conv=conv,
                session_id=session_row.id if session_row else None,
            )
            return {
                "handled": False,
                "reason": "awaiting_start_unparsed",
                "order_id": order.id,
                "recipient_id": recipient.id,
                "log_id": log_id,
                "inbound_message_id": inbound_message_id,
                "extracted_fields": reply.extracted_fields,
            }
        effective_matcher = start_matcher or (
            "structured_button"
            if reply.button_title or reply.button_id or reply.button_payload
            else "plain_text_fuzzy"
        )
        log_start_detection(
            trace_id=resolve_trace_id(config=config, recipient=recipient),
            config=config,
            order=order,
            recipient=recipient,
            session=session_row,
            detected=True,
            matcher=effective_matcher,
            handler="survey_whatsapp_conversation_service.handle_inbound_reply",
            reply_summary={
                "raw_body": str(body or "")[:120],
                "button_title": reply.button_title,
                "button_id": reply.button_id,
                "normalized_text": reply.normalized_answer,
            },
        )
        if session_row is None:
            session_row = recover_survey_session_from_welcome(
                db,
                order=order,
                recipient=recipient,
                config=config,
            )
        log_survey_test(
            "first_question_send_attempt",
            order=order,
            recipient=recipient,
            session=session_row,
            config=config,
            handler="survey_whatsapp_conversation_service.handle_inbound_reply",
            result="pending",
            current_step=0,
        )
        send_result = send_first_question(db, order=order, recipient=recipient, config=config)
        db.refresh(recipient)
        log_normalized_inbound(
            reply,
            phase="start_survey_transition",
            order_id=order.id,
            session_id=session_row.id if session_row else None,
            conv_step=1,
            awaiting_start=False,
            send_result=bool(send_result.get("sent")),
            next_template_id=send_result.get("template_id"),
            next_template_name=str(send_result.get("template_name") or ""),
            extra={"detected_action": START_ACTION, "send_result": send_result},
        )
        if not send_result.get("sent"):
            return {
                "handled": False,
                "reason": send_result.get("reason") or "first_question_send_failed",
                "order_id": order.id,
                "recipient_id": recipient.id,
                "log_id": log_id,
                "inbound_message_id": inbound_message_id,
                "send_result": send_result,
            }
        session_after_start = SurveySessionService.get_active_by_recipient(db, recipient.id)
        log_wa_test_mode(
            "start_transition",
            order=order,
            recipient=recipient,
            config=config,
            session=session_after_start,
            current_step=0,
            next_template_id=send_result.get("template_id"),
            next_template_name=str(send_result.get("template_name") or ""),
            branch=START_ACTION,
        )
        payload = mark_inbound_processed(
            _recipient_result(recipient),
            log_id=log_id,
            inbound_message_id=inbound_message_id,
        )
        _save_recipient_result(db, recipient, payload)
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "started": True,
            "action": START_ACTION,
            "next_template_id": send_result.get("template_id"),
            "next_template_name": send_result.get("template_name"),
            "log_id": log_id,
            "inbound_message_id": inbound_message_id,
        }

    flow = _whatsapp_flow(config)
    if is_graph_flow(config) and not should_use_builder_linear_runtime(config):
        log_vague_negative_decision(
            "inbound_graph_path",
            order_id=order.id,
            recipient_id=recipient.id,
            step=step,
            answer=str(body or "")[:120],
            handler="survey_whatsapp_conversation_service.handle_inbound_reply",
            extra={"reason": "graph_flow_not_linear"},
        )
        return _handle_inbound_reply_graph(
            db,
            order=order,
            recipient=recipient,
            config=config,
            flow=flow,
            questions=questions,
            body=body,
            reply=reply,
            log_id=log_id,
            inbound_message_id=inbound_message_id,
            org_id=org_id,
        )
    if is_graph_flow(config) and should_use_builder_linear_runtime(config):
        logger.error(
            "%s builder_graph_blocked_inbound order=%s session=%s — refusing stale graph path",
            LOG_PREFIX,
            order.id,
            session_row.id if session_row else None,
        )

    variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
    org_name = variables["organisation_name"]
    organiser = variables["organiser_name"]

    conv = _wa_conversation(payload)
    step = int(conv.get("step") or 0)
    total = int(conv.get("total") or len(questions))
    answers: list[dict[str, Any]] = list(conv.get("answers") or [])
    elaboration_only = False

    if is_awaiting_final_feedback(conv):
        session = SurveySessionService.get_active_by_recipient(db, recipient.id)
        return _handle_final_feedback_inbound(
            db,
            order=order,
            recipient=recipient,
            config=config,
            flow=flow,
            questions=questions,
            conv=conv,
            payload=payload,
            session=session,
            step=step,
            total=total,
            org_name=org_name,
            organiser=organiser,
            reply=reply,
            body=body,
            log_id=log_id,
            inbound_message_id=inbound_message_id,
        )

    if is_awaiting_vague_followup_reply(conv):
        voice = _try_voice_note_reply(
            db,
            order=order,
            recipient=recipient,
            payload=payload,
            conv=conv,
            question=None,
            reply=reply,
            inbound_message_id=inbound_message_id,
            log_id=log_id,
            session_id=session_row.id if session_row else None,
            answer_context="followup",
            step_index=int(conv.get("followup_for_step") or step or 0),
            config=config,
        )
        if voice and voice.get("handled") and (
            voice.get("voice_rejected") or (voice.get("duplicate") and not voice.get("answer"))
        ):
            return {
                "handled": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
                "voice_note": True,
                "duplicate": bool(voice.get("duplicate")),
                "voice_rejected": bool(voice.get("voice_rejected")),
                "log_id": log_id,
            }
        elaboration_only = True
        if voice and voice.get("accepted"):
            answers = list(voice.get("answers") or conv.get("answers") or [])
        else:
            merge_elaboration_into_answers(answers, reply.normalized_answer or str(body or "").strip())
        step = int(conv.get("followup_for_step") or step or 0)
        conv["answers"] = answers
        mark_vague_followup_answered(conv)
        payload["extracted_answers"] = [
            {"question": a["question"], "answer": a.get("answer_display") or a["answer"]} for a in answers
        ]
        payload["wa_conversation"] = conv

    if step < 1 or step > total:
        return {"handled": False, "reason": "invalid_step"}

    if elaboration_only:
        try:
            question = resolve_conversation_step(
                config,
                step,
                order_id=order.id,
                session_id=session_row.id if session_row else None,
            )
        except SurveyBuilderFlowError as exc:
            logger.error("%s linear_step_resolve_failed order=%s step=%s err=%s", LOG_PREFIX, order.id, step, exc)
            return {"handled": False, "reason": "step_resolve_failed", "detail": str(exc)}
        answer = str(answers[-1].get("answer") or "") if answers else ""
        session = SurveySessionService.get_active_by_recipient(db, recipient.id)
        if session is None:
            session = SurveySessionService.start_linear_session(
                db,
                order=order,
                recipient=recipient,
                config=config,
                question_count=total,
            )
        payload = SurveySessionService.attach_session_to_result(payload, session)
        from app.services.survey_results_service import build_extracted_answer_entries

        extracted = build_extracted_answer_entries(answers)
        payload["extracted_answers"] = extracted
        payload["channel"] = "whatsapp"
        conv["answers"] = answers
        payload["wa_conversation"] = conv
    else:
        try:
            if is_awaiting_tell_us_more_reply(conv):
                variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
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

        effective_body = reply.normalized_answer or str(body or "").strip()
        from app.services.survey_wa_open_text_service import voice_note_answer_context

        voice_context = voice_note_answer_context(conv=conv, question=question)
        if is_awaiting_tell_us_more_reply(conv) or is_awaiting_vague_followup_reply(conv):
            voice_context = "followup"
        voice = _try_voice_note_reply(
            db,
            order=order,
            recipient=recipient,
            payload=payload,
            conv=conv,
            question=question,
            reply=reply,
            inbound_message_id=inbound_message_id,
            log_id=log_id,
            session_id=session_row.id if session_row else None,
            answer_context=voice_context,
            step_index=step,
            config=config,
        )
        if voice and voice.get("handled") and (
            voice.get("voice_rejected") or (voice.get("duplicate") and not voice.get("answer"))
        ):
            return {
                "handled": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
                "voice_note": True,
                "duplicate": bool(voice.get("duplicate")),
                "voice_rejected": bool(voice.get("voice_rejected")),
                "log_id": log_id,
            }
        if voice and voice.get("accepted"):
            answer_entry = dict(voice.get("answer") or {})
            answer = str(answer_entry.get("answer_text") or answer_entry.get("answer") or "").strip()
        else:
            answer = match_answer(effective_body, question)
            answer_entry = None

        if answer_entry is None:
            session_for_gate = SurveySessionService.get_active_by_recipient(db, recipient.id)
            gated = _try_bare_yes_no_open_question_gate(
                db,
                order=order,
                recipient=recipient,
                config=config,
                flow=flow,
                questions=questions,
                conv=conv,
                payload=payload,
                session=session_for_gate,
                step=step,
                total=total,
                org_name=org_name,
                organiser=organiser,
                question=question,
                effective_body=effective_body,
                log_id=log_id,
                inbound_message_id=inbound_message_id,
            )
            if gated is not None:
                return gated

        q_display = survey_question_display(
            db,
            config=config,
            question=question,
            recipient=recipient,
            index=step,
            total=total,
            org_id=str(order.org_id),
        )
        answer_order = len(answers)
        if isinstance(answer_entry, dict):
            answer_entry = {
                **answer_entry,
                "step_role": str(question.get("step_role") or answer_entry.get("step_role") or ""),
                "question": str(
                    q_display.get("preview_body")
                    or q_display.get("body")
                    or answer_entry.get("question")
                    or question.get("text")
                    or f"Question {step}"
                ),
                "reply_type": question.get("reply_type") or answer_entry.get("reply_type"),
                "answer_index": answer_order,
                "step_index": step,
            }
        answers.append(
            answer_entry
            if isinstance(answer_entry, dict)
            else {
                "step_role": str(question.get("step_role") or ""),
                "question": str(q_display.get("preview_body") or q_display.get("body") or question.get("text") or f"Question {step}"),
                "answer": answer,
                "reply_type": question.get("reply_type"),
                "answer_index": answer_order,
                "step_index": step,
            }
        )

        from app.services.survey_results_service import build_extracted_answer_entries

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
            raw_value=str(body or answer or "").strip() or "[voice note]",
            normalized_value=answer,
            config=config,
        )

        extracted = build_extracted_answer_entries(answers)
        payload["extracted_answers"] = extracted
        payload["channel"] = "whatsapp"
        conv["answers"] = answers
        payload = SurveySessionService.attach_session_to_result(payload, session)

        if not tell_us_more_blocks_vague_followup(config, conv):
            evaluation = evaluate_vague_negative_followup(
                db,
                answer=answer,
                question=question,
                config=config,
                order_id=order.id,
                org_id=str(order.org_id),
                recipient_phone=recipient.phone or "",
                log_id=log_id,
                webhook_org_id=org_id,
            )
            log_vague_negative_decision(
                "linear_evaluated",
                order_id=order.id,
                recipient_id=recipient.id,
                step=step,
                answer=answer,
                handler="survey_whatsapp_conversation_service.handle_inbound_reply",
                decision=evaluation.get("decision"),
                service_window=evaluation.get("service_window"),
                extra={
                    "should_send": evaluation.get("should_send"),
                    "template_id": question.get("template_id"),
                    "metadata_present": evaluation.get("metadata_present"),
                    "heuristic_fallback": evaluation.get("heuristic_fallback"),
                },
            )
            if evaluation.get("should_send") and evaluation.get("followup_text"):
                followup_text = str(evaluation["followup_text"])
                mark_vague_followup_prompt_sent(conv, step=step)
                payload["wa_conversation"] = conv
                payload = mark_inbound_processed(
                    payload, log_id=log_id, inbound_message_id=inbound_message_id
                )
                recipient.status = "in_progress"
                _save_recipient_result(db, recipient, payload)
                sent = _send_freeform_whatsapp(
                    db,
                    order=order,
                    recipient=recipient,
                    body=followup_text,
                    pacing=PACING_BRANCH,
                    config=config,
                )
                log_vague_negative_decision(
                    "followup_sent" if sent else "followup_send_failed",
                    order_id=order.id,
                    recipient_id=recipient.id,
                    step=step,
                    answer=answer,
                    handler="survey_whatsapp_conversation_service.handle_inbound_reply",
                    decision=evaluation.get("decision"),
                    service_window=evaluation.get("service_window"),
                    extra={"sent": sent, "followup_text": followup_text[:120]},
                )
                logger.info(
                    "%s vague_negative_followup_sent order=%s recipient=%s step=%s sent=%s text=%r",
                    LOG_PREFIX,
                    order.id,
                    recipient.id,
                    step,
                    sent,
                    followup_text[:120],
                )
                return {
                    "handled": True,
                    "order_id": order.id,
                    "recipient_id": recipient.id,
                    "step": step,
                    "vague_followup": True,
                    "sent": sent,
                    "log_id": log_id,
                    "decision_reason": (evaluation.get("decision") or {}).get("reason"),
                }
            if evaluation.get("should_ask") and not (evaluation.get("service_window") or {}).get("open"):
                log_vague_negative_decision(
                    "followup_skipped_window_closed",
                    order_id=order.id,
                    recipient_id=recipient.id,
                    step=step,
                    answer=answer,
                    handler="survey_whatsapp_conversation_service.handle_inbound_reply",
                    decision=evaluation.get("decision"),
                    service_window=evaluation.get("service_window"),
                )
                logger.info(
                    "%s vague_negative_followup_skipped_window_closed order=%s recipient=%s step=%s reason=%s",
                    LOG_PREFIX,
                    order.id,
                    recipient.id,
                    step,
                    (evaluation.get("service_window") or {}).get("reason"),
                )
            elif not evaluation.get("should_ask"):
                log_vague_negative_decision(
                    "followup_not_needed",
                    order_id=order.id,
                    recipient_id=recipient.id,
                    step=step,
                    answer=answer,
                    handler="survey_whatsapp_conversation_service.handle_inbound_reply",
                    decision=evaluation.get("decision"),
                )
        else:
            log_vague_negative_decision(
                "followup_skipped_tell_us_more_pending",
                order_id=order.id,
                recipient_id=recipient.id,
                step=step,
                answer=answer,
                handler="survey_whatsapp_conversation_service.handle_inbound_reply",
            )

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
                mark_tell_us_more_answered(conv)
            elif (
                should_use_builder_linear_runtime(config)
                and runtime_tell_us_more_enabled(config)
                and not conv.get("tell_us_more_pending")
                and not tell_us_more_already_fired_for_step(conv, step)
                and is_tell_us_more_trigger_question(question)
                and is_low_answer_for_tell_us_more(
                    answer,
                    threshold=runtime_low_rating_threshold(config),
                    question=question,
                    db=db,
                )
            ):
                variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
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
                mark_tell_us_more_fired_for_step(conv, step)
                mark_tell_us_more_prompt_sent(conv)
                log_wa_test_mode(
                    "branch_taken",
                    order=order,
                    recipient=recipient,
                    config=config,
                    session=session_row,
                    current_step=step,
                    next_template_id=next_q.get("template_id"),
                    next_template_name=str(next_q.get("template_name") or ""),
                    branch="tell_us_more",
                    extra={"answer": answer, "threshold": runtime_low_rating_threshold(config)},
                )
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
        if payload_source == "builder_tell_us_more_template":
            conv["tell_us_more_asked"] = True
            conv["tell_us_more_pending"] = True
            mark_tell_us_more_fired_for_step(conv, step)
            if not conv.get("tell_us_more_sent_at"):
                mark_tell_us_more_prompt_sent(conv)
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
            org_id=str(order.org_id),
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
        _save_recipient_result(db, recipient, payload, enqueue_translation=True)
        next_pacing = PACING_BRANCH if payload_source == "builder_tell_us_more_template" else PACING_STEP
        if payload_source == "builder_tell_us_more_template":
            sent = _send_freeform_whatsapp(
                db,
                order=order,
                recipient=recipient,
                body=next_body,
                pacing=next_pacing,
                config=config,
            )
        else:
            sent = _send_message(
                db,
                order=order,
                recipient=recipient,
                body=next_body,
                config=config,
                question=next_q,
                pacing=next_pacing,
            )
        if sent:
            log_wa_test_mode(
                "step_sent",
                order=order,
                recipient=recipient,
                config=config,
                session=session,
                current_step=next_step,
                next_template_id=next_q.get("template_id"),
                next_template_name=str(next_q.get("template_name") or ""),
                branch=payload_source if payload_source != "builder_step_sequence" else None,
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

    if (
        runtime_final_feedback_enabled(config)
        and not conv.get("final_feedback_done")
        and not is_awaiting_final_feedback(conv)
    ):
        settings = final_feedback_settings(config)
        if closing_uses_yes_no_gate(config):
            log_final_feedback(
                "enabled_start_yes_no",
                order_id=order.id,
                recipient_id=recipient.id,
                handler="survey_whatsapp_conversation_service.handle_inbound_reply",
                extra={"settings": settings, "marker": "WA_FINAL_FEEDBACK_YES_NO_ACTIVE"},
            )
            begin_final_feedback_yes_no(conv)
            payload["wa_conversation"] = conv
            session = SurveySessionService.get_active_by_recipient(db, recipient.id)
            payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
            _save_recipient_result(db, recipient, payload)
            yes_no_q = build_final_feedback_yes_no_question(settings, db=db, config=config)
            yes_no_body = format_question_message(
                yes_no_q,
                index=total,
                total=total,
                variables=_survey_variables(config, recipient, db=db, org_id=str(order.org_id)),
            )
            sent = _send_message(
                db,
                order=order,
                recipient=recipient,
                body=yes_no_body,
                config=config,
                question=yes_no_q,
                pacing=PACING_BRANCH,
            )
            log_final_feedback(
                "yes_no_prompt_sent",
                order_id=order.id,
                recipient_id=recipient.id,
                handler="survey_whatsapp_conversation_service.handle_inbound_reply",
                extra={"sent": sent},
            )
            return {
                "handled": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
                "final_feedback": "awaiting_yes_no",
                "sent": sent,
                "log_id": log_id,
            }

        log_final_feedback(
            "enabled_start_closing_open_text",
            order_id=order.id,
            recipient_id=recipient.id,
            handler="survey_whatsapp_conversation_service.handle_inbound_reply",
            extra={"settings": settings},
        )
        begin_final_feedback_open_text(conv)
        payload["wa_conversation"] = conv
        session = SurveySessionService.get_active_by_recipient(db, recipient.id)
        payload = mark_inbound_processed(payload, log_id=log_id, inbound_message_id=inbound_message_id)
        _save_recipient_result(db, recipient, payload)
        open_text_q = build_final_feedback_open_text_question(settings, db=db, config=config)
        open_text_body = format_question_message(
            open_text_q,
            index=total,
            total=total,
            variables=_survey_variables(config, recipient, db=db, org_id=str(order.org_id)),
        )
        sent = _send_message(
            db,
            order=order,
            recipient=recipient,
            body=open_text_body,
            config=config,
            question=open_text_q,
            pacing=PACING_BRANCH,
        )
        log_final_feedback(
            "closing_open_text_prompt_sent",
            order_id=order.id,
            recipient_id=recipient.id,
            handler="survey_whatsapp_conversation_service.handle_inbound_reply",
            extra={"sent": sent},
        )
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "final_feedback": "awaiting_open_text",
            "sent": sent,
            "log_id": log_id,
        }

    log_final_feedback(
        "disabled_skip_to_thank_you",
        order_id=order.id,
        recipient_id=recipient.id,
        handler="survey_whatsapp_conversation_service.handle_inbound_reply",
        extra={"enabled": runtime_final_feedback_enabled(config)},
    )
    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    return _complete_linear_survey_thank_you(
        db,
        order=order,
        recipient=recipient,
        config=config,
        flow=flow,
        questions=questions,
        conv=conv,
        payload=payload,
        session=session,
        step=step,
        total=total,
        org_name=org_name,
        organiser=organiser,
        log_id=log_id,
        inbound_message_id=inbound_message_id,
    )


def _handle_inbound_reply_graph(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    flow: dict[str, Any],
    questions: list[dict[str, Any]],
    body: str,
    reply: NormalizedWaInboundReply,
    log_id: int | None,
    inbound_message_id: str | None = None,
    org_id: str | None = None,
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

    variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
    org_name = variables["organisation_name"]
    organiser = variables["organiser_name"]

    payload = _recipient_result(recipient)
    conv = _wa_conversation(payload)
    step = int(conv.get("step") or 0)
    from app.services.survey_flow_config_service import max_question_visits

    total = int(conv.get("total") or max_question_visits(config))
    answers: list[dict[str, Any]] = list(conv.get("answers") or [])
    elaboration_only = False

    if is_awaiting_vague_followup_reply(conv):
        session_row = SurveySessionService.get_active_by_recipient(db, recipient.id)
        voice = _try_voice_note_reply(
            db,
            order=order,
            recipient=recipient,
            payload=payload,
            conv=conv,
            question=None,
            reply=reply,
            inbound_message_id=inbound_message_id,
            log_id=log_id,
            session_id=session_row.id if session_row else None,
            answer_context="followup",
            step_index=int(conv.get("followup_for_step") or step or 0),
            config=config,
        )
        if voice and voice.get("handled") and (
            voice.get("voice_rejected") or (voice.get("duplicate") and not voice.get("answer"))
        ):
            return {
                "handled": True,
                "order_id": order.id,
                "recipient_id": recipient.id,
                "voice_note": True,
                "duplicate": bool(voice.get("duplicate")),
                "voice_rejected": bool(voice.get("voice_rejected")),
                "log_id": log_id,
            }
        elaboration_only = True
        if voice and voice.get("accepted"):
            answers = list(voice.get("answers") or conv.get("answers") or [])
        else:
            merge_elaboration_into_answers(answers, reply.normalized_answer or str(body or "").strip())
        step = int(conv.get("followup_for_step") or step or 0)
        conv["answers"] = answers
        mark_vague_followup_answered(conv)
        payload["wa_conversation"] = conv

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
    if not elaboration_only:
        answers.append(
            {
                "question": str(question.get("text") or f"Question {step}"),
                "answer": answer,
                "reply_type": question.get("reply_type"),
                "node_key": current_node_key,
            }
        )

        if not tell_us_more_blocks_vague_followup(config, conv) and should_ask_vague_negative_followup(
            answer=answer, question=question, config=config
        ):
            evaluation = evaluate_vague_negative_followup(
                db,
                answer=answer,
                question=question,
                config=config,
                order_id=order.id,
                org_id=str(order.org_id),
                recipient_phone=recipient.phone or "",
                log_id=log_id,
                webhook_org_id=org_id,
            )
            log_vague_negative_decision(
                "graph_evaluated",
                order_id=order.id,
                recipient_id=recipient.id,
                step=step,
                answer=answer,
                handler="survey_whatsapp_conversation_service._handle_inbound_reply_graph",
                decision=evaluation.get("decision"),
                service_window=evaluation.get("service_window"),
            )
            if evaluation.get("should_send") and evaluation.get("followup_text"):
                followup_text = str(evaluation["followup_text"])
                mark_vague_followup_prompt_sent(conv, step=step)
                conv["current_node_key"] = current_node_key
                conv["answers"] = answers
                payload["extracted_answers"] = [{"question": a["question"], "answer": a["answer"]} for a in answers]
                payload["wa_conversation"] = conv
                payload = mark_inbound_processed(
                    payload, log_id=log_id, inbound_message_id=inbound_message_id
                )
                _save_recipient_result(db, recipient, payload)
                sent = _send_freeform_whatsapp(
                    db,
                    order=order,
                    recipient=recipient,
                    body=followup_text,
                    pacing=PACING_BRANCH,
                    config=config,
                )
                return {
                    "handled": True,
                    "order_id": order.id,
                    "recipient_id": recipient.id,
                    "step": step,
                    "vague_followup": True,
                    "sent": sent,
                    "log_id": log_id,
                }
    else:
        payload["extracted_answers"] = [
            {"question": a["question"], "answer": a.get("answer_display") or a["answer"]} for a in answers
        ]
        conv["answers"] = answers

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

    from app.services.survey_results_service import build_extracted_answer_entries

    extracted = build_extracted_answer_entries(answers)
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
        from app.services.crm_unhappy_task_service import maybe_post_survey_crm_actions

        maybe_post_survey_crm_actions(db, order, recipient)
        try:
            from app.services.survey_ai_followup_service import schedule_wa_if_eligible

            schedule_wa_if_eligible(db, order=order, recipient=recipient)
        except Exception:
            logger.exception(
                "%s ai_followup_schedule_failed order=%s recipient=%s", LOG_PREFIX, order.id, recipient.id
            )
        from app.workers.survey_wa_recommendations_tasks import enqueue_survey_recommendations

        enqueue_survey_recommendations(order.id)
        _maybe_complete_order(db, order)
        return {
            "handled": True,
            "order_id": order.id,
            "recipient_id": recipient.id,
            "completed": True,
            "outcome_key": result.get("outcome_key"),
            "log_id": log_id,
        }

    variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
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
        db,
        order=order,
        recipient=recipient,
        body=next_body,
        config=config,
        question=next_q or None,
        pacing=PACING_STEP,
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


def advance_after_tell_us_more_timeout(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    config: dict[str, Any],
    payload: dict[str, Any],
    conv: dict[str, Any],
) -> bool:
    """Skip unanswered low-rating tell-us-more and send the next middle question."""
    from app.services.survey_wa_open_text_state import mark_tell_us_more_timeout

    step = int(conv.get("step") or 1)
    total = int(conv.get("total") or 0)
    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    mark_tell_us_more_timeout(conv)
    next_step = step + 1
    if next_step > total:
        payload["wa_conversation"] = conv
        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
        db.commit()
        return False
    try:
        next_q = resolve_conversation_step(
            config,
            next_step,
            order_id=order.id,
            session_id=session.id if session else None,
        )
    except SurveyBuilderFlowError:
        return False
    variables = _survey_variables(config, recipient, db=db, org_id=str(order.org_id))
    next_body = _question_outbound_body(
        db,
        config=config,
        question=next_q,
        recipient=recipient,
        index=next_step,
        total=total,
        org_id=str(order.org_id),
    )
    conv["step"] = next_step
    conv["current_template_id"] = next_q.get("template_id")
    conv["current_node_key"] = next_q.get("node_key")
    payload["wa_conversation"] = conv
    recipient.result_json = json.dumps(payload, ensure_ascii=False)
    db.add(recipient)
    if session is not None:
        SurveySessionService.advance_linear(db, session, config=config, from_step=step, to_step=next_step)
    db.commit()
    return _send_message(
        db,
        order=order,
        recipient=recipient,
        body=next_body,
        config=config,
        question=next_q,
        pacing=PACING_STEP,
    )
