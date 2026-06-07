"""Auto vague-negative WhatsApp survey follow-up — metadata, detection, free-form prompts."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

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


def should_ask_vague_negative_followup(
    *,
    answer: str,
    question: dict[str, Any],
    config: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    meta = metadata or parse_auto_followup_from_question(question)
    if meta.get("auto_followup_enabled") is False:
        return False

    raw = str(answer or "").strip()
    lowered = raw.lower()
    if not lowered:
        return False

    overrides = get_followup_overrides(config)
    for term in overrides["skip_followup_terms"]:
        if term and term in lowered:
            return False
    for term in overrides["force_negative_terms"]:
        if term and term in lowered:
            return True

    if is_specific_complaint(raw):
        return False

    answer_kind = str(meta.get("answer_kind") or infer_answer_kind(str(question.get("step_role") or "")))
    threshold = meta.get("low_score_threshold")
    if threshold is not None:
        try:
            threshold = int(threshold)
        except (TypeError, ValueError):
            threshold = DEFAULT_LOW_SCORE_THRESHOLD

    if answer_kind == "rating":
        if is_low_score_answer(raw, threshold=threshold):
            return True
        if is_vague_negative_phrase(raw):
            return True
        return False

    if answer_kind == "yes_no" and lowered in {"no", "not really", "nah"}:
        return True

    if is_vague_negative_phrase(raw):
        return True

    return False


def is_whatsapp_service_window_open(
    db: Session,
    *,
    org_id: str,
    recipient_phone: str,
    log_id: int | None = None,
    reference_time: datetime | None = None,
) -> bool:
    """True when a free-form session message is allowed (24h after last user inbound)."""
    now = reference_time or datetime.utcnow()
    window = timedelta(hours=SERVICE_WINDOW_HOURS)

    if log_id is not None:
        row = db.get(WhatsAppLog, int(log_id))
        if row is not None and str(row.direction or "").lower() == "inbound":
            if row.org_id == org_id and (now - row.created_at) <= window:
                return True

    from sqlalchemy import select

    digits = re.sub(r"\D", "", str(recipient_phone or ""))
    stmt = (
        select(WhatsAppLog)
        .where(WhatsAppLog.org_id == org_id)
        .where(WhatsAppLog.direction == "inbound")
        .order_by(WhatsAppLog.created_at.desc())
        .limit(20)
    )
    for row in db.execute(stmt).scalars():
        to_digits = re.sub(r"\D", "", str(row.from_number or row.to_number or ""))
        if digits and to_digits and (digits.endswith(to_digits[-10:]) or to_digits.endswith(digits[-10:])):
            return (now - row.created_at) <= window
    return False


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
