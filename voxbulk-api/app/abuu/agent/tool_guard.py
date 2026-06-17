"""Phase 1 guarded tool execution — validate before mutating session/order state."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.orm import Session

from app.abuu import agent_trace
from app.abuu.agent.intent_gate import phase1_enabled, resolve_restaurant_ref, user_named_target_restaurant
from app.abuu.agent.session import Session as AgentSession
from app.abuu.agent.session_reset import is_session_reset_message
from app.abuu.agent.skills import execute_tool
from app.abuu.services.voice_order_debug_service import get_debug_request_id

_MUTATING_TOOLS = frozenset(
    {
        "select_restaurant",
        "change_restaurant",
        "add_to_cart",
        "remove_from_cart",
        "confirm_order",
        "cancel_order",
    }
)

_ERROR_PREFIXES = (
    "No restaurant selected",
    "Restaurant not found",
    "Something went wrong",
    "This action is not available",
    "Item not found",
    "Cart is empty",
    "Unknown tool:",
    "change_restaurant blocked",
    "change_restaurant requires",
)


def session_state_snapshot(session: AgentSession) -> dict[str, Any]:
    return {
        "restaurant_id": session.restaurant_id,
        "active_order_id": session.active_order_id,
        "stage": session.stage,
        "cart": copy.deepcopy(list(session.cart or [])),
        "context": copy.deepcopy(dict(session.context or {})),
    }


def restore_session_state(session: AgentSession, snapshot: dict[str, Any]) -> None:
    session.restaurant_id = snapshot.get("restaurant_id")
    session.active_order_id = snapshot.get("active_order_id")
    session.stage = str(snapshot.get("stage") or session.stage)
    session.cart = copy.deepcopy(list(snapshot.get("cart") or []))
    session.context = copy.deepcopy(dict(snapshot.get("context") or {}))


def is_tool_error_result(result: str) -> bool:
    text = str(result or "").strip()
    return any(text.startswith(prefix) for prefix in _ERROR_PREFIXES)


def is_proposal_success(tool_name: str, result: str, session: AgentSession) -> bool:
    if str(tool_name or "").strip() != "propose_add_to_cart":
        return False
    from app.abuu.agent.pending_action import get_pending_action

    return not is_tool_error_result(result) and get_pending_action(session) is not None


def validate_tool_call(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    session: AgentSession,
    user_text: str,
    db: Session,
) -> str | None:
    """Return error message if the tool call must be blocked; None if allowed."""
    if not phase1_enabled():
        return None

    ranked_rows = session.context.get("turn_ranked_restaurants") or session.context.get("ranked_restaurants") or []
    if not isinstance(ranked_rows, list):
        ranked_rows = []

    if tool_name == "change_restaurant":
        if not tool_input:
            return "change_restaurant blocked: empty arguments are not allowed in Phase 1."
        if user_named_target_restaurant(db, user_text=user_text, ranked_rows=ranked_rows):
            return (
                "change_restaurant blocked: customer named a target restaurant in the same message."
            )
        if not is_session_reset_message(user_text):
            return "change_restaurant blocked: customer did not ask to switch or list restaurants."

    if tool_name == "select_restaurant":
        ref = str(tool_input.get("restaurant_id") or "").strip()
        if not ref:
            return "select_restaurant requires restaurant_id."
        resolved = resolve_restaurant_ref(db, session, ref)
        if resolved is None:
            return f"Restaurant not found: {ref}"
        session.context["phase1_requested_restaurant_id"] = resolved.id

    if tool_name == "search_menu" and not session.restaurant_id:
        return "No restaurant selected. Use select_restaurant first."

    return None


def execute_tool_guarded(
    db: Session,
    session: AgentSession,
    *,
    customer: Any,
    tool_name: str,
    tool_input: dict[str, Any],
    user_text: str,
    correlation_id: str | None = None,
) -> str:
    corr = correlation_id or get_debug_request_id() or ""
    before = session_state_snapshot(session)
    agent_trace.state_before(
        correlation_id=corr,
        tool=tool_name,
        state=before,
    )

    block_reason = validate_tool_call(
        tool_name=tool_name,
        tool_input=tool_input or {},
        session=session,
        user_text=user_text,
        db=db,
    )
    if block_reason:
        agent_trace.state_after(
            correlation_id=corr,
            tool=tool_name,
            blocked=True,
            reason=block_reason,
            state=before,
        )
        return block_reason

    pre_mutate = session_state_snapshot(session) if tool_name in _MUTATING_TOOLS else None
    result = execute_tool(
        db,
        session,
        customer=customer,
        tool_name=tool_name,
        tool_input=tool_input or {},
    )

    if phase1_enabled() and tool_name in _MUTATING_TOOLS and is_tool_error_result(result):
        if pre_mutate is not None:
            restore_session_state(session, pre_mutate)
        agent_trace.state_after(
            correlation_id=corr,
            tool=tool_name,
            rolled_back=True,
            result_preview=agent_trace.clip(result),
            state=session_state_snapshot(session),
        )
        return result

    agent_trace.state_after(
        correlation_id=corr,
        tool=tool_name,
        state=session_state_snapshot(session),
        result_preview=agent_trace.clip(result),
    )
    return result
