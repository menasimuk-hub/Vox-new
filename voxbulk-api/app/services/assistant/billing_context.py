"""Secondary billing checks — only when an explicit user task may be blocked."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.services.assistant.tools import AssistantTools

# Intents where billing/package state can legitimately block or delay the action.
_BILLING_BLOCK_INTENTS = frozenset(
    {
        "launch_check",
        "create_survey",
        "create_template",
        "create_feedback",
    }
)


def fetch_billing_access(db: Session, org: Organisation) -> dict[str, Any]:
    return AssistantTools.billing_access(db, org)


def billing_blocks_intent(intent: str) -> bool:
    return intent in _BILLING_BLOCK_INTENTS


def billing_note_for_intent(access: dict[str, Any], intent: str) -> tuple[str | None, str | None]:
    """
    Return (blocking_reason, message_suffix) only when billing is relevant to this intent.
    Template creation is not blocked by package exhaustion (launch uses wallet separately).
    """
    if not billing_blocks_intent(intent):
        return None, None

    if intent == "create_template":
        # Designing templates in the wizard does not require an active package allowance.
        return None, None

    next_label = str(access.get("next_action_label") or access.get("next_action") or "").strip()
    block_reason = str(access.get("block_reason") or "").strip()

    if intent == "launch_check":
        if block_reason:
            return block_reason, f" Note: {block_reason}"
        if next_label and any(k in next_label.lower() for k in ("exhausted", "payment", "mandate", "wallet", "invoice")):
            return next_label, f" Heads-up on billing: {next_label}"
        return None, None

    if intent in {"create_survey", "create_feedback"}:
        if block_reason and "suspend" in block_reason.lower():
            return block_reason, f" Billing note: {block_reason}"
        return None, None

    return None, None
