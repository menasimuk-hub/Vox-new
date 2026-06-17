"""Transactional-first routing before Phase 1 browse fallbacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.abuu.agent.pending_action import (
    apply_pending_add_items,
    clear_transactional_context,
    format_cart_summary_for_session,
    get_pending_action,
    is_affirmative_reply,
    is_cart_inquiry,
    is_explicit_flow_exit,
    is_negative_reply,
    is_transactional_flow,
)
from app.abuu.models.entities import CustomerProfile

if TYPE_CHECKING:
    from app.abuu.agent.session import Session as AgentSession

TransactionalBranch = str


def try_transactional_reply(
    db: Session,
    session: AgentSession,
    *,
    customer: CustomerProfile,
    user_text: str,
) -> tuple[str, TransactionalBranch] | None:
    """Resolve pending cart confirmation and cart inquiries before Phase 1 browse."""
    lang = session.language or "ar"
    pending = get_pending_action(session)

    if pending is not None:
        if is_explicit_flow_exit(user_text):
            clear_transactional_context(session)
            return None

        if is_affirmative_reply(user_text):
            try:
                reply = apply_pending_add_items(db, session, customer=customer)
                return reply, "transactional_pending_confirmed"
            except ValueError as exc:
                if lang == "ar":
                    return str(exc) or "ما قدرت أضيف للسلة.", "transactional_pending_error"
                return str(exc) or "Could not add to cart.", "transactional_pending_error"

        if is_negative_reply(user_text):
            clear_transactional_context(session)
            if lang == "ar":
                return "تمام، ما أضفتهم. شو بدك تطلب؟", "transactional_pending_cancelled"
            return "OK, I didn't add them. What would you like?", "transactional_pending_cancelled"

        if is_cart_inquiry(user_text):
            summary = format_cart_summary_for_session(db, session, lang)
            return summary, "transactional_pending_cart_summary"

        if lang == "ar":
            return "ما فهمت تأكيدك. قول نعم أو لا، أو اسأل عن السلة.", "transactional_pending_clarify"
        return "I didn't catch that. Say yes or no, or ask about your cart.", "transactional_pending_clarify"

    if is_transactional_flow(session) and is_cart_inquiry(user_text):
        summary = format_cart_summary_for_session(db, session, lang)
        return summary, "transactional_cart_summary"

    if is_transactional_flow(session) and not is_explicit_flow_exit(user_text):
        # Block accidental browse routing — handled by intent_gate guards; no reply here.
        return None

    return None
