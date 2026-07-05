"""Shared Markdown parser for WA Survey + Customer Feedback template imports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from app.services.survey_industry_seed_service import _service_slug
from app.services.survey_whatsapp_template_service import META_BODY_HARD_MAX_CHARS, META_BUTTON_LABEL_MAX_CHARS

MdFormat = Literal["multilang_feedback", "feedback_en", "survey_abc", "unknown"]

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)
_TOPIC_NUM_RE = re.compile(r"^(\d+)\.\s+(.+)$")
_LANG_HEADER_RE = re.compile(r"^(.+?)\s*\(([a-z]{2}(?:_[A-Z]{2})?)\)\s*$", re.IGNORECASE)
_FEEDBACK_ITEM_RE = re.compile(r"^\*\*(\d+)\s*[–-]\s*(.+?)\*\*$")
_OPTION_LINE_RE = re.compile(r"[A-Z]\)\s*")
_VAR_RE = re.compile(r"\{\{(\d+)\}\}")

# MD code → stored language for FeedbackWaTemplate / Meta
LANGUAGE_MAP: dict[str, str] = {
    "en": "en_GB",
    "zh": "zh_CN",
    "pt": "pt_PT",
    "no": "nb",
}

DEFAULT_EXPECTED_LANGS = frozenset(
    {
        "en_GB",
        "zh_CN",
        "hi",
        "es",
        "fr",
        "ar",
        "bn",
        "pt_PT",
        "ru",
        "ur",
        "de",
        "it",
        "nl",
        "pl",
        "ro",
        "el",
        "sv",
        "cs",
        "nb",
    }
)


@dataclass
class MdLangVariant:
    language_code: str
    language_label: str
    body: str
    buttons: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass
class MdTopic:
    index: int
    name: str
    variants: list[MdLangVariant] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ParsedMdPack:
    format: MdFormat
    file_title: str | None = None
    topics: list[MdTopic] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_md_language(raw: str) -> str:
    code = str(raw or "").strip().lower().replace("-", "_")
    if code in LANGUAGE_MAP:
        return LANGUAGE_MAP[code]
    if code.startswith("en"):
        return "en_GB"
    return code


def topic_slug(name: str) -> str:
    return _service_slug(name)


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", str(text or "")).strip()


def sanitize_button_label(raw: str) -> str:
    label = re.sub(r"\s+", " ", strip_emoji(raw)).strip()
    if not label:
        label = "Option"
    original_len = len(label)
    if len(label) > META_BUTTON_LABEL_MAX_CHARS:
        label = label[:META_BUTTON_LABEL_MAX_CHARS].rstrip()
    return label


def sanitize_body(raw: str) -> str:
    body = re.sub(r"\s+", " ", str(raw or "").strip())
    if len(body) > META_BODY_HARD_MAX_CHARS:
        body = body[: META_BODY_HARD_MAX_CHARS - 1].rstrip() + "…"
    return body


def extract_body_variables(body: str) -> list[str]:
    nums = sorted({int(m.group(1)) for m in _VAR_RE.finditer(str(body or ""))})
    if not nums:
        return []
    return [f"Sample {n}" for n in nums]


def infer_step_role(buttons: list[str]) -> str:
    joined = " ".join(buttons).lower()
    if any(word in joined for word in ("yes", "no", "maybe", "definitely", "unlikely", "会", "不会", "نعم", "لا")):
        return "yes_no"
    if any(word in joined for word in ("excellent", "good", "poor", "rating", "bad")):
        return "rating"
    return "abc_choice"


def parse_buttons_line(line: str) -> list[str]:
    text = str(line or "").strip()
    if not text:
        return []
    if _OPTION_LINE_RE.search(text):
        parts = _OPTION_LINE_RE.split(text)
        return [sanitize_button_label(p) for p in parts if p.strip()]
    if "/" in text:
        return [sanitize_button_label(p) for p in text.split("/") if p.strip()]
    if "|" in text:
        return [sanitize_button_label(p) for p in text.split("|") if p.strip()]
    return []


def _looks_like_options_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text:
        return False
    if "/" in text or "|" in text:
        return True
    return len(re.findall(r"[A-Z]\)", text)) >= 2


def _detect_format(text: str) -> MdFormat:
    raw = str(text or "")
    if re.search(r"^\d+\.\s+\S", raw, re.MULTILINE) and re.search(
        r"^.+\([a-z]{2}(?:_[A-Z]{2})?\)\s*$", raw, re.MULTILINE | re.IGNORECASE
    ):
        return "multilang_feedback"
    if re.search(r"^\*\*\d+\s*[–-]", raw, re.MULTILINE) and re.search(r"^Body:", raw, re.MULTILINE | re.IGNORECASE):
        return "feedback_en"
    if any(_looks_like_options_line(line) for line in raw.splitlines() if line.strip()):
        return "survey_abc"
    return "unknown"


def parse_multilang_feedback(text: str, *, source_name: str = "") -> ParsedMdPack:
    pack = ParsedMdPack(format="multilang_feedback")
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = raw.splitlines()

    first_nonempty = next((ln.strip() for ln in lines if ln.strip()), "")
    if first_nonempty and not _TOPIC_NUM_RE.match(first_nonempty):
        pack.file_title = first_nonempty

    current_topic: MdTopic | None = None
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        topic_match = _TOPIC_NUM_RE.match(line)
        if topic_match:
            if current_topic is not None:
                pack.topics.append(current_topic)
            current_topic = MdTopic(
                index=int(topic_match.group(1)),
                name=topic_match.group(2).strip(),
            )
            continue

        if current_topic is None:
            continue

        lang_match = _LANG_HEADER_RE.match(line)
        if not lang_match:
            current_topic.errors.append(f"Expected language header after topic {current_topic.name!r}, got: {line[:60]}")
            continue

        lang_label = lang_match.group(1).strip()
        lang_code = normalize_md_language(lang_match.group(2))

        body_lines: list[str] = []
        while i < len(lines):
            candidate = lines[i].strip()
            if not candidate:
                i += 1
                if body_lines:
                    break
                continue
            if _TOPIC_NUM_RE.match(candidate) or _LANG_HEADER_RE.match(candidate):
                break
            if _looks_like_options_line(candidate):
                if not body_lines:
                    current_topic.errors.append(f"{current_topic.name} ({lang_code}): missing body before buttons")
                break
            body_lines.append(candidate)
            i += 1

        while i < len(lines) and not lines[i].strip():
            i += 1

        if i >= len(lines):
            current_topic.errors.append(f"{current_topic.name} ({lang_code}): missing buttons line")
            continue

        buttons_line = lines[i].strip()
        if not _looks_like_options_line(buttons_line):
            current_topic.errors.append(
                f"{current_topic.name} ({lang_code}): expected buttons line, got: {buttons_line[:60]}"
            )
            continue
        i += 1
        buttons = parse_buttons_line(buttons_line)
        body = sanitize_body("\n".join(body_lines) if len(body_lines) > 1 else (body_lines[0] if body_lines else ""))

        variant_warnings: list[str] = []
        if not body:
            current_topic.errors.append(f"{current_topic.name} ({lang_code}): empty body")
            continue
        if len(buttons) < 2:
            current_topic.errors.append(f"{current_topic.name} ({lang_code}): need at least 2 buttons, got {buttons!r}")
            continue
        if len(buttons) > 3:
            current_topic.errors.append(f"{current_topic.name} ({lang_code}): max 3 buttons, got {len(buttons)}")
            buttons = buttons[:3]
        for btn in buttons:
            raw_btn = btn
            if len(raw_btn) > META_BUTTON_LABEL_MAX_CHARS:
                variant_warnings.append(f"Button {raw_btn!r} truncated to 20 chars for Meta")

        if lang_code.startswith("en") and "visit" not in body.lower() and "order" not in body.lower() and "today" not in body.lower():
            variant_warnings.append("English body may fail Meta UTILITY lint (no recent visit/order anchor)")

        current_topic.variants.append(
            MdLangVariant(
                language_code=lang_code,
                language_label=lang_label,
                body=body,
                buttons=buttons,
                warnings=variant_warnings,
            )
        )

    if current_topic is not None:
        pack.topics.append(current_topic)

    if not pack.topics:
        label = source_name or "file"
        pack.parse_errors.append(f"No numbered topics found in {label}. Expected lines like '1. Overall Experience'.")

    for topic in pack.topics:
        langs = {v.language_code for v in topic.variants}
        if len(langs) < len(DEFAULT_EXPECTED_LANGS):
            missing = sorted(DEFAULT_EXPECTED_LANGS - langs)
            topic.warnings.append(f"Missing {len(missing)} language(s): {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}")

    return pack


def parse_md_pack(text: str, *, source_name: str = "", format_hint: MdFormat | None = None) -> ParsedMdPack:
    fmt = format_hint or _detect_format(text)
    if fmt == "multilang_feedback":
        return parse_multilang_feedback(text, source_name=source_name)
    pack = ParsedMdPack(format=fmt)
    pack.parse_errors.append(
        f"Format {fmt!r} is not fully implemented in shared parser yet. Use multilang_feedback for Customer Feedback."
    )
    return pack


def build_dry_run_plan(
    pack: ParsedMdPack,
    *,
    industry_name: str,
    industry_slug: str,
    existing_template_count: int = 0,
    existing_meta_name_count: int = 0,
    replace: bool = True,
    create_missing_topics: bool = True,
    existing_topic_slugs: set[str] | None = None,
    min_langs: int = 19,
) -> dict[str, Any]:
    """Human-readable plan of exactly what import would do."""
    existing_topic_slugs = existing_topic_slugs or set()
    topics_preview: list[dict[str, Any]] = []
    warnings: list[str] = list(pack.warnings)
    errors: list[str] = list(pack.parse_errors)

    templates_to_create = 0
    topics_to_create = 0
    topics_to_update = 0

    for topic in pack.topics:
        slug = topic_slug(topic.name)
        topic_errors = list(topic.errors)
        topic_warnings = list(topic.warnings)
        if topic_errors:
            errors.extend(topic_errors)

        if slug in existing_topic_slugs:
            topic_action = "update_existing"
            topics_to_update += 1
        elif create_missing_topics:
            topic_action = "create_new"
            topics_to_create += 1
        else:
            topic_action = "skip_missing"
            errors.append(f"Topic {topic.name!r} (slug {slug}) not found and create_missing=false")

        lang_count = len(topic.variants)
        templates_to_create += lang_count
        if lang_count < min_langs:
            topic_warnings.append(f"Only {lang_count} language(s); expected at least {min_langs}")

        en_variant = next((v for v in topic.variants if v.language_code.startswith("en")), topic.variants[0] if topic.variants else None)

        meta_name_preview = ""
        if industry_slug:
            try:
                from app.services.customer_feedback.feedback_telnyx_push_service import (
                    preview_feedback_meta_template_name,
                )

                meta_name_preview = preview_feedback_meta_template_name(
                    industry_slug=industry_slug,
                    survey_type_slug=slug,
                )
            except Exception:  # noqa: BLE001
                meta_name_preview = f"voxbulk_cf_{industry_slug}_{slug}_{slug}_xxxxxxxx"

        topics_preview.append(
            {
                "index": topic.index,
                "name": topic.name,
                "slug": slug,
                "meta_name_preview": meta_name_preview,
                "action": topic_action,
                "language_count": lang_count,
                "languages": [v.language_code for v in topic.variants],
                "english_body_preview": (en_variant.body[:120] + "…") if en_variant and len(en_variant.body) > 120 else (en_variant.body if en_variant else ""),
                "english_buttons": en_variant.buttons if en_variant else [],
                "step_role": infer_step_role(en_variant.buttons) if en_variant else None,
                "variants_preview": [
                    {
                        "language": v.language_code,
                        "language_label": v.language_label,
                        "body_preview": v.body[:80] + ("…" if len(v.body) > 80 else ""),
                        "buttons": v.buttons,
                        "warnings": v.warnings,
                    }
                    for v in topic.variants[:5]
                ],
                "more_language_count": max(0, lang_count - 5),
                "warnings": topic_warnings,
                "errors": topic_errors,
            }
        )
        warnings.extend(topic_warnings)
        for v in topic.variants:
            warnings.extend(v.warnings)

    plan_steps: list[str] = []
    if replace and existing_template_count:
        plan_steps.append(
            f"Delete {existing_template_count} existing WhatsApp template row(s) for industry “{industry_name}” (slug: {industry_slug})"
        )
        if existing_meta_name_count:
            plan_steps.append(
                f"Best-effort delete {existing_meta_name_count} Meta template name(s) linked to this industry before re-seed"
            )
    elif replace:
        plan_steps.append(f"No existing templates to delete for industry “{industry_name}”")

    if topics_to_create:
        plan_steps.append(f"Create {topics_to_create} new survey topic(s) under this industry")
    if topics_to_update:
        plan_steps.append(f"Match/update {topics_to_update} existing survey topic(s) by title slug")

    plan_steps.append(f"Insert or replace {templates_to_create} template row(s) ({len(pack.topics)} topics × languages)")
    plan_steps.append(
        "Set all new rows to telnyx_sync_status=draft — Meta sync is separate (Industry actions > Sync)"
    )
    if industry_slug:
        plan_steps.append(
            f"Meta template names use prefix voxbulk_cf_{industry_slug}_… (UTILITY category — Meta has no industry folders)"
        )
    plan_steps.append("System templates (thank you, tell us more, etc.) are NOT changed")

    ok = not errors and bool(pack.topics) and templates_to_create > 0

    return {
        "ok": ok,
        "dry_run": True,
        "format_detected": pack.format,
        "file_title": pack.file_title,
        "industry_name": industry_name,
        "industry_slug": industry_slug,
        "replace": replace,
        "create_missing_topics": create_missing_topics,
        "summary": {
            "topics_in_file": len(pack.topics),
            "topics_to_create": topics_to_create,
            "topics_to_update": topics_to_update,
            "language_versions_to_write": templates_to_create,
            "templates_to_delete": existing_template_count if replace else 0,
            "meta_names_to_delete": existing_meta_name_count if replace else 0,
            "expected_languages_per_topic": min_langs,
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "plan_steps": plan_steps,
        "topics": topics_preview,
        "warnings": warnings,
        "errors": errors,
        "message": (
            "Dry-run OK — safe to import."
            if ok
            else f"Dry-run found {len(errors)} error(s) — fix before import."
        ),
    }
