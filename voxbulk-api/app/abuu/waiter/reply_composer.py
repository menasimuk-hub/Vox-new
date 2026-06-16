"""Waiter reply composer — template first, optional DeepSeek polish with timeout fallback."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.action_runner import ActionResult
from app.abuu.conversation.fact_bundle import FactBundle
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.conversation.reply_composer import ReplyComposer
from app.abuu.conversation.wa_sanitize import wa_customer_sanitize
from app.abuu.models.entities import CustomerProfile
from app.abuu.waiter.deepseek_client import WaiterDeepSeekClient
from app.abuu.waiter.trace import trace

_REPLY_PROMPT = """You are a warm Gaza WhatsApp food-order waiter (YallaSay). Arabic-first; support English and mixed Arabizi.
Rules:
- Short (2-4 lines), friendly, light emoji (1-2 max)
- Use ONLY facts provided — never invent menu items, prices, or restaurants
- Never show internal IDs, slugs, or technical fields
- One order = one restaurant; each order costs 15 NIS delivery fee
- If facts list dishes, show them — never ask to clarify when food type is already named (دجاج, سمك, etc.)"""


class WaiterReplyComposer:
    @staticmethod
    def compose(
        main_db: Session,
        intent: AbuuIntent,
        facts: FactBundle,
        action: ActionResult,
        session: AgentSession,
        *,
        customer: CustomerProfile,
        user_text: str,
        deepseek_ready: bool,
        abuu_db: Session | None = None,
    ) -> str:
        if action.reply_hint:
            reply = action.reply_hint
        else:
            lang = session.language or "ar"
            template = ReplyComposer._template(
                intent, facts, action, session, customer=customer, lang=lang, abuu_db=abuu_db
            )
            reply = template
            if deepseek_ready and action.action not in {"cross_restaurant_blocked", "item_added"}:
                facts_block = json.dumps(
                    {
                        "intent": intent.name,
                        "facts_text": template,
                        "user_message": user_text,
                        "cart_items": len(session.cart or []),
                        "restaurant_bound": bool(session.restaurant_id),
                    },
                    ensure_ascii=False,
                )
                ds = WaiterDeepSeekClient.complete(
                    main_db,
                    system_prompt=_REPLY_PROMPT,
                    user_content=facts_block,
                    max_tokens=400,
                    temperature=0.4,
                )
                if ds.fallback_used:
                    trace("INTENT", name=intent.name, source="template_fallback", fallback=True)
                elif ds.text:
                    from app.abuu.waiter.ordering_policy import is_generic_clarify_reply

                    if is_generic_clarify_reply(ds.text) and facts.customer_lines:
                        trace("INTENT", name=intent.name, source="template_fallback", fallback=True)
                    else:
                        reply = ds.text

        if action.upsell_hint and action.upsell_hint not in reply:
            reply = f"{reply}\n{action.upsell_hint}".strip()
        sanitized = wa_customer_sanitize(reply)
        trace("OUT", intent=intent.name, action=action.action, preview=sanitized[:200])
        return sanitized
