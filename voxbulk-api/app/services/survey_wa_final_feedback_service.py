"""Optional final additional feedback step before survey thank-you (WhatsApp builder)."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)
LOG_PREFIX = "[wa-final-feedback]"

DEFAULT_YES_NO_QUESTION = "Would you like to add anything else before we finish?"
DEFAULT_OPEN_TEXT_PROMPT = "Please share anything else you'd like us to know."

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
) -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "yes_no_question": str(yes_no_question or DEFAULT_YES_NO_QUESTION).strip(),
        "open_text_prompt": str(open_text_prompt or DEFAULT_OPEN_TEXT_PROMPT).strip(),
    }


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
    conv["awaiting_final_feedback_text"] = True
    conv.pop("awaiting_final_feedback_yes_no", None)


def build_final_feedback_yes_no_question(settings: dict[str, Any]) -> dict[str, Any]:
    question = str(settings.get("yes_no_question") or DEFAULT_YES_NO_QUESTION).strip()
    return {
        **YES_NO_MATCH_QUESTION,
        "text": question or DEFAULT_YES_NO_QUESTION,
        "step_role": FINAL_FEEDBACK_YES_NO_ROLE,
    }


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
                {k: entry[k] for k in ("answer_source", "transcription_status", "voice_note_job_id", "detected_language")}
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
    payload["wa_conversation"] = conv
    payload.setdefault("final_additional_feedback", None)
    payload.setdefault("final_feedback_skip_reason", reason)
