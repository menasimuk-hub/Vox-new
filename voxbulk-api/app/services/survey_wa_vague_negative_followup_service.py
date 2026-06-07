"""Auto vague-negative WhatsApp survey follow-up — metadata, detection, free-form prompts."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
LOG_PREFIX = "[wa-vague-followup]"

from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.whatsapp_log import WhatsAppLog
from app.services.survey_step_bank_service import normalize_step_role

FOLLOWUP_MODE_AUTO_VAGUE = "auto_vague_negative"
DEFAULT_LOW_SCORE_THRESHOLD = 3
SERVICE_WINDOW_HOURS = 24

VAGUE_NEGATIVE_PHRASES = frozenset(
    {
        "bad",
        "poor",
        "not good",
        "terrible",
        "awful",
        "horrible",
        "disappointing",
        "disappointed",
        "unhappy",
        "unsatisfied",
        "not happy",
        "not great",
        "could be better",
        "could've been better",
        "could have been better",
        "very poor",
        "very bad",
        "not helpful",
        "not satisfied",
    }
)

DEFAULT_FORCE_NEGATIVE_TERMS: tuple[str, ...] = ()
DEFAULT_SKIP_FOLLOWUP_TERMS: tuple[str, ...] = (
    "price too high",
    "too expensive",
    "delivery was late",
    "support never replied",
    "never replied",
    "app kept crashing",
    "booking took too long",
    "waited too long",
    "too slow",
    "rude staff",
    "wrong order",
    "missing items",
)

SPECIFIC_COMPLAINT_RE = re.compile(
    r"\b("
    r"too (?:expensive|high|slow|long|late|cold|hot|noisy|crowded)|"
    r"never (?:replied|responded|called|came|arrived)|"
    r"didn['']?t (?:reply|respond|work|arrive|show)|"
    r"was (?:late|slow|rude|cold|broken|dirty|closed)|"
    r"kept (?:crashing|freezing|loading)|"
    r"wrong (?:order|item|room|date|time)|"
    r"missing (?:items|parts|ingredients)|"
    r"not (?:fresh|clean|available)|"
    r"overcharged|understaffed|unprofessional|"
    r"price (?:was )?too high|"
    r"cost(?:s)? too much|"
    r"wait(?:ed|ing) (?:too )?(?:long|hours)|"
    r"booking took|"
    r"support (?:never|didn['']?t)|"
    r"delivery (?:was )?(?:late|delayed|missing)|"
    r"food (?:was )?(?:cold|stale|undercooked|overcooked)|"
    r"staff (?:was )?(?:rude|unhelpful)|"
    r"because .{8,}|"
    r"due to .{8,}|"
    r"since .{8,}"
    r")\b",
    re.IGNORECASE,
)

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food_quality": ("food", "meal", "dish", "taste", "flavour", "flavor", "menu", "cuisine"),
    "delivery": ("delivery", "delivered", "courier", "driver", "shipping", "dispatch"),
    "support": ("support", "helpdesk", "customer service", "service team", "call centre", "call center"),
    "pricing": ("price", "pricing", "cost", "fee", "charge", "expensive", "affordable", "value"),
    "staff": ("staff", "team member", "employee", "reception", "waiter", "waitress", "nurse", "doctor"),
    "cleanliness": ("clean", "cleanliness", "hygiene", "sanitary", "tidy"),
    "booking_experience": ("booking", "appointment", "schedule", "reservation", "check-in", "check in"),
    "overall_service": ("service", "experience", "visit", "overall"),
}

PROFILE_BY_TOPIC: dict[str, str] = {
    "food_quality": "quality_issue",
    "delivery": "delivery_issue",
    "support": "service_issue",
    "pricing": "pricing_issue",
    "staff": "service_issue",
    "cleanliness": "quality_issue",
    "booking_experience": "service_issue",
    "overall_service": "general_experience",
}

STEP_ROLE_TO_ANSWER_KIND: dict[str, str] = {
    "rating": "rating",
    "yes_no": "yes_no",
    "helpfulness": "rating",
    "feeling_word": "rating",
    "abc_choice": "short_text",
    "reason": "long_text",
    "follow_up": "long_text",
    "improvement": "long_text",
}

RATING_BUTTON_LOW = frozenset({"poor", "not helpful", "no", "1", "2"})

FOLLOWUP_PATTERNS: tuple[str, ...] = (
    "What was wrong with {topic_phrase}?",
    "What issue did you have with {topic_phrase}?",
    "What went wrong with {topic_phrase}?",
    "Could you share a bit more about {topic_phrase}?",
    "We're sorry to hear that. What happened with {topic_phrase}?",
)

FALLBACK_FOLLOWUP = "We're sorry to hear that. Could you tell us a bit more?"


def _loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def template_has_variables(item: dict[str, Any]) -> bool:
    from app.services.survey_wa_template_pack_service import _var_re_from_text

    combined = f"{item.get('header') or ''} {item.get('body') or ''}"
    return bool(_var_re_from_text(combined))


def normalize_template_example_values(item: dict[str, Any]) -> dict[str, Any]:
    """Remove fake 'sample' placeholders; omit examples when no variables exist."""
    out = dict(item)
    if not template_has_variables(out):
        out["example_values"] = []
        return out

    from app.services.survey_wa_template_pack_service import _var_re_from_text

    combined = f"{out.get('header') or ''} {out.get('body') or ''}"
    var_ids = _var_re_from_text(combined)
    defaults = {1: "Alex", 2: "Northgate Dental", 3: "https://example.com/survey"}
    examples: list[str] = []
    for vid in range(1, max(var_ids) + 1):
        raw = ""
        if isinstance(out.get("example_values"), list) and len(out["example_values"]) >= vid:
            raw = str(out["example_values"][vid - 1] or "").strip()
        if not raw or raw.lower() == "sample":
            raw = defaults.get(vid, "Guest")
        examples.append(raw)
    out["example_values"] = examples
    return out


def infer_question_topic(
    *,
    survey_type_slug: str = "",
    industry_slug: str = "",
    step_role: str = "",
    question_text: str = "",
) -> str:
    haystack = " ".join(
        [
            str(survey_type_slug or "").replace("_", " "),
            str(industry_slug or "").replace("_", " "),
            str(question_text or ""),
        ]
    ).lower()
    best_topic = "overall_service"
    best_score = 0
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in haystack)
        if score > best_score:
            best_score = score
            best_topic = topic
    if step_role == "rating" and "food" in haystack:
        return "food_quality"
    return best_topic


def infer_answer_kind(step_role: str) -> str:
    role = normalize_step_role(step_role or "rating")
    return STEP_ROLE_TO_ANSWER_KIND.get(role, "short_text")


def infer_followup_profile(question_topic: str, survey_type_slug: str = "") -> str:
    if question_topic in PROFILE_BY_TOPIC:
        return PROFILE_BY_TOPIC[question_topic]
    slug = str(survey_type_slug or "").lower()
    if "delivery" in slug:
        return "delivery_issue"
    if "price" in slug or "cost" in slug:
        return "pricing_issue"
    if "food" in slug or "quality" in slug:
        return "quality_issue"
    return "general_experience"


def build_auto_followup_metadata(
    *,
    survey_type: SurveyType,
    industry_slug: str = "",
    step_role: str = "rating",
    question_text: str = "",
) -> dict[str, Any]:
    topic = infer_question_topic(
        survey_type_slug=str(survey_type.slug or ""),
        industry_slug=industry_slug,
        step_role=step_role,
        question_text=question_text,
    )
    answer_kind = infer_answer_kind(step_role)
    threshold = DEFAULT_LOW_SCORE_THRESHOLD if answer_kind == "rating" else None
    return {
        "auto_followup_enabled": True,
        "followup_mode": FOLLOWUP_MODE_AUTO_VAGUE,
        "question_topic": topic,
        "answer_kind": answer_kind,
        "low_score_threshold": threshold,
        "followup_profile": infer_followup_profile(topic, str(survey_type.slug or "")),
    }


def attach_auto_followup_to_template_item(
    item: dict[str, Any],
    *,
    survey_type: SurveyType,
    industry_slug: str = "",
) -> dict[str, Any]:
    out = dict(item)
    meta = build_auto_followup_metadata(
        survey_type=survey_type,
        industry_slug=industry_slug,
        step_role=str(out.get("step_role") or "rating"),
        question_text=str(out.get("body") or ""),
    )
    out["auto_followup"] = meta
    out["outcome_variables"] = {"auto_followup": meta}
    return out


def parse_auto_followup_from_template(row: TelnyxWhatsappTemplate | None) -> dict[str, Any]:
    if row is None:
        return {}
    data = _loads(row.outcome_variables_json)
    if isinstance(data, dict) and isinstance(data.get("auto_followup"), dict):
        return dict(data["auto_followup"])
    return {}


def parse_auto_followup_from_question(question: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(question, dict):
        return {}
    meta = question.get("auto_followup")
    if isinstance(meta, dict):
        return dict(meta)
    return {}


def get_followup_overrides(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = config if isinstance(config, dict) else {}
    raw = cfg.get("wa_survey_followup_overrides") or {}
    if not isinstance(raw, dict):
        raw = {}
    force = [str(x).strip().lower() for x in (raw.get("force_negative_terms") or DEFAULT_FORCE_NEGATIVE_TERMS) if str(x).strip()]
    skip = [str(x).strip().lower() for x in (raw.get("skip_followup_terms") or DEFAULT_SKIP_FOLLOWUP_TERMS) if str(x).strip()]
    return {"force_negative_terms": force, "skip_followup_terms": skip}


def _topic_phrase(question: dict[str, Any], metadata: dict[str, Any]) -> str:
    body = str(question.get("text") or question.get("body") or "").strip()
    topic = str(metadata.get("question_topic") or "").replace("_", " ")
    if body:
        cleaned = re.sub(r"[⭐🌟✨!?]+$", "", body).strip()
        cleaned = re.sub(r"^(how (?:was|would|did)|what (?:was|did)|rate|please rate)\s+", "", cleaned, flags=re.I)
        cleaned = cleaned.rstrip("?.")
        if len(cleaned) >= 8:
            return cleaned.lower()
    if topic:
        return topic
    return "your experience"


def generate_followup_text(*, question: dict[str, Any], metadata: dict[str, Any] | None = None) -> str:
    meta = metadata or parse_auto_followup_from_question(question)
    phrase = _topic_phrase(question, meta)
    profile = str(meta.get("followup_profile") or "")
    idx = hash(profile) % len(FOLLOWUP_PATTERNS)
    pattern = FOLLOWUP_PATTERNS[idx]
    try:
        text = pattern.format(topic_phrase=phrase)
    except Exception:
        text = FALLBACK_FOLLOWUP
    if len(text) > 500:
        return FALLBACK_FOLLOWUP
    return text


def is_specific_complaint(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if not raw:
        return False
    if len(raw.split()) >= 6 and any(w in raw for w in ("because", "due to", "since", "when", "after")):
        return True
    return bool(SPECIFIC_COMPLAINT_RE.search(raw))


def is_vague_negative_phrase(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if not raw:
        return False
    if raw in VAGUE_NEGATIVE_PHRASES:
        return True
    for phrase in VAGUE_NEGATIVE_PHRASES:
        if raw == phrase or raw.startswith(phrase + " ") or raw.endswith(" " + phrase):
            return True
    return False


def is_low_score_answer(answer: str, *, threshold: int | None = None) -> bool:
    raw = str(answer or "").strip().lower()
    if not raw:
        return False
    if raw in RATING_BUTTON_LOW:
        return True
    star_match = re.match(r"^(\d)\s*(?:star|stars)?$", raw)
    if star_match:
        score = int(star_match.group(1))
        limit = threshold if threshold is not None else DEFAULT_LOW_SCORE_THRESHOLD
        return score <= limit
    try:
        score = int(raw)
        limit = threshold if threshold is not None else DEFAULT_LOW_SCORE_THRESHOLD
        return score <= limit
    except ValueError:
        return False


def explain_vague_negative_decision(
    *,
    answer: str,
    question: dict[str, Any],
    config: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return should_ask plus explicit branch reason for tracing (works without template metadata)."""
    meta = metadata if metadata is not None else parse_auto_followup_from_question(question)
    metadata_present = bool(meta)
    heuristic_fallback = not metadata_present

    raw = str(answer or "").strip()
    lowered = raw.lower()
    answer_kind = str(meta.get("answer_kind") or infer_answer_kind(str(question.get("step_role") or "")))
    threshold = meta.get("low_score_threshold")
    if threshold is not None:
        try:
            threshold = int(threshold)
        except (TypeError, ValueError):
            threshold = DEFAULT_LOW_SCORE_THRESHOLD

    base = {
        "should_ask": False,
        "reason": "unknown",
        "metadata_present": metadata_present,
        "heuristic_fallback": heuristic_fallback,
        "answer_kind": answer_kind,
        "step_role": str(question.get("step_role") or ""),
        "question_topic": meta.get("question_topic"),
        "low_score_threshold": threshold,
    }

    if meta.get("auto_followup_enabled") is False:
        return {**base, "reason": "auto_followup_disabled"}

    if not lowered:
        return {**base, "reason": "empty_answer"}

    overrides = get_followup_overrides(config)
    for term in overrides["skip_followup_terms"]:
        if term and term in lowered:
            return {**base, "reason": "skip_followup_term", "matched_term": term}

    for term in overrides["force_negative_terms"]:
        if term and term in lowered:
            return {**base, "should_ask": True, "reason": "force_negative_term", "matched_term": term}

    if is_specific_complaint(raw):
        return {**base, "reason": "specific_complaint_detected"}

    if answer_kind == "rating":
        if is_low_score_answer(raw, threshold=threshold):
            return {**base, "should_ask": True, "reason": "low_score_rating"}
        if is_vague_negative_phrase(raw):
            return {**base, "should_ask": True, "reason": "vague_negative_phrase"}
        return {**base, "reason": "rating_not_negative"}

    if answer_kind == "yes_no" and lowered in {"no", "not really", "nah"}:
        return {**base, "should_ask": True, "reason": "yes_no_negative"}

    if is_vague_negative_phrase(raw):
        return {**base, "should_ask": True, "reason": "vague_negative_phrase"}

    return {**base, "reason": "not_vague_negative"}


def should_ask_vague_negative_followup(
    *,
    answer: str,
    question: dict[str, Any],
    config: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    return bool(
        explain_vague_negative_decision(
            answer=answer,
            question=question,
            config=config,
            metadata=metadata,
        ).get("should_ask")
    )


def _inbound_phone_matches(row: WhatsAppLog, recipient_phone: str) -> bool:
    digits = re.sub(r"\D", "", str(recipient_phone or ""))
    from_digits = re.sub(r"\D", "", str(row.from_number or ""))
    if not digits or not from_digits:
        return False
    return digits.endswith(from_digits[-10:]) or from_digits.endswith(digits[-10:])


def _service_window_org_context(
    *,
    matched_order_org_id: str,
    webhook_org_id: str | None = None,
) -> dict[str, str | None]:
    matched_key = str(matched_order_org_id or "").strip()
    webhook_key = str(webhook_org_id or "").strip()
    effective = matched_key or webhook_key or None
    return {
        "matched_order_org_id": matched_key or None,
        "webhook_org_id": webhook_key or None,
        "effective_org_id": effective,
    }


def explain_service_window(
    db: Session,
    *,
    org_id: str,
    recipient_phone: str,
    log_id: int | None = None,
    reference_time: datetime | None = None,
    webhook_org_id: str | None = None,
) -> dict[str, Any]:
    """Explain why the 24h WhatsApp service window is open or closed."""
    now = reference_time or datetime.utcnow()
    window = timedelta(hours=SERVICE_WINDOW_HOURS)
    org_key = str(org_id or "").strip()
    org_context = _service_window_org_context(
        matched_order_org_id=org_key,
        webhook_org_id=webhook_org_id,
    )

    if log_id is not None:
        row = db.get(WhatsAppLog, int(log_id))
        if row is None:
            return {**org_context, "open": False, "reason": "log_id_not_found", "log_id": log_id}
        if str(row.direction or "").lower() != "inbound":
            return {
                **org_context,
                "open": False,
                "reason": "log_id_not_inbound",
                "log_id": log_id,
                "direction": row.direction,
            }
        log_org = str(row.org_id or "")
        age = now - row.created_at
        age_seconds = int(age.total_seconds())
        within_window = age <= window
        phone_matches = _inbound_phone_matches(row, recipient_phone)

        if log_org == org_key:
            if within_window:
                return {
                    **org_context,
                    "open": True,
                    "reason": "current_inbound_log",
                    "log_id": log_id,
                    "age_seconds": age_seconds,
                }
            return {
                **org_context,
                "open": False,
                "reason": "log_id_outside_window",
                "log_id": log_id,
                "age_seconds": age_seconds,
            }

        # Survey recipient matched to order org; webhook log may be scoped to a different org.
        if within_window and phone_matches:
            return {
                **org_context,
                "open": True,
                "reason": "current_inbound_log_survey_matched",
                "log_id": log_id,
                "log_org_id": log_org,
                "age_seconds": age_seconds,
                "org_mismatch_accepted": True,
            }
        if not within_window:
            return {
                **org_context,
                "open": False,
                "reason": "log_id_outside_window",
                "log_id": log_id,
                "log_org_id": log_org,
                "age_seconds": age_seconds,
            }
        if not phone_matches:
            return {
                **org_context,
                "open": False,
                "reason": "log_id_phone_mismatch",
                "log_id": log_id,
                "log_org_id": log_org,
            }
        return {
            **org_context,
            "open": False,
            "reason": "log_id_org_mismatch",
            "log_id": log_id,
            "log_org_id": log_org,
            "expected_org_id": org_key,
        }

    from sqlalchemy import select

    digits = re.sub(r"\D", "", str(recipient_phone or ""))
    org_keys: list[str] = []
    for candidate in (org_key, str(webhook_org_id or "").strip()):
        if candidate and candidate not in org_keys:
            org_keys.append(candidate)

    for search_org in org_keys:
        stmt = (
            select(WhatsAppLog)
            .where(WhatsAppLog.org_id == search_org)
            .where(WhatsAppLog.direction == "inbound")
            .order_by(WhatsAppLog.created_at.desc())
            .limit(20)
        )
        for row in db.execute(stmt).scalars():
            if not _inbound_phone_matches(row, recipient_phone):
                continue
            age = now - row.created_at
            age_seconds = int(age.total_seconds())
            if age <= window:
                return {
                    **org_context,
                    "open": True,
                    "reason": "recent_inbound_log",
                    "log_id": row.id,
                    "age_seconds": age_seconds,
                    "searched_org_id": search_org,
                }
            return {
                **org_context,
                "open": False,
                "reason": "recent_inbound_outside_window",
                "log_id": row.id,
                "age_seconds": age_seconds,
                "searched_org_id": search_org,
            }
    return {
        **org_context,
        "open": False,
        "reason": "no_recent_inbound_for_phone",
        "phone_digits": digits[-4:] if digits else "",
        "searched_org_ids": org_keys,
    }


def log_vague_negative_decision(
    event: str,
    *,
    order_id: str | None = None,
    recipient_id: str | None = None,
    step: int | None = None,
    answer: str | None = None,
    handler: str = "",
    decision: dict[str, Any] | None = None,
    service_window: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    logger.info(
        "%s %s order_id=%s recipient_id=%s step=%s answer=%r handler=%s "
        "decision=%s service_window=%s extra=%s",
        LOG_PREFIX,
        event,
        order_id,
        recipient_id,
        step,
        (answer or "")[:120],
        handler,
        decision or {},
        service_window or {},
        extra or {},
    )


def evaluate_vague_negative_followup(
    db: Session,
    *,
    answer: str,
    question: dict[str, Any],
    config: dict[str, Any] | None,
    order_id: str,
    org_id: str,
    recipient_phone: str,
    log_id: int | None = None,
    webhook_org_id: str | None = None,
) -> dict[str, Any]:
    """Full decision: should ask, why, service window, follow-up text if applicable."""
    meta = parse_auto_followup_from_question(question)
    decision = explain_vague_negative_decision(
        answer=answer,
        question=question,
        config=config,
        metadata=meta,
    )
    service_window = explain_service_window(
        db,
        org_id=org_id,
        recipient_phone=recipient_phone,
        log_id=log_id,
        webhook_org_id=webhook_org_id,
    )
    followup_text = None
    if decision.get("should_ask") and service_window.get("open"):
        followup_text = generate_followup_text(question=question, metadata=meta)
    should_ask = bool(decision.get("should_ask"))
    should_send = bool(should_ask and service_window.get("open"))
    log_vague_negative_decision(
        "service_window_validation",
        order_id=order_id,
        answer=answer,
        decision=decision,
        service_window=service_window,
        extra={
            "should_ask": should_ask,
            "should_send": should_send,
            "webhook_org_id": service_window.get("webhook_org_id") or webhook_org_id,
            "matched_order_org_id": service_window.get("matched_order_org_id") or org_id,
            "effective_org_id": service_window.get("effective_org_id"),
            "log_id": log_id,
        },
    )
    return {
        "should_ask": should_ask,
        "should_send": should_send,
        "decision": decision,
        "service_window": service_window,
        "followup_text": followup_text,
        "metadata_present": decision.get("metadata_present"),
        "heuristic_fallback": decision.get("heuristic_fallback"),
    }


def is_whatsapp_service_window_open(
    db: Session,
    *,
    org_id: str,
    recipient_phone: str,
    log_id: int | None = None,
    reference_time: datetime | None = None,
    webhook_org_id: str | None = None,
) -> bool:
    """True when a free-form session message is allowed (24h after last user inbound)."""
    return bool(
        explain_service_window(
            db,
            org_id=org_id,
            recipient_phone=recipient_phone,
            log_id=log_id,
            reference_time=reference_time,
            webhook_org_id=webhook_org_id,
        ).get("open")
    )


def merge_elaboration_into_answers(answers: list[dict[str, Any]], elaboration: str) -> None:
    if not answers:
        return
    last = answers[-1]
    last["elaboration"] = str(elaboration or "").strip()
    base = str(last.get("answer") or "").strip()
    if base and last["elaboration"]:
        last["answer_display"] = f"{base} — {last['elaboration']}"
    elif last["elaboration"]:
        last["answer_display"] = last["elaboration"]
