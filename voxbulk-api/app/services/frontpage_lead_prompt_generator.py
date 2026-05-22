from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.models.knowledge_base_file import KnowledgeBaseFile
from app.services.agents.base import AgentMessage
from app.services.knowledge_base_service import build_kb_context_text
from app.constants.frontpage_consent import (
    INTAKE_CONVERSATION_PACE,
    PHONE_CONFIRM_ONCE_RULE,
    UK_CALLBACK_CONSENT_SHORT,
    VOICE_INTERRUPT_RULE,
    VOICE_NO_REPEAT_RULE,
)
from app.services.providers.openai_service import OpenAIProviderService

_META = """You are an expert prompt engineer for VOXBULK website lead-capture voice agents.

Write a BEHAVIOURAL system prompt for a live browser voice agent named Jode.

Output rules (critical):
- Return ONLY the system prompt plain text — no JSON, no markdown fences, no sample dialogue.
- NEVER write a call script, numbered lines to speak, or quoted example sentences the agent must recite.
- Use short sections and bullet rules (role, tone, flow, do-nots).
- British English. One or two short sentences per spoken turn.
- Jode qualifies leads on the website only. She schedules Adam (sales) to call back — no live transfer.
- Opening hello and recording notice are handled by Telnyx greeting — instruct Jode NOT to repeat them.
- Use only facts from the knowledge base for product claims — do not invent pricing."""

_INSTRUCTION = (
    "Write the behavioural system prompt for website Talk to us (Jode). Include these rules (paraphrase, do not quote as dialogue):\n"
    f"- {PHONE_CONFIRM_ONCE_RULE}\n"
    f"- {UK_CALLBACK_CONSENT_SHORT}\n"
    f"- {INTAKE_CONVERSATION_PACE}\n"
    f"- {VOICE_INTERRUPT_RULE}\n"
    f"- {VOICE_NO_REPEAT_RULE}\n"
    "Flow: greet by name → understand business and need → if they want sales/pricing, offer Adam callback + consent + time → "
    "confirm phone once at end if callback agreed. Use operator description and KB facts only."
)


def _extract_system_prompt(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Empty response from DeepSeek")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json|markdown|text)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()

    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                value = str(data.get("system_prompt") or "").strip()
                if value:
                    return value
        except json.JSONDecodeError:
            match = re.search(r'"system_prompt"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
            if match:
                try:
                    return json.loads(f'"{match.group(1)}"')
                except json.JSONDecodeError:
                    return match.group(1).replace("\\n", "\n").replace('\\"', '"').strip()

    return text


def _kb_section(files: list[KnowledgeBaseFile]) -> str:
    body = build_kb_context_text(files)
    if not body:
        return "No knowledge base files selected."
    return (
        "Knowledge base facts (for your reference when writing rules — do NOT paste verbatim dialogue from KB):\n\n"
        f"{body}"
    )


def generate_frontpage_lead_prompt(
    db: Session,
    *,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
) -> str:
    user = "\n\n".join(
        [
            f"Operator description:\n{description.strip()}",
            _kb_section(knowledge_files),
        ]
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_META,
        messages=[AgentMessage(role="user", content=f"{user}\n\n{_INSTRUCTION}")],
        max_tokens=1800,
        temperature=0.35,
        provider="deepseek",
    )
    value = _extract_system_prompt(result.assistant_text)
    if not value:
        raise ValueError("DeepSeek returned an empty system prompt")
    if _looks_like_dialogue_script(value):
        raise ValueError(
            "Generated prompt looks like a call script, not behavioural rules. "
            "Use the jode-system-prompt.md template from kb-upload-ready/lead/ instead."
        )
    return value


def _looks_like_dialogue_script(text: str) -> bool:
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    quoted = sum(1 for ln in lines if ln.startswith('"') or ln.startswith("'") or "?" in ln and len(ln) < 120)
    return quoted >= 3 and quoted / max(len(lines), 1) > 0.4
