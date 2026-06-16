"""Waiter intent router — wraps conversation router with interpretation hints."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.intent_router import AbuuIntent, IntentRouter
from app.abuu.waiter.interpretation import InterpretationResult
from app.abuu.waiter.trace import trace


class WaiterIntentRouter:
    @staticmethod
    def classify(
        main_db: Session,
        text: str,
        session: AgentSession,
        interpretation: InterpretationResult | None = None,
    ) -> AbuuIntent:
        if interpretation and interpretation.category_hints:
            session.context = dict(session.context or {})
            session.context["voice_interpretation"] = interpretation.to_context_json()
        intent = IntentRouter.classify(main_db, text, session)
        if interpretation and interpretation.category_hints and intent.name == "food_search":
            merged = list(intent.categories or [])
            for hint in interpretation.category_hints:
                if hint not in merged:
                    merged.append(hint)
            intent = AbuuIntent(
                name=intent.name,
                categories=merged,
                item_query=interpretation.inferred_item_query or intent.item_query,
                confidence=max(intent.confidence, interpretation.confidence),
                source="waiter_interpretation",
            )
        trace("INTENT", name=intent.name, source=intent.source, categories=intent.categories)
        return intent
