"""Multi-language consistency audit and selective UTILITY rewrites for marketing purge."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_wa_utility_rewrite_service import (
    DEFAULT_UTILITY_LLM_MODEL,
    DEFAULT_UTILITY_LLM_PROVIDER,
    _body_has_recommend_intent,
    parse_cfs_meta_name,
    rewrite_body_for_utility,
)
from app.services.wa_template_utility_lint import lint_utility_template

logger = logging.getLogger(__name__)

_WAS_GROUP_RE = re.compile(
    r"^was_(?:system_)?(.+?)_(\d{3})_([a-z]{2})(?:_[a-z0-9]{4,8})?$",
    re.I,
)
_CFS_GROUP_RE = re.compile(r"^cfs_([^_]+)_(.+)_([a-z]{2,3})_v(\d+)$", re.I)

_EN_LANGS = frozenset({"en", "en_gb", "en_us", "english"})


@dataclass
class LangVariant:
    local_template_id: int | str | None
    label: str
    remote_name: str
    language: str
    product: str
    body_before: str
    buttons: list[str]
    body_after: str = ""
    rewritten: bool = False
    skip_reason: str | None = None
    industry_slug: str | None = None
    industry_name: str | None = None
    topic_name: str | None = None
    template_key: str | None = None
    new_meta_name: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_template_id": self.local_template_id,
            "label": self.label,
            "remote_name": self.remote_name,
            "language": self.language,
            "product": self.product,
            "body_before": self.body_before,
            "body_after": self.body_after,
            "buttons": self.buttons,
            "rewritten": self.rewritten,
            "skip_reason": self.skip_reason,
            "new_meta_name": self.new_meta_name,
            "industry_slug": self.industry_slug,
            "topic_name": self.topic_name,
            "template_key": self.template_key,
            "meta": self.meta,
        }


@dataclass
class TemplateGroup:
    group_key: str
    product: str
    variants: list[LangVariant] = field(default_factory=list)
    anchor_lang: str | None = None
    aligned_langs: list[str] = field(default_factory=list)
    inconsistent_langs: list[str] = field(default_factory=list)
    audit_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_key": self.group_key,
            "product": self.product,
            "anchor_lang": self.anchor_lang,
            "aligned_langs": self.aligned_langs,
            "inconsistent_langs": self.inconsistent_langs,
            "audit_notes": self.audit_notes,
            "variants": [v.to_dict() for v in self.variants],
        }


def parse_group_key(remote_name: str, *, product: str) -> str:
    name = str(remote_name or "").strip().lower()
    if product == "feedback":
        match = _CFS_GROUP_RE.match(name)
        if match:
            ind, topic, _lang, ver = match.groups()
            return f"cfs_{ind}_{topic}_v{ver}"
        return name
    match = _WAS_GROUP_RE.match(name)
    if match:
        middle, seq, _lang = match.groups()
        return f"was_{middle}_{seq}"
    return name


def _norm_lang_token(lang: str | None) -> str:
    raw = str(lang or "en").strip().lower().replace("-", "_")
    if raw.startswith("en"):
        return "en"
    return raw.split("_", 1)[0] if raw else "en"


def _pick_anchor_variant(variants: list[LangVariant]) -> LangVariant:
    for preferred in ("en_gb", "en", "en_us"):
        for variant in variants:
            if _norm_lang_token(variant.language) == _norm_lang_token(preferred):
                return variant
    return variants[0]


def _parse_audit_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def audit_multilang_consistency(
    db: Session,
    group: TemplateGroup,
    *,
    llm_provider: str = DEFAULT_UTILITY_LLM_PROVIDER,
    llm_model: str | None = DEFAULT_UTILITY_LLM_MODEL,
) -> tuple[list[str], list[str], str]:
    """Return (aligned_langs, inconsistent_langs, notes)."""
    if len(group.variants) <= 1:
        only = _norm_lang_token(group.variants[0].language) if group.variants else "en"
        return [only], [], "single_language_group"

    anchor = _pick_anchor_variant(group.variants)
    anchor_lang = _norm_lang_token(anchor.language)
    lines: list[str] = []
    for variant in group.variants:
        lang = _norm_lang_token(variant.language)
        lines.append(
            f"[{lang}] buttons={', '.join(variant.buttons) or 'n/a'}\n{variant.body_before}"
        )
    system_prompt = (
        "You audit WhatsApp template translations for semantic consistency. "
        "Return ONLY valid JSON: "
        '{"anchor_lang":"en","aligned":["de","fr"],"inconsistent":["ar"],"notes":"brief reason"}'
        "\nMark a language inconsistent ONLY if its meaning diverges from the anchor "
        "(wrong topic, missing intent, extra marketing, mistranslation). "
        "Minor wording differences that preserve meaning count as aligned."
    )
    user_prompt = (
        f"Anchor language: {anchor_lang}\n"
        f"Template group: {group.group_key}\n"
        f"Product: {group.product}\n\n"
        + "\n\n".join(lines)
    )
    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system_prompt,
            messages=[AgentMessage(role="user", content=user_prompt)],
            max_tokens=300,
            temperature=0.1,
            provider=str(llm_provider or DEFAULT_UTILITY_LLM_PROVIDER).strip().lower(),
            model=str(llm_model or "").strip() or None,
        )
        parsed = _parse_audit_json(result.assistant_text) or {}
        aligned = [_norm_lang_token(x) for x in (parsed.get("aligned") or []) if str(x).strip()]
        inconsistent = [_norm_lang_token(x) for x in (parsed.get("inconsistent") or []) if str(x).strip()]
        notes = str(parsed.get("notes") or "").strip()
        if anchor_lang not in aligned and anchor_lang not in inconsistent:
            aligned.append(anchor_lang)
        return aligned, inconsistent, notes
    except Exception as exc:
        logger.warning("multilang_audit_fallback group=%s err=%s", group.group_key, str(exc)[:200])
        all_langs = [_norm_lang_token(v.language) for v in group.variants]
        return [anchor_lang], [lang for lang in all_langs if lang != anchor_lang], "audit_failed_rewrite_all"


def _lang_needs_rewrite(
    variant: LangVariant,
    *,
    aligned_langs: list[str],
    inconsistent_langs: list[str],
    anchor_body_after: str,
) -> tuple[bool, str | None]:
    lang = _norm_lang_token(variant.language)
    if _body_has_recommend_intent(variant.body_before):
        return True, "recommend_intent_rule_based"
    lint_before = lint_utility_template(
        body=variant.body_before,
        buttons=variant.buttons,
        language=variant.language,
        meta_category="utility",
        template_key=variant.template_key,
    )
    if lang in inconsistent_langs:
        return True, "meaning_inconsistent_with_anchor"
    if not lint_before.ok:
        return True, "utility_lint_failed"
    if lang in aligned_langs and variant.body_before.strip() == anchor_body_after.strip():
        return False, "aligned_and_unchanged"
    if lang in aligned_langs:
        lint_match = lint_utility_template(
            body=variant.body_before,
            buttons=variant.buttons,
            language=variant.language,
            meta_category="utility",
            template_key=variant.template_key,
        )
        if lint_match.ok:
            return False, "aligned_utility_compliant"
    return True, "anchor_rewrite_or_drift"


def rewrite_group_variants(
    db: Session,
    group: TemplateGroup,
    *,
    use_llm: bool = True,
    llm_provider: str = DEFAULT_UTILITY_LLM_PROVIDER,
    llm_model: str | None = DEFAULT_UTILITY_LLM_MODEL,
) -> TemplateGroup:
    aligned, inconsistent, notes = audit_multilang_consistency(
        db,
        group,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    group.aligned_langs = aligned
    group.inconsistent_langs = inconsistent
    group.audit_notes = notes
    anchor = _pick_anchor_variant(group.variants)
    group.anchor_lang = _norm_lang_token(anchor.language)

    anchor_needs, anchor_reason = _lang_needs_rewrite(
        anchor,
        aligned_langs=aligned,
        inconsistent_langs=inconsistent,
        anchor_body_after="",
    )
    if anchor_needs and use_llm:
        anchor.body_after = rewrite_body_for_utility(
            db,
            original_body=anchor.body_before,
            button_labels=anchor.buttons,
            template_name=anchor.label,
            display_name=anchor.topic_name or anchor.template_key,
            use_llm=True,
            llm_provider=llm_provider,
            llm_model=llm_model,
            industry_slug=anchor.industry_slug,
            industry_name=anchor.industry_name,
            topic_name=anchor.topic_name or anchor.template_key,
            language=anchor.language,
        )
        anchor.rewritten = anchor.body_after.strip() != anchor.body_before.strip()
        anchor.skip_reason = None if anchor.rewritten else anchor_reason
    elif anchor_needs:
        from app.services.survey_wa_utility_rewrite_service import _rule_based_utility_body

        anchor.body_after = _rule_based_utility_body(
            anchor.body_before,
            topic_hint=anchor.topic_name or anchor.template_key or "",
            industry_slug=anchor.industry_slug,
            industry_name=anchor.industry_name,
            language=anchor.language,
        )
        anchor.rewritten = anchor.body_after.strip() != anchor.body_before.strip()
        anchor.skip_reason = None if anchor.rewritten else anchor_reason
    else:
        anchor.body_after = anchor.body_before
        anchor.rewritten = False
        anchor.skip_reason = anchor_reason

    for variant in group.variants:
        if variant is anchor:
            continue
        needs, reason = _lang_needs_rewrite(
            variant,
            aligned_langs=aligned,
            inconsistent_langs=inconsistent,
            anchor_body_after=anchor.body_after,
        )
        if not needs:
            variant.body_after = variant.body_before
            variant.rewritten = False
            variant.skip_reason = reason
            continue
        if use_llm:
            variant.body_after = rewrite_body_for_utility(
                db,
                original_body=variant.body_before,
                button_labels=variant.buttons,
                template_name=variant.label,
                display_name=variant.topic_name or variant.template_key,
                use_llm=True,
                llm_provider=llm_provider,
                llm_model=llm_model,
                industry_slug=variant.industry_slug,
                industry_name=variant.industry_name,
                topic_name=variant.topic_name or variant.template_key,
                language=variant.language,
            )
        else:
            from app.services.survey_wa_utility_rewrite_service import _rule_based_utility_body

            variant.body_after = _rule_based_utility_body(
                variant.body_before,
                topic_hint=variant.topic_name or variant.template_key or "",
                industry_slug=variant.industry_slug,
                industry_name=variant.industry_name,
                language=variant.language,
            )
        variant.rewritten = variant.body_after.strip() != variant.body_before.strip()
        variant.skip_reason = None if variant.rewritten else reason
    return group


def build_groups_from_candidates(candidates: list[dict[str, Any]]) -> list[TemplateGroup]:
    """Cluster actionable purge candidates by topic group key."""
    buckets: dict[str, TemplateGroup] = {}
    for item in candidates:
        if not item.get("actionable"):
            continue
        product = str(item.get("product") or "survey")
        remote_name = str(item.get("remote_name") or item.get("name") or "")
        cfs_meta = parse_cfs_meta_name(remote_name) if product == "feedback" else None
        group_key = parse_group_key(remote_name, product=product)
        group = buckets.setdefault(
            group_key,
            TemplateGroup(group_key=group_key, product=product),
        )
        body = str(item.get("body_preview") or "")
        if len(body) >= 160 and item.get("full_body"):
            body = str(item.get("full_body") or body)
        lang = str(item.get("remote_language") or item.get("language") or "en_gb")
        if cfs_meta and cfs_meta.get("lang"):
            lang = f"{cfs_meta['lang']}_gb" if len(str(cfs_meta["lang"])) == 2 else str(cfs_meta["lang"])
        group.variants.append(
            LangVariant(
                local_template_id=item.get("id") or item.get("feedback_template_id"),
                label=str(item.get("name") or item.get("process_name") or remote_name),
                remote_name=remote_name,
                language=lang,
                product=product,
                body_before=body,
                buttons=list(item.get("buttons") or []),
                industry_slug=item.get("industry_slug") or (cfs_meta.get("industry") if cfs_meta else None),
                topic_name=(
                    item.get("survey_type")
                    or item.get("template_key")
                    or (cfs_meta.get("topic") if cfs_meta else None)
                ),
                template_key=item.get("template_key") or (cfs_meta.get("topic_key") if cfs_meta else None),
                meta={
                    "reasons": item.get("reasons"),
                    "remote_profiles": item.get("remote_profiles"),
                },
            )
        )
    return list(buckets.values())
