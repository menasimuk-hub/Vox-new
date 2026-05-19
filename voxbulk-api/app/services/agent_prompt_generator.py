from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.models.knowledge_base_file import KnowledgeBaseFile
from app.services.agents.base import AgentMessage
from app.services.knowledge_base_service import build_kb_context_text
from app.services.providers.openai_service import OpenAIProviderService

_WORKFLOW_META = """You are an expert voice-agent workflow designer for VOXBULK.
Return ONLY valid JSON with one string field:
- "call_workflow": numbered step-by-step call flow (greeting through close), when to ask questions, escalation, callback confirmation.

British English. Be specific and operational. No markdown fences."""

_PROMPT_META = """You are an expert prompt engineer for VOXBULK voice and chat agents.
Return ONLY valid JSON with one string field:
- "system_prompt": role, tone, constraints, knowledge usage, safety. Must align with the approved call workflow.

British English. Be specific and operational. No markdown fences."""

_BOTH_META = """You are an expert prompt engineer for VOXBULK voice and chat agents.
Return ONLY valid JSON with exactly two string fields:
- "system_prompt": role, tone, constraints, knowledge usage, safety
- "call_workflow": numbered call flow (greeting through close), when to ask questions, escalation

British English. Be specific and operational. No markdown fences."""


def _extract_json_object(raw: str) -> dict:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("DeepSeek response must be a JSON object")
    return data


def _parse_json_field(raw: str, field: str) -> str:
    data = _extract_json_object(raw)
    value = str(data.get(field) or "").strip()
    if not value:
        raise ValueError(f"Generated JSON must include non-empty {field}")
    return value


def _parse_both_fields(raw: str) -> dict[str, str]:
    data = _extract_json_object(raw)
    system_prompt = str(data.get("system_prompt") or "").strip()
    call_workflow = str(data.get("call_workflow") or "").strip()
    if not system_prompt or not call_workflow:
        raise ValueError("Generated JSON must include non-empty system_prompt and call_workflow")
    return {"system_prompt": system_prompt, "call_workflow": call_workflow}


def _kb_section(files: list[KnowledgeBaseFile]) -> str:
    body = build_kb_context_text(files)
    if not body:
        return "No knowledge base files selected."
    return (
        "Knowledge base file contents (authoritative — base workflow and prompt on these facts only; "
        "do not invent pricing or policy):\n\n"
        f"{body}"
    )


def _user_block(*, agent_name: str, description: str, knowledge_files: list[KnowledgeBaseFile], call_workflow: str | None = None) -> str:
    parts = [
        f"Agent name: {agent_name or 'Unnamed agent'}",
        f"Operator description (what this agent should do):\n{description}",
        _kb_section(knowledge_files),
    ]
    if call_workflow:
        parts.append(f"Approved call workflow (system prompt must follow this):\n{call_workflow}")
    return "\n\n".join(parts)


def _complete_json(db: Session, *, meta: str, user: str, instruction: str) -> str:
    result = OpenAIProviderService.complete(
        db,
        system_prompt=meta,
        messages=[AgentMessage(role="user", content=f"{user}\n\n{instruction}")],
        max_tokens=2500,
        temperature=0.4,
        provider="deepseek",
    )
    return result.assistant_text


def generate_call_workflow(
    db: Session,
    *,
    agent_name: str,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
) -> dict[str, str]:
    description = str(description or "").strip()
    if not description:
        raise ValueError("description is required to generate workflow")
    user = _user_block(agent_name=agent_name, description=description, knowledge_files=knowledge_files)
    raw = _complete_json(
        db,
        meta=_WORKFLOW_META,
        user=user,
        instruction="Produce call_workflow suitable for live phone or browser voice calls.",
    )
    try:
        workflow = _parse_json_field(raw, "call_workflow")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("DeepSeek returned invalid JSON for workflow generation") from exc
    return {"call_workflow": workflow}


def generate_system_prompt(
    db: Session,
    *,
    agent_name: str,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
    call_workflow: str,
) -> dict[str, str]:
    description = str(description or "").strip()
    workflow = str(call_workflow or "").strip()
    if not description:
        raise ValueError("description is required to generate prompt")
    if not workflow:
        raise ValueError("call_workflow is required before generating system prompt")
    user = _user_block(
        agent_name=agent_name,
        description=description,
        knowledge_files=knowledge_files,
        call_workflow=workflow,
    )
    raw = _complete_json(
        db,
        meta=_PROMPT_META,
        user=user,
        instruction="Produce system_prompt suitable for live phone or browser voice calls.",
    )
    try:
        prompt = _parse_json_field(raw, "system_prompt")
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("DeepSeek returned invalid JSON for prompt generation") from exc
    return {"system_prompt": prompt}


def generate_agent_prompts(
    db: Session,
    *,
    agent_name: str,
    description: str,
    knowledge_files: list[KnowledgeBaseFile],
) -> dict[str, str]:
    """Legacy: generate workflow and prompt together."""
    description = str(description or "").strip()
    if not description:
        raise ValueError("description is required to generate prompts")
    user = _user_block(agent_name=agent_name, description=description, knowledge_files=knowledge_files)
    raw = _complete_json(
        db,
        meta=_BOTH_META,
        user=user,
        instruction="Produce system_prompt and call_workflow suitable for live phone or browser voice calls.",
    )
    try:
        return _parse_both_fields(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("DeepSeek returned invalid JSON for prompt generation") from exc
