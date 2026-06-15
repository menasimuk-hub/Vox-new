from __future__ import annotations

from typing import Any

from app.schemas.assistant import (
    AssistantChatOut,
    AssistantContextIn,
    AssistantNextAction,
    AssistantPendingAction,
    AssistantUiCommand,
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
    ui_commands: list[AssistantUiCommand] | None = None,
    blocking_reason: str | None = None,
    pending_action: AssistantPendingAction | None = None,
    policy_refused: bool = False,
    error_occurred: bool = False,
    support_report_token: str | None = None,
    suggested_prompts: list[str] | None = None,
) -> AssistantChatOut:
    resolved_ui = ui_commands or []
    resolved_next = next_actions or []
    if not resolved_next and resolved_ui:
        for cmd in resolved_ui:
            if cmd.kind in {"navigate", "open_panel"} and cmd.route:
                resolved_next.append(
                    AssistantNextAction(
                        id=cmd.id,
                        label=cmd.label,
                        kind="open_panel" if cmd.kind == "open_panel" else "navigate",
                        route=cmd.route,
                    )
                )
    return AssistantChatOut(
        ok=not policy_refused,
        primary_message=primary_message,
        highlight_type=highlight_type or "",
        highlight_id=highlight_id,
        highlight_label=highlight_label,
        next_actions=resolved_next,
        ui_commands=resolved_ui,
        blocking_reason=blocking_reason,
        confidence=confidence,
        intent=intent,
        pending_action=pending_action,
        policy_refused=policy_refused,
        error_occurred=error_occurred,
        support_report_token=support_report_token,
        suggested_prompts=suggested_prompts or [],
    )


def plan_subscription_dict(sub, plan) -> dict[str, Any]:
    return {
        "subscription": SubscriptionOut.model_validate(sub).model_dump() if sub else None,
        "plan": PlanOut.model_validate(plan).model_dump() if plan else None,
    }
