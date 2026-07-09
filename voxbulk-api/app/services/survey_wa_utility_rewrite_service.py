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

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)

_RECOMMEND_INTENT_RE = re.compile(
    r"\bwould you recommend\b|\bhow likely are you\b.*\brecommend\b|\blikely are you to recommend\b|"
    r"\brecommend us\b|\brecommend us to\b|\breturn intent\b|\breferral likelihood\b|\brenewal intent\b|"
    r"\bnet promoter\b|\bnps\b",
    re.IGNORECASE,
)

_WAS_TOPIC_SUFFIX_RE = re.compile(r"^was_(?:system_)?(.+)_(\d{3})_(en|ar)$", re.I)

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
)

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
    industry_slug: str | None = None,
    industry_name: str | None = None,
) -> str:
    from app.services.wa_template_utility_content import resolve_industry_frame, utility_body_for_topic

    emoji, cleaned = _extract_leading_emoji(original)
    if leading_emoji:
        emoji = leading_emoji
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    frame = resolve_industry_frame(industry_slug, industry_name, language="en")
    if not cleaned:
        cleaned = frame["experience"]
    # Never force visit language onto employee surveys.
    if frame["key"] == "employee" and "visit" in cleaned.lower():
        topic = topic_hint.strip() or frame["fallback_topic"]
        return _prepend_leading_emoji(
            emoji,
            _sanitize_body(f"How would you rate {topic} at work? Reply with one option below."),
        )
    if (
        _mentions_recent_interaction(cleaned)
        and not (frame["key"] == "employee" and "visit" in cleaned.lower())
        and not _body_has_recommend_intent(cleaned)
    ):
        return _prepend_leading_emoji(emoji, _sanitize_body(cleaned))
    topic = topic_hint.strip() or frame["fallback_topic"]
    return _prepend_leading_emoji(
        emoji,
        _sanitize_body(
            utility_body_for_topic(
                topic,
                emoji="",
                industry_slug=industry_slug,
                industry_name=industry_name,
            ).lstrip()
        ),
    )


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
        parts = [p for p in middle.split("_") if p]
        if parts and parts[0] == "employee" and len(parts) > 1:
            return " ".join(parts[1:])
        if len(parts) >= 2:
            return " ".join(parts[-2:])
        return middle.replace("_", " ").strip() or "your recent experience"
    if base.startswith("voxbulk_survey_"):
        base = base[len("voxbulk_survey_") :]
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


def rewrite_body_for_utility(
    db: Session,
    *,
    original_body: str,
    button_labels: list[str],
    template_name: str,
    display_name: str | None = None,
    use_llm: bool = True,
    llm_provider: str = "openai",
    industry_slug: str | None = None,
    industry_name: str | None = None,
    topic_name: str | None = None,
) -> str:
    from app.services.wa_template_utility_content import resolve_industry_frame

    topic = (topic_name or _topic_from_template_name(template_name)).strip()
    label = display_name or template_name
    frame = resolve_industry_frame(industry_slug, industry_name, language="en")
    leading_emoji, _ = _extract_leading_emoji(original_body)
    if not use_llm:
        return _rule_based_utility_body(
            original_body,
            topic_hint=topic,
            leading_emoji=leading_emoji,
            industry_slug=industry_slug,
            industry_name=industry_name,
        )

    system_prompt = (
        "You rewrite WhatsApp message template BODY text so Meta approves them as UTILITY category "
        "(Feedback Survey sub-type). Return ONLY valid JSON: "
        '{"body":"rewritten question text","notes":"one line why this is utility-compliant"}'
        + _META_UTILITY_GUIDANCE
        + "\nAvoid ALL marketing signals: sale, discount, offer, gift, reward, promotion, new, "
        "loyalty, refer-a-friend, return intent, upsell, vague brand surveys."
    )
    emoji_hint = (
        f"Keep this leading emoji at the start: {leading_emoji}"
        if leading_emoji
        else "No leading emoji in the original."
    )
    user_prompt = (
        f"Industry: {industry_name or industry_slug or 'n/a'} (frame={frame['key']})\n"
        f"Template: {label}\n"
        f"Survey topic: {topic}\n"
        f"Context phrase to use: {frame['context']}\n"
        f"Current BODY:\n{original_body}\n\n"
        f"{emoji_hint}\n"
        f"Quick-reply buttons (keep meaning aligned): {', '.join(button_labels) or 'n/a'}\n\n"
        "Rewrite BODY only. Match the industry frame exactly."
    )
    try:
        result = OpenAIProviderService.complete(
            db,
            system_prompt=system_prompt,
            messages=[AgentMessage(role="user", content=user_prompt)],
            max_tokens=400,
            temperature=0.2,
            provider=str(llm_provider or "openai").strip().lower(),
        )
        parsed = _parse_rewrite_json(result.assistant_text)
        body = str((parsed or {}).get("body") or "").strip()
        body = _sanitize_body(body)
        if not body:
            raise ValueError("empty body from model")
        if frame["key"] == "employee" and "visit" in body.lower():
            body = _rule_based_utility_body(
                body,
                topic_hint=topic,
                leading_emoji=leading_emoji,
                industry_slug=industry_slug,
                industry_name=industry_name,
            )
        elif not _mentions_recent_interaction(body):
            body = _rule_based_utility_body(
                body,
                topic_hint=topic,
                leading_emoji=leading_emoji,
                industry_slug=industry_slug,
                industry_name=industry_name,
            )
        else:
            body = _prepend_leading_emoji(leading_emoji, body)
        return body
    except Exception as exc:
        logger.warning("utility_rewrite_llm_fallback name=%s err=%s", template_name, str(exc)[:200])
        return _rule_based_utility_body(
            original_body,
            topic_hint=topic,
            leading_emoji=leading_emoji,
            industry_slug=industry_slug,
            industry_name=industry_name,
        )


def apply_utility_rewrite_to_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    use_llm: bool = True,
    llm_provider: str = "openai",
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
    if _body_has_recommend_intent(old_body):
        use_llm = False

    new_body = rewrite_body_for_utility(
        db,
        original_body=old_body,
        button_labels=buttons,
        template_name=row.name,
        display_name=row.display_name,
        use_llm=use_llm,
        llm_provider=llm_provider,
        industry_slug=industry_slug,
        industry_name=industry_name,
        topic_name=topic_name,
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


def discover_was_utility_rewrite_candidates(
    db: Session,
    *,
    name_contains: str | None = None,
    industry_slug: str | None = None,
    include_already_utility: bool = False,
) -> list[dict[str, Any]]:
    """Find was_* templates that need UTILITY-compliant BODY rewrites."""
    from app.models.industry import Industry

    query = (
        select(TelnyxWhatsappTemplate, SurveyType, Industry)
        .outerjoin(SurveyType, SurveyType.id == TelnyxWhatsappTemplate.survey_type_id)
        .outerjoin(Industry, Industry.id == SurveyType.industry_id)
        .where(TelnyxWhatsappTemplate.name.like("was_%"))
        .order_by(TelnyxWhatsappTemplate.name.asc())
    )
    if name_contains:
        query = query.where(TelnyxWhatsappTemplate.name.ilike(f"%{name_contains.strip()}%"))
    if industry_slug:
        query = query.where(Industry.slug == str(industry_slug).strip().lower())

    out: list[dict[str, Any]] = []
    for row, st, ind in db.execute(query).all():
        if not include_already_utility and _already_submitted_utility_migration(row):
            continue
        body = _template_body_text(row)
        needs, reasons = _template_needs_utility_rewrite(row, body=body)
        if not needs:
            continue
        out.append(
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "category": row.category,
                "industry_slug": getattr(ind, "slug", None),
                "survey_type": getattr(st, "name", None),
                "body_preview": body[:160],
                "reasons": reasons,
            }
        )
    return out


def _needs_utility_clone_for_category_change(row: TelnyxWhatsappTemplate) -> bool:
    """Meta never allows category changes on APPROVED templates.

    Local row.category may already be UTILITY from a prior failed push attempt while
    Telnyx/Meta still has the original MARKETING-approved template linked — always
    clone to *_utu_* when a real remote id is still attached.
    """
    if is_utility_clone_template_name(row.name):
        return False
    return (
        str(row.status or "").upper() == "APPROVED"
        and _has_remote_telnyx_id(row)
    )


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
