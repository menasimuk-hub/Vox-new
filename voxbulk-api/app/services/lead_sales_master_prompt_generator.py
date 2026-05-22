from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.knowledge_base_file import KnowledgeBaseFile
from app.services.agents.base import AgentMessage
from app.services.knowledge_base_service import build_kb_context_text
from app.constants.frontpage_consent import SALES_RECORDING_NOTICE_SHORT
from app.services.providers.openai_service import OpenAIProviderService

_META = """You are an expert prompt engineer for VOXBULK outbound sales voice agents (Telnyx).

Write the master system prompt for scheduled follow-up sales calls to website leads.

Output rules:
- Return ONLY the system prompt plain text (no JSON, no markdown fences).
- British English. Consultative, never deceptive.
- The agent must confirm the callback time, reference the website enquiry, handle objections, and secure a next step.
- Do not invent pricing or terms not in the knowledge base.
- If the knowledge base defines the outbound agent's name (e.g. Adam) and the intake agent (e.g. Jode), use those exact names only — never Sarah/Alex unless that is the name in the KB.
- Use only the sales-scoped knowledge base — Adam's library is separate from Jode's lead library."""

_INSTRUCTION = (
    "Write the master outbound sales agent system prompt using the operator description and knowledge base. "
    f"Include this rule verbatim: {SALES_RECORDING_NOTICE_SHORT} "
    "Keep turns short. This master prompt will be customised per lead before each call."
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
        "Knowledge base (authoritative — do not invent facts beyond these):\n\n" + kb_body
        if kb_body
        else "No knowledge base files selected."
    )
    user = f"Operator description:\n{description.strip()}\n\n{kb_section}\n\n{_INSTRUCTION}"
    result = OpenAIProviderService.complete(
        db,
        system_prompt=_META,
        messages=[AgentMessage(role="user", content=user)],
        max_tokens=2500,
        temperature=0.4,
        provider="deepseek",
    )
    return _extract_prompt(result.assistant_text)
