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
    if name.startswith("cfs_") or name.startswith("voxbulk_cf_") or name.startswith("voxbulk_sales_") or name.startswith("voxbulk_interview_"):
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


def _keeper_score(row: TelnyxWhatsappTemplate) -> tuple:
    """Higher is better — prefer standard name, regenerated draft, approved, newer."""
    name = str(row.name or "").lower()
    status = str(row.status or "").upper()
    sync = str(row.local_sync_status or "").lower()
    standard = 1 if "_standard" in name and "_abc_" not in name and "_utu_" not in name else 0
    not_pack = 0 if ("_abc_" in name or "_utu_" in name) else 1
    regenerated = 1 if sync in {"needs_resubmit", "draft", "local_changes"} else 0
    approved = 1 if status == "APPROVED" else 0
    updated = row.updated_at.timestamp() if row.updated_at else 0.0
    name_len = -len(name)
    return (standard, not_pack, regenerated, approved, updated, name_len, -int(row.id or 0))


def list_survey_template_rows(
    db: Session,
    *,
    industry_slug: str | None = None,
    offset: int = 0,
    limit: int | None = None,
    one_per_topic_lang: bool = True,
) -> list[TelnyxWhatsappTemplate]:
    system_type_ids = {
        str(st.id)
        for st in db.execute(
            select(SurveyType).where(SurveyType.system_template_kind.is_not(None))
        ).scalars().all()
    }
    q = select(TelnyxWhatsappTemplate).where(
        or_(
            TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
            TelnyxWhatsappTemplate.survey_type_id.is_not(None),
        )
    ).order_by(TelnyxWhatsappTemplate.id.asc())
    rows = [
        r
        for r in db.execute(q).scalars().all()
        if _is_survey_product_row(r) and str(r.survey_type_id or "") not in system_type_ids
    ]
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
    # Never regenerate pack duplicates — one keeper per topic + language.
    if one_per_topic_lang:
        best: dict[tuple[str, str], TelnyxWhatsappTemplate] = {}
        for row in rows:
            type_id = str(row.survey_type_id or f"name:{row.name}")
            lang = str(row.language or "en_GB")
            lang_key = (
                "ar"
                if lang.lower().startswith("ar")
                else "en"
                if lang.lower().startswith("en")
                else lang.lower()
            )
            key = (type_id, lang_key)
            current = best.get(key)
            if current is None or _keeper_score(row) > _keeper_score(current):
                best[key] = row
        rows = sorted(best.values(), key=lambda r: int(r.id or 0))
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
        frame = resolve_industry_frame(
            ctx.get("industry_slug"),
            ctx.get("industry_name"),
            language=ctx.get("language"),
        )
        # Employee/workplace and open-text system kinds do not use visit anchors.
        need_anchor = (
            kind not in NO_BUTTON_KINDS
            and kind != "welcome"
            and frame.get("key") != "employee"
        )
        lint = lint_utility_template(
            body=_body_from_components(new_components),
            buttons=extract_buttons_from_components(new_components),
            language=ctx.get("language"),
            meta_category="utility",
            require_transaction_anchor=need_anchor,
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


def dedupe_survey_templates(
    db: Session,
    *,
    dry_run: bool = True,
    delete_on_meta: bool = False,
) -> dict[str, Any]:
    """Keep one template per (survey_type_id, language). Delete extras.

    Does not create rows. Prefer ``*_standard`` over pack variants (``_abc_``, ``_utu_``).
    """
    from app.services.survey_type_template_service import SurveyTypeTemplateService
    from app.services.survey_whatsapp_template_service import SurveyWhatsappTemplateService

    # Never touch global system templates (named + anonymous welcome share one survey type).
    system_type_ids = {
        str(st.id)
        for st in db.execute(
            select(SurveyType).where(SurveyType.system_template_kind.is_not(None))
        ).scalars().all()
    }
    rows = [
        r
        for r in db.execute(
            select(TelnyxWhatsappTemplate).where(
                TelnyxWhatsappTemplate.name.ilike("voxbulk_survey_%"),
                TelnyxWhatsappTemplate.survey_type_id.is_not(None),
            )
        ).scalars().all()
        if _is_survey_product_row(r) and str(r.survey_type_id or "") not in system_type_ids
    ]
    groups: dict[tuple[str, str], list[TelnyxWhatsappTemplate]] = {}
    for row in rows:
        lang = str(row.language or "en_GB").strip() or "en_GB"
        # Normalize language family so en_GB and en_US do not both survive for one topic.
        lang_key = "ar" if lang.lower().startswith("ar") else "en" if lang.lower().startswith("en") else lang.lower()
        key = (str(row.survey_type_id), lang_key)
        groups.setdefault(key, []).append(row)

    kept: list[dict[str, Any]] = []
    deleted: list[dict[str, Any]] = []
    for (type_id, lang_key), group in groups.items():
        if len(group) <= 1:
            if group:
                kept.append(
                    {
                        "template_id": group[0].id,
                        "survey_type_id": type_id,
                        "language": lang_key,
                        "name": group[0].name,
                    }
                )
            continue
        ordered = sorted(group, key=_keeper_score, reverse=True)
        winner = ordered[0]
        kept.append(
            {
                "template_id": winner.id,
                "survey_type_id": type_id,
                "language": lang_key,
                "name": winner.name,
                "duplicates_removed": len(ordered) - 1,
            }
        )
        # Ensure winner is mapped as default for the survey type.
        if not dry_run:
            try:
                SurveyTypeTemplateService.upsert_mapping(
                    db,
                    survey_type_id=type_id,
                    template_id=int(winner.id),
                    usable_as_standard=True,
                    usable_as_anonymous=False,
                    is_default_standard=True,
                    is_default_anonymous=False,
                )
            except Exception as exc:
                migration_progress(f"  map keep {winner.id} warn: {exc}")
                try:
                    db.rollback()
                except Exception:
                    pass
        for loser in ordered[1:]:
            entry = {
                "template_id": loser.id,
                "name": loser.name,
                "survey_type_id": type_id,
                "language": loser.language,
                "kept_id": winner.id,
            }
            if dry_run:
                entry["action"] = "would_delete"
                deleted.append(entry)
                continue
            try:
                # Always remove local row. Meta delete is best-effort so a Meta
                # failure cannot leave pack duplicates in the hub.
                if delete_on_meta:
                    try:
                        SurveyWhatsappTemplateService.delete_template(db, loser)
                        entry["action"] = "deleted_local_and_meta"
                    except Exception as meta_exc:
                        entry["meta_error"] = str(meta_exc)[:200]
                        try:
                            db.rollback()
                        except Exception:
                            pass
                        # Row may still exist if Meta path failed before local delete.
                        loser2 = db.get(TelnyxWhatsappTemplate, int(loser.id))
                        if loser2 is not None:
                            SurveyWhatsappTemplateService.delete_template_local(db, loser2)
                        entry["action"] = "deleted_local_meta_failed"
                else:
                    SurveyWhatsappTemplateService.delete_template_local(db, loser)
                    entry["action"] = "deleted_local"
            except Exception as exc:
                entry["action"] = "failed"
                entry["error"] = str(exc)[:200]
                try:
                    db.rollback()
                except Exception:
                    pass
            deleted.append(entry)

    report = {
        "ok": True,
        "dry_run": dry_run,
        "delete_on_meta": delete_on_meta,
        "groups": len(groups),
        "kept": len(kept),
        "deleted_or_would_delete": len(deleted),
        "kept_rows": kept,
        "deleted_rows": deleted,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS_DIR / f"dedupe-survey-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_path"] = str(path)
    migration_progress(
        f"Dedupe survey templates dry_run={dry_run} kept={len(kept)} "
        f"removed={len(deleted)} report={path}"
    )
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
