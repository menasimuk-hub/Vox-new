"""Load facts for waiter pipeline — delegates to FactBundleLoader."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.fact_bundle import FactBundle, FactBundleLoader
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.models.entities import CustomerProfile
from app.abuu.waiter.interpretation import InterpretationResult
from app.abuu.waiter.menu_query_builder import build_menu_query
from app.abuu.waiter.trace import trace


class WaiterFactLoader:
    @staticmethod
    def load(
        abuu_db: Session,
        intent: AbuuIntent,
        session: AgentSession,
        *,
        customer: CustomerProfile,
        interpretation: InterpretationResult | None = None,
        main_db: Session | None = None,
        query_text: str | None = None,
    ) -> FactBundle:
        if interpretation and interpretation.category_hints and intent.name == "food_search":
            intent = AbuuIntent(
                name=intent.name,
                categories=list(set(list(intent.categories or []) + interpretation.category_hints)),
                item_query=interpretation.inferred_item_query or intent.item_query,
                confidence=intent.confidence,
                source=intent.source,
            )
        menu_query = build_menu_query(intent, interpretation)
        if not query_text:
            query_text = menu_query.text_query or intent.item_query or ""
        trace(
            "MENU",
            intent=intent.name,
            categories=menu_query.categories,
            drink_only=getattr(menu_query, "drink_only", False),
            offer_only=getattr(menu_query, "offer_only", False),
        )
        bundle = FactBundleLoader.load(
            abuu_db,
            intent,
            session,
            customer=customer,
            main_db=main_db,
            query_text=query_text,
        )
        trace("MENU", intent=intent.name, items=len(bundle.food_items))
        return bundle
