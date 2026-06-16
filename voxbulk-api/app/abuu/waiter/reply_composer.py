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
from app.core.config import get_settings

_REPLY_PROMPT = """You are a Palestinian/Jordanian Arabic dialect assistant for a food ordering service called Yallasay. Your only job is to make the message sound natural in Palestinian/Jordanian dialect.

STRICT RULES you must never break:
- Never change the format of the message
- Never change numbered lists to bullet points or vice versa
- Never add items that are not in the original message
- Never remove items that are in the original message
- Never change prices
- Never change the order of items listed
- Never add new questions that are not in the original message
- Never use Gulf Arabic words — only Palestinian/Jordanian dialect
- Keep emojis exactly as they are in the original
- If the original message is already good, return it unchanged
- Output only the final message, nothing else"""


def _format_conversation_history(session: AgentSession, *, user_text: str, max_messages: int = 5) -> str:
    ctx = session.context or {}
    stored = list(ctx.get("messages") or [])
    if not stored:
        return user_text
    tail = stored[-max_messages:]
    lines = ["Previous conversation:"]
    for entry in tail:
        role = str(entry.get("role") or "")
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        label = "Customer" if role == "customer" else "Agent"
        lines.append(f"{label}: {text}")
    lines.append(f"Current message: {user_text}")
    return "\n".join(lines)


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
            polish_enabled = get_settings().abuu_deepseek_polish_enabled
            if (
                polish_enabled
                and deepseek_ready
                and action.action not in {"cross_restaurant_blocked", "item_added", "addons_prompt"}
            ):
                history_block = _format_conversation_history(session, user_text=user_text)
                facts_block = json.dumps(
                    {
                        "intent": intent.name,
                        "facts_text": template,
                        "user_message": history_block,
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
