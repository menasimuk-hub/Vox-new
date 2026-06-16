"""Natural waiter phrasing for Abuu WhatsApp replies."""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.abuu.agent.session import Session as AgentSession
from app.abuu.conversation.action_runner import ActionResult
from app.abuu.conversation.fact_bundle import FactBundle
from app.abuu.conversation.intent_router import AbuuIntent
from app.abuu.services.customer_memory_service import first_name, saved_address_summary
from app.abuu.services.kb_service import format_greeting, resolve_settings
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)

_REPLY_PROMPT = """You are a warm Gaza WhatsApp food-order waiter (YallaSay). Arabic-first; support English and mixed Arabizi.
Rules:
- Short (2-4 lines), friendly, light emoji (1-2 max)
- Use ONLY facts provided — never invent menu items, prices, or restaurants
- Never show internal IDs, slugs, or technical fields
- Do not ask for menu numbers unless necessary
- One order = one restaurant; each order costs 15 NIS delivery fee
- Do not repeat the same greeting if conversation already started
- If facts list dishes, show them — never ask the customer to clarify when they already named a food type (دجاج, سمك, etc.)"""


class ReplyComposer:
    @staticmethod
    def compose(
        main_db: Session,
        intent: AbuuIntent,
        facts: FactBundle,
        action: ActionResult,
        session: AgentSession,
        *,
        customer,
        user_text: str,
        deepseek_ready: bool,
        abuu_db: Session | None = None,
    ) -> str:
        if action.reply_hint:
            return action.reply_hint

        lang = session.language or "ar"
        template = ReplyComposer._template(
            intent, facts, action, session, customer=customer, lang=lang, abuu_db=abuu_db
        )
        if not deepseek_ready or action.action in {"cross_restaurant_blocked", "item_added"}:
            return template

        try:
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
            result = OpenAIProviderService.complete(
                main_db,
                system_prompt=_REPLY_PROMPT,
                messages=[AgentMessage(role="user", content=facts_block)],
                max_tokens=400,
                temperature=0.4,
                provider="deepseek",
            )
            text = str(result.assistant_text or "").strip()
            if text:
                from app.abuu.waiter.ordering_policy import is_generic_clarify_reply

                if is_generic_clarify_reply(text) and facts.customer_lines:
                    return template
                return text
        except Exception:
            logger.warning("abuu_reply_compose_fallback", exc_info=True)
        return template

    @staticmethod
    def _template(
        intent: AbuuIntent,
        facts: FactBundle,
        action: ActionResult,
        session: AgentSession,
        *,
        customer,
        lang: str,
        abuu_db: Session | None = None,
    ) -> str:
        name = first_name(customer.name) if customer else None

        if intent.name == "greet" and abuu_db is not None:
            settings = resolve_settings(abuu_db)
            addr = saved_address_summary(abuu_db, customer) if customer else None
            msg = format_greeting(settings, first_name=name, lang=lang, saved_address=addr)
            if lang == "ar":
                msg += "\n\nاحكيلي شو جوعان — دجاج، سمك، لحم… وأنا بجهّزلك 👨‍🍳"
            else:
                msg += "\n\nTell me what you're craving — chicken, fish, meat… 👨‍🍳"
            return msg

        if intent.name == "food_search":
            if facts.customer_lines:
                header = "هذي اقتراحات تناسب طلبك 🍽️" if lang == "ar" else "Here's what matches 🍽️"
                body = "\n".join(facts.customer_lines)
                footer = (
                    "قول اسم الطبق اللي بيعجبك وأنا بضيفه 😋"
                    if lang == "ar"
                    else "Say the dish name you want and I'll add it 😋"
                )
                return f"{header}\n{body}\n{footer}"
            if lang == "ar":
                return "ما لقيت أطباق لهذا الطلب حالياً — جرّب نوع تاني أو اسأل عن المطاعم 🙏"
            return "No matching dishes right now — try another type or ask for restaurants 🙏"

        if intent.name == "restaurant_list" and facts.restaurant_list_text:
            prefix = "المطاعم المتاحة:" if lang == "ar" else "Available restaurants:"
            return f"{prefix}\n{facts.restaurant_list_text}"

        if intent.name == "offers" and facts.offers_text:
            prefix = "عروض اليوم 🔥" if lang == "ar" else "Today's offers 🔥"
            return f"{prefix}\n{facts.offers_text}"

        if intent.name == "menu_browse":
            if facts.menu_text:
                return facts.menu_text
            return facts.customer_lines[0] if facts.customer_lines else (
                "قولّي شو بدك من المنيو" if lang == "ar" else "Tell me what you'd like from the menu"
            )

        if intent.name == "select_item" and facts.customer_lines:
            header = "قريب من طلبك:" if lang == "ar" else "Close matches:"
            return header + "\n" + "\n".join(facts.customer_lines)

        if action.action == "confirm":
            return "تأكيد" if lang == "ar" else "Confirm when ready"

        if lang == "ar":
            return "كيف بقدر أساعدك في طلبك؟ 🍽️"
        return "How can I help with your order? 🍽️"
