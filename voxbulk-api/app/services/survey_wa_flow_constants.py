"""Canonical names and conversation keys for WhatsApp survey open-text flows.

Two separate flows — do not mix:
  • tell_us_more_on_low_rating  — after low rating button tap (system kind tell_us_more)
  • final_additional_feedback   — optional closing question (system kind final_feedback)
"""

from __future__ import annotations

# Runtime branch keys (builder_runtime.branches)
TELL_US_MORE_BRANCH = "tell_us_more_on_low_rating"
CLOSING_BRANCH = "final_additional_feedback"

# System template kinds (SurveyType.system_template_kind)
SYSTEM_KIND_TELL_US_MORE = "tell_us_more"
SYSTEM_KIND_CLOSING = "final_feedback"

# step_role values at send time
STEP_ROLE_TELL_US_MORE = "reason"
STEP_ROLE_CLOSING = "final_feedback_text"
STEP_ROLE_CLOSING_YES_NO_LEGACY = "final_feedback_yes_no"

# Log prefixes
LOG_TELL_US_MORE = "[wa-tell-us-more]"
LOG_CLOSING = "[wa-closing-question]"

# Open-text idle skip (seconds)
OPEN_TEXT_TIMEOUT_SEC = 300
BUTTON_ABANDON_HOURS = 20

WHATSAPP_SEND_FAILURE_HINT = (
    "Could not send the WhatsApp message. Check Admin → Connection Profiles and template approval."
)

# tell_us_more outcome values (low rating branch only)
TUM_OUTCOME_ANSWERED = "answered"
TUM_OUTCOME_SKIPPED_TIMEOUT = "skipped_timeout"
TUM_OUTCOME_SKIPPED_EMPTY = "skipped_empty"

# closing outcome values
CLOSING_OUTCOME_ANSWERED = "answered"
CLOSING_OUTCOME_SKIPPED_TIMEOUT = "skipped_timeout"
CLOSING_OUTCOME_DECLINED = "declined"

# wa_conversation keys — tell_us_more (low rating)
KEY_TUM_PENDING = "tell_us_more_pending"
KEY_TUM_ASKED = "tell_us_more_asked"
KEY_TUM_FIRED_STEPS = "tell_us_more_fired_steps"
KEY_TUM_SENT_AT = "tell_us_more_sent_at"
KEY_TUM_DEADLINE = "tell_us_more_deadline"
KEY_TUM_OUTCOME = "tell_us_more_outcome"
KEY_TUM_ELIGIBLE_FOLLOWUP = "tell_us_more_eligible_for_followup"
KEY_TUM_FOLLOWUP_HANDLED = "tell_us_more_followup_handled"

# wa_conversation keys — closing question
KEY_CLOSING_AWAITING = "awaiting_final_feedback_text"
KEY_CLOSING_DONE = "final_feedback_done"
KEY_CLOSING_DEADLINE = "final_feedback_text_deadline"
KEY_CLOSING_OUTCOME = "final_feedback_outcome"

# wa_conversation keys — survey lifecycle
KEY_SURVEY_STARTED_AT = "survey_started_at"

# wa_conversation keys — last outbound prompt kind (debug + voice routing)
KEY_LAST_OUTBOUND_KIND = "last_outbound_kind"
OUTBOUND_KIND_TELL_US_MORE = "tell_us_more"
OUTBOUND_KIND_VAGUE_AUTO_FOLLOWUP = "vague_auto_followup"
OUTBOUND_KIND_FINAL_FEEDBACK = "final_feedback"

# Scale/button steps that may branch to tell-us-more on worst answer (Poor / No / etc.)
TELL_US_MORE_TRIGGER_ROLES = frozenset(
    {"rating", "feeling_word", "helpfulness", "yes_no", "abc_choice"}
)

# Canonical button label order (best first → worst last in Meta BUTTONS array)
CANONICAL_RATING = ("Excellent", "Good", "Poor")
CANONICAL_MORALE = ("High", "Moderate", "Low")
CANONICAL_YES_NO = ("Yes", "No")
CANONICAL_HELPFULNESS = ("Very helpful", "Partly helpful", "Not helpful")
CANONICAL_FEELING = ("Great", "Okay", "Poor")

LOW_RATING_LABELS = frozenset(
    {
        "poor",
        "poorly",
        "not helpful",
        "no",
        "bad",
        "terrible",
        "awful",
        "worst",
        "low",
        "unlikely",
        "not really",
        "not worth it",
        "needs work",
        "needs improvement",
        "too long",
        "slow",
        "unclear",
        "unfriendly",
        "overpriced",
        "too crowded",
        "difficult",
        "not for me",
        "disagree",
        "strongly disagree",
        "very unlikely",
        "ضعيف",
        "لا",
        "سيئ",
        "kötü",
        "schlecht",
        "mal",
        "mauvais",
    }
)


def order_scale_labels(labels: list[str], *, step_role: str = "rating") -> list[str]:
    """Reorder scale labels: best/highest first, worst/lowest last (Meta BUTTONS array order)."""
    from app.services.survey_step_bank_service import normalize_step_role

    role = normalize_step_role(step_role)
    canonical: tuple[str, ...]
    if role == "rating":
        canonical = CANONICAL_RATING
    elif role == "yes_no":
        canonical = CANONICAL_YES_NO
    elif role == "helpfulness":
        canonical = CANONICAL_HELPFULNESS
    elif role == "feeling_word":
        canonical = CANONICAL_FEELING
    else:
        return list(labels)
    if len(labels) < 2:
        return list(labels)
    label_map = {str(l).strip().lower(): str(l).strip() for l in labels if str(l).strip()}
    keys = set(label_map.keys())
    if keys == {"high", "moderate", "low"} or keys >= {"high", "moderate", "low"}:
        canonical = CANONICAL_MORALE
    ordered: list[str] = []
    for canon in canonical:
        key = canon.lower()
        if key in label_map:
            ordered.append(label_map[key])
    for raw in labels:
        text = str(raw).strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def order_scale_button_dicts(buttons: list[dict], *, step_role: str = "rating") -> list[dict]:
    """Reorder button component dicts to canonical best-first order."""
    labels = [
        str(b.get("text") or b.get("label") or "").strip()
        for b in buttons
        if isinstance(b, dict)
    ]
    ordered_labels = order_scale_labels([x for x in labels if x], step_role=step_role)
    if not ordered_labels:
        return list(buttons)
    by_label = {
        str(b.get("text") or b.get("label") or "").strip().lower(): b
        for b in buttons
        if isinstance(b, dict) and str(b.get("text") or b.get("label") or "").strip()
    }
    out: list[dict] = []
    for label in ordered_labels:
        btn = by_label.get(label.lower())
        if btn is not None:
            out.append(btn)
    return out or list(buttons)
