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
    RECORDING_NOTICE_SHORT,
    UK_CALLBACK_CONSENT_SHORT,
)
from app.services.providers.openai_service import OpenAIProviderService

_META = """You are an expert prompt engineer for VOXBULK website lead-capture voice agents.

Write the complete system prompt for a live browser voice sales agent.

Output rules (critical):
- Return ONLY the system prompt plain text.
- Do NOT wrap in JSON, markdown code fences, or quotes.
- British English, warm and professional, one or two short sentences per turn.
- Use the visitor's first name naturally once you know it.
- Confirm their company and what they need help with.
- Do not invent pricing or features not supported by the knowledge base.
- Keep every turn short (one or two sentences). Do not repeat the same question.
- If the knowledge base defines the agent's name (e.g. "Your name is Jode"), use ONLY that name. Never substitute Sarah, Alex, or other names from other documents."""

_INSTRUCTION = (
    "Write the system prompt for a website Talk to us voice agent that qualifies inbound leads "
    "for sales follow-up. Include these rules verbatim in the prompt:\n"
    f"- {RECORDING_NOTICE_SHORT}\n"
    f"- {PHONE_CONFIRM_ONCE_RULE}\n"
    f"- {UK_CALLBACK_CONSENT_SHORT}\n"
    f"- {INTAKE_CONVERSATION_PACE}\n"
    "Use the operator description and knowledge base below."
)


def _extract_system_prompt(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("Empty response from DeepSeek")

    if text.startswith("```"):
        text = re.sub(r"^```(?:json|markdown|text)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text).strip()

    # Legacy JSON responses
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
        "Knowledge base file contents (authoritative — do not invent facts beyond these):\n\n"
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
        max_tokens=2500,
        temperature=0.4,
        provider="deepseek",
    )
    value = _extract_system_prompt(result.assistant_text)
    if not value:
        raise ValueError("DeepSeek returned an empty system prompt")
    return value
