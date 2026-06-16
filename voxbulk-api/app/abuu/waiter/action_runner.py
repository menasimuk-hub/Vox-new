"""Deterministic actions — delegates to conversation ActionRunner."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.action_runner import ActionResult, ActionRunner
from app.abuu.conversation.fact_bundle import FactBundle
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.models.entities import CustomerOrder, CustomerProfile
from app.abuu.waiter.trace import trace


class WaiterActionRunner:
    @staticmethod
    def run(
        db: Session,
        intent: AbuuIntent,
        facts: FactBundle,
        session: AgentSession,
        *,
        customer: CustomerProfile,
        order: CustomerOrder | None,
    ) -> ActionResult:
        result = ActionRunner.run(db, intent, facts, session, customer=customer, order=order)
        trace("ACTION", action=result.action, delegate=result.delegate)
        if result.action == "cross_restaurant_blocked":
            trace("GUARD", conflict="cross_restaurant_blocked")
        return result
