"""DeepSeek tool-use agent loop for Abuu WhatsApp ordering."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.prompts import build_system_prompt
from app.abuu.agent.session import Session, load_session, save_session
from app.abuu.agent.skills import enabled_openai_tools, execute_tool
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import unknown_message
from app.core.config import get_settings
from app.services.provider_settings import ProviderSettingsService
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)


def _truncate_messages(messages: list[dict[str, Any]], max_messages: int) -> list[dict[str, Any]]:
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]


def _chat_messages_from_history(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    converted: list[dict[str, str]] = []
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
        converted.append({"role": role, "content": str(content or "")})
    return converted


def _deepseek_platform_ready(main_db: Session) -> bool:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(main_db, provider="deepseek")
    return bool(enabled and cfg and str(cfg.get("api_key") or "").strip())


def _format_user_turn(text: str, *, input_source: str, lang: str) -> str:
    cleaned = str(text or "").strip()
    if input_source != "voice":
        return cleaned
    if lang == "en":
        return f"[Voice note transcript — interpret food order intent]: {cleaned}"
    return f"[رسالة صوتية — فهم نية الطلب]: {cleaned}"


class AbuuAgentLoop:
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
        settings = get_settings()
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        session = load_session(abuu_db, phone)
        user_turn = _format_user_turn(text, input_source=input_source, lang=session.language or "ar")
        session.messages.append({"role": "user", "content": user_turn})

        if not _deepseek_platform_ready(main_db):
            logger.error("abuu_agent_deepseek_not_configured phone=%s", phone)
            reply = unknown_message(session.language)
            session.messages.append({"role": "assistant", "content": reply})
            save_session(abuu_db, session, message_id=message_id)
            return {"handled": True, "action": "agent_error", "reply": reply}

        try:
            reply = AbuuAgentLoop._run_loop(abuu_db, main_db, session, customer=customer)
        except Exception:
            logger.exception(
                "abuu_agent_loop_failed phone=%s restaurant=%s",
                phone,
                session.restaurant_id,
            )
            if session.language == "ar":
                reply = "عذراً، حصل خطأ. حاول مرة أخرى أو اكتب طلبك."
            else:
                reply = "Sorry, something went wrong. Please try again or type your order."

        session.messages.append({"role": "assistant", "content": reply})
        save_session(abuu_db, session, message_id=message_id)
        return {
            "handled": True,
            "action": "agent_reply",
            "reply": reply,
            "step": session.stage,
            "restaurant_id": session.restaurant_id,
            "order_id": session.active_order_id,
        }

    @staticmethod
    def _run_loop(abuu_db: Session, main_db: Session, session: Session, *, customer: Any) -> str:
        settings = get_settings()
        system_prompt = build_system_prompt(abuu_db, session, customer=customer)
        openai_tools = enabled_openai_tools(abuu_db)
        history = _truncate_messages(session.messages, settings.abuu_agent_max_history)
        chat_messages: list[dict[str, Any]] = _chat_messages_from_history(history)

        for _turn in range(max(1, settings.abuu_agent_max_turns)):
            completion = OpenAIProviderService.complete_chat_raw(
                main_db,
                system_prompt=system_prompt,
                messages=chat_messages,
                tools=openai_tools or None,
                model=settings.abuu_agent_model,
                max_tokens=1024,
                provider="deepseek",
            )
            if completion.usage:
                logger.info("abuu_agent_llm_usage usage=%s", completion.usage)

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
                return completion.assistant_text

        if session.language == "ar":
            return "كيف أقدر أساعدك في طلبك؟"
        return "How can I help with your order?"
