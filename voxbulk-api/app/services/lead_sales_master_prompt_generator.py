from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.knowledge_base_file import KnowledgeBaseFile
from app.services.agents.base import AgentMessage
from app.services.knowledge_base_service import build_kb_context_text
from app.constants.frontpage_consent import (
    SALES_RECORDING_NOTICE_SHORT,
    VOICE_INTERRUPT_RULE,
    VOICE_NO_REPEAT_RULE,
)
from app.services.providers.openai_service import OpenAIProviderService

_META = """You are an expert prompt engineer for VOXBULK outbound sales voice agents (Telnyx).

Write a BEHAVIOURAL master system prompt for Adam — outbound sales follow-up calls.

Output rules:
- Return ONLY plain text system prompt — no JSON, no fences, no sample dialogue or quoted lines to recite.
- Use bullet rules: role, tone, call flow, objection handling, do-nots.
- British English. Short turns. Adam is confident and consultative, not pushy.
- Jode handled website intake — Adam has context; do not re-ask what Jode already captured.
- Opening and recording are in Telnyx greeting — Adam must NOT repeat them.
- Pricing only from knowledge base — never invent numbers."""

_INSTRUCTION = (
    "Write Adam's master behavioural prompt using operator description and KB. Include (paraphrase, no dialogue script):\n"
    f"- {SALES_RECORDING_NOTICE_SHORT}\n"
    f"- {VOICE_INTERRUPT_RULE}\n"
    f"- {VOICE_NO_REPEAT_RULE}\n"
    "Flow: confirm time → reference Jode enquiry → diagnose need → present fit → trial close. "
    "Per-lead facts are appended separately before each call."
)


def _extract_prompt(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Empty response from DeepSeek")
    if text.startswith("```"):
        text = re.sub(r"^```(?:\w+)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    return text


def generate_lead_sales_master_prompt(
    db: Session,
    *,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
) -> str:
    kb_body = build_kb_context_text(knowledge_files)
    kb_section = (
        "Knowledge base facts (reference only — do NOT paste as spoken script):\n\n" + kb_body
        if kb_body
        else "No knowledge base files selected."
    )
    user = f"Operator description:\n{description.strip()}\n\n{kb_section}\n\n{_INSTRUCTION}"
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_META,
        messages=[AgentMessage(role="user", content=user)],
        max_tokens=1800,
        temperature=0.35,
        provider="deepseek",
    )
    return _extract_prompt(result.assistant_text)
