"""LLM provider resolution and handler delegation for the dashboard assistant."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.assistant.orchestrator import _HANDLERS
from app.services.assistant.service_registry import INTENT_REGISTRY


def assistant_llm_provider(db: Session) -> str:
    settings = get_settings()
    selected = str(settings.assistant_llm_provider or "openai").strip().lower()
    if selected in {"openai", "deepseek", "deepinfra", "groq"}:
        return selected
    return "openai"


def assistant_llm_model(db: Session) -> str | None:
    settings = get_settings()
    explicit = str(settings.assistant_llm_model or "").strip()
    if explicit:
        return explicit
    provider = assistant_llm_provider(db)
    if provider == "deepinfra":
        return "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
    if provider == "deepseek":
        return "deepseek-chat"
    return None


def should_delegate_to_handler(intent: str) -> bool:
    if intent in {"create_ticket", "general_help"}:
        return True
    spec = INTENT_REGISTRY.get(intent)
    if spec is not None and spec.tool_name is None:
        return intent in _HANDLERS or intent == "general_help"
    if intent in _HANDLERS and spec is None:
        return True
    return False
