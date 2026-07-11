"""Rewrite WA survey template BODY text for Meta UTILITY (Feedback Survey) compliance."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_wa_md_seed_service import _build_abc_choice_components, _sanitize_body
from app.services.survey_whatsapp_template_service import (
    META_BODY_HARD_MAX_CHARS,
    SYNC_ERROR,
    SYNC_LOCAL_CHANGES,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _dumps,
    _effective_components,
    _has_remote_telnyx_id,
    _loads,
    _normalize_draft_components,
    _persist_normalized_draft,
    _refresh_local_sync_status,
    normalize_wa_template_category,
)
from app.services.wa_migration_progress import migration_progress
from app.services.wa_template_utility_lint import clamp_utility_button_labels, lint_utility_template
from app.services.wa_template_meta_sync import (
    is_utility_clone_template_name,
    suggest_utility_clone_template_name,
)

logger = logging.getLogger(__name__)

DEFAULT_UTILITY_LLM_PROVIDER = "deepinfra"
# Ranked for multilingual UTILITY rewrites on DeepInfra (verified on VPS).
DEEPINFRA_UTILITY_MODELS: tuple[str, ...] = (
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
    "Qwen/Qwen2.5-72B-Instruct",
)
DEFAULT_UTILITY_LLM_MODEL = DEEPINFRA_UTILITY_MODELS[0]
DEFAULT_UTILITY_LLM_FALLBACK_PROVIDER = "deepseek"
UTILITY_LLM_REQUEST_TIMEOUT_SECONDS = 120.0


def utility_llm_model_chain(
    *,
    provider: str | None = None,
    llm_model: str | None = None,
) -> list[tuple[str, str | None]]:
    """Ordered (provider, model) attempts for utility BODY rewrites."""
    selected = str(provider or DEFAULT_UTILITY_LLM_PROVIDER).strip().lower()
    if selected == "deepinfra":
        models = list(DEEPINFRA_UTILITY_MODELS)
        if llm_model and str(llm_model).strip() not in models:
            models.insert(0, str(llm_model).strip())
        return [("deepinfra", model) for model in models]
    if selected == "deepseek":
        return [("deepseek", llm_model or None)]
    return [(selected, llm_model or None)]


def _probe_llm_provider(
    db: Session,
    *,
    provider: str,
    model: str | None = None,
    timeout_seconds: float = UTILITY_LLM_REQUEST_TIMEOUT_SECONDS,
) -> bool:
    from app.services.agents.base import AgentMessage

    try:
        OpenAIProviderService.complete(
            db,
            system_prompt='Return JSON only: {"ok":true}',
            messages=[AgentMessage(role="user", content="ping")],
            max_tokens=32,
            temperature=0,
            provider=provider,
            model=model,
            request_timeout=timeout_seconds,
        )
        return True
    except Exception:
        return False


def resolve_utility_llm_config(db: Session, *, probe: bool = False) -> dict[str, str]:
    """Utility rewrite LLM: DeepInfra multilingual models (Admin DB), else DeepSeek."""
    from app.services.provider_settings import ProviderSettingsService

    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepinfra")
    config = cfg if isinstance(cfg, dict) else {}
    api_key = str(config.get("api_key") or "").strip()
    if api_key:
        base_url = OpenAIProviderService._deepinfra_chat_base_url_from_config(config)
        chosen_model = DEFAULT_UTILITY_LLM_MODEL
        if probe:
            for candidate in DEEPINFRA_UTILITY_MODELS:
                if _probe_llm_provider(db, provider="deepinfra", model=candidate):
                    chosen_model = candidate
                    break
            else:
                chosen_model = ""
        if chosen_model:
            return {
                "provider": DEFAULT_UTILITY_LLM_PROVIDER,
                "model": chosen_model,
                "models": ",".join(DEEPINFRA_UTILITY_MODELS),
                "api_key_set": True,
                "base_url": base_url,
                "integration_enabled": bool(enabled),
                "source": "deepinfra",
            }

    ds_cfg, ds_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepseek")
    ds_config = ds_cfg if isinstance(ds_cfg, dict) else {}
    ds_key = str(ds_config.get("api_key") or "").strip()
    ds_model = str(ds_config.get("model") or ds_config.get("default_model") or "deepseek-chat").strip()
    if ds_key and (not probe or _probe_llm_provider(db, provider="deepseek", model=ds_model)):
        ds_base = str(ds_config.get("base_url") or "https://api.deepseek.com").strip().rstrip("/")
        return {
            "provider": DEFAULT_UTILITY_LLM_FALLBACK_PROVIDER,
            "model": ds_model,
            "models": ds_model,
            "api_key_set": True,
            "base_url": ds_base,
            "integration_enabled": bool(ds_enabled),
            "source": "deepseek_fallback",
        }

    if api_key:
        raise ValueError(
            "DeepInfra API key is set but no chat model responded. "
            "Check Admin → Integrations → DeepInfra base URL (use https://api.deepinfra.com/v1/openai, not Whisper)."
        )
    raise ValueError(
        "No utility LLM available. Configure DeepInfra or DeepSeek in Admin → Integrations."
    )

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+"
    "\uFE0F?",
    flags=re.UNICODE,
)

_RECOMMEND_INTENT_RE = re.compile(
    r"\bwould you recommend\b|\bhow likely are you\b|\blikely are you to\b|"
    r"\brecommend\b|\breturn intent\b|\breferral likelihood\b|\brenewal intent\b|"
    r"\bnet promoter\b|\bnps\b|\bshop with us again\b|\bshop with us\b.*\bagain\b|"
    r"\brepeat purchase\b|\bpurchase intent\b|\battend our events again\b",
    re.IGNORECASE,
)

_WAS_TOPIC_SUFFIX_RE = re.compile(r"^was_(?:system_)?(.+)_(\d{3})_(en|ar)(?:_[a-z0-9]{4,8})?$", re.I)
_CFS_META_NAME_RE = re.compile(r"^cfs_([^_]+)_(.+)_([a-z]{2,3})_v(\d+)$", re.I)

_ENGLISH_UTILITY_MARKERS = (
    "how would you rate",
    "reply with one option below",
    "following your recent",
    "after your recent",
)

_UTILITY_CONTEXT_PHRASES = (
    "recent visit",
    "recent interaction",
    "recent experience",
    "recent service",
    "recent engagement",
    "recent order",
    "recent transaction",
    "following your",
    "after your recent",
    "at work",
    "in your role",
    "in your job",
    "your team",
    "your manager",
    "your workplace",
    "reciente",
    "visita",
    "estancia",
    "experiencia",
    "nuestro hotel",
    "su experiencia",
    "su estancia",
    # Arabic recent-interaction anchors (Convert LLM + lint path)
    "تجربتك الأخيرة",
    "زيارتك الأخيرة",
    "في تجربتك",
    "في زيارتك",
    "في عملك",
    "بعد زيارتك",
    "بعد تجربتك",
    "المقدمة من فريقنا",
)


def parse_cfs_meta_name(name: str) -> dict[str, str] | None:
    """Parse cfs_{industry}_{topic}_{lang}_v{n} Meta names."""
    match = _CFS_META_NAME_RE.match(str(name or "").strip().lower())
    if not match:
        return None
    return {
        "industry": str(match.group(1) or "").strip(),
        "topic_key": str(match.group(2) or "").strip(),
        "topic": str(match.group(2) or "").replace("_", " ").strip(),
        "lang": str(match.group(3) or "").strip(),
        "version": str(match.group(4) or "").strip(),
    }


def _language_code_from_value(language: str | None, *, template_name: str = "") -> str:
    cfs = parse_cfs_meta_name(template_name)
    cfs_lang = str(cfs.get("lang") or "").strip().lower() if cfs else ""
    was_match = _WAS_TOPIC_SUFFIX_RE.match(str(template_name or "").strip().lower())
    was_lang = str(was_match.group(3) or "").strip().lower() if was_match else ""
    raw = str(language or "").strip().lower().replace("-", "_")
    # Prefer explicit non-English tokens from the template name when row.language is missing/English.
    name_lang = cfs_lang or was_lang
    if name_lang and name_lang not in {"en"} and (not raw or raw.startswith("en")):
        return name_lang
    if raw.startswith("en"):
        return "en"
    if raw.startswith("ar"):
        return "ar"
    if raw:
        head = raw.split("_", 1)[0]
        if len(head) >= 2:
            return head
    if name_lang:
        return name_lang
    return "en"


def _language_token_from_manifest(
    language: str | None,
    *,
    remote_name: str = "",
) -> str:
    cfs = parse_cfs_meta_name(remote_name)
    raw = str(language or "").strip()
    if cfs and cfs.get("lang"):
        inferred = str(cfs["lang"]).strip().lower()
        if not raw or raw.lower().replace("-", "_").startswith("en"):
            return f"{inferred}_gb" if len(inferred) == 2 else inferred
    return raw or "en_gb"


def lang_variant_from_manifest_item(item: dict[str, Any]) -> "LangVariant":
    """Rebuild a LangVariant from saved manifest JSON with cfs_* metadata filled in."""
    from app.services.wa_marketing_utility_multilang_service import LangVariant

    remote_name = str(item.get("remote_name") or item.get("label") or "").strip()
    cfs = parse_cfs_meta_name(remote_name) if remote_name else None
    return LangVariant(
        local_template_id=item.get("local_template_id"),
        label=remote_name or str(item.get("label") or ""),
        remote_name=remote_name,
        language=_language_token_from_manifest(
            str(item.get("language") or item.get("remote_language") or ""),
            remote_name=remote_name,
        ),
        product=str(item.get("product") or "survey"),
        body_before=str(item.get("body_before") or ""),
        buttons=list(item.get("buttons") or []),
        industry_slug=item.get("industry_slug") or (cfs.get("industry") if cfs else None),
        topic_name=(
            item.get("topic_name")
            or item.get("survey_type")
            or item.get("template_key")
            or (cfs.get("topic") if cfs else None)
        ),
        template_key=item.get("template_key") or (cfs.get("topic_key") if cfs else None),
        meta=item.get("meta") or {},
    )


def _is_non_english_language(language: str | None, *, template_name: str = "") -> bool:
    """True for any locale that must not be force-rewritten into English Utility copy."""
    code = _language_code_from_value(language, template_name=template_name)
    return code != "en"


def _language_label(language: str | None, *, template_name: str = "") -> str:
    code = _language_code_from_value(language, template_name=template_name)
    labels = {
        "en": "English",
        "ar": "Arabic (Modern Standard)",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "zh": "Chinese",
        "pt": "Portuguese",
        "hi": "Hindi",
    }
    return labels.get(code, code)


def _original_looks_utility_safe(
    original: str,
    *,
    language: str | None = None,
    template_name: str = "",
) -> bool:
    """Non-English feedback questions that are already utility-safe — keep unchanged."""
    from app.services.wa_template_utility_content import is_promo_wording

    text = str(original or "").strip()
    if not text or _body_has_recommend_intent(text) or is_promo_wording(text):
        return False
    if "?" not in text and "؟" not in text:
        return False
    if _is_non_english_language(language, template_name=template_name):
        return True
    return _mentions_recent_interaction(text)


_META_UTILITY_GUIDANCE = """
Meta WhatsApp UTILITY — Feedback Survey rules (2025):
- Must collect feedback on a previous engagement with the organisation (visit, service, OR work/role for employee surveys).
- Must be specific to the survey topic and industry context (not a generic marketing survey).
- Must be NON-PROMOTIONAL: no offers, discounts, upsell, loyalty promos, or persuasive marketing tone.
- Keep the original leading emoji when present (one emoji at the start is fine for feedback tone).
- Match the industry frame: employee/workplace surveys must NOT say "visit"; use work/role language.
- Customer-facing surveys may use visit/service language.
- Keep the same rating intent and answer options meaning; only rewrite the BODY question sentence(s).
- BODY must be plain text with NO {{1}} variables for these abc_choice templates.
- Max {max_chars} characters.
- CRITICAL: Output BODY in the SAME language as the input BODY (Spanish stays Spanish, French stays French, etc.). Never translate to English unless the input is English.
""".format(max_chars=META_BODY_HARD_MAX_CHARS)


@dataclass
class UtilityRewriteResult:
    template_name: str
    ok: bool
    old_body: str
    new_body: str
    message: str
    pushed: bool = False


def load_template_names_from_file(path: str) -> list[str]:
    names: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            names.append(text)
    return names


def _extract_body_and_buttons(components: list[Any]) -> tuple[str, list[str]]:
    body = ""
    buttons: list[str] = []
    for comp in components:
        if not isinstance(comp, dict):
            continue
        ctype = str(comp.get("type") or "").upper()
        if ctype == "BODY":
            body = str(comp.get("text") or "").strip()
        elif ctype == "BUTTONS":
            for btn in comp.get("buttons") or []:
                if isinstance(btn, dict):
                    label = str(btn.get("text") or btn.get("title") or "").strip()
                    if label:
                        buttons.append(label)
    return body, buttons


def _extract_leading_emoji(text: str) -> tuple[str, str]:
    raw = str(text or "").strip()
    match = _EMOJI_RE.match(raw)
    if not match:
        return "", raw
    emoji = match.group(0)
    rest = raw[match.end() :].lstrip()
    rest = re.sub(r"^\uFE0F\s*", "", rest)
    return emoji, rest


def _prepend_leading_emoji(emoji: str, body: str) -> str:
    text = str(body or "").strip()
    if not emoji:
        return text
    if text.startswith(emoji):
        return text
    return f"{emoji} {text}".strip()


def _normalize_leading_emoji_text(text: str) -> str:
    """Collapse stray spaces inside/with leading emoji (Meta rejects some sequences)."""
    raw = str(text or "").strip()
    emoji, rest = _extract_leading_emoji(raw)
    if not emoji:
        return re.sub(r"\s+", " ", raw).strip()
    rest = re.sub(r"\s+", " ", rest).strip()
    return _prepend_leading_emoji(emoji, rest)


def _mentions_recent_interaction(text: str) -> bool:
    lower = str(text or "").lower()
    return any(phrase in lower for phrase in _UTILITY_CONTEXT_PHRASES)


def _forced_utility_body_same_language(
    *,
    topic: str,
    lang_code: str,
    industry_slug: str | None,
    industry_name: str | None,
    frame_key: str,
    original_cleaned: str,
    template_name: str = "",
) -> str:
    """Build Utility body in the template's language — never translate AR/ES/… into English."""
    from app.services.wa_template_utility_content import (
        employee_utility_body_for_topic,
        utility_body_ar_for_topic,
        utility_body_for_topic,
    )

    if lang_code == "ar":
        return utility_body_ar_for_topic(
            topic,
            emoji="",
            industry_slug=industry_slug,
            industry_name=industry_name,
            original_body=original_cleaned,
        ).lstrip()

    if lang_code != "en":
        # No curated Utility frames for ES/FR/… — keep original when already Utility-safe;
        # otherwise keep the original question (sanitized) rather than English topic copy.
        if _original_looks_utility_safe(
            original_cleaned,
            language=lang_code,
            template_name=template_name,
        ):
            return _sanitize_body(original_cleaned)
        return _sanitize_body(original_cleaned)

    if frame_key == "employee":
        return (
            employee_utility_body_for_topic(topic)
            or utility_body_for_topic(
                topic,
                emoji="",
                industry_slug=industry_slug,
                industry_name=industry_name,
            ).lstrip()
        )
    return utility_body_for_topic(
        topic,
        emoji="",
        industry_slug=industry_slug,
        industry_name=industry_name,
    ).lstrip()


def _rule_based_utility_body(
    original: str,
    *,
    topic_hint: str = "",
    leading_emoji: str = "",
    industry_slug: str | None = None,
    industry_name: str | None = None,
    language: str | None = None,
    template_name: str = "",
    force_rewrite: bool = False,
) -> str:
    from app.services.wa_template_utility_content import (
        employee_utility_body_for_topic,
        is_promo_wording,
        resolve_industry_frame,
        utility_body_for_topic,
    )

    emoji, cleaned = _extract_leading_emoji(original)
    if leading_emoji:
        emoji = leading_emoji
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    lang_code = _language_code_from_value(language, template_name=template_name)
    frame = resolve_industry_frame(industry_slug, industry_name, language=lang_code if lang_code == "ar" else "en")
    topic = topic_hint.strip() or frame["fallback_topic"]

    if force_rewrite:
        body = _forced_utility_body_same_language(
            topic=topic,
            lang_code=lang_code,
            industry_slug=industry_slug,
            industry_name=industry_name,
            frame_key=frame["key"],
            original_cleaned=cleaned,
            template_name=template_name,
        )
        return _normalize_leading_emoji_text(_prepend_leading_emoji(emoji, _sanitize_body(body)))

    if _is_non_english_language(lang_code, template_name=template_name) and _original_looks_utility_safe(
        cleaned,
        language=lang_code,
        template_name=template_name,
    ):
        return _normalize_leading_emoji_text(_prepend_leading_emoji(emoji, _sanitize_body(cleaned)))
    if not cleaned:
        cleaned = frame["experience"]
    # Never force visit language onto employee surveys.
    if frame["key"] == "employee":
        if "visit" in cleaned.lower():
            body = employee_utility_body_for_topic(topic) or utility_body_for_topic(
                topic,
                emoji="",
                industry_slug=industry_slug,
                industry_name=industry_name,
            ).lstrip()
            return _normalize_leading_emoji_text(_prepend_leading_emoji(emoji, _sanitize_body(body)))
        mapped = employee_utility_body_for_topic(topic)
        if mapped:
            return _normalize_leading_emoji_text(_prepend_leading_emoji(emoji, _sanitize_body(mapped)))
        if (
            cleaned
            and "?" in cleaned
            and not _body_has_recommend_intent(cleaned)
            and not is_promo_wording(cleaned)
        ):
            return _normalize_leading_emoji_text(_prepend_leading_emoji(emoji, _sanitize_body(cleaned)))
    if (
        _mentions_recent_interaction(cleaned)
        and not (frame["key"] == "employee" and "visit" in cleaned.lower())
        and not _body_has_recommend_intent(cleaned)
    ):
        return _normalize_leading_emoji_text(_prepend_leading_emoji(emoji, _sanitize_body(cleaned)))
    body = utility_body_for_topic(
        topic,
        emoji="",
        industry_slug=industry_slug,
        industry_name=industry_name,
    ).lstrip()
    return _normalize_leading_emoji_text(_prepend_leading_emoji(emoji, _sanitize_body(body)))


def _parse_rewrite_json(raw: str) -> dict[str, Any] | None:
    text = str(raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _topic_from_template_name(name: str) -> str:
    base = str(name or "").strip().lower()
    was_match = _WAS_TOPIC_SUFFIX_RE.match(base)
    if was_match:
        middle = str(was_match.group(1) or "").strip("_")
        if "would_recommend" in middle:
            return "would recommend"
        if "return_intent" in middle:
            return "return intent"
        if "repeat_purchase" in middle or "repeat purchase" in middle.replace("_", " "):
            return "repeat purchase intent"
        parts = [p for p in middle.split("_") if p]
        if parts and parts[0] == "employee" and len(parts) > 1:
            return " ".join(parts[1:])
        if len(parts) >= 2:
            return " ".join(parts[-2:])
        return middle.replace("_", " ").strip() or "your recent experience"
    if base.startswith("voxbulk_survey_"):
        base = base[len("voxbulk_survey_") :]
    cfs = parse_cfs_meta_name(base if base.startswith("cfs_") else name)
    if cfs:
        return cfs["topic"]
    if base.startswith("cfs_"):
        base = base[4:]
        base = re.sub(r"_[a-z]{2,3}_v\d+$", "", base)
        parts = base.split("_", 1)
        if len(parts) == 2:
            return parts[1].replace("_", " ").strip()
    base = re.sub(r"_abc_[a-f0-9]{6}$", "", base)
    base = re.sub(r"_standard$", "", base)
    base = base.replace("_", " ")
    return base.strip() or "your recent experience"


def _survey_type_for_template_row(db: Session, row: TelnyxWhatsappTemplate) -> tuple[str | None, str | None]:
    st_id = str(row.survey_type_id or "").strip()
    if not st_id:
        return None, None
    st = db.get(SurveyType, st_id)
    if st is None:
        return None, None
    return str(st.slug or "") or None, str(st.name or "") or None


def _topic_for_template_row(db: Session, row: TelnyxWhatsappTemplate) -> str:
    _slug, st_name = _survey_type_for_template_row(db, row)
    if st_name:
        return st_name.strip()
    return _topic_from_template_name(row.name)


def _industry_for_template_row(db: Session, row: TelnyxWhatsappTemplate) -> tuple[str | None, str | None]:
    st_id = str(row.survey_type_id or "").strip()
    if not st_id:
        return None, None
    st = db.get(SurveyType, st_id)
    if st is None or not st.industry_id:
        return None, None
    ind = db.get(Industry, st.industry_id)
    if ind is None:
        return None, None
    return str(ind.slug or "") or None, str(ind.name or "") or None


def _body_has_recommend_intent(text: str) -> bool:
    return bool(_RECOMMEND_INTENT_RE.search(str(text or "")))


def _looks_english_utility_template(body: str) -> bool:
    low = str(body or "").lower()
    return any(marker in low for marker in _ENGLISH_UTILITY_MARKERS)


def rewrite_body_for_utility(
    db: Session,
    *,
    original_body: str,
    button_labels: list[str],
    template_name: str,
    display_name: str | None = None,
    use_llm: bool = True,
    llm_provider: str = DEFAULT_UTILITY_LLM_PROVIDER,
    llm_model: str | None = None,
    industry_slug: str | None = None,
    industry_name: str | None = None,
    topic_name: str | None = None,
    language: str | None = None,
    force_rewrite: bool = False,
) -> str:
    from app.services.wa_template_utility_content import resolve_industry_frame

    lang_code = _language_code_from_value(language, template_name=template_name)
    cfs = parse_cfs_meta_name(template_name)
    if cfs:
        industry_slug = industry_slug or cfs.get("industry")
        topic_name = topic_name or cfs.get("topic")
    topic = (topic_name or _topic_from_template_name(template_name)).strip()
    label = display_name or template_name
    frame_lang = "ar" if lang_code == "ar" else "en"
    frame = resolve_industry_frame(industry_slug, industry_name, language=frame_lang)
    leading_emoji, _ = _extract_leading_emoji(original_body)

    def _fallback_body(source: str | None = None) -> str:
        return _rule_based_utility_body(
            str(source if source is not None else original_body),
            topic_hint=topic,
            leading_emoji=leading_emoji,
            industry_slug=industry_slug,
            industry_name=industry_name,
            language=lang_code,
            template_name=template_name,
            force_rewrite=force_rewrite,
        )

    if not use_llm:
        return _fallback_body()

    from app.services.wa_template_utility_lint import lint_utility_template

    lint_before = lint_utility_template(
        body=original_body,
        buttons=button_labels,
        language=language or lang_code,
        meta_category="utility",
        template_key=topic_name,
    )
    # Convert / force path must still produce a Utility rewrite even when local lint already passes
    # (Meta may still have MARKETING classification on the live name).
    if lint_before.ok and not force_rewrite:
        return _normalize_leading_emoji_text(
            _prepend_leading_emoji(leading_emoji, _sanitize_body(str(original_body).strip()))
        )

    system_prompt = (
        "You rewrite WhatsApp message template BODY text so Meta approves them as UTILITY category "
        "(Feedback Survey sub-type). Return ONLY valid JSON: "
        '{"body":"rewritten question text","notes":"one line why this is utility-compliant"}'
        + _META_UTILITY_GUIDANCE
        + "\nAvoid ALL marketing signals: sale, discount, offer, gift, reward, promotion, new, "
        "loyalty, refer-a-friend, return intent, upsell, vague brand surveys.\n"
        "CRITICAL meaning rule: Keep the SAME specific subject as Current BODY "
        "(e.g. nutrition advice / النصائح الغذائية stays that topic). "
        "Never replace a specific topic with vague 'this service' / 'هذه الخدمة' / 'your experience' alone. "
        "Never rewrite into NPS, recommend-to-others, return-intent, or referral questions."
    )
    emoji_hint = (
        f"Keep this leading emoji at the start: {leading_emoji}"
        if leading_emoji
        else "No leading emoji in the original."
    )
    user_prompt = (
        f"Output language: {_language_label(lang_code, template_name=template_name)} (same as input BODY — do NOT translate to English)\n"
        f"Industry: {industry_name or industry_slug or 'n/a'} (frame={frame['key']})\n"
        f"Template: {label}\n"
        f"Survey topic: {topic}\n"
        f"Context phrase to use: {frame['context']}\n"
        f"Current BODY:\n{original_body}\n\n"
        f"{emoji_hint}\n"
        f"Quick-reply buttons (keep meaning aligned): {', '.join(button_labels) or 'n/a'}\n\n"
        "Rewrite BODY only. Preserve the specific survey subject from Current BODY + Survey topic. "
        "Match the industry frame exactly. "
        "If the current BODY lacks a recent-visit/stay/experience/work anchor, add one naturally "
        "in the output language WITHOUT erasing the specific topic."
    )
    try:
        chain = utility_llm_model_chain(provider=llm_provider, llm_model=llm_model)
        if str(llm_provider or "").strip().lower() != "deepinfra":
            chain.append(("deepseek", None))
        last_exc: Exception | None = None
        for attempt_provider, attempt_model in chain:
            try:
                result = OpenAIProviderService.complete(
                    db,
                    system_prompt=system_prompt,
                    messages=[AgentMessage(role="user", content=user_prompt)],
                    max_tokens=400,
                    temperature=0.2,
                    provider=attempt_provider,
                    model=attempt_model,
                    request_timeout=UTILITY_LLM_REQUEST_TIMEOUT_SECONDS,
                )
                parsed = _parse_rewrite_json(result.assistant_text)
                body = str((parsed or {}).get("body") or "").strip()
                body = _sanitize_body(body)
                if not body:
                    raise ValueError("empty body from model")
                if force_rewrite and body.strip().lower() == _sanitize_body(str(original_body)).strip().lower():
                    return _fallback_body()
                if _is_non_english_language(lang_code, template_name=template_name) and _looks_english_utility_template(body):
                    return _fallback_body()
                if frame["key"] == "employee" and "visit" in body.lower():
                    return _fallback_body(body)
                if not _mentions_recent_interaction(body):
                    if _is_non_english_language(lang_code, template_name=template_name):
                        return _fallback_body()
                    return _fallback_body(body)
                # Reject NPS / recommend copy even when the model added a recent-visit anchor.
                lint_after = lint_utility_template(
                    body=body,
                    buttons=button_labels,
                    language=language or lang_code,
                    meta_category="utility",
                    template_key=topic_name,
                )
                if not lint_after.ok or _body_has_recommend_intent(body):
                    return _fallback_body()
                # Reject vague "هذه الخدمة" when original had a specific Arabic subject.
                if lang_code == "ar" and "هذه الخدمة" in body:
                    from app.services.wa_template_utility_content import extract_arabic_topic_from_body

                    if extract_arabic_topic_from_body(original_body):
                        return _fallback_body()
                return _normalize_leading_emoji_text(_prepend_leading_emoji(leading_emoji, body))
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "utility_rewrite_llm_attempt_failed name=%s provider=%s model=%s err=%s",
                    template_name,
                    attempt_provider,
                    attempt_model or "(default)",
                    str(exc)[:200],
                )
                continue
        if last_exc:
            raise last_exc
        raise ValueError("no LLM providers available for utility rewrite")
    except Exception as exc:
        logger.warning("utility_rewrite_llm_fallback name=%s err=%s", template_name, str(exc)[:200])
        return _fallback_body()


def apply_utility_rewrite_to_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    use_llm: bool = True,
    llm_provider: str = DEFAULT_UTILITY_LLM_PROVIDER,
    llm_model: str | None = None,
    new_body_override: str | None = None,
    force_rewrite: bool = False,
) -> tuple[str, str]:
    components = _effective_components(row)
    if not components:
        remote = _loads(row.components_json)
        if isinstance(remote, list) and remote:
            components = remote
    if not components:
        raise SurveyWhatsappTemplateError(f"No components to rewrite for {row.name}")

    old_body, buttons = _extract_body_and_buttons(components)
    if not old_body:
        raise SurveyWhatsappTemplateError(f"Missing BODY text for {row.name}")

    buttons = clamp_utility_button_labels(buttons)

    industry_slug, industry_name = _industry_for_template_row(db, row)
    topic_name = _topic_for_template_row(db, row)
    from app.services.wa_template_utility_content import (
        AR_RATING_BUTTONS,
        RATING_BUTTONS,
        _is_would_recommend_topic,
        buttons_labels_equal,
        utility_buttons_matching_body,
    )

    recommend_topic = _is_would_recommend_topic(topic_name) or "would_recommend" in str(
        row.name or ""
    ).lower()
    recommend_buttons = any(_body_has_recommend_intent(b) for b in buttons)
    # NPS / would-recommend must become overall-satisfaction + rating buttons (never LLM NPS copy).
    if recommend_topic or recommend_buttons or _body_has_recommend_intent(old_body):
        use_llm = False
        lang_ar = str(row.language or "").lower().startswith("ar")
        buttons = list(AR_RATING_BUTTONS if lang_ar else RATING_BUTTONS)

    if new_body_override is not None and str(new_body_override).strip():
        new_body = str(new_body_override).strip()
    else:
        new_body = rewrite_body_for_utility(
            db,
            original_body=old_body,
            button_labels=buttons,
            template_name=row.name,
            display_name=row.display_name,
            use_llm=use_llm,
            llm_provider=llm_provider,
            llm_model=llm_model,
            industry_slug=industry_slug,
            industry_name=industry_name,
            topic_name=topic_name,
            language=row.language,
            force_rewrite=force_rewrite or recommend_topic or recommend_buttons,
        )
    new_body = _normalize_leading_emoji_text(new_body)

    # After BODY rewrite, realign quick-replies so labels match the question (not leftover MARKETING text).
    matched = utility_buttons_matching_body(
        body=new_body,
        topic_name=topic_name,
        template_name=row.name,
        language=row.language,
    )
    if force_rewrite or recommend_topic or recommend_buttons or not buttons_labels_equal(buttons, matched):
        buttons = clamp_utility_button_labels(matched)

    lint = lint_utility_template(
        body=new_body,
        buttons=buttons,
        language=row.language,
        meta_category="utility",
    )
    if not lint.ok:
        # Last resort: force rule-based satisfaction body + rating buttons, then re-lint.
        if recommend_topic or recommend_buttons or _body_has_recommend_intent(new_body):
            new_body = rewrite_body_for_utility(
                db,
                original_body=old_body,
                button_labels=buttons,
                template_name=row.name,
                display_name=row.display_name,
                use_llm=False,
                industry_slug=industry_slug,
                industry_name=industry_name,
                topic_name=topic_name or "would recommend",
                language=row.language,
                force_rewrite=True,
            )
            new_body = _normalize_leading_emoji_text(new_body)
            buttons = clamp_utility_button_labels(
                utility_buttons_matching_body(
                    body=new_body,
                    topic_name=topic_name or "would recommend",
                    template_name=row.name,
                    language=row.language,
                )
            )
            lint = lint_utility_template(
                body=new_body,
                buttons=buttons,
                language=row.language,
                meta_category="utility",
            )
        if not lint.ok:
            # Button labels alone may still fail lint — force matched set once more.
            buttons = clamp_utility_button_labels(
                utility_buttons_matching_body(
                    body=new_body,
                    topic_name=topic_name,
                    template_name=row.name,
                    language=row.language,
                )
                or list(RATING_BUTTONS)
            )
            lint = lint_utility_template(
                body=new_body,
                buttons=buttons,
                language=row.language,
                meta_category="utility",
            )
        if not lint.ok:
            msgs = "; ".join(i.message for i in lint.issues)
            raise SurveyWhatsappTemplateError(f"Utility lint failed for {row.name}: {msgs}")
    if not buttons:
        normalized = _normalize_draft_components(components)
        for comp in normalized:
            if str(comp.get("type") or "").upper() == "BODY":
                comp["text"] = new_body
        draft = normalized
    else:
        draft = _build_abc_choice_components(body=new_body, options=buttons)

    row.category = normalize_wa_template_category("UTILITY", required=True)
    row.draft_components_json = _dumps(draft)
    row.local_sync_status = SYNC_LOCAL_CHANGES
    _persist_normalized_draft(db, row, draft)
    row.local_sync_status = _refresh_local_sync_status(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return old_body, new_body


def _already_submitted_utility_migration(row: TelnyxWhatsappTemplate) -> bool:
    """True when UTILITY row is already on Meta (PENDING/APPROVED) — safe to skip re-push."""
    if str(row.category or "").upper() != "UTILITY":
        return False
    if not _has_remote_telnyx_id(row):
        return False
    if str(row.local_sync_status or "") == SYNC_ERROR:
        return False
    if str(row.last_push_error or "").strip():
        return False
    return str(row.status or "").upper() in {"PENDING", "APPROVED"}


def _find_template_row(db: Session, name: str) -> TelnyxWhatsappTemplate | None:
    clean = str(name or "").strip()
    if not clean:
        return None
    rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == clean)
        ).scalars().all()
    )
    if len(rows) > 1:
        raise SurveyWhatsappTemplateError(
            f"Multiple templates named {clean!r} — pass template id or filter by survey type"
        )
    if rows:
        return rows[0]
    clone_name = suggest_utility_clone_template_name(clean)
    if clone_name == clean:
        return None
    clone_rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == clone_name)
        ).scalars().all()
    )
    if len(clone_rows) > 1:
        raise SurveyWhatsappTemplateError(
            f"Multiple templates named {clone_name!r} — pass template id or filter by survey type"
        )
    return clone_rows[0] if clone_rows else None


def _template_body_text(row: TelnyxWhatsappTemplate) -> str:
    components = _effective_components(row)
    body, _buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])
    if body:
        return body
    return str(row.body_preview or "").strip()


def _template_needs_utility_rewrite(
    row: TelnyxWhatsappTemplate,
    *,
    body: str | None = None,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    name_lower = str(row.name or "").lower()
    text = body if body is not None else _template_body_text(row)
    category = str(row.category or "").upper()
    status = str(row.status or "").upper()

    if category == "MARKETING":
        reasons.append("category_marketing")
    if status == "REJECTED":
        reasons.append("status_rejected")
    if str(row.last_push_error or "").strip():
        reasons.append("last_push_error")
    if "would_recommend" in name_lower or "return_intent" in name_lower:
        reasons.append("name_recommend_topic")
    if _body_has_recommend_intent(text):
        reasons.append("body_recommend_intent")

    from app.services.wa_template_utility_lint import lint_utility_template

    buttons: list[str] = []
    components = _effective_components(row)
    if isinstance(components, list):
        _body, buttons = _extract_body_and_buttons(components)
        if not text:
            text = _body
    lint = lint_utility_template(
        body=text,
        buttons=buttons,
        language=row.language,
        meta_category=row.category,
    )
    if not lint.ok:
        reasons.append("utility_lint_fail")

    return bool(reasons), reasons


def _remote_item_is_marketing(item: dict[str, Any]) -> bool:
    category = str(item.get("category") or "").strip().upper()
    return "MARKET" in category


def _serialize_local_candidate(
    row: TelnyxWhatsappTemplate,
    *,
    st: SurveyType | None,
    ind: Any,
    body: str,
    reasons: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "process_name": row.name,
        "actionable": True,
        "status": row.status,
        "category": row.category,
        "industry_slug": getattr(ind, "slug", None),
        "survey_type": getattr(st, "name", None),
        "body_preview": body[:160],
        "reasons": reasons,
    }
    if extra:
        payload.update(extra)
    return payload


def discover_was_utility_rewrite_candidates_local(
    db: Session,
    *,
    name_contains: str | None = None,
    industry_slug: str | None = None,
    include_already_utility: bool = False,
    was_only: bool = True,
) -> list[dict[str, Any]]:
    """Find survey templates needing rewrite from local DB signals only."""
    from app.models.industry import Industry
    from app.services.wa_template_product_scope import is_survey_platform_row

    query = (
        select(TelnyxWhatsappTemplate, SurveyType, Industry)
        .outerjoin(SurveyType, SurveyType.id == TelnyxWhatsappTemplate.survey_type_id)
        .outerjoin(Industry, Industry.id == SurveyType.industry_id)
        .order_by(TelnyxWhatsappTemplate.name.asc())
    )
    if was_only:
        query = query.where(TelnyxWhatsappTemplate.name.like("was_%"))
    if name_contains:
        query = query.where(TelnyxWhatsappTemplate.name.ilike(f"%{name_contains.strip()}%"))
    if industry_slug:
        query = query.where(Industry.slug == str(industry_slug).strip().lower())

    out: list[dict[str, Any]] = []
    for row, st, ind in db.execute(query).all():
        if was_only is False and not is_survey_platform_row(db, row):
            continue
        if not include_already_utility and _already_submitted_utility_migration(row):
            continue
        body = _template_body_text(row)
        needs, reasons = _template_needs_utility_rewrite(row, body=body)
        if not needs:
            continue
        out.append(_serialize_local_candidate(row, st=st, ind=ind, body=body, reasons=reasons))
    return out


def discover_remote_marketing_survey_templates(
    db: Session,
    *,
    name_contains: str | None = None,
    industry_slug: str | None = None,
    profile_ids: list[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Match admin matrix: live MARKETING templates on Meta/Telnyx survey scope."""
    from app.models.industry import Industry
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
    from app.services.wa_template_product_scope import filter_remote_for_service_code, is_survey_platform_name
    from app.services.wa_template_profile_push_service import WaTemplateProfilePushService
    from app.services.wa_template_sync_profile import summarize_for_connection_profile
    from app.services.wa_template_sync_service import WaTemplateSyncService

    primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code="survey")
    backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code="survey")
    pids = [str(pid).strip() for pid in (profile_ids or []) if str(pid or "").strip()]
    if not pids:
        pids = [pid for pid in (primary_id, backup_id) if pid]

    profile_summaries: list[dict[str, Any]] = []
    marketing_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for pid in pids:
        summary = summarize_for_connection_profile(db, pid, service_code="survey")
        profile_summaries.append(summary)
        if not summary.get("ok"):
            continue
        remote_all = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
            db,
            connection_profile_id=pid,
            service_code="survey",
            allow_account_waba_fallback=False,
        )
        remote = filter_remote_for_service_code(remote_all, "survey")
        provider = str(summary.get("provider") or "unknown").strip().lower()
        for item in remote:
            if not isinstance(item, dict) or not _remote_item_is_marketing(item):
                continue
            remote_name = str(item.get("name") or "").strip().lower()
            if not remote_name or not is_survey_platform_name(remote_name):
                continue
            if name_contains and name_contains.strip().lower() not in remote_name:
                continue
            lang = str(item.get("language") or item.get("language_code") or "en_gb").strip().lower()
            key = (remote_name, lang)
            entry = marketing_by_key.setdefault(
                key,
                {
                    "remote_name": remote_name,
                    "remote_language": lang,
                    "remote_status": str(item.get("status") or "").upper() or None,
                    "remote_profiles": [],
                    "reasons": [],
                },
            )
            entry["remote_profiles"].append(
                {
                    "profile_id": pid,
                    "provider": provider,
                    "status": str(item.get("status") or "").upper() or None,
                    "label": summary.get("profile_label"),
                }
            )
            reason = f"remote_marketing_{provider}"
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)

    local_rows = WaTemplateSyncService.collect_survey_mirror_templates(db)
    candidates: list[dict[str, Any]] = []
    needle = name_contains.strip().lower() if name_contains else ""

    for (_remote_name, _lang), entry in sorted(marketing_by_key.items()):
        row = WaTemplateSyncService._find_local_row_for_meta_live_name(
            local_rows, entry["remote_name"], entry["remote_language"]
        )
        st: SurveyType | None = None
        ind: Industry | None = None
        if row is not None and row.survey_type_id:
            st = db.get(SurveyType, row.survey_type_id)
            if st is not None and st.industry_id:
                ind = db.get(Industry, st.industry_id)
        if industry_slug and str(getattr(ind, "slug", None) or "").lower() != str(industry_slug).strip().lower():
            continue
        if needle and row is not None and needle not in str(row.name or "").lower():
            if needle not in entry["remote_name"]:
                continue

        body = _template_body_text(row) if row is not None else ""
        reasons = list(entry["reasons"])
        local_category = str(row.category or "").upper() if row is not None else None
        if row is not None and local_category == "UTILITY":
            reasons.append("local_category_utility_desync")

        if row is None:
            candidates.append(
                {
                    "id": None,
                    "name": entry["remote_name"],
                    "process_name": None,
                    "actionable": False,
                    "status": entry.get("remote_status"),
                    "category": "MARKETING",
                    "local_category": None,
                    "industry_slug": None,
                    "survey_type": None,
                    "body_preview": "",
                    "remote_name": entry["remote_name"],
                    "remote_profiles": entry["remote_profiles"],
                    "reasons": reasons + ["no_local_row"],
                }
            )
            continue

        candidates.append(
            _serialize_local_candidate(
                row,
                st=st,
                ind=ind,
                body=body,
                reasons=reasons,
                extra={
                    "remote_name": entry["remote_name"],
                    "remote_profiles": entry["remote_profiles"],
                    "local_category": row.category,
                },
            )
        )

    meta_marketing = telnyx_marketing = 0
    for summary in profile_summaries:
        if not summary.get("ok"):
            continue
        count = int((summary.get("summary") or {}).get("marketing") or 0)
        provider = str(summary.get("provider") or "").strip().lower()
        if provider == "meta":
            meta_marketing = count
        elif provider == "telnyx":
            telnyx_marketing = count

    overview = {
        "profiles": profile_summaries,
        "remote_marketing_meta": meta_marketing,
        "remote_marketing_telnyx": telnyx_marketing,
        "unique_remote_marketing": len(marketing_by_key),
        "actionable_local_matches": sum(1 for item in candidates if item.get("actionable")),
        "missing_local_row": sum(1 for item in candidates if not item.get("actionable")),
    }
    return overview, candidates


def _resolve_product_for_remote_name(remote_name: str) -> str:
    from app.services.wa_template_product_scope import is_feedback_platform_name, is_survey_platform_name

    n = str(remote_name or "").strip().lower()
    if is_survey_platform_name(n):
        return "survey"
    if is_feedback_platform_name(n):
        return "feedback"
    return "orphan"


def _find_feedback_row_for_remote_name(db: Session, remote_name: str) -> Any | None:
    from app.models.customer_feedback import FeedbackWaTemplate

    clean = str(remote_name or "").strip().lower()
    if not clean:
        return None
    row = db.execute(
        select(FeedbackWaTemplate).where(FeedbackWaTemplate.meta_template_name == clean).limit(1)
    ).scalar_one_or_none()
    if row is not None:
        return row
    from app.services.customer_feedback.feedback_telnyx_push_service import _feedback_meta_name_for_template

    for tpl in db.execute(select(FeedbackWaTemplate)).scalars().all():
        try:
            meta_name = str(_feedback_meta_name_for_template(db, tpl) or "").strip().lower()
        except Exception:
            continue
        if meta_name == clean:
            return tpl
    return None


def discover_remote_marketing_templates(
    db: Session,
    *,
    name_contains: str | None = None,
    industry_slug: str | None = None,
    profile_ids: list[str] | None = None,
    service_code: str = "survey",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Match admin matrix: live MARKETING templates on Meta/Telnyx for all managed products."""
    from app.models.industry import Industry
    from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
    from app.services.wa_template_product_scope import is_managed_product_remote_name, is_protected_template_name
    from app.services.wa_template_profile_push_service import WaTemplateProfilePushService
    from app.services.wa_template_sync_profile import summarize_for_connection_profile
    from app.services.wa_template_sync_service import WaTemplateSyncService

    primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code=service_code)
    backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code=service_code)
    pids = [str(pid).strip() for pid in (profile_ids or []) if str(pid or "").strip()]
    if not pids:
        pids = [pid for pid in (primary_id, backup_id) if pid]

    profile_summaries: list[dict[str, Any]] = []
    marketing_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for pid in pids:
        summary = summarize_for_connection_profile(db, pid, service_code=service_code)
        profile_summaries.append(summary)
        if not summary.get("ok"):
            continue
        remote_all = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
            db,
            connection_profile_id=pid,
            service_code=service_code,
            allow_account_waba_fallback=False,
        )
        provider = str(summary.get("provider") or "unknown").strip().lower()
        for item in remote_all:
            if not isinstance(item, dict) or not _remote_item_is_marketing(item):
                continue
            remote_name = str(item.get("name") or "").strip().lower()
            if not remote_name or is_protected_template_name(remote_name):
                continue
            if not is_managed_product_remote_name(remote_name):
                continue
            if name_contains and name_contains.strip().lower() not in remote_name:
                continue
            lang = str(item.get("language") or item.get("language_code") or "en_gb").strip().lower()
            key = (remote_name, lang)
            entry = marketing_by_key.setdefault(
                key,
                {
                    "remote_name": remote_name,
                    "remote_language": lang,
                    "remote_status": str(item.get("status") or "").upper() or None,
                    "remote_profiles": [],
                    "reasons": [],
                    "product": _resolve_product_for_remote_name(remote_name),
                },
            )
            entry["remote_profiles"].append(
                {
                    "profile_id": pid,
                    "provider": provider,
                    "status": str(item.get("status") or "").upper() or None,
                    "label": summary.get("profile_label"),
                }
            )
            reason = f"remote_marketing_{provider}"
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)

    local_rows = WaTemplateSyncService.collect_survey_mirror_templates(db)
    candidates: list[dict[str, Any]] = []
    needle = name_contains.strip().lower() if name_contains else ""

    for (_remote_name, _lang), entry in sorted(marketing_by_key.items()):
        product = str(entry.get("product") or "orphan")
        remote_name = entry["remote_name"]
        row = None
        feedback_row = None
        st: SurveyType | None = None
        ind: Any = None
        body = ""

        if product == "survey":
            row = WaTemplateSyncService._find_local_row_for_meta_live_name(
                local_rows, remote_name, entry["remote_language"]
            )
            if row is not None and row.survey_type_id:
                st = db.get(SurveyType, row.survey_type_id)
                if st is not None and st.industry_id:
                    ind = db.get(Industry, st.industry_id)
            if industry_slug and str(getattr(ind, "slug", None) or "").lower() != str(industry_slug).strip().lower():
                continue
            if row is not None:
                body = _template_body_text(row)
        elif product == "feedback":
            feedback_row = _find_feedback_row_for_remote_name(db, remote_name)
            if feedback_row is not None:
                body = str(feedback_row.body_text or "").strip()
                if feedback_row.industry_id:
                    from app.models.customer_feedback import FeedbackIndustry

                    find = db.get(FeedbackIndustry, feedback_row.industry_id)
                    if industry_slug and str(getattr(find, "slug", None) or "").lower() != str(industry_slug).strip().lower():
                        continue

        if needle:
            matched = needle in remote_name
            if row is not None and needle in str(row.name or "").lower():
                matched = True
            if feedback_row is not None and needle in str(feedback_row.template_key or "").lower():
                matched = True
            if not matched:
                continue

        reasons = list(entry["reasons"])
        actionable = row is not None or feedback_row is not None

        if not actionable:
            candidates.append(
                {
                    "id": None,
                    "name": remote_name,
                    "process_name": None,
                    "actionable": False,
                    "status": entry.get("remote_status"),
                    "category": "MARKETING",
                    "product": product,
                    "local_category": None,
                    "industry_slug": None,
                    "survey_type": None,
                    "body_preview": "",
                    "remote_name": remote_name,
                    "remote_profiles": entry["remote_profiles"],
                    "reasons": reasons + ["no_local_row"],
                }
            )
            continue

        if row is not None:
            local_category = str(row.category or "").upper()
            if local_category == "UTILITY":
                reasons.append("local_category_utility_desync")
            candidates.append(
                _serialize_local_candidate(
                    row,
                    st=st,
                    ind=ind,
                    body=body,
                    reasons=reasons,
                    extra={
                        "remote_name": remote_name,
                        "remote_profiles": entry["remote_profiles"],
                        "local_category": row.category,
                        "product": "survey",
                    },
                )
            )
        elif feedback_row is not None:
            local_category = str(feedback_row.meta_category or "").upper()
            if local_category == "UTILITY":
                reasons.append("local_category_utility_desync")
            candidates.append(
                {
                    "id": str(feedback_row.id),
                    "name": remote_name,
                    "process_name": remote_name,
                    "actionable": True,
                    "status": str(feedback_row.telnyx_sync_status or ""),
                    "category": str(feedback_row.meta_category or "MARKETING").upper(),
                    "product": "feedback",
                    "local_category": feedback_row.meta_category,
                    "industry_slug": None,
                    "survey_type": str(feedback_row.template_key or ""),
                    "body_preview": body[:160],
                    "reasons": reasons,
                    "remote_name": remote_name,
                    "remote_profiles": entry["remote_profiles"],
                    "feedback_template_id": str(feedback_row.id),
                    "template_key": str(feedback_row.template_key or ""),
                    "language": str(feedback_row.language or ""),
                }
            )

    meta_marketing = telnyx_marketing = 0
    by_product: dict[str, int] = {"survey": 0, "feedback": 0, "orphan": 0}
    for summary in profile_summaries:
        if not summary.get("ok"):
            continue
        count = int((summary.get("summary") or {}).get("marketing") or 0)
        provider = str(summary.get("provider") or "").strip().lower()
        if provider == "meta":
            meta_marketing = count
        elif provider == "telnyx":
            telnyx_marketing = count
    for item in candidates:
        prod = str(item.get("product") or "orphan")
        by_product[prod] = by_product.get(prod, 0) + 1

    overview = {
        "profiles": profile_summaries,
        "remote_marketing_meta": meta_marketing,
        "remote_marketing_telnyx": telnyx_marketing,
        "unique_remote_marketing": len(marketing_by_key),
        "actionable_local_matches": sum(1 for item in candidates if item.get("actionable")),
        "missing_local_row": sum(1 for item in candidates if not item.get("actionable")),
        "by_product": by_product,
    }
    return overview, candidates


def discover_was_utility_rewrite_candidates(
    db: Session,
    *,
    name_contains: str | None = None,
    industry_slug: str | None = None,
    include_already_utility: bool = False,
    source: str = "remote",
) -> list[dict[str, Any]]:
    """Find survey templates that need UTILITY-compliant BODY rewrites.

    ``source=remote`` (default) lists live MARKETING rows on Meta/Telnyx — matches admin matrix.
    ``source=local`` uses DB-only heuristics (often far fewer rows when Meta reclassified).
    """
    mode = str(source or "remote").strip().lower()
    if mode == "local":
        return discover_was_utility_rewrite_candidates_local(
            db,
            name_contains=name_contains,
            industry_slug=industry_slug,
            include_already_utility=include_already_utility,
        )
    _overview, candidates = discover_remote_marketing_survey_templates(
        db,
        name_contains=name_contains,
        industry_slug=industry_slug,
    )
    return [item for item in candidates if item.get("actionable")]


def _needs_utility_clone_for_category_change(row: TelnyxWhatsappTemplate) -> bool:
    """Meta never allows category changes on APPROVED/PENDING templates with a live remote id.

    Local row.category may already be UTILITY from a prior failed push attempt while
    Telnyx/Meta still has the original MARKETING-approved template linked — bump seq
    (was_*) or clone (*_utu_*) when a real remote id is still attached.
    """
    if is_utility_clone_template_name(row.name):
        return False
    status = str(row.status or "").upper()
    return status in {"APPROVED", "PENDING"} and _has_remote_telnyx_id(row)


def _prepare_approved_template_for_utility_push(
    db: Session,
    row: TelnyxWhatsappTemplate,
) -> tuple[TelnyxWhatsappTemplate, str | None]:
    if not _needs_utility_clone_for_category_change(row):
        return row, None
    from seed_data.wa_survey_template_naming import is_was_survey_name, suggest_next_was_seq_name

    used_names = {
        str(r[0]).strip().lower()
        for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
        if r[0]
    }
    clone_name: str | None = None
    if is_was_survey_name(row.name):
        clone_name = suggest_next_was_seq_name(row.name, used_names=used_names)
    if not clone_name:
        clone_name = suggest_utility_clone_template_name(row.name)
    clash = db.execute(
        select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == clone_name)
    ).scalar_one_or_none()
    if clash is not None and clash.id != row.id:
        raise SurveyWhatsappTemplateError(
            f"Utility clone name already exists: {clone_name}",
            payload={"template_name": row.name, "suggested_template_name": clone_name},
        )
    logger.info(
        "utility_rewrite_clone_rename",
        extra={
            "template_id": row.id,
            "from_name": row.name,
            "to_name": clone_name,
            "status": str(row.status or "").upper(),
            "local_category": row.category,
        },
    )
    renamed = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, clone_name)
    return renamed, clone_name


def refresh_row_from_telnyx(db: Session, row: TelnyxWhatsappTemplate) -> None:
    record_id = str(row.telnyx_record_id or "").strip()
    if record_id:
        SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
        db.refresh(row)
        return
    linked = TelnyxWhatsappTemplateSyncService.find_remote_template(
        db,
        names=[str(row.name or "")],
        language=str(row.language or "en_GB"),
    )
    if linked is None:
        raise SurveyWhatsappTemplateError(f"Template not found on Telnyx: {row.name}")
    from app.services.survey_whatsapp_template_service import _apply_remote_telnyx_item

    _apply_remote_telnyx_item(db, row, linked, overwrite_draft=False)
    db.add(row)
    db.commit()
    db.refresh(row)


def process_template_names(
    db: Session,
    names: list[str],
    *,
    sync_remote: bool = False,
    save: bool = False,
    push: bool = False,
    dry_run: bool = False,
    use_llm: bool = True,
    llm_provider: str = "openai",
    skip_already_pushed: bool = True,
    push_delay_seconds: float = 0.0,
) -> list[UtilityRewriteResult]:
    import sys
    import time

    total = len([n for n in names if str(n or "").strip()])
    results: list[UtilityRewriteResult] = []
    index = 0
    for name in names:
        clean = str(name or "").strip()
        if not clean:
            continue
        index += 1
        migration_progress(f"[{index}/{total}] {clean} …")
        row = _find_template_row(db, clean)
        if row is None:
            results.append(
                UtilityRewriteResult(
                    template_name=clean,
                    ok=False,
                    old_body="",
                    new_body="",
                    message="Not found in database — run admin sync or seed first",
                )
            )
            continue
        try:
            if (
                push
                and save
                and not dry_run
                and skip_already_pushed
                and _already_submitted_utility_migration(row)
            ):
                components = _effective_components(row)
                old_body, _buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])
                results.append(
                    UtilityRewriteResult(
                        template_name=row.name,
                        ok=True,
                        old_body=old_body,
                        new_body=old_body,
                        message="already on Meta (skipped)",
                        pushed=True,
                    )
                )
                migration_progress("  -> OK skipped (already on Meta)")
                continue

            if sync_remote and _has_remote_telnyx_id(row):
                refresh_row_from_telnyx(db, row)
                db.refresh(row)

            components = _effective_components(row)
            old_body, buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])

            if dry_run:
                industry_slug, industry_name = _industry_for_template_row(db, row)
                topic_name = _topic_for_template_row(db, row)
                use_llm_local = use_llm
                if _body_has_recommend_intent(old_body):
                    use_llm_local = False
                new_body = rewrite_body_for_utility(
                    db,
                    original_body=old_body,
                    button_labels=buttons,
                    template_name=row.name,
                    display_name=row.display_name,
                    use_llm=use_llm_local,
                    llm_provider=llm_provider,
                    industry_slug=industry_slug,
                    industry_name=industry_name,
                    topic_name=topic_name,
                )
                dry_msg = "dry-run"
                if _needs_utility_clone_for_category_change(row):
                    from seed_data.wa_survey_template_naming import is_was_survey_name, suggest_next_was_seq_name

                    used_names = {
                        str(r[0]).strip().lower()
                        for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
                        if r[0]
                    }
                    next_name = None
                    if is_was_survey_name(row.name):
                        next_name = suggest_next_was_seq_name(row.name, used_names=used_names)
                    next_name = next_name or suggest_utility_clone_template_name(row.name)
                    dry_msg = (
                        f"dry-run — would rename to {next_name} "
                        "and push as new UTILITY template"
                    )
                results.append(
                    UtilityRewriteResult(
                        template_name=row.name,
                        ok=True,
                        old_body=old_body,
                        new_body=new_body,
                        message=dry_msg,
                    )
                )
                continue

            if not save and not push:
                results.append(
                    UtilityRewriteResult(
                        template_name=row.name,
                        ok=False,
                        old_body=old_body,
                        new_body="",
                        message="Specify --save or --push to persist rewrite",
                    )
                )
                continue

            renamed_to: str | None = None
            if push:
                row, renamed_to = _prepare_approved_template_for_utility_push(db, row)

            old_body, new_body = apply_utility_rewrite_to_row(
                db, row, use_llm=use_llm, llm_provider=llm_provider
            )
            pushed = False
            msg = "rewritten"
            if renamed_to:
                msg = f"renamed to {renamed_to}"
            if push:
                if push_delay_seconds > 0:
                    time.sleep(push_delay_seconds)
                push_result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                pushed = True
                push_msg = str(push_result.get("sync_message") or push_result.get("message") or "pushed")
                msg = f"{msg}; {push_msg}" if renamed_to else push_msg
            results.append(
                UtilityRewriteResult(
                    template_name=row.name,
                    ok=True,
                    old_body=old_body,
                    new_body=new_body,
                    message=msg,
                    pushed=pushed,
                )
            )
            migration_progress(f"  -> OK {msg}")
        except SurveyWhatsappTemplateError as exc:
            msg = str(exc)
            payload = getattr(exc, "payload", None) or {}
            provider_error = str(payload.get("provider_error") or "").strip()
            if provider_error:
                msg = f"{msg} | provider: {provider_error[:400]}"
            print(f"FAIL {clean}: {msg}", file=sys.stderr, flush=True)
            migration_progress(f"  -> FAIL {msg[:200]}")
            results.append(
                UtilityRewriteResult(
                    template_name=clean,
                    ok=False,
                    old_body="",
                    new_body="",
                    message=msg,
                )
            )
        except Exception as exc:
            print(f"FAIL {clean}: {exc}", file=sys.stderr, flush=True)
            migration_progress(f"  -> FAIL {exc}")
            results.append(
                UtilityRewriteResult(
                    template_name=clean,
                    ok=False,
                    old_body="",
                    new_body="",
                    message=str(exc),
                )
            )
    return results
