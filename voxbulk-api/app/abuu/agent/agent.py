"""DeepSeek Gaza Agent loop for Abuu WhatsApp ordering."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.agent.gaza_context import prefetch_gaza_agent_context
from app.abuu.agent.intent_gate import freeze_turn_restaurant_snapshot, phase1_enabled, try_deterministic_reply
from app.abuu.agent.prefetch import prefetch_offers, prefetch_restaurant_list
from app.abuu.agent.prompts import build_system_prompt
from app.abuu.agent.session import Session, load_session, save_session
from app.abuu.agent.session_reset import clear_restaurant_binding, hard_reset_session, is_offer_query, is_session_reset_message
from app.abuu.services.intent_service import is_abuu_start_message
from app.abuu.agent.skills import enabled_openai_tools, execute_tool
from app.abuu.agent.tool_guard import execute_tool_guarded, is_tool_error_result
from app.abuu import agent_trace
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.reply_service import unknown_message
from app.abuu.services.voice_order_debug_service import VoiceOrderDebugService, debug_enabled, get_debug_request_id
from app.core.config import get_settings
from app.abuu.models.entities import CustomerOrder
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


def _last_user_message(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content") or "")
    return ""


def _deepseek_platform_ready(main_db: Session) -> bool:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(main_db, provider="deepseek")
    return bool(enabled and cfg and str(cfg.get("api_key") or "").strip())


def _agent_session_snapshot(session: Session) -> dict[str, Any]:
    return {
        "restaurant_id": session.restaurant_id,
        "stage": session.stage,
        "cart": list(session.cart or []),
        "context": dict(session.context or {}),
        "active_order_id": session.active_order_id,
        "language": session.language,
    }


def _correlation_id(message_id: str | None) -> str:
    return str(message_id or get_debug_request_id() or uuid.uuid4())


def _record_agent_final_order(
    abuu_db: Session,
    session: Session,
    *,
    requested_restaurant_id: str | None = None,
) -> None:
    if not debug_enabled() or not session.active_order_id:
        return
    order = abuu_db.get(CustomerOrder, session.active_order_id)
    if order is None:
        return
    requested = requested_restaurant_id or session.context.get("phase1_requested_restaurant_id")
    if order.status in {"cancelled", "delivered"}:
        return
    if requested and str(order.restaurant_id or "") != str(requested):
        return
    if session.restaurant_id and str(order.restaurant_id or "") != str(session.restaurant_id):
        return
    VoiceOrderDebugService.record_final_order(
        abuu_db,
        order=order,
        requested_restaurant_id=requested,
    )


def _record_phase1_parsed(
    abuu_db: Session,
    *,
    session: Session,
    reply: str,
    input_source: str,
    branch: str,
    tool_calls: list[dict[str, Any]] | None = None,
    last_raw_response: str | dict[str, Any] = "",
) -> None:
    if not debug_enabled() or input_source != "voice":
        return
    VoiceOrderDebugService.record_llm_raw(abuu_db, raw_response=last_raw_response or reply)
    VoiceOrderDebugService.record_parsed(
        abuu_db,
        parsed={
            "pipeline": "agent",
            "branch": branch,
            "reply": reply,
            "tool_calls": tool_calls or [],
            "cart": list(session.cart or []),
            "stage": session.stage,
            "restaurant_id": session.restaurant_id,
        },
        parse_status="ok",
    )


def _format_user_turn(text: str, *, input_source: str, lang: str) -> str:
    """Format inbound text for agent chat history.

    Voice notes are transcribed server-side before this runs; pass the transcript
    as plain user text so the LLM treats it like a typed WhatsApp message.
    """
    del input_source, lang  # kept for call-site compatibility
    return str(text or "").strip()


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
        customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone)
        session = load_session(abuu_db, phone)
        user_turn = _format_user_turn(text, input_source=input_source, lang=session.language or "ar")

        if is_abuu_start_message(text):
            hard_reset_session(abuu_db, session)
        elif is_session_reset_message(text):
            clear_restaurant_binding(abuu_db, session, full_reset=True)

        session.messages.append({"role": "user", "content": user_turn})

        agent_trace.turn_start(
            phone=phone,
            msg_id=message_id,
            correlation_id=_correlation_id(message_id),
            input_source=input_source,
            text=agent_trace.clip(text),
            stage=session.stage,
            restaurant_id=session.restaurant_id or "",
            cart_items=len(session.cart or []),
            history_len=len(session.messages),
        )

        if not _deepseek_platform_ready(main_db):
            logger.error("abuu_agent_deepseek_not_configured phone=%s", phone)
            reply = unknown_message(session.language)
            session.messages.append({"role": "assistant", "content": reply})
            save_session(abuu_db, session, message_id=message_id)
            return {"handled": True, "action": "agent_error", "reply": reply}

        try:
            reply = AbuuAgentLoop._run_loop(
                abuu_db,
                main_db,
                session,
                customer=customer,
                user_text=text,
                phone=phone,
                message_id=message_id,
                input_source=input_source,
            )
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
        requested_restaurant_id = session.context.get("phase1_requested_restaurant_id") or session.restaurant_id
        _record_agent_final_order(abuu_db, session, requested_restaurant_id=requested_restaurant_id)
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
    def _run_loop(
        abuu_db: Session,
        main_db: Session,
        session: Session,
        *,
        customer: Any,
        user_text: str = "",
        phone: str = "",
        message_id: str | None = None,
        input_source: str = "text",
    ) -> str:
        settings = get_settings()
        correlation_id = _correlation_id(message_id)
        prefetch_gaza_agent_context(abuu_db, session, customer=customer)
        if not session.restaurant_id and not session.context.get("prefetched_restaurant_list"):
            prefetch_restaurant_list(abuu_db, session, customer_id=customer.id)
        if is_offer_query(user_text):
            prefetch_offers(abuu_db, session, query=user_text)

        if phase1_enabled():
            freeze_turn_restaurant_snapshot(abuu_db, session, customer_id=customer.id)
            deterministic = try_deterministic_reply(
                abuu_db,
                session,
                customer=customer,
                user_text=user_text,
            )
            if deterministic:
                reply, branch = deterministic
                if debug_enabled() and input_source == "voice":
                    VoiceOrderDebugService.record_llm_prompt(
                        abuu_db,
                        system_prompt="",
                        messages=[{"role": "user", "content": user_text}],
                        session_snapshot=_agent_session_snapshot(session),
                    )
                _record_phase1_parsed(
                    abuu_db,
                    session=session,
                    reply=reply,
                    input_source=input_source,
                    branch=branch,
                )
                agent_trace.llm_reply(
                    phone=phone,
                    msg_id=message_id,
                    correlation_id=correlation_id,
                    turn=0,
                    reply_preview=agent_trace.clip(reply),
                    action=branch,
                )
                agent_trace.turn_end(
                    phone=phone,
                    msg_id=message_id,
                    correlation_id=correlation_id,
                    restaurant_id=session.restaurant_id or "",
                )
                return reply

        agent_trace.prefetch(
            phone=phone,
            msg_id=message_id,
            offers=bool(session.context.get("prefetched_offers")),
            restaurants=bool(session.context.get("prefetched_restaurant_list")),
            menu=bool(session.context.get("prefetched_menu")),
        )

        system_prompt = build_system_prompt(abuu_db, session, customer=customer)
        history = _truncate_messages(session.messages, settings.abuu_agent_max_history)
        chat_messages: list[dict[str, Any]] = _chat_messages_from_history(history)

        if debug_enabled() and input_source == "voice":
            VoiceOrderDebugService.record_llm_prompt(
                abuu_db,
                system_prompt=system_prompt,
                messages=chat_messages,
                session_snapshot=_agent_session_snapshot(session),
            )

        if settings.abuu_agent_waiter_mode:
            agent_trace.llm_request(
                phone=phone,
                msg_id=message_id,
                turn=1,
                waiter_mode=True,
                tools=0,
                user_msg=agent_trace.clip(_last_user_message(chat_messages)),
            )
            reply = AbuuAgentLoop._waiter_completion(main_db, system_prompt, chat_messages, settings)
            if debug_enabled() and input_source == "voice":
                VoiceOrderDebugService.record_llm_raw(abuu_db, raw_response=reply)
                VoiceOrderDebugService.record_parsed(
                    abuu_db,
                    parsed={"pipeline": "agent", "waiter_mode": True, "reply": reply},
                    parse_status="ok",
                )
            agent_trace.llm_reply(
                phone=phone,
                msg_id=message_id,
                turn=1,
                reply_preview=agent_trace.clip(reply),
                action="agent_reply",
            )
            return reply

        openai_tools = enabled_openai_tools(abuu_db)
        max_turns = max(1, settings.abuu_agent_max_turns)
        phase1 = phase1_enabled()
        phase1_max_tool_rounds = 1 if phase1 else max_turns
        phase1_max_tool_executions = 2 if phase1 else max_turns * 4
        collected_tool_calls: list[dict[str, Any]] = []
        last_raw_response: str | dict[str, Any] = ""
        tool_rounds = 0
        tool_executions = 0
        tool_failures = 0
        for turn_idx in range(max_turns):
            turn_num = turn_idx + 1
            if phase1 and tool_rounds >= phase1_max_tool_rounds and tool_failures > 0:
                break
            agent_trace.llm_request(
                phone=phone,
                msg_id=message_id,
                correlation_id=correlation_id,
                turn=turn_num,
                waiter_mode=False,
                tools=len(openai_tools or []),
                user_msg=agent_trace.clip(_last_user_message(chat_messages)),
            )
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

            if debug_enabled() and input_source == "voice":
                last_raw_response = completion.raw_assistant_message or completion.assistant_text or ""

            if completion.tool_calls:
                if phase1:
                    tool_rounds += 1
                    if tool_rounds > phase1_max_tool_rounds:
                        break
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
                    if phase1 and tool_executions >= phase1_max_tool_executions:
                        break
                    tool_input = call.arguments if isinstance(call.arguments, dict) else {}
                    collected_tool_calls.append(
                        {"name": call.name, "arguments": tool_input, "turn": turn_num}
                    )
                    if phase1:
                        result = execute_tool_guarded(
                            abuu_db,
                            session,
                            customer=customer,
                            tool_name=call.name,
                            tool_input=tool_input,
                            user_text=user_text,
                            correlation_id=correlation_id,
                        )
                    else:
                        result = execute_tool(
                            abuu_db,
                            session,
                            customer=customer,
                            tool_name=call.name,
                            tool_input=tool_input,
                        )
                    tool_executions += 1
                    if phase1 and is_tool_error_result(result):
                        tool_failures += 1
                    agent_trace.llm_tool(
                        phone=phone,
                        msg_id=message_id,
                        correlation_id=correlation_id,
                        turn=turn_num,
                        tool=call.name,
                        args=tool_input,
                        result_preview=agent_trace.clip(result),
                    )
                    chat_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": result,
                        }
                    )
                if phase1 and tool_failures > 0:
                    break
                continue

            if completion.assistant_text:
                if debug_enabled() and input_source == "voice":
                    VoiceOrderDebugService.record_llm_raw(abuu_db, raw_response=last_raw_response or completion.assistant_text)
                    VoiceOrderDebugService.record_parsed(
                        abuu_db,
                        parsed={
                            "pipeline": "agent",
                            "reply": completion.assistant_text,
                            "tool_calls": collected_tool_calls,
                            "cart": list(session.cart or []),
                            "stage": session.stage,
                        },
                        parse_status="ok",
                    )
                agent_trace.llm_reply(
                    phone=phone,
                    msg_id=message_id,
                    turn=turn_num,
                    reply_preview=agent_trace.clip(completion.assistant_text),
                    action="agent_reply",
                )
                return completion.assistant_text

        if phase1 and tool_failures > 0:
            fallback = (
                "ما قدرت أغيّر المطعم. قول اسم المطعم أو اعرض المطاعم."
                if session.language == "ar"
                else "I couldn't switch restaurants. Say a restaurant name or ask for the list."
            )
            parse_error = "phase1_tool_blocked"
        else:
            fallback = "كيف أقدر أساعدك في طلبك؟" if session.language == "ar" else "How can I help with your order?"
            parse_error = "max_turns_exceeded"
        if debug_enabled() and input_source == "voice":
            VoiceOrderDebugService.record_llm_raw(abuu_db, raw_response=last_raw_response or fallback)
            VoiceOrderDebugService.record_parsed(
                abuu_db,
                parsed={
                    "pipeline": "agent",
                    "reply": fallback,
                    "tool_calls": collected_tool_calls,
                    "cart": list(session.cart or []),
                    "stage": session.stage,
                    "restaurant_id": session.restaurant_id,
                },
                parse_status="fallback" if parse_error == "max_turns_exceeded" else "ok",
                parse_error=parse_error if parse_error == "max_turns_exceeded" else None,
            )
        agent_trace.llm_reply(
            phone=phone,
            msg_id=message_id,
            correlation_id=correlation_id,
            turn=max_turns,
            reply_preview=agent_trace.clip(fallback),
            action="agent_fallback" if parse_error == "max_turns_exceeded" else "phase1_tool_blocked",
        )
        agent_trace.turn_end(
            phone=phone,
            msg_id=message_id,
            correlation_id=correlation_id,
            restaurant_id=session.restaurant_id or "",
        )
        return fallback

    @staticmethod
    def _waiter_completion(
        main_db: Session,
        system_prompt: str,
        chat_messages: list[dict[str, Any]],
        settings: Any,
    ) -> str:
        completion = OpenAIProviderService.complete_chat_raw(
            main_db,
            system_prompt=system_prompt,
            messages=chat_messages,
            tools=None,
            model=settings.abuu_agent_model,
            max_tokens=512,
            provider="deepseek",
        )
        if completion.usage:
            logger.info("gaza_agent_llm_usage usage=%s", completion.usage)
        if completion.assistant_text:
            return completion.assistant_text.strip()
        return "كيف أقدر أساعدك في طلبك؟"
