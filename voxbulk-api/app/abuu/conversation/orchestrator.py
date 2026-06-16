"""Unified conversational WhatsApp ordering pipeline."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.agent import _deepseek_platform_ready
from app.abuu.agent.session import load_session, save_session
from app.abuu.conversation.action_runner import ActionRunner
from app.abuu.conversation.fact_bundle import FactBundleLoader
from app.abuu.conversation.intent_router import IntentRouter
from app.abuu.conversation.reply_composer import ReplyComposer
from app.abuu.conversation.wa_sanitize import wa_customer_sanitize
from app.abuu.models.entities import CustomerOrder
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AbuuConversationOrchestrator:
    @staticmethod
    def handle(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        text: str,
        message_id: str | None = None,
        org_id: str | None = None,
    ) -> dict[str, Any]:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        draft_session = AbuuOrderDraftService.get_session(abuu_db, phone)
        order = (
            abuu_db.get(CustomerOrder, draft_session.active_order_id)
            if draft_session and draft_session.active_order_id
            else None
        )
        session = load_session(abuu_db, phone)
        session.language = customer.preferred_language or session.language or "ar"

        intent = IntentRouter.classify(main_db, text, session)
        facts = FactBundleLoader.load(abuu_db, intent, session, customer=customer)
        action = ActionRunner.run(abuu_db, intent, facts, session, customer=customer, order=order)

        if action.delegate == "confirm":
            save_session(abuu_db, session, message_id=message_id)
            return {
                "handled": True,
                "action": "delegate_confirm",
                "intent": intent.name,
            }
        if action.delegate == "cancel":
            save_session(abuu_db, session, message_id=message_id)
            return {"handled": True, "action": "cancelled", "intent": intent.name}

        deepseek = _deepseek_platform_ready(main_db)
        reply = ReplyComposer.compose(
            main_db,
            intent,
            facts,
            action,
            session,
            customer=customer,
            user_text=text,
            deepseek_ready=deepseek,
            abuu_db=abuu_db,
        )
        reply = wa_customer_sanitize(reply)

        session.messages.append({"role": "user", "content": text})
        session.messages.append({"role": "assistant", "content": reply})
        if action.action == "item_added":
            session.stage = "browsing"
        save_session(abuu_db, session, message_id=message_id)

        return {
            "handled": True,
            "action": (action.action if action.action not in {None, "", "none"} else intent.name),
            "reply": reply,
            "intent": intent.name,
            "restaurant_id": session.restaurant_id,
            "order_id": session.active_order_id,
            "step": session.stage,
        }

    @staticmethod
    def conversation_enabled() -> bool:
        settings = get_settings()
        if not settings.abuu_agent_enabled:
            return False
        mode = str(getattr(settings, "abuu_conversation_mode", "orchestrator") or "orchestrator").lower()
        return mode in {"orchestrator", "waiter", "1"}
