"""LLM classify + synthesize orchestrator for the dashboard assistant."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import CurrentPrincipal
from app.schemas.assistant import (
    AssistantChatIn,
    AssistantChatOut,
    AssistantNextAction,
    AssistantUiCommand,
)
from app.services.agents.base import AgentMessage
from app.services.assistant.assistant_llm import assistant_llm_model, assistant_llm_provider, should_delegate_to_handler
from app.services.assistant.error_monitor import record_assistant_failure
from app.services.assistant.highlights import build_out, nav_action
from app.services.assistant.intent import IntentMatch, classify_intent
from app.services.assistant.orchestrator import AssistantOrchestrator, _HANDLERS, _handle_general, _context_with_history
from app.services.assistant.policy_coach import build_policy_refusal_response
from app.services.assistant.policy_gate import check_policy
from app.services.assistant.prompt_builder import (
    build_classify_system_prompt,
    build_synthesize_system_prompt,
    build_general_help_system_prompt,
)
from app.services.assistant.support_report import issue_support_report_token
from app.services.assistant.safe_tools import user_display_name
from app.services.assistant.service_registry import (
    INTENT_REGISTRY,
    ToolResult,
    default_ui_commands_for_intent,
    execute_intent,
    registry_intent_names,
    tool_data_for_prompt,
)
from app.services.assistant.service_gate import check_intent_service_gate
from app.services.assistant.rate_limit import check_assistant_rate_limit
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)

_MAX_HISTORY_TURNS = 16


def _parse_json(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    return list(history or [])[-_MAX_HISTORY_TURNS:]


def _history_block(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for item in _trim_history(history):
        role = str(item.get("role") or "user")
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _llm_complete(db: Session, *, system_prompt: str, user_content: str, max_tokens: int, temperature: float) -> str:
    provider = assistant_llm_provider(db)
    model = assistant_llm_model(db)
    resp = OpenAIProviderService.complete(
        db,
        system_prompt=system_prompt,
        messages=[AgentMessage(role="user", content=user_content)],
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        provider=provider,
    )
    return str(resp.assistant_text or "")


class LlmAssistantOrchestrator:
    @staticmethod
    def handle_chat(
        db: Session,
        *,
        principal: CurrentPrincipal,
        payload: AssistantChatIn,
        is_admin: bool = False,
    ) -> AssistantChatOut:
        from app.services.assistant import conversation_service, help_retrieval_service
        
        rate = check_assistant_rate_limit(org_id=principal.org_id, user_id=principal.user_id, endpoint="chat")
        if not rate.allowed:
            return build_out(
                primary_message="Please wait a moment before sending another message.",
                confidence=0.99,
                intent="rate_limited",
            )

        policy = check_policy(payload.message)
        if not policy.allowed:
            return build_policy_refusal_response(
                reason=policy.reason or "That request is not permitted.",
                suggested_prompts=list(policy.suggested_prompts),
                nav_route=policy.nav_route,
            )

        from app.services.assistant.tools import AssistantTools

        org = AssistantTools.get_org(db, principal.org_id)
        if org is None:
            return build_out(primary_message="Organisation not found.", confidence=1.0, blocking_reason="org_not_found")

        enabled = payload.context.enabled_services or []
        history_payload = [{"role": h.role, "text": h.text} for h in payload.history]
        chat_context = _context_with_history(payload)
        intent_match = LlmAssistantOrchestrator._classify(
            db,
            message=payload.message,
            history=history_payload,
            is_admin=is_admin,
            enabled_services=enabled,
        )

        if not is_admin:
            gated = check_intent_service_gate(
                intent_match.intent,
                enabled_services=enabled,
                service_code=intent_match.service_code or payload.context.service_code,
            )
            if gated is not None:
                return gated

        # Get or create conversation
        conversation_id = payload.conversation_id
        conversation = None
        if conversation_id:
            conversation = conversation_service.get_conversation(db, conversation_id, principal.user_id)
        if not conversation and not is_admin:
            conversation = conversation_service.create_conversation(
                db, principal.org_id, principal.user_id, title=payload.message[:100]
            )
            conversation_id = conversation.id
        
        # Try RAG retrieval for general/help-like intents
        help_chunks = []
        source_type = None
        help_intents = {"general_help", "unknown", "open_faq"}
        if intent_match.intent in help_intents:
            help_chunks = help_retrieval_service.retrieve(
                db,
                question=payload.message,
                enabled_services=enabled,
                limit=5,
            )
            if help_chunks:
                source_type = "knowledge_base"
                for chunk in help_chunks:
                    help_retrieval_service._increment_usage_count(db, chunk["kind"], chunk["source_id"])

        # How-to / FAQ: synthesize with LLM + RAG (never dump raw snippets when LLM is on)
        if intent_match.intent in help_intents:
            result = LlmAssistantOrchestrator._answer_help(
                db,
                principal=principal,
                message=payload.message,
                intent=intent_match.intent,
                confidence=intent_match.confidence,
                history=history_payload,
                enabled_services=enabled,
                help_chunks=help_chunks,
                context=chat_context,
                org=org,
                is_admin=is_admin,
            )
            if conversation and not is_admin:
                conversation_service.append_message(db, conversation_id, "user", payload.message)
                msg = conversation_service.append_message(
                    db,
                    conversation_id,
                    "assistant",
                    result.primary_message,
                    source_type=result.source_type or source_type,
                    sources=result.sources or (help_chunks if help_chunks else None),
                )
                result.conversation_id = conversation_id
                result.message_id = msg.id
            return result

        if should_delegate_to_handler(intent_match.intent):
            handler = _HANDLERS.get(intent_match.intent) or _handle_general
            result = handler(
                db,
                principal=principal,
                org=org,
                message=payload.message,
                intent=intent_match,
                context=chat_context,
                is_admin=is_admin,
            )
            # Persist message if conversation exists
            if conversation and not is_admin:
                conversation_service.append_message(
                    db, conversation_id, "user", payload.message
                )
                msg = conversation_service.append_message(
                    db,
                    conversation_id,
                    "assistant",
                    result.primary_message,
                    source_type=source_type or result.source_type,
                    sources=help_chunks if help_chunks else None,
                )
                result.conversation_id = conversation_id
                result.message_id = msg.id
            return result

        if intent_match.intent.startswith("admin_"):
            return AssistantOrchestrator.handle_chat(db, principal=principal, payload=payload, is_admin=is_admin)

        if intent_match.intent not in INTENT_REGISTRY:
            handler = _HANDLERS.get(intent_match.intent) or _handle_general
            result = handler(
                db,
                principal=principal,
                org=org,
                message=payload.message,
                intent=intent_match,
                context=chat_context,
                is_admin=is_admin,
            )
            # Persist message if conversation exists
            if conversation and not is_admin:
                conversation_service.append_message(
                    db, conversation_id, "user", payload.message
                )
                msg = conversation_service.append_message(
                    db,
                    conversation_id,
                    "assistant",
                    result.primary_message,
                    source_type=source_type or result.source_type,
                    sources=help_chunks if help_chunks else None,
                )
                result.conversation_id = conversation_id
                result.message_id = msg.id
            return result

        tool_result = execute_intent(
            db,
            intent=intent_match.intent,
            params=intent_match.params,
            principal=principal,
            org=org,
            context=payload.context,
            message=payload.message,
        )

        if not tool_result.ok:
            return LlmAssistantOrchestrator._error_response(
                db,
                principal=principal,
                message=payload.message,
                intent=intent_match.intent,
                tool_result=tool_result,
                history=history_payload,
            )

        primary, ui_commands, highlight = LlmAssistantOrchestrator._synthesize(
            db,
            message=payload.message,
            intent=intent_match.intent,
            tool_result=tool_result,
            history=history_payload,
            enabled_services=enabled,
            help_context=help_chunks,
        )

        next_actions = _ui_commands_to_next_actions(ui_commands)
        
        # Determine final source_type
        final_source_type = source_type
        if not final_source_type:
            if help_chunks:
                final_source_type = "knowledge_base"
            elif tool_result.data:
                final_source_type = "account_data"
            else:
                final_source_type = "general_ai"
        
        # Persist message if conversation exists
        message_id = None
        if conversation and not is_admin:
            conversation_service.append_message(
                db, conversation_id, "user", payload.message
            )
            msg = conversation_service.append_message(
                db,
                conversation_id,
                "assistant",
                primary,
                source_type=final_source_type,
                sources=help_chunks if help_chunks else None,
            )
            message_id = msg.id
            if final_source_type == "general_ai" and float(intent_match.confidence or 0) < 0.65:
                conversation_service.enqueue_faq_suggestion(
                    db,
                    question=payload.message,
                    sample_answer=primary,
                    org_id=principal.org_id,
                    user_id=principal.user_id,
                )

        return build_out(
            primary_message=primary,
            confidence=intent_match.confidence,
            intent=intent_match.intent,
            highlight_type=str(highlight.get("highlight_type") or ""),
            highlight_id=highlight.get("highlight_id"),
            highlight_label=highlight.get("highlight_label"),
            next_actions=next_actions,
            ui_commands=ui_commands,
            source_type=final_source_type,
            sources=help_chunks if help_chunks else [],
            conversation_id=conversation_id,
            message_id=message_id,
        )

    @staticmethod
    def _answer_help(
        db: Session,
        *,
        principal: CurrentPrincipal,
        message: str,
        intent: str,
        confidence: float,
        history: list[dict[str, str]],
        enabled_services: list[str],
        help_chunks: list[dict[str, Any]],
        context: Any,
        org: Any,
        is_admin: bool,
    ) -> AssistantChatOut:
        """Answer how-to/FAQ with LLM grounded in RAG chunks (fallback to handler if LLM off)."""
        settings = get_settings()
        defaults = default_ui_commands_for_intent(intent, data={}, params={})
        for idx, chunk in enumerate(help_chunks[:3]):
            url = str(chunk.get("url") or "/account/support/faq")
            title = str(chunk.get("title") or "Help article")[:40]
            defaults.append(
                AssistantUiCommand(
                    id=f"help_src_{idx}",
                    kind="navigate",
                    route=url,
                    label=title,
                )
            )

        if not settings.assistant_llm_enabled:
            return _handle_general(
                db,
                principal=principal,
                org=org,
                message=message,
                intent=IntentMatch(intent=intent, confidence=confidence),
                context=context,
                is_admin=is_admin,
            )

        kb_items = []
        for chunk in help_chunks:
            kb_items.append(
                f"- title: {chunk.get('title')}\n  snippet: {chunk.get('snippet')}\n  url: {chunk.get('url')}"
            )
        kb_block = "\n".join(kb_items) if kb_items else "(no Help Centre hits)"
        user_prompt = json.dumps(
            {
                "user_message": message,
                "intent": intent,
                "history": _history_block(history),
                "has_help_hits": bool(help_chunks),
            },
            ensure_ascii=False,
        ) + f"\n\nHelp Centre excerpts:\n{kb_block}"

        try:
            text = _llm_complete(
                db,
                system_prompt=build_general_help_system_prompt(enabled_services=enabled_services or None),
                user_content=user_prompt,
                max_tokens=800,
                temperature=0.3,
            )
            parsed = _parse_json(text)
            primary = str(parsed.get("primary_message") or "").strip()
            if not primary:
                raise ValueError("empty primary_message")
            ui_commands = _parse_ui_commands(parsed.get("ui_commands"), defaults)
            next_actions = _ui_commands_to_next_actions(ui_commands)
            source_type = "knowledge_base" if help_chunks else "general_ai"
            return build_out(
                primary_message=primary,
                confidence=max(0.55, float(confidence or 0.7)),
                intent=intent,
                next_actions=next_actions,
                ui_commands=ui_commands,
                source_type=source_type,
                sources=help_chunks,
            )
        except Exception:
            logger.warning("assistant_help_synthesize_fallback", exc_info=True)
            record_assistant_failure(endpoint_label="llm_provider")
            return _handle_general(
                db,
                principal=principal,
                org=org,
                message=message,
                intent=IntentMatch(intent=intent, confidence=confidence),
                context=context,
                is_admin=is_admin,
            )

    @staticmethod
    def _classify(
        db: Session,
        *,
        message: str,
        history: list[dict[str, str]],
        is_admin: bool,
        enabled_services: list[str],
    ) -> IntentMatch:
        regex_match = classify_intent(message, is_admin=is_admin)
        settings = get_settings()
        if not settings.assistant_llm_enabled:
            return regex_match

        allowed = list(registry_intent_names())
        if "create_ticket" not in allowed:
            allowed.append("create_ticket")

        user_prompt = json.dumps(
            {
                "message": message,
                "history": _trim_history(history),
                "allowed_intents": allowed,
            },
            ensure_ascii=False,
        )
        try:
            text = _llm_complete(
                db,
                system_prompt=build_classify_system_prompt(enabled_services=enabled_services or None),
                user_content=user_prompt,
                max_tokens=400,
                temperature=0.1,
            )
            parsed = _parse_json(text)
            intent = str(parsed.get("intent") or regex_match.intent)
            if intent not in INTENT_REGISTRY and intent != "create_ticket":
                intent = regex_match.intent
            confidence = float(parsed.get("confidence") or regex_match.confidence)
            params = parsed.get("params") if isinstance(parsed.get("params"), dict) else {}
            return IntentMatch(intent=intent, confidence=confidence, service_code=regex_match.service_code, params=params)
        except Exception:
            logger.warning("assistant_llm_classify_fallback", exc_info=True)
            record_assistant_failure(endpoint_label="llm_provider")
            return regex_match

    @staticmethod
    def _synthesize(
        db: Session,
        *,
        message: str,
        intent: str,
        tool_result: ToolResult,
        history: list[dict[str, str]],
        enabled_services: list[str],
        help_context: list[dict[str, Any]] | None = None,
    ) -> tuple[str, list[AssistantUiCommand], dict[str, str | None]]:
        defaults = default_ui_commands_for_intent(intent, data=tool_result.data, params=tool_result.params_sent)
        fallback_msg = _default_message(intent, tool_result)

        settings = get_settings()
        # navigation_only skips LLM unless we have Help Centre context to ground the answer
        if not settings.assistant_llm_enabled or (tool_result.navigation_only and not help_context):
            highlight = _highlight_from_commands(defaults)
            return fallback_msg, defaults, highlight
        
        has_kb = bool(help_context)
        kb_block = ""
        if help_context:
            kb_items = [f"- {chunk['title']}: {chunk['snippet']}" for chunk in help_context]
            kb_block = "\n\nHelp Centre context:\n" + "\n".join(kb_items)

        user_prompt = json.dumps(
            {
                "user_message": message,
                "intent": intent,
                "tool_data": tool_data_for_prompt(tool_result),
                "history": _history_block(history),
            },
            ensure_ascii=False,
        ) + kb_block
        try:
            text = _llm_complete(
                db,
                system_prompt=build_synthesize_system_prompt(enabled_services=enabled_services or None, has_kb_context=has_kb),
                user_content=user_prompt,
                max_tokens=700,
                temperature=0.35,
            )
            parsed = _parse_json(text)
            primary = str(parsed.get("primary_message") or fallback_msg).strip() or fallback_msg
            ui_commands = _parse_ui_commands(parsed.get("ui_commands"), defaults)
            highlight = _highlight_from_commands(ui_commands)
            return primary, ui_commands, highlight
        except Exception:
            logger.warning("assistant_llm_synthesize_fallback intent=%s", intent, exc_info=True)
            record_assistant_failure(endpoint_label="llm_provider")
            highlight = _highlight_from_commands(defaults)
            return fallback_msg, defaults, highlight

    @staticmethod
    def _error_response(
        db: Session,
        *,
        principal: CurrentPrincipal,
        message: str,
        intent: str,
        tool_result: ToolResult,
        history: list[dict[str, str]],
    ) -> AssistantChatOut:
        record_assistant_failure(endpoint_label=tool_result.endpoint_label or intent)
        name = user_display_name(db, principal)
        token = issue_support_report_token(
            org_id=principal.org_id,
            user_id=principal.user_id,
            payload={
                "user_message": message,
                "intent": intent,
                "endpoint_label": tool_result.endpoint_label,
                "params": tool_result.params_sent,
                "error_code": tool_result.error_code,
                "error_detail": tool_result.error_detail,
                "history": _trim_history(history),
            },
        )
        return build_out(
            primary_message=(
                f"Sorry {name}, I couldn't load that just now. "
                "You can open Billing or Usage for the latest figures, or send this to our support team."
            ),
            confidence=0.4,
            intent=intent,
            blocking_reason="temporary_data_error",
            next_actions=[
                nav_action("billing", "Open billing", "/account/billing"),
                nav_action("usage", "View usage", "/account/usage"),
            ],
            error_occurred=True,
            support_report_token=token,
        )


def _parse_ui_commands(raw: Any, defaults: list[AssistantUiCommand]) -> list[AssistantUiCommand]:
    if not isinstance(raw, list) or not raw:
        return defaults
    out: list[AssistantUiCommand] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        cmd_id = str(item.get("id") or f"cmd_{idx}")
        kind = str(item.get("kind") or "navigate")
        if kind not in {"navigate", "highlight", "scroll_to", "open_panel"}:
            kind = "navigate"
        out.append(
            AssistantUiCommand(
                id=cmd_id,
                kind=kind,  # type: ignore[arg-type]
                route=item.get("route"),
                label=str(item.get("label") or "Open"),
                highlight_type=str(item.get("highlight_type") or ""),
                highlight_id=item.get("highlight_id"),
                highlight_label=item.get("highlight_label"),
            )
        )
    return out or defaults


def _highlight_from_commands(commands: list[AssistantUiCommand]) -> dict[str, str | None]:
    for cmd in commands:
        if cmd.highlight_id and cmd.highlight_type:
            return {
                "highlight_type": cmd.highlight_type,
                "highlight_id": cmd.highlight_id,
                "highlight_label": cmd.highlight_label,
            }
    return {"highlight_type": "", "highlight_id": None, "highlight_label": None}


def _ui_commands_to_next_actions(commands: list[AssistantUiCommand]) -> list[AssistantNextAction]:
    actions: list[AssistantNextAction] = []
    for cmd in commands:
        if cmd.kind in {"navigate", "open_panel"} and cmd.route:
            actions.append(
                AssistantNextAction(
                    id=cmd.id,
                    label=cmd.label,
                    kind="open_panel" if cmd.kind == "open_panel" else "navigate",
                    route=cmd.route,
                )
            )
        elif cmd.kind in {"highlight", "scroll_to"} and cmd.route:
            actions.append(AssistantNextAction(id=cmd.id, label=cmd.label, kind="navigate", route=cmd.route))
    return actions


def _default_message(intent: str, tool_result: ToolResult) -> str:
    spec = INTENT_REGISTRY.get(intent)
    label = spec.dashboard_section if spec else "your account"
    if tool_result.navigation_only:
        return f"I can help you with {label}. Use the shortcuts below to continue."
    data = tool_result.data
    if isinstance(data, dict):
        if intent == "wallet_low":
            wallet = data.get("wallet") or {}
            balance = wallet.get("wallet_balance_display") or wallet.get("wallet_balance_gbp") or "£0.00"
            return f"Your wallet balance is {balance}."
        if intent == "usage_summary":
            usage = data.get("usage") or {}
            calls = usage.get("calls") or {}
            if calls:
                return f"AI calls: {calls.get('used', 0)}/{calls.get('included', 0)} minutes used this period."
    return f"Here is the latest information for {label}."
