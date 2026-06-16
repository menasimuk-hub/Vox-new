"""Replay voice order pipeline stages 2-5 without writing orders."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import CustomerOrder
from app.abuu.services.abuu_voice_service import AbuuVoiceService, _dialect_prompt_for_language, _stt_language
from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.voice_order_debug_service import VoiceOrderDebugService
from app.abuu.waiter.smart_pipeline import ParsedAction, _parse_ai_response
from app.abuu.waiter.deepseek_client import WaiterDeepSeekClient
from app.core.config import get_settings
from app.services.providers.openai_service import OpenAIProviderService


class VoiceOrderReplayService:
    @staticmethod
    def replay(
        abuu_db: Session,
        main_db: Session,
        *,
        order_request_id: str | None = None,
        audio_path: str | None = None,
        phone: str | None = None,
        from_step: int = 2,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        if not dry_run:
            raise ValueError("replay only supports dry_run=True")

        bundle = None
        row_pipeline = "agent"
        lang = "ar"

        if order_request_id:
            bundle = VoiceOrderDebugService.get_bundle(abuu_db, order_request_id)
            if bundle is None:
                raise ValueError(f"order_request_id not found: {order_request_id}")
            row_pipeline = str(bundle.get("pipeline") or "agent")
            phone = phone or str(bundle.get("customer_phone") or "")
            stages = bundle.get("stages") or {}
            audio_path = audio_path or (stages.get("1_audio") or {}).get("storage_path")
        elif not audio_path or not phone:
            raise ValueError("Provide order_request_id or both --audio and --phone")

        if phone:
            customer = AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang=lang)
            lang = customer.preferred_language or lang

        live = bundle or {}
        live_stages = live.get("stages") or {}
        replay_stages: dict[str, Any] = {}

        if from_step <= 2:
            path = Path(str(audio_path or ""))
            if not path.is_file():
                replay_stages["2_stt_raw"] = {"error": f"audio file not found: {audio_path}"}
            else:
                raw = AbuuVoiceService._transcribe_file(
                    main_db,
                    path,
                    language=_stt_language(lang),
                    dialect_prompt=_dialect_prompt_for_language(lang),
                ).strip()
                replay_stages["2_stt_raw"] = {"transcript": raw}

        if from_step <= 3:
            saved_prompt = live_stages.get("3_llm_prompt") or {}
            if saved_prompt.get("system_prompt"):
                replay_stages["3_llm_prompt"] = saved_prompt
            else:
                replay_stages["3_llm_prompt"] = {
                    "error": "no saved prompt; send a live voice message with debug enabled first",
                }

        prompt_block = replay_stages.get("3_llm_prompt") or live_stages.get("3_llm_prompt") or {}
        system_prompt = str(prompt_block.get("system_prompt") or "")
        messages = prompt_block.get("messages") or []
        if isinstance(messages, str):
            try:
                messages = json.loads(messages)
            except json.JSONDecodeError:
                messages = []

        if from_step <= 4 and system_prompt:
            if row_pipeline == "smart":
                result = WaiterDeepSeekClient.complete(
                    main_db,
                    system_prompt=system_prompt,
                    user_content=".",
                    max_tokens=600,
                    temperature=0.2,
                )
                replay_stages["4_llm_raw"] = {
                    "response": result.text,
                    "fallback_used": result.fallback_used,
                    "error": result.error,
                }
            else:
                settings = get_settings()
                chat_messages = messages if isinstance(messages, list) else []
                if settings.abuu_agent_waiter_mode:
                    completion = OpenAIProviderService.complete_chat_raw(
                        main_db,
                        system_prompt=system_prompt,
                        messages=chat_messages,
                        tools=None,
                        model=settings.abuu_agent_model,
                        max_tokens=512,
                        provider="deepseek",
                    )
                    replay_stages["4_llm_raw"] = {
                        "response": completion.assistant_text or "",
                        "raw_assistant_message": completion.raw_assistant_message,
                    }
                else:
                    from app.abuu.agent.skills import enabled_openai_tools

                    openai_tools = enabled_openai_tools(abuu_db)
                    completion = OpenAIProviderService.complete_chat_raw(
                        main_db,
                        system_prompt=system_prompt,
                        messages=chat_messages,
                        tools=openai_tools or None,
                        model=settings.abuu_agent_model,
                        max_tokens=1024,
                        provider="deepseek",
                    )
                    replay_stages["4_llm_raw"] = {
                        "response": completion.assistant_text or "",
                        "raw_assistant_message": completion.raw_assistant_message,
                        "tool_calls": [
                            {"name": c.name, "arguments": c.arguments} for c in (completion.tool_calls or [])
                        ],
                    }

        if from_step <= 5:
            raw_block = replay_stages.get("4_llm_raw") or live_stages.get("4_llm_raw") or {}
            raw_text = raw_block.get("response") if isinstance(raw_block, dict) else raw_block
            if isinstance(raw_text, dict):
                raw_text = json.dumps(raw_text, ensure_ascii=False)
            if row_pipeline == "smart" and raw_text:
                parsed = _parse_ai_response(str(raw_text))
                replay_stages["5_parsed"] = {
                    "action": asdict(parsed),
                    "parse_status": "ok" if parsed.action != "none" or parsed.reply else "fallback",
                }
            elif raw_block.get("tool_calls"):
                replay_stages["5_parsed"] = {
                    "action": {"tool_calls": raw_block.get("tool_calls"), "pipeline": "agent"},
                    "parse_status": "ok",
                }
            elif raw_text:
                replay_stages["5_parsed"] = {
                    "action": {"reply": str(raw_text), "pipeline": "agent"},
                    "parse_status": "ok",
                }
            else:
                replay_stages["5_parsed"] = {"error": "no LLM response to parse"}

        orders_before = abuu_db.query(CustomerOrder).count() if hasattr(abuu_db, "query") else 0

        return {
            "order_request_id": order_request_id,
            "pipeline": row_pipeline,
            "dry_run": True,
            "from_step": from_step,
            "live": live_stages,
            "replay": replay_stages,
            "orders_unchanged": True,
            "orders_count_before": orders_before,
        }
