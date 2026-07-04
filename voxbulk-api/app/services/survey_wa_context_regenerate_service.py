"""Regenerate existing WA Survey template drafts with context-aware OpenAI copy.

Updates rows in place only — never creates industries, topics, or template records.
Never pushes to Meta; caller must push explicitly after review.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.agents.base import AgentMessage
from app.services.providers.openai_service import OpenAIProviderService
from app.services.wa_migration_progress import migration_progress
from app.services.wa_template_utility_content import (
    NO_BUTTON_KINDS,
    build_utility_components,
    buttons_for_language,
    ensure_leading_emoji,
    extract_buttons_from_components,
    is_promo_wording,
    resolve_industry_frame,
)
from app.services.wa_template_utility_lint import lint_utility_template

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(__file__).resolve().parents[2] / "seed-data" / "wa-survey" / "migration-reports"

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E0-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)


def _loads(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _body_from_components(components: list[dict[str, Any]]) -> str:
    for comp in components:
        if str(comp.get("type") or "").upper() == "BODY":
            return str(comp.get("text") or "").strip()
    return ""


def _is_arabic(lang: str | None) -> bool:
    return str(lang or "").strip().lower().startswith("ar")


def _is_survey_product_row(row: TelnyxWhatsappTemplate) -> bool:
    name = str(row.name or "").lower()
    key = str(row.sales_template_key or "").lower()
    # Explicit product prefixes win (some rows have stale active_for_interview flags).
    if name.startswith("voxbulk_survey_"):
        return True
    if name.startswith("voxbulk_cf_") or name.startswith("voxbulk_sales_") or name.startswith("voxbulk_interview_"):
        return False
    if key.startswith("sales_") or key.startswith("interview_"):
        return False
    return bool(row.survey_type_id)


def _row_context(db: Session, row: TelnyxWhatsappTemplate) -> dict[str, Any]:
    topic_name = str(row.display_name or "").strip()
    system_kind = None
    industry_slug = None
    industry_name = None
    st = db.get(SurveyType, row.survey_type_id) if row.survey_type_id else None
    if st is not None:
        topic_name = str(st.name or topic_name).strip()
        system_kind = str(st.system_template_kind or "").strip().lower() or None
        if st.industry_id:
            ind = db.get(Industry, st.industry_id)
            if ind is not None:
                industry_slug = ind.slug
                industry_name = ind.name
    if not topic_name:
        topic_name = str(row.name or "survey").replace("voxbulk_survey_", "").replace("_", " ")
    step_role = str(row.step_role or "").strip().lower() or None
    if not system_kind:
        name_l = str(row.name or "").lower()
        for kind in ("welcome", "thank_you", "tell_us_more", "final_feedback"):
            if kind in name_l:
                system_kind = kind
                break
    return {
        "topic_name": topic_name,
        "system_kind": system_kind,
        "industry_slug": industry_slug,
        "industry_name": industry_name,
        "step_role": step_role,
        "language": str(row.language or "en_GB"),
    }


def _expected_buttons(ctx: dict[str, Any]) -> list[str]:
    kind = ctx.get("system_kind")
    return buttons_for_language(
        kind or ctx.get("topic_name"),
        name=str(ctx.get("topic_name") or ""),
        language=ctx.get("language"),
        system_kind=kind,
    )


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
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


def _openai_regenerate_copy(
    db: Session,
    *,
    ctx: dict[str, Any],
    old_body: str,
) -> tuple[str, list[str]]:
    frame = resolve_industry_frame(
        ctx.get("industry_slug"),
        ctx.get("industry_name"),
        language=ctx.get("language"),
    )
    kind = ctx.get("system_kind")
    ar = _is_arabic(ctx.get("language"))
    expected = _expected_buttons(ctx)

    if kind == "welcome":
        button_rule = (
            'Exactly one button: "ابدأ الاستبيان"' if ar else 'Exactly one button: "Start survey"'
        )
    elif kind in NO_BUTTON_KINDS:
        button_rule = "No buttons (empty array). User replies with free text or voice."
    else:
        button_rule = (
            f"Exactly these rating buttons (same order): {expected}"
            if expected
            else "Three rating buttons: Excellent, Good, Poor (or Arabic equivalents)."
        )

    lang_rule = (
        "Write fully in Arabic. No English topic words."
        if ar
        else "Write in clear British English."
    )

    system_prompt = (
        "You write WhatsApp UTILITY survey template copy. Return ONLY valid JSON:\n"
        '{"body":"emoji + one question","buttons":["label",...]}\n'
        "Rules:\n"
        "- Utility only: no sale, discount, offer, gift, reward, promotion, loyalty, marketing, upsell.\n"
        "- Body must match the survey topic and industry context exactly.\n"
        f"- Industry frame key={frame['key']}: use context “{frame['context']}”. "
        "Employee/workplace surveys must NEVER say visit/visitor/customer visit.\n"
        "- Start body with exactly one relevant emoji.\n"
        f"- {button_rule}\n"
        f"- {lang_rule}\n"
        "- Max 1024 characters for body. Button labels max 25 characters.\n"
        "- No {{variables}} unless welcome needs {{1}} for first name (prefer no variables).\n"
    )
    user_prompt = (
        f"Industry: {ctx.get('industry_name') or ctx.get('industry_slug') or 'n/a'}\n"
        f"Topic / survey type: {ctx.get('topic_name')}\n"
        f"System kind: {kind or 'topic_rating'}\n"
        f"Step role: {ctx.get('step_role') or 'n/a'}\n"
        f"Language: {ctx.get('language')}\n"
        f"Current body (replace):\n{old_body or '(empty)'}\n"
        "Write a high-quality replacement body and buttons."
    )
    result = OpenAIProviderService.complete(
        db,
        system_prompt=system_prompt,
        messages=[AgentMessage(role="user", content=user_prompt)],
        max_tokens=500,
        temperature=0.35,
        provider="openai",
    )
    parsed = _parse_llm_json(result.assistant_text) or {}
    body = str(parsed.get("body") or "").strip()
    buttons_raw = parsed.get("buttons")
    buttons: list[str] = []
    if isinstance(buttons_raw, list):
        for item in buttons_raw:
            if isinstance(item, str) and item.strip():
                buttons.append(item.strip()[:25])
            elif isinstance(item, dict):
                label = str(item.get("text") or item.get("title") or "").strip()
                if label:
                    buttons.append(label[:25])

    # Enforce button rules regardless of model drift.
    if kind == "welcome":
        buttons = list(expected)
    elif kind in NO_BUTTON_KINDS:
        buttons = []
    elif expected:
        buttons = list(expected)

    body = ensure_leading_emoji(
        body,
        industry_slug=ctx.get("industry_slug"),
        industry_name=ctx.get("industry_name"),
        language=ctx.get("language"),
    )
    if frame["key"] == "employee" and "visit" in body.lower():
        raise ValueError("model returned visit language for employee survey")
    if is_promo_wording(body) or any(is_promo_wording(b) for b in buttons):
        raise ValueError("promo wording in generated copy")
    return body, buttons


def list_survey_template_rows(
    db: Session,
    *,
    industry_slug: str | None = None,
    offset: int = 0,
    limit: int | None = None,
) -> list[TelnyxWhatsappTemplate]:
    q = select(TelnyxWhatsappTemplate).where(
        or_(
            TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
            TelnyxWhatsappTemplate.survey_type_id.is_not(None),
        )
    ).order_by(TelnyxWhatsappTemplate.id.asc())
    rows = [r for r in db.execute(q).scalars().all() if _is_survey_product_row(r)]
    if industry_slug:
        slug = str(industry_slug).strip().lower()
        filtered: list[TelnyxWhatsappTemplate] = []
        for row in rows:
            ctx = _row_context(db, row)
            if str(ctx.get("industry_slug") or "").lower() == slug:
                filtered.append(row)
            elif not ctx.get("industry_slug") and slug in str(row.name or "").lower():
                filtered.append(row)
        rows = filtered
    if offset:
        rows = rows[offset:]
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    return rows


def regenerate_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    save: bool = False,
    use_llm: bool = True,
) -> dict[str, Any]:
    """Regenerate one existing row in place. Never creates rows. Never pushes Meta."""
    ctx = _row_context(db, row)
    components = _loads(row.draft_components_json) or _loads(row.components_json)
    old_body = _body_from_components(components) or str(row.body_preview or "")
    old_buttons = extract_buttons_from_components(components)
    allow_empty = ctx.get("system_kind") in NO_BUTTON_KINDS

    try:
        if use_llm:
            body, buttons = _openai_regenerate_copy(db, ctx=ctx, old_body=old_body)
        else:
            from app.services.wa_template_utility_content import (
                utility_body_ar_for_topic,
                utility_body_for_topic,
            )

            if _is_arabic(ctx.get("language")):
                body = utility_body_ar_for_topic(
                    ctx.get("topic_name"),
                    industry_slug=ctx.get("industry_slug"),
                    industry_name=ctx.get("industry_name"),
                )
            else:
                body = utility_body_for_topic(
                    ctx.get("topic_name"),
                    industry_slug=ctx.get("industry_slug"),
                    industry_name=ctx.get("industry_name"),
                )
            buttons = _expected_buttons(ctx)

        new_components = build_utility_components(
            body=body,
            buttons=buttons,
            language=ctx.get("language"),
            industry_slug=ctx.get("industry_slug"),
            industry_name=ctx.get("industry_name"),
            allow_empty_buttons=allow_empty,
        )
        kind = ctx.get("system_kind")
        lint = lint_utility_template(
            body=_body_from_components(new_components),
            buttons=extract_buttons_from_components(new_components),
            language=ctx.get("language"),
            meta_category="utility",
            require_transaction_anchor=kind not in NO_BUTTON_KINDS and kind != "welcome",
            allow_variables=kind == "welcome",
        )
        if not lint.ok:
            detail = "; ".join(f"{i.code}: {i.message}" for i in lint.issues[:5])
            raise ValueError(f"utility lint failed: {detail}")

        entry = {
            "ok": True,
            "template_id": row.id,
            "name": row.name,
            "topic": ctx.get("topic_name"),
            "industry_slug": ctx.get("industry_slug"),
            "system_kind": ctx.get("system_kind"),
            "language": ctx.get("language"),
            "old_body": old_body,
            "new_body": _body_from_components(new_components),
            "old_buttons": old_buttons,
            "new_buttons": extract_buttons_from_components(new_components),
            "saved": False,
            "error": None,
        }
        if save:
            status = str(row.status or "").upper()
            row.draft_components_json = _dumps(new_components)
            row.body_preview = entry["new_body"]
            row.category = "UTILITY"
            row.local_sync_status = (
                "needs_resubmit" if status in {"APPROVED", "PENDING", "REJECTED"} else "draft"
            )
            row.updated_at = datetime.utcnow()
            db.add(row)
            entry["saved"] = True
        return entry
    except Exception as exc:
        logger.warning(
            "survey_context_regen_failed id=%s name=%s err=%s",
            row.id,
            row.name,
            str(exc)[:200],
        )
        return {
            "ok": False,
            "template_id": row.id,
            "name": row.name,
            "topic": ctx.get("topic_name"),
            "industry_slug": ctx.get("industry_slug"),
            "system_kind": ctx.get("system_kind"),
            "language": ctx.get("language"),
            "old_body": old_body,
            "new_body": None,
            "old_buttons": old_buttons,
            "new_buttons": None,
            "saved": False,
            "error": str(exc)[:300],
        }


def regenerate_batch(
    db: Session,
    *,
    industry_slug: str | None = None,
    offset: int = 0,
    limit: int = 20,
    save: bool = False,
    use_llm: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    rows = list_survey_template_rows(
        db, industry_slug=industry_slug, offset=offset, limit=limit
    )
    total = len(rows)
    results: list[dict[str, Any]] = []
    migration_progress(
        f"Regenerate survey templates offset={offset} limit={limit} "
        f"industry={industry_slug or 'all'} save={save and not dry_run} count={total}"
    )
    for index, row in enumerate(rows, start=1):
        migration_progress(f"[{index}/{total}] id={row.id} {row.name} …")
        entry = regenerate_row(
            db,
            row,
            save=bool(save and not dry_run),
            use_llm=use_llm,
        )
        results.append(entry)
        if entry.get("ok"):
            migration_progress(f"  -> OK {entry.get('new_body', '')[:80]}")
        else:
            migration_progress(f"  -> FAIL {entry.get('error')}")

    if save and not dry_run:
        db.commit()

    ok_count = sum(1 for r in results if r.get("ok"))
    report = {
        "ok": True,
        "offset": offset,
        "limit": limit,
        "industry_slug": industry_slug,
        "save": bool(save and not dry_run),
        "dry_run": dry_run,
        "scanned": total,
        "succeeded": ok_count,
        "failed": total - ok_count,
        "items": results,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    slug = (industry_slug or "all").replace("/", "_")
    path = REPORTS_DIR / f"regen-{slug}-{stamp}-o{offset}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(path)
    migration_progress(f"Report written: {path}")
    return report


def push_template_ids(db: Session, template_ids: list[int]) -> dict[str, Any]:
    """Push existing regenerated templates to Meta. Explicit approval step only."""
    from app.services.survey_whatsapp_template_service import (
        SurveyWhatsappTemplateError,
        SurveyWhatsappTemplateService,
    )

    pushed = 0
    failed: list[dict[str, Any]] = []
    for tid in template_ids:
        row = db.get(TelnyxWhatsappTemplate, int(tid))
        if row is None:
            failed.append({"template_id": tid, "error": "not found"})
            continue
        try:
            SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=True)
            pushed += 1
            migration_progress(f"Pushed {tid} {row.name}")
        except SurveyWhatsappTemplateError as exc:
            failed.append({"template_id": tid, "error": str(exc)[:200]})
            migration_progress(f"Push FAIL {tid}: {exc}")
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            failed.append({"template_id": tid, "error": str(exc)[:200]})
            migration_progress(f"Push FAIL {tid}: {exc}")
    return {"ok": True, "pushed": pushed, "failed": failed}
