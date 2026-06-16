"""Waiter pipeline — coordinates layers A through G."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.agent import _deepseek_platform_ready
from app.abuu.agent.session import save_session
from app.abuu.conversation.wa_sanitize import wa_customer_sanitize
from app.abuu.menu_intelligence.dietary_detector import DietaryDetector
from app.abuu.models.entities import CustomerOrder
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.menu_intelligence.query_expansion import (
    UNKNOWN_QUERY_REPLY_AR,
    expand_food_query,
    expansion_context_payload,
    intent_with_expansion,
)
from app.abuu.waiter.action_runner import WaiterActionRunner
from app.abuu.waiter.fact_loader import WaiterFactLoader
from app.abuu.waiter.intent_router import WaiterIntentRouter
from app.abuu.waiter.interpretation import InterpretationResult, WaiterInterpretation
from app.abuu.waiter.reply_composer import WaiterReplyComposer
from app.abuu.waiter.session_store import WaiterSessionStore
from app.abuu.waiter.smart_pipeline import SmartPipeline
from app.abuu.waiter.trace import trace
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WaiterPipeline:
    @staticmethod
    def enabled_for_phone(phone: str) -> bool:
        settings = get_settings()
        mode = str(settings.abuu_conversation_mode or "").lower()
        if mode not in {"waiter_v2", "waiter2", "waiter-v2"}:
            return False
        if not settings.abuu_agent_enabled:
            return False
        allowlist = str(settings.abuu_waiter_v2_allowlist or "").strip()
        if not allowlist:
            return True
        allowed = {p.strip() for p in allowlist.split(",") if p.strip()}
        return phone in allowed

    @staticmethod
    def handle(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        text: str,
        message_id: str | None = None,
        org_id: str | None = None,
        interpretation: InterpretationResult | None = None,
        is_voice: bool = False,
        stt_confidence: float = 0.0,
        stt_needs_clarification: bool = False,
    ) -> dict[str, Any]:
        if get_settings().abuu_smart_pipeline_enabled:
            return SmartPipeline.handle(
                abuu_db,
                main_db,
                phone=phone,
                text=text,
                message_id=message_id,
                org_id=org_id,
                interpretation=interpretation,
                is_voice=is_voice,
                stt_confidence=stt_confidence,
                stt_needs_clarification=stt_needs_clarification,
            )

        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        session, _state = WaiterSessionStore.load(abuu_db, phone)
        session.language = customer.preferred_language or session.language or "ar"

        working_text = text
        if interpretation is None and is_voice:
            interpretation = WaiterInterpretation.interpret(
                abuu_db,
                main_db,
                transcript=text,
                stt_confidence=stt_confidence,
                session=session,
                customer=customer,
                lang=session.language,
                is_voice=True,
                stt_needs_clarification=stt_needs_clarification,
            )
        if interpretation:
            working_text = interpretation.corrected_transcript
            WaiterSessionStore.apply_interpretation(session, interpretation)
            if (
                interpretation.needs_clarification
                and interpretation.clarification_prompt
                and interpretation.should_block_turn()
            ):
                ctx = session.context or {}
                if not ctx.get("voice_clarification_sent"):
                    session.context = dict(ctx)
                    session.context["voice_clarification_sent"] = True
                    session.context["clarification_count"] = int(ctx.get("clarification_count") or 0) + 1
                    save_session(abuu_db, session, message_id=message_id)
                    trace("OUT", preview=interpretation.clarification_prompt[:200], clarify=True)
                    return {
                        "handled": True,
                        "action": "voice_clarification",
                        "reply": interpretation.clarification_prompt,
                        "reason": interpretation.clarification_reason,
                    }

        trace("IN", phone=phone, text=working_text[:200], voice=is_voice)

        WaiterSessionStore.append_context_message(session, role="customer", text=working_text)

        voice_ctx = (session.context or {}).get("voice_interpretation") or {}
        allergy_uncertain = bool(voice_ctx.get("allergy_uncertain"))

        dietary = DietaryDetector.detect(working_text)
        if dietary.allergens_avoid and not allergy_uncertain:
            session.context["allergen_avoid"] = dietary.allergens_avoid
        if dietary.dietary_tags:
            session.context["dietary_tags"] = dietary.dietary_tags
        if dietary.kitchen_note and not allergy_uncertain:
            session.context["kitchen_allergy_note"] = dietary.kitchen_note

        intent = WaiterIntentRouter.classify(main_db, working_text, session, interpretation)
        session.context["current_intent"] = intent.name

        expanded_query_text: str | None = None
        if intent.name in {"food_search", "select_item"}:
            expansion = expand_food_query(main_db, raw=working_text)
            session.context = dict(session.context or {})
            session.context["last_query_expansion"] = expansion_context_payload(expansion)
            if expansion.unknown:
                save_session(abuu_db, session, message_id=message_id)
                trace("OUT", preview=UNKNOWN_QUERY_REPLY_AR[:200], clarify=True)
                return {
                    "handled": True,
                    "action": "query_clarification",
                    "reply": UNKNOWN_QUERY_REPLY_AR,
                    "intent": intent.name,
                }
            intent = intent_with_expansion(intent, expansion)
            expanded_query_text = expansion.expanded
            session.context["current_intent"] = intent.name

        draft_session = AbuuOrderDraftService.get_session(abuu_db, phone)
        order = (
            abuu_db.get(CustomerOrder, draft_session.active_order_id)
            if draft_session and draft_session.active_order_id
            else None
        )

        facts = WaiterFactLoader.load(
            abuu_db,
            intent,
            session,
            customer=customer,
            interpretation=interpretation,
            main_db=main_db,
            query_text=expanded_query_text,
        )
        action = WaiterActionRunner.run(
            abuu_db, intent, facts, session, customer=customer, order=order
        )

        if action.delegate == "confirm":
            WaiterSessionStore.save(abuu_db, session, message_id=message_id)
            return {"handled": True, "action": "delegate_confirm", "intent": intent.name}
        if action.delegate == "cancel":
            WaiterSessionStore.save(abuu_db, session, message_id=message_id)
            return {"handled": True, "action": "cancelled", "intent": intent.name}

        deepseek = _deepseek_platform_ready(main_db)
        reply = WaiterReplyComposer.compose(
            main_db,
            intent,
            facts,
            action,
            session,
            customer=customer,
            user_text=working_text,
            deepseek_ready=deepseek,
            abuu_db=abuu_db,
        )
        reply = wa_customer_sanitize(reply)

        WaiterSessionStore.append_context_message(session, role="agent", text=reply)
        session.messages.append({"role": "user", "content": working_text})
        session.messages.append({"role": "assistant", "content": reply})
        if action.action == "item_added":
            session.stage = "browsing"
        session.context["session_schema_version"] = 2
        WaiterSessionStore.save(abuu_db, session, message_id=message_id)

        return {
            "handled": True,
            "action": (action.action if action.action not in {None, "", "none"} else intent.name),
            "reply": reply,
            "intent": intent.name,
            "restaurant_id": session.restaurant_id,
            "order_id": session.active_order_id,
            "step": session.stage,
        }
