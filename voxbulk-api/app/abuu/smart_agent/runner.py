"""Smart Waiter Agent runtime — DeepSeek tool-calling loop."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.agent import _deepseek_platform_ready
from app.abuu.agent.prefetch import prefetch_offers, prefetch_restaurant_list
from app.abuu.agent.session import Session as AgentSession, load_session, save_session
from app.abuu.agent.session_reset import (
    clear_restaurant_binding,
    is_offer_query,
    is_session_reset_message,
)
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.smart_agent.prompt import build_smart_prompt
from app.abuu.smart_agent.tools import (
    execute_tool,
    hydrate_safety_into_session,
    openai_tools,
)
from app.core.config import get_settings
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)


def _truncate(messages: list[dict[str, Any]], max_messages: int) -> list[dict[str, Any]]:
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def _chat_messages_from_history(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role not in {"user", "assistant"}:
            continue
        if isinstance(content, list):
            text_parts = [
                str(block.get("text") or "")
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            content = "\n".join(p for p in text_parts if p).strip()
        out.append({"role": role, "content": str(content or "")})
    return out


def _format_user_turn(text: str, *, input_source: str, lang: str) -> str:
    cleaned = str(text or "").strip()
    if input_source != "voice":
        return cleaned
    if lang == "en":
        return f"[Voice transcript — interpret food order intent]: {cleaned}"
    return f"[رسالة صوتية — افهم نية الطلب]: {cleaned}"


class SmartWaiterAgent:
    """Tool-calling DeepSeek agent. Drop-in replacement for AbuuAgentLoop in opt-in pipeline."""

    @staticmethod
    def enabled_for_phone(phone: str) -> bool:
        settings = get_settings()
        if not settings.abuu_smart_agent_enabled:
            return False
        raw = (settings.abuu_smart_agent_allowlist or "").strip()
        if not raw:
            return True  # enabled with empty allowlist == all phones
        normalized = (phone or "").strip()
        if not normalized:
            return False
        allowed = {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}
        return normalized in allowed

    @staticmethod
    def run(
        abuu_db: Session,
        main_db: Session,
        *,
        phone: str,
        text: str,
        message_id: str | None = None,
        org_id: str | None = None,
        input_source: str = "text",
    ) -> dict[str, Any]:
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        session = load_session(abuu_db, phone)
        lang = session.language or customer.preferred_language or "ar"
        session.language = lang

        if is_session_reset_message(text) and not session.cart:
            clear_restaurant_binding(abuu_db, session)

        # Merge persisted + freshly-detected allergies/dietary into the session BEFORE the LLM sees the prompt.
        hydrate_safety_into_session(session, customer, text=text)

        user_turn = _format_user_turn(text, input_source=input_source, lang=lang)
        session.messages.append({"role": "user", "content": user_turn})

        if not _deepseek_platform_ready(main_db):
            logger.error("smart_agent_deepseek_not_configured phone=%s", phone)
            reply = (
                "خدمة الطلبات الذكية غير متاحة حالياً. حاول لاحقاً."
                if lang == "ar"
                else "Smart ordering is not available right now. Please try again later."
            )
            session.messages.append({"role": "assistant", "content": reply})
            save_session(abuu_db, session, message_id=message_id)
            return {"handled": True, "action": "smart_agent_error", "reply": reply}

        try:
            reply = SmartWaiterAgent._run_loop(
                abuu_db,
                main_db,
                session,
                customer=customer,
                user_text=text,
            )
        except Exception:
            logger.exception(
                "smart_agent_loop_failed phone=%s restaurant=%s",
                phone,
                session.restaurant_id,
            )
            reply = (
                "عذراً، حصل خطأ. حاول مرة ثانية أو اكتب طلبك."
                if lang == "ar"
                else "Sorry, something went wrong. Please try again or type your order."
            )

        session.messages.append({"role": "assistant", "content": reply})
        save_session(abuu_db, session, message_id=message_id)
        return {
            "handled": True,
            "action": "smart_agent_reply",
            "reply": reply,
            "step": session.stage,
            "restaurant_id": session.restaurant_id,
            "order_id": session.active_order_id,
        }

    # --------------------------------------------------------------- #
    # Tool-calling loop
    # --------------------------------------------------------------- #

    @staticmethod
    def _run_loop(
        abuu_db: Session,
        main_db: Session,
        session: AgentSession,
        *,
        customer: Any,
        user_text: str = "",
    ) -> str:
        settings = get_settings()

        # Pre-fetch restaurant list / offers so the model has facts without spending a tool call.
        if not session.restaurant_id and not session.context.get("prefetched_restaurant_list"):
            prefetch_restaurant_list(abuu_db, session, customer_id=customer.id)
        if is_offer_query(user_text):
            prefetch_offers(abuu_db, session, query=user_text)

        system_prompt = build_smart_prompt(abuu_db, session, customer=customer)
        history = _truncate(session.messages, settings.abuu_agent_max_history)
        chat_messages: list[dict[str, Any]] = _chat_messages_from_history(history)
        tools = openai_tools()
        lang = session.language or "ar"
        max_turns = max(1, int(settings.abuu_smart_agent_max_turns or 6))

        for _turn in range(max_turns):
            completion = OpenAIProviderService.complete_chat_raw(
                main_db,
                system_prompt=system_prompt,
                messages=chat_messages,
                tools=tools,
                model=settings.abuu_smart_agent_model,
                max_tokens=1024,
                temperature=float(settings.abuu_smart_agent_temperature or 0.3),
                provider="deepseek",
            )
            if completion.usage:
                logger.info("smart_agent_llm_usage usage=%s", completion.usage)

            if completion.tool_calls:
                assistant_msg = completion.raw_assistant_message or {
                    "role": "assistant",
                    "content": completion.assistant_text or None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in completion.tool_calls
                    ],
                }
                chat_messages.append(assistant_msg)
                for call in completion.tool_calls:
                    result = execute_tool(
                        abuu_db,
                        session,
                        customer=customer,
                        tool_name=call.name,
                        tool_input=call.arguments if isinstance(call.arguments, dict) else {},
                    )
                    chat_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result,
                        }
                    )
                continue

            if completion.assistant_text:
                return completion.assistant_text.strip()

            break

        if lang == "ar":
            return "كيف أقدر أساعدك في طلبك؟"
        return "How can I help with your order?"
