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
from app.abuu.menu_intelligence.query_expansion import (
    UNKNOWN_QUERY_REPLY_AR,
    expand_food_query,
    expansion_context_payload,
    intent_with_expansion,
)
from app.abuu.conversation.reply_composer import ReplyComposer
from app.abuu.conversation.wa_sanitize import wa_customer_sanitize
from app.abuu.models.entities import CustomerOrder
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import voice_unclear_transcript_message
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

        if not str(text or "").strip():
            reply = voice_unclear_transcript_message(session.language or "ar")
            return {"handled": True, "action": "voice_empty", "reply": reply}

        from app.abuu.agent.menu_pick_parser import is_menu_pick_message
        from app.abuu.agent.pending_action import (
            format_cart_summary_for_session,
            is_cart_inquiry,
            propose_menu_picks_from_text,
        )

        lang = session.language or "ar"
        if is_cart_inquiry(text):
            reply = format_cart_summary_for_session(abuu_db, session, lang)
            session.messages.append({"role": "user", "content": text})
            session.messages.append({"role": "assistant", "content": reply})
            save_session(abuu_db, session, message_id=message_id)
            return {
                "handled": True,
                "action": "cart_summary",
                "reply": wa_customer_sanitize(reply),
                "restaurant_id": session.restaurant_id,
            }

        if session.restaurant_id and is_menu_pick_message(text):
            reply = propose_menu_picks_from_text(abuu_db, session, user_text=text, lang=lang)
            session.messages.append({"role": "user", "content": text})
            session.messages.append({"role": "assistant", "content": reply})
            save_session(abuu_db, session, message_id=message_id)
            return {
                "handled": True,
                "action": "propose_menu_items",
                "reply": wa_customer_sanitize(reply),
                "restaurant_id": session.restaurant_id,
            }

        from app.abuu.menu_intelligence.dietary_detector import DietaryDetector

        voice_ctx = (session.context or {}).get("voice_interpretation") or {}
        allergy_uncertain = bool(voice_ctx.get("allergy_uncertain"))

        dietary = DietaryDetector.detect(text)
        if dietary.allergens_avoid and not allergy_uncertain:
            session.context["allergen_avoid"] = dietary.allergens_avoid
        if dietary.dietary_tags:
            session.context["dietary_tags"] = dietary.dietary_tags
        if dietary.kitchen_note and not allergy_uncertain:
            session.context["kitchen_allergy_note"] = dietary.kitchen_note

        intent = IntentRouter.classify(main_db, text, session)
        expanded_query_text: str | None = None
        if intent.name in {"food_search", "select_item"}:
            expansion = expand_food_query(main_db, raw=text)
            session.context = dict(session.context or {})
            session.context["last_query_expansion"] = expansion_context_payload(expansion)
            if expansion.unknown:
                save_session(abuu_db, session, message_id=message_id)
                return {
                    "handled": True,
                    "action": "query_clarification",
                    "reply": UNKNOWN_QUERY_REPLY_AR,
                    "intent": intent.name,
                }
            intent = intent_with_expansion(intent, expansion)
            expanded_query_text = expansion.expanded

        facts = FactBundleLoader.load(
            abuu_db,
            intent,
            session,
            customer=customer,
            main_db=main_db,
            query_text=expanded_query_text,
        )
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
        try:
            save_session(abuu_db, session, message_id=message_id)
        except Exception:
            logger.exception(
                "abuu_orchestrator_session_save_failed phone=%s message_id=%s",
                phone,
                message_id,
            )
            raise

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
