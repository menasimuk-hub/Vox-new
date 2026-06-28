"""EU script content moderation via DeepInfra (Mistral) OpenAI-compatible chat API."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.provider_settings import ProviderSettingsService
from app.services.providers.openai_service import OpenAIProviderService

logger = logging.getLogger(__name__)

DEFAULT_MODERATION_BASE_URL = "https://api.deepinfra.com/v1/openai"
DEFAULT_MODERATION_MODEL = "mistralai/Mistral-Small-3.2-24B-Instruct-2506"

MODERATION_CATEGORIES = ("safe", "racism", "offensive", "sexual", "political")

DEEPINFRA_MODERATION_MODELS: list[dict[str, str]] = [
    {
        "id": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        "label": "Mistral Small 3.2 24B (recommended)",
    },
    {
        "id": "mistralai/Mistral-Small-24B-Instruct-2501",
        "label": "Mistral Small 24B 2501 (faster)",
    },
    {
        "id": "mistralai/Mistral-Nemo-Instruct-2407",
        "label": "Mistral Nemo 2407 (budget, multilingual)",
    },
    {
        "id": "mistralai/Mistral-7B-Instruct-v0.3",
        "label": "Mistral 7B (lightweight)",
    },
    {
        "id": "mistralai/Mistral-Small-3.1-24B-Instruct-2503",
        "label": "Mistral Small 3.1 (legacy → 3.2 on DeepInfra)",
    },
]

_MODERATION_SYSTEM = """You are a content safety reviewer for outbound AI phone scripts (job interviews and customer surveys) used in the UK/EU and internationally.
Review the user's script text for harmful content before it is approved for live calls.

Scripts may be written in ANY language (English, Arabic, French, etc.). Judge the MEANING of the content, not the language used.
Normal professional interview and survey language is SAFE in any language — job skills, screening criteria, availability, and neutral business questions are acceptable.

Return ONLY valid JSON with exactly these keys:
- "safe": boolean — true only if the script is acceptable for professional outbound calls
- "category": one of "safe", "racism", "offensive", "sexual", "political"
- "reason": short explanation for the customer when not safe — use the SAME language as the script when possible (empty string if safe)

Flag as NOT safe when the script contains:
- racism: racist, discriminatory, or hateful content targeting protected groups
- offensive: harassment, slurs, threats, extreme insults, or gratuitously abusive language
- sexual: sexual, explicit, or adult content inappropriate for professional calls
- political: partisan campaigning, inflammatory political messaging, or election advocacy

Do NOT flag scripts simply because they are written in Arabic or another non-English language.
No markdown fences. No extra keys."""


def moderation_model_ids() -> set[str]:
    return {str(row["id"]) for row in DEEPINFRA_MODERATION_MODELS}


def normalize_moderation_config(config: dict[str, Any] | None) -> dict[str, Any]:
    cfg = dict(config or {})
    model = str(cfg.get("moderation_model") or DEFAULT_MODERATION_MODEL).strip()
    if model not in moderation_model_ids():
        model = DEFAULT_MODERATION_MODEL
    base_url = str(cfg.get("moderation_base_url") or DEFAULT_MODERATION_BASE_URL).strip().rstrip("/")
    enabled_raw = cfg.get("moderation_enabled")
    moderation_enabled = True if enabled_raw is None else bool(enabled_raw)
    return {
        **cfg,
        "moderation_enabled": moderation_enabled,
        "moderation_model": model,
        "moderation_base_url": base_url or DEFAULT_MODERATION_BASE_URL,
    }


def is_moderation_enabled(db: Session) -> bool:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepinfra")
    if enabled:
        normalized = normalize_moderation_config(cfg if isinstance(cfg, dict) else {})
        return bool(normalized.get("moderation_enabled"))
    return bool(str(os.getenv("DEEPINFRA_API_KEY") or "").strip())


def _moderation_runtime_config(db: Session) -> dict[str, Any]:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepinfra")
    config = normalize_moderation_config(cfg if isinstance(cfg, dict) else {})
    api_key = str(config.get("api_key") or os.getenv("DEEPINFRA_API_KEY") or "").strip()
    if not api_key:
        raise ValueError("DeepInfra API key is not configured")
    if not enabled and not os.getenv("DEEPINFRA_API_KEY"):
        raise ValueError("DeepInfra integration is disabled")
    return {
        "api_key": api_key,
        "base_url": str(config.get("moderation_base_url") or DEFAULT_MODERATION_BASE_URL).strip().rstrip("/"),
        "model": str(config.get("moderation_model") or DEFAULT_MODERATION_MODEL).strip(),
    }


def _parse_moderation_json(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _normalize_result(data: dict[str, Any], *, fallback_reason: str = "") -> dict[str, Any]:
    category = str(data.get("category") or "").strip().lower()
    if category not in MODERATION_CATEGORIES:
        category = "offensive" if not bool(data.get("safe")) else "safe"
    safe = bool(data.get("safe")) and category == "safe"
    if category != "safe":
        safe = False
    reason = str(data.get("reason") or fallback_reason or "").strip()
    if not safe and not reason:
        reason = f"Script flagged for {category} content."
    return {"safe": safe, "category": "safe" if safe else category, "reason": reason if not safe else ""}


def moderate_content(text: str, *, db: Session, language_code: str | None = None) -> dict[str, Any]:
    """Scan script text. Returns {safe, category, reason}. Fail-closed on API errors."""
    script = str(text or "").strip()
    if not script:
        return {"safe": False, "category": "offensive", "reason": "Script text is empty."}
    try:
        runtime = _moderation_runtime_config(db)
    except ValueError as exc:
        logger.warning("script_moderation_config_missing err=%s", exc)
        return {"safe": False, "category": "error", "reason": str(exc)}

    lang_hint = str(language_code or "").strip()
    user_content = f"Review this outbound phone script:\n\n{script[:12000]}"
    if lang_hint:
        from app.utils.script_language import script_language_label

        user_content = f"Script language: {script_language_label(lang_hint)}\n\n{user_content}"

    payload = {
        "model": runtime["model"],
        "messages": [
            {"role": "system", "content": _MODERATION_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 256,
        "temperature": 0.1,
    }
    url = f"{runtime['base_url']}/chat/completions"
    headers = {"Authorization": f"Bearer {runtime['api_key']}", "Content-Type": "application/json"}
    try:
        response = OpenAIProviderService._http_client().post(url, json=payload, headers=headers)
        response.raise_for_status()
        body = response.json()
        content = str(((body.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        parsed = _parse_moderation_json(content)
        if not parsed:
            return {
                "safe": False,
                "category": "error",
                "reason": "Content review returned an invalid response. Try again or contact support.",
            }
        return _normalize_result(parsed)
    except Exception as exc:
        logger.exception("script_moderation_api_failed")
        return {
            "safe": False,
            "category": "error",
            "reason": f"Content review is temporarily unavailable: {exc}",
        }
