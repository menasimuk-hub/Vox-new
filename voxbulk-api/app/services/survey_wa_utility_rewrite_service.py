"""Rewrite WA survey template BODY text for Meta UTILITY (Feedback Survey) compliance."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_wa_md_seed_service import _build_abc_choice_components, _sanitize_body
from app.services.survey_whatsapp_template_service import (
    META_BODY_HARD_MAX_CHARS,
    SYNC_LOCAL_CHANGES,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _dumps,
    _effective_components,
    _loads,
    _normalize_draft_components,
    _persist_normalized_draft,
    _refresh_local_sync_status,
    normalize_wa_template_category,
)
from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService

logger = logging.getLogger(__name__)

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
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
)

_META_UTILITY_GUIDANCE = """
Meta WhatsApp UTILITY — Feedback Survey rules (2025):
- Must collect feedback on a PREVIOUS order, transaction, or engagement with the business.
- Must be specific to the interaction (not a generic marketing survey).
- Must be NON-PROMOTIONAL: no offers, discounts, upsell, loyalty promos, or persuasive marketing tone.
- Keep the original leading emoji when present (one emoji at the start is fine for feedback tone).
- Do NOT use vague openers like "We'd love your feedback" without tying to a recent interaction.
- Use exactly ONE recent-interaction phrase; do not stack multiple (bad: "Following your recent visit, based on your recent purchase, …").
- Good pattern: "😊 Following your recent visit, how would you rate …?" or "After your recent service experience, …"
- Keep the same rating intent and answer options meaning; only rewrite the BODY question sentence(s).
- BODY must be plain text with NO {{1}} variables for these abc_choice templates.
- Max {max_chars} characters.
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
    return emoji, rest


def _prepend_leading_emoji(emoji: str, body: str) -> str:
    text = str(body or "").strip()
    if not emoji:
        return text
    if text.startswith(emoji):
        return text
    return f"{emoji} {text}".strip()


def _mentions_recent_interaction(text: str) -> bool:
    lower = str(text or "").lower()
    return any(phrase in lower for phrase in _UTILITY_CONTEXT_PHRASES)


def _rule_based_utility_body(
    original: str,
    *,
    topic_hint: str = "",
    leading_emoji: str = "",
) -> str:
    emoji, cleaned = _extract_leading_emoji(original)
    if leading_emoji:
        emoji = leading_emoji
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        cleaned = "your experience"
    if _mentions_recent_interaction(cleaned):
        return _prepend_leading_emoji(emoji, _sanitize_body(cleaned))
    topic = topic_hint.strip() or "your recent experience"
    if cleaned.endswith("?"):
        inner = cleaned[:-1].strip()
        rewritten = f"Following your recent visit, {inner.lower()}?"
    else:
        rewritten = f"Following your recent visit, how would you rate {topic}?"
    return _prepend_leading_emoji(emoji, _sanitize_body(rewritten))


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
    if base.startswith("voxbulk_survey_"):
        base = base[len("voxbulk_survey_") :]
    base = re.sub(r"_abc_[a-f0-9]{6}$", "", base)
    base = base.replace("_", " ")
    return base.strip() or "your recent experience"


def rewrite_body_for_utility(
    db: Session,
    *,
    original_body: str,
    button_labels: list[str],
    template_name: str,
    display_name: str | None = None,
    use_deepseek: bool = True,
) -> str:
    topic = _topic_from_template_name(template_name)
    label = display_name or template_name
    leading_emoji, _ = _extract_leading_emoji(original_body)
    if not use_deepseek:
        return _rule_based_utility_body(
            original_body,
            topic_hint=topic,
            leading_emoji=leading_emoji,
        )

    system_prompt = (
        "You rewrite WhatsApp message template BODY text so Meta approves them as UTILITY category "
        "(Feedback Survey sub-type). Return ONLY valid JSON: "
        '{"body":"rewritten question text","notes":"one line why this is utility-compliant"}'
        + _META_UTILITY_GUIDANCE
    )
    emoji_hint = (
        f"Keep this leading emoji at the start: {leading_emoji}"
        if leading_emoji
        else "No leading emoji in the original."
    )
    user_prompt = (
        f"Template: {label}\n"
        f"Survey topic hint: {topic}\n"
        f"Current BODY:\n{original_body}\n\n"
        f"{emoji_hint}\n"
        f"Quick-reply buttons (keep meaning aligned): {', '.join(button_labels) or 'n/a'}\n\n"
        "Rewrite BODY only."
    )
    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system_prompt,
            messages=[AgentMessage(role="user", content=user_prompt)],
            max_tokens=400,
            temperature=0.2,
            provider="deepseek",
        )
        parsed = _parse_rewrite_json(result.assistant_text)
        body = str((parsed or {}).get("body") or "").strip()
        body = _sanitize_body(body)
        if not body:
            raise ValueError("empty body from model")
        if not _mentions_recent_interaction(body):
            body = _rule_based_utility_body(
                body,
                topic_hint=topic,
                leading_emoji=leading_emoji,
            )
        else:
            body = _prepend_leading_emoji(leading_emoji, body)
        return body
    except Exception as exc:
        logger.warning("utility_rewrite_deepseek_fallback name=%s err=%s", template_name, str(exc)[:200])
        return _rule_based_utility_body(
            original_body,
            topic_hint=topic,
            leading_emoji=leading_emoji,
        )


def apply_utility_rewrite_to_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    use_deepseek: bool = True,
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

    new_body = rewrite_body_for_utility(
        db,
        original_body=old_body,
        button_labels=buttons,
        template_name=row.name,
        display_name=row.display_name,
        use_deepseek=use_deepseek,
    )
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

    _apply_remote_telnyx_item(row, linked, overwrite_draft=False)
    db.add(row)
    db.commit()
    db.refresh(row)


def process_template_names(
    db: Session,
    names: list[str],
    *,
    sync_remote: bool = False,
    push: bool = False,
    dry_run: bool = False,
    use_deepseek: bool = True,
) -> list[UtilityRewriteResult]:
    results: list[UtilityRewriteResult] = []
    for name in names:
        clean = str(name or "").strip()
        if not clean:
            continue
        row = db.execute(
            select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == clean)
        ).scalar_one_or_none()
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
            if sync_remote:
                refresh_row_from_telnyx(db, row)
                db.refresh(row)

            components = _effective_components(row)
            old_body, buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])

            if dry_run:
                new_body = rewrite_body_for_utility(
                    db,
                    original_body=old_body,
                    button_labels=buttons,
                    template_name=row.name,
                    display_name=row.display_name,
                    use_deepseek=use_deepseek,
                )
                results.append(
                    UtilityRewriteResult(
                        template_name=clean,
                        ok=True,
                        old_body=old_body,
                        new_body=new_body,
                        message="dry-run",
                    )
                )
                continue

            old_body, new_body = apply_utility_rewrite_to_row(db, row, use_deepseek=use_deepseek)
            pushed = False
            msg = "rewritten"
            if push:
                push_result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                pushed = True
                msg = str(push_result.get("sync_message") or push_result.get("message") or "pushed")
            results.append(
                UtilityRewriteResult(
                    template_name=clean,
                    ok=True,
                    old_body=old_body,
                    new_body=new_body,
                    message=msg,
                    pushed=pushed,
                )
            )
        except Exception as exc:
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
