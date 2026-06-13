from __future__ import annotations

from typing import Any

from app.schemas.assistant import (
    AssistantChatOut,
    AssistantContextIn,
    AssistantNextAction,
    AssistantPendingAction,
)
from app.schemas.dashboard import PlanOut, SubscriptionOut


def empty_highlight() -> dict[str, Any]:
    return {"highlight_type": "", "highlight_id": None, "highlight_label": None}


def nav_action(action_id: str, label: str, route: str) -> AssistantNextAction:
    return AssistantNextAction(id=action_id, label=label, kind="navigate", route=route)


def confirm_action(action_id: str, label: str, token: str) -> AssistantNextAction:
    return AssistantNextAction(id=action_id, label=label, kind="confirm", action_id=token)


def build_out(
    *,
    primary_message: str,
    confidence: float = 0.85,
    intent: str | None = None,
    highlight_type: str = "",
    highlight_id: str | None = None,
    highlight_label: str | None = None,
    next_actions: list[AssistantNextAction] | None = None,
    blocking_reason: str | None = None,
    pending_action: AssistantPendingAction | None = None,
    policy_refused: bool = False,
) -> AssistantChatOut:
    return AssistantChatOut(
        ok=not policy_refused,
        primary_message=primary_message,
        highlight_type=highlight_type or "",
        highlight_id=highlight_id,
        highlight_label=highlight_label,
        next_actions=next_actions or [],
        blocking_reason=blocking_reason,
        confidence=confidence,
        intent=intent,
        pending_action=pending_action,
        policy_refused=policy_refused,
    )


def plan_subscription_dict(sub, plan) -> dict[str, Any]:
    return {
        "subscription": SubscriptionOut.model_validate(sub).model_dump() if sub else None,
        "plan": PlanOut.model_validate(plan).model_dump() if plan else None,
    }
