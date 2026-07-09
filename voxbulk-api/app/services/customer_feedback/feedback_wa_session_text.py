"""Buttonless Customer Feedback templates — send as WhatsApp session text, not Meta HSM."""

from __future__ import annotations

from app.models.customer_feedback import FeedbackWaTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template
from app.services.customer_feedback.feedback_telnyx_push_service import parse_feedback_buttons

# System templates that stay local per wa-template-sync-contract (no Meta push/approval).
CF_SESSION_TEXT_TEMPLATE_KEYS = frozenset({"thank_you", "tell_us_more", "open_question"})

CF_SESSION_TEXT_STEP_ROLES = frozenset({"thank_you", "tell_us_more", "final_feedback_text"})


def feedback_template_must_send_as_session_text(tpl: FeedbackWaTemplate | None) -> bool:
    """True when the row is delivered as in-session free text (never Meta template send)."""
    if tpl is None:
        return False
    if is_marketing_wa_template(tpl):
        return False
    key = str(tpl.template_key or "").strip().lower()
    if key in CF_SESSION_TEXT_TEMPLATE_KEYS:
        return True
    role = str(tpl.step_role or "").strip().lower()
    if role in CF_SESSION_TEXT_STEP_ROLES:
        return True
    # Global system row with no quick-reply buttons (excluding marketing opt-in).
    if tpl.industry_id is None and tpl.survey_type_id is None and key != "marketing_opt_in":
        if not parse_feedback_buttons(tpl.buttons_json):
            return True
    return False
