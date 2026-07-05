"""Optional final additional feedback step before survey thank-you (WhatsApp builder)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_flow_constants import (
    KEY_CLOSING_DEADLINE,
    KEY_CLOSING_OUTCOME,
    KEY_LAST_OUTBOUND_KIND,
    OPEN_TEXT_TIMEOUT_SEC,
    OUTBOUND_KIND_FINAL_FEEDBACK,
)

logger = logging.getLogger(__name__)
LOG_PREFIX = "[wa-closing-question]"

DEFAULT_YES_NO_QUESTION = "Would you like to add anything else before we finish?"
DEFAULT_OPEN_TEXT_PROMPT = "Please share anything else you'd like us to know."
FINAL_FEEDBACK_TEXT_TIMEOUT_SEC = OPEN_TEXT_TIMEOUT_SEC

FINAL_FEEDBACK_YES_NO_TEMPLATE_NAMES = (
    "voxbulk_survey_final_feedback_global_final_feedback_voice_note",
    "final_feedback_global_final_feedback_voice_note",
)

FINAL_FEEDBACK_YES_NO_ROLE = "final_feedback_yes_no"
FINAL_FEEDBACK_TEXT_ROLE = "final_feedback_text"

YES_NO_MATCH_QUESTION = {
    "step_role": FINAL_FEEDBACK_YES_NO_ROLE,
    "reply_type": "true_false",
    "options": ["Yes", "No"],
}


def final_feedback_settings(config: dict[str, Any] | None) -> dict[str, Any]:
    """Resolved copy + enabled flag from order config / builder runtime."""
    cfg = config if isinstance(config, dict) else {}
    runtime = cfg.get("builder_runtime") if isinstance(cfg.get("builder_runtime"), dict) else {}
    branch = (runtime.get("branches") or {}).get("final_additional_feedback") or {}
    enabled = bool(
        branch.get("enabled")
        if branch
        else cfg.get("allow_final_additional_feedback")
    )
    yes_no = str(
        branch.get("yes_no_question")
        or cfg.get("final_feedback_yes_no_question")
        or DEFAULT_YES_NO_QUESTION
    ).strip()
    open_text = str(
        branch.get("open_text_prompt")
        or cfg.get("final_feedback_open_text_prompt")
        or DEFAULT_OPEN_TEXT_PROMPT
    ).strip()
    return {
        "enabled": enabled,
        "yes_no_question": yes_no or DEFAULT_YES_NO_QUESTION,
        "open_text_prompt": open_text or DEFAULT_OPEN_TEXT_PROMPT,
    }


def runtime_final_feedback_enabled(config: dict[str, Any] | None) -> bool:
    return bool(final_feedback_settings(config).get("enabled"))


def build_final_feedback_branch(
    *,
    enabled: bool = False,
    yes_no_question: str | None = None,
    open_text_prompt: str | None = None,
    use_yes_no_gate: bool = False,
) -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "use_yes_no_gate": bool(use_yes_no_gate),
        "yes_no_question": str(yes_no_question or DEFAULT_YES_NO_QUESTION).strip(),
        "open_text_prompt": str(open_text_prompt or DEFAULT_OPEN_TEXT_PROMPT).strip(),
    }


def closing_uses_yes_no_gate(config: dict[str, Any] | None) -> bool:
    cfg = config if isinstance(config, dict) else {}
    runtime = cfg.get("builder_runtime") if isinstance(cfg.get("builder_runtime"), dict) else {}
    branch = (runtime.get("branches") or {}).get("final_additional_feedback") or {}
    if "use_yes_no_gate" in branch:
        return bool(branch.get("use_yes_no_gate"))
    return bool(cfg.get("final_feedback_use_yes_no_gate"))


def log_final_feedback(
    event: str,
    *,
    order_id: str | None = None,
    recipient_id: str | None = None,
    handler: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    logger.info(
        "%s %s order_id=%s recipient_id=%s handler=%s extra=%s",
        LOG_PREFIX,
        event,
        order_id,
        recipient_id,
        handler,
        extra or {},
    )


def parse_final_feedback_yes_no(raw: str) -> str | None:
    text = str(raw or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in {"yes", "y", "yeah", "yep", "sure", "ok", "okay"}:
        return "Yes"
    if lowered in {"no", "n", "nope", "nah", "not really"}:
        return "No"
    for opt in YES_NO_MATCH_QUESTION["options"]:
        if lowered == str(opt).lower():
            return opt
    m = re.match(r"^(\d+)\b", text)
    if m:
        idx = int(m.group(1)) - 1
        opts = YES_NO_MATCH_QUESTION["options"]
        if 0 <= idx < len(opts):
            return str(opts[idx])
    return None


def is_awaiting_final_feedback(conv: dict[str, Any]) -> bool:
    """True when collecting optional open-text final feedback (legacy yes/no flag included)."""
    return bool(conv.get("awaiting_final_feedback_text") or conv.get("awaiting_final_feedback_yes_no"))


def begin_final_feedback_yes_no(conv: dict[str, Any]) -> None:
    """Enter optional closing yes/no gate before open-text prompt."""
    conv["awaiting_final_feedback_yes_no"] = True
    conv.pop("awaiting_final_feedback_text", None)


def begin_final_feedback_open_text(conv: dict[str, Any]) -> None:
    """Enter the open-text final feedback stage after user chooses Yes."""
    from datetime import datetime, timedelta, timezone

    conv["awaiting_final_feedback_text"] = True
    conv.pop("awaiting_final_feedback_yes_no", None)
    conv[KEY_LAST_OUTBOUND_KIND] = OUTBOUND_KIND_FINAL_FEEDBACK
    conv[KEY_CLOSING_DEADLINE] = (
        datetime.now(timezone.utc) + timedelta(seconds=FINAL_FEEDBACK_TEXT_TIMEOUT_SEC)
    ).isoformat()
    conv.pop(KEY_CLOSING_OUTCOME, None)


def is_bare_yes_no_reply(raw: str) -> str | None:
    """Return Yes/No when the message is only an affirmation, not substantive feedback."""
    text = str(raw or "").strip()
    if not text:
        return None
    choice = parse_final_feedback_yes_no(text)
    if not choice:
        return None
    normalized = text.lower().strip().rstrip(".!")
    if choice == "Yes" and normalized in {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "1"}:
        return choice
    if choice == "No" and normalized in {"no", "n", "nope", "nah", "not really", "2"}:
        return choice
    return None


def _approved_template_row(db: Session, template_id: int) -> TelnyxWhatsappTemplate | None:
    try:
        row = db.get(TelnyxWhatsappTemplate, int(template_id))
    except (TypeError, ValueError):
        return None
    if row is None or str(row.status or "").upper() != "APPROVED":
        return None
    return row


def _body_text_from_template_row(row: TelnyxWhatsappTemplate) -> str:
    preview = str(row.body_preview or "").strip()
    if preview:
        return preview
    try:
        components = json.loads(row.components_json or "[]")
        if isinstance(components, list):
            for comp in components:
                if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
                    body = str(comp.get("text") or "").strip()
                    if body:
                        return body
    except Exception:
        pass
    return str(row.display_name or row.name or "").strip()


def resolve_final_feedback_yes_no_template(
    db: Session,
    config: dict[str, Any] | None = None,
) -> TelnyxWhatsappTemplate | None:
    """Approved Telnyx yes/no template for the voice-note final feedback gate."""
    cfg = config if isinstance(config, dict) else {}
    runtime = cfg.get("builder_runtime") if isinstance(cfg.get("builder_runtime"), dict) else {}
    branch = (runtime.get("branches") or {}).get("final_additional_feedback") or {}
    configured_id = branch.get("yes_no_template_id") or cfg.get("final_feedback_yes_no_template_id")
    if configured_id:
        row = _approved_template_row(db, int(configured_id))
        if row is not None:
            return row

    for name in FINAL_FEEDBACK_YES_NO_TEMPLATE_NAMES:
        row = db.execute(
            select(TelnyxWhatsappTemplate)
            .where(
                TelnyxWhatsappTemplate.name == name,
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .limit(1)
        ).scalar_one_or_none()
        if row is not None and str(row.status or "").upper() == "APPROVED":
            return row

    row = db.execute(
        select(TelnyxWhatsappTemplate)
        .where(
            TelnyxWhatsappTemplate.name.ilike("%final_feedback%voice_note%"),
            TelnyxWhatsappTemplate.active_for_survey.is_(True),
        )
        .order_by(TelnyxWhatsappTemplate.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is not None and str(row.status or "").upper() == "APPROVED":
        return row
    return None


def build_final_feedback_yes_no_question(
    settings: dict[str, Any],
    *,
    db: Session | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if db is not None:
        row = resolve_final_feedback_yes_no_template(db, config)
        if row is not None:
            body = _body_text_from_template_row(row)
            log_final_feedback(
                "yes_no_template_resolved",
                extra={"template_id": row.id, "template_name": row.name},
            )
            return {
                **YES_NO_MATCH_QUESTION,
                "template_id": row.id,
                "template_name": row.name,
                "text": body or str(settings.get("yes_no_question") or DEFAULT_YES_NO_QUESTION).strip(),
                "step_role": FINAL_FEEDBACK_YES_NO_ROLE,
            }
        if runtime_final_feedback_enabled(config):
            logger.error(
                "%s missing_yes_no_template config_keys=%s",
                LOG_PREFIX,
                list((config or {}).keys())[:12],
            )

    question = str(settings.get("yes_no_question") or DEFAULT_YES_NO_QUESTION).strip()
    return {
        **YES_NO_MATCH_QUESTION,
        "text": question or DEFAULT_YES_NO_QUESTION,
        "step_role": FINAL_FEEDBACK_YES_NO_ROLE,
    }


def build_final_feedback_open_text_question(
    settings: dict[str, Any],
    *,
    db: Session | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = str(settings.get("open_text_prompt") or DEFAULT_OPEN_TEXT_PROMPT).strip()
    question: dict[str, Any] = {
        "reply_type": "long_text",
        "step_role": FINAL_FEEDBACK_TEXT_ROLE,
        "text": prompt or DEFAULT_OPEN_TEXT_PROMPT,
    }
    if db is None:
        return question

    from app.services.survey_system_template_service import SurveySystemTemplateService

    template_id = SurveySystemTemplateService.resolve_final_feedback_template_id(db, config)
    if template_id:
        row = _approved_template_row(db, template_id)
        if row is not None:
            question["template_id"] = row.id
            question["template_name"] = row.name
            body = _body_text_from_template_row(row)
            if body:
                question["text"] = body
            log_final_feedback(
                "open_text_template_resolved",
                extra={"template_id": row.id, "template_name": row.name},
            )
    elif runtime_final_feedback_enabled(config):
        logger.warning("%s missing_open_text_template using_prompt_copy", LOG_PREFIX)
    return question


def should_offer_final_feedback(config: dict[str, Any], conv: dict[str, Any]) -> bool:
    if conv.get("final_feedback_done"):
        return False
    if conv.get("awaiting_followup") or conv.get("tell_us_more_pending"):
        return False
    if is_awaiting_final_feedback(conv):
        return True
    return runtime_final_feedback_enabled(config)


def persist_final_feedback_yes_no(
    payload: dict[str, Any],
    *,
    choice: str,
    settings: dict[str, Any],
) -> None:
    question = str(settings.get("yes_no_question") or DEFAULT_YES_NO_QUESTION)
    conv = payload.setdefault("wa_conversation", {})
    answers = list(conv.get("answers") or [])
    answers.append(
        {
            "step_role": FINAL_FEEDBACK_YES_NO_ROLE,
            "question": question,
            "answer": choice,
            "reply_type": "true_false",
        }
    )
    conv["answers"] = answers
    conv["final_feedback_yes_no"] = choice
    payload["final_feedback_yes_no"] = choice
    extracted = list(payload.get("extracted_answers") or [])
    extracted.append({"question": question, "answer": choice, "step_role": FINAL_FEEDBACK_YES_NO_ROLE})
    payload["extracted_answers"] = extracted
    payload["wa_conversation"] = conv


def persist_final_feedback_text(
    payload: dict[str, Any],
    *,
    text: str,
    settings: dict[str, Any],
    voice_answer: dict[str, Any] | None = None,
) -> None:
    from app.services.survey_wa_open_text_service import merge_voice_metadata

    prompt = str(settings.get("open_text_prompt") or DEFAULT_OPEN_TEXT_PROMPT)
    cleaned = str(text or "").strip()
    conv = payload.setdefault("wa_conversation", {})
    answers = list(conv.get("answers") or [])
    entry: dict[str, Any] = {
        "step_role": FINAL_FEEDBACK_TEXT_ROLE,
        "question": prompt,
        "answer": cleaned,
        "answer_text": cleaned,
        "reply_type": "long_text",
    }
    if isinstance(voice_answer, dict):
        entry = merge_voice_metadata(entry, voice_answer)
        if not cleaned and voice_answer.get("answer_source") == "voice_note":
            entry["answer"] = cleaned
            entry["answer_text"] = cleaned
    answers.append(entry)
    conv["answers"] = answers
    conv["final_additional_feedback"] = cleaned
    payload["final_additional_feedback"] = cleaned
    extracted = list(payload.get("extracted_answers") or [])
    extracted.append(
        {
            "question": prompt,
            "answer": cleaned,
            "answer_text": cleaned,
            "step_role": FINAL_FEEDBACK_TEXT_ROLE,
            "final_additional_feedback": cleaned,
            **(
                {k: entry[k] for k in ("answer_source", "transcription_status", "voice_note_job_id", "detected_language") if k in entry}
                if isinstance(voice_answer, dict)
                else {}
            ),
        }
    )
    payload["extracted_answers"] = extracted
    payload["wa_conversation"] = conv


def mark_final_feedback_skipped(payload: dict[str, Any], *, reason: str) -> None:
    conv = payload.setdefault("wa_conversation", {})
    conv["final_feedback_done"] = True
    conv.pop("awaiting_final_feedback_yes_no", None)
    conv.pop("awaiting_final_feedback_text", None)
    conv.pop("final_feedback_text_deadline", None)
    payload["wa_conversation"] = conv
    payload.setdefault("final_additional_feedback", None)
    payload.setdefault("final_feedback_skip_reason", reason)


def try_complete_survey_after_final_feedback_voice(db, job) -> None:
    """Complete survey + thank-you if voice transcription finished while still in final feedback."""
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.models.survey_voice_note_job import SurveyVoiceNoteJob

    if not isinstance(job, SurveyVoiceNoteJob) or job.answer_context != "final_feedback":
        return

    recipient = db.get(ServiceOrderRecipient, job.recipient_id)
    order = db.get(ServiceOrder, job.order_id)
    if recipient is None or order is None:
        return
    if str(recipient.status or "").lower() == "completed":
        return

    try:
        payload = json.loads(recipient.result_json or "{}")
    except Exception:
        return
    if not isinstance(payload, dict):
        return

    conv = payload.get("wa_conversation") or {}
    if conv.get("final_feedback_done") or not conv.get("awaiting_final_feedback_text"):
        return

    from app.services.survey_whatsapp_conversation_service import _complete_linear_survey_thank_you

    from app.services.survey_session_service import SurveySessionService

    settings = final_feedback_settings(_order_config_from_service_order(order))
    text = str(job.answer_text or "").strip()
    persist_final_feedback_text(payload, text=text, settings=settings)
    conv = payload["wa_conversation"]
    conv["final_feedback_done"] = True
    conv.pop("awaiting_final_feedback_text", None)
    payload["wa_conversation"] = conv
    recipient.result_json = json.dumps(payload, ensure_ascii=False)
    db.add(recipient)
    db.commit()

    config = _order_config_from_service_order(order)
    flow, questions = _survey_completion_context(config)
    session = SurveySessionService.get_active_by_recipient(db, recipient.id)
    from app.services.survey_wa_org_context_service import resolve_survey_organisation_name

    org_name = resolve_survey_organisation_name(db, org_id=str(order.org_id), config=config)
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
    step = int(conv.get("step") or 0)
    total = int(conv.get("total") or len(questions))

    log_final_feedback(
        "voice_transcript_completed_survey",
        order_id=order.id,
        recipient_id=recipient.id,
        handler="survey_wa_final_feedback_service.try_complete_survey_after_final_feedback_voice",
        extra={"job_id": job.id, "text_len": len(text)},
    )
    _complete_linear_survey_thank_you(
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
        log_id=job.whatsapp_log_id,
        inbound_message_id=job.inbound_message_id,
    )


def _order_config_from_service_order(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _survey_completion_context(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from app.services.survey_builder_flow_service import survey_questions_from_config

    flow = config.get("whatsapp_flow")
    flow = flow if isinstance(flow, dict) else {}
    questions = survey_questions_from_config(config) or list(flow.get("questions") or [])
    return flow, questions


def process_final_feedback_timeouts(db: Session, *, limit: int = 50) -> int:
    """Complete surveys when open-text final feedback was not received within the deadline."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.service_order import ServiceOrder, ServiceOrderRecipient

    now = datetime.now(timezone.utc)
    rows = db.execute(
        select(ServiceOrderRecipient)
        .where(ServiceOrderRecipient.status == "in_progress")
        .order_by(ServiceOrderRecipient.created_at.asc())
        .limit(max(limit * 10, 50))
    ).scalars().all()

    completed = 0
    for recipient in rows:
        if completed >= limit:
            break
        try:
            payload = json.loads(recipient.result_json or "{}")
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        conv = payload.get("wa_conversation") or {}
        if not isinstance(conv, dict) or not conv.get("awaiting_final_feedback_text"):
            continue
        raw_deadline = conv.get("final_feedback_text_deadline")
        if not raw_deadline:
            continue
        try:
            deadline = datetime.fromisoformat(str(raw_deadline).replace("Z", "+00:00"))
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if deadline > now:
            continue

        order = db.get(ServiceOrder, recipient.order_id)
        if order is None:
            continue
        config = _order_config_from_service_order(order)
        from app.services.survey_session_service import SurveySessionService
        from app.services.survey_whatsapp_conversation_service import _complete_linear_survey_thank_you
        from app.services.survey_wa_org_context_service import resolve_survey_organisation_name

        flow, questions = _survey_completion_context(config)
        session = SurveySessionService.get_active_by_recipient(db, recipient.id)
        org_name = resolve_survey_organisation_name(db, org_id=str(order.org_id), config=config)
        organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
        step = int(conv.get("step") or 0)
        total = int(conv.get("total") or len(questions))

        mark_final_feedback_skipped(payload, reason="timeout")
        conv = payload["wa_conversation"]
        conv.pop("final_feedback_text_deadline", None)
        payload["wa_conversation"] = conv
        recipient.result_json = json.dumps(payload, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        log_final_feedback(
            "open_text_timeout_thank_you",
            order_id=order.id,
            recipient_id=recipient.id,
            handler="survey_wa_final_feedback_service.process_final_feedback_timeouts",
        )
        _complete_linear_survey_thank_you(
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
            log_id=None,
            inbound_message_id=None,
        )
        completed += 1

    return completed
