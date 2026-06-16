"""Single session load/save API for waiter pipeline."""

from __future__ import annotations

from app.abuu.agent.session import Session as AgentSession, load_session, save_session
from app.abuu.waiter.session_state import WaiterSessionState


class WaiterSessionStore:
    @staticmethod
    def load(abuu_db, phone: str) -> tuple[AgentSession, WaiterSessionState]:
        session = load_session(abuu_db, phone)
        ctx = session.context or {}
        state = WaiterSessionState(
            phone=phone,
            customer_id=session.customer_id,
            language=session.language or "ar",
            stage=session.stage,
            active_order_id=session.active_order_id,
            bound_restaurant_id=session.restaurant_id,
            messages=list(session.messages),
            current_intent=ctx.get("current_intent"),
            allergen_avoid=list(ctx.get("allergen_avoid") or []),
            dietary_tags=list(ctx.get("dietary_tags") or []),
            allergy_uncertain=bool((ctx.get("voice_interpretation") or {}).get("allergy_uncertain")),
            context=dict(ctx),
        )
        return session, state

    @staticmethod
    def save(abuu_db, session: AgentSession, *, message_id: str | None = None) -> None:
        save_session(abuu_db, session, message_id=message_id)

    @staticmethod
    def apply_interpretation(session: AgentSession, interpretation) -> None:
        session.context = dict(session.context or {})
        session.context["voice_interpretation"] = interpretation.to_context_json()
        session.context["current_intent"] = interpretation.final_inferred_intent
