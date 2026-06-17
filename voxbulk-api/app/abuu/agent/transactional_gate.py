"""Deprecated wrapper — routing lives in turn_router.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

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
    """Backward-compatible shim; use try_turn_router_reply instead."""
    from app.abuu.agent.turn_router import try_turn_router_reply

    result = try_turn_router_reply(db, session, customer=customer, user_text=user_text)
    if result is None:
        return None
    reply, branch, _slots = result
    if branch.startswith("transactional_"):
        return reply, branch
    return None
