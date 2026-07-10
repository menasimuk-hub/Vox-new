"""Admin Convert flow: Meta MARKETING survey/CF templates → Utility (same DB id)."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.wa_template_profile_status import WaTemplateProfileStatus
from app.services.survey_wa_utility_rewrite_service import (
    DEFAULT_UTILITY_LLM_FALLBACK_PROVIDER,
    _extract_body_and_buttons,
    apply_utility_rewrite_to_row,
    discover_remote_marketing_templates,
    resolve_utility_llm_config,
)
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _effective_components,
    survey_template_to_dict,
)
from app.services.wa_marketing_purge_service import delete_remote_template_by_name
from app.services.wa_template_meta_sync import suggest_utility_clone_template_name
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService
from app.services.wa_template_utility_lint import lint_utility_template
from seed_data.wa_survey_template_naming import is_was_survey_name, suggest_next_was_seq_name

_WAS_SEQ_RE = re.compile(r"^(.+_)(\d{3})_(en|ar)(?:_[a-z0-9]{4,8})?$", re.I)
_CFS_VER_RE = re.compile(r"^(cfs_.+)_v(\d+)$", re.I)

logger = logging.getLogger(__name__)

ConvertTarget = Literal["99", "55", "all"]


def resolve_convert_llm_config(db: Session) -> dict[str, str]:
    """Prefer DeepSeek for Convert regenerate; fall back to DeepInfra utility chain."""
    from app.services.provider_settings import ProviderSettingsService

    ds_cfg, ds_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="deepseek")
    ds_config = ds_cfg if isinstance(ds_cfg, dict) else {}
    ds_key = str(ds_config.get("api_key") or "").strip()
    ds_model = str(ds_config.get("model") or ds_config.get("default_model") or "deepseek-chat").strip()
    if ds_key:
        ds_base = str(ds_config.get("base_url") or "https://api.deepseek.com").strip().rstrip("/")
        return {
            "provider": DEFAULT_UTILITY_LLM_FALLBACK_PROVIDER,
            "model": ds_model,
            "models": ds_model,
            "api_key_set": True,
            "base_url": ds_base,
            "integration_enabled": bool(ds_enabled),
            "source": "deepseek",
        }

    try:
        cfg = resolve_utility_llm_config(db, probe=False)
        cfg["source"] = str(cfg.get("source") or "deepinfra")
        return cfg
    except ValueError:
        raise ValueError(
            "No Convert LLM available. Configure DeepSeek or DeepInfra in Admin → Integrations."
        ) from None


def _clear_profile_status_for_template(db: Session, template_id: int) -> int:
    result = db.execute(
        delete(WaTemplateProfileStatus).where(WaTemplateProfileStatus.template_id == int(template_id))
    )
    db.commit()
    return int(result.rowcount or 0)


def _suggest_survey_next_name(db: Session, row: TelnyxWhatsappTemplate) -> str | None:
    used = {
        str(r[0]).strip().lower()
        for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
        if r[0]
    }
    if is_was_survey_name(row.name):
        return suggest_next_was_seq_name(row.name, used_names=used)
    return suggest_utility_clone_template_name(row.name) or f"{row.name}_utu"


def _previous_was_seq_name(name: str | None) -> str | None:
    """was_…_002_en → was_…_001_en (for Convert retry after rename already applied)."""
    m = _WAS_SEQ_RE.match(str(name or "").strip())
    if not m:
        return None
    seq = int(m.group(2))
    if seq <= 1:
        return None
    return f"{m.group(1)}{seq - 1:03d}_{m.group(3).lower()}"


def _profile_ids_for_targets(
    db: Session,
    *,
    targets: ConvertTarget,
    service_code: str,
) -> list[tuple[str, str]]:
    """Return [(connection_profile_id, label), ...] for 99 / 55 / all."""
    primary = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code=service_code)
    backup = WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code=service_code)
    out: list[tuple[str, str]] = []
    if targets in ("99", "all") and primary:
        out.append((primary, "99"))
    if targets in ("55", "all") and backup:
        out.append((backup, "55"))
    if targets == "99" and not primary and backup:
        # Misconfigured: treat single profile as primary
        out.append((backup, "99"))
    return out


def list_marketing_for_convert(
    db: Session,
    *,
    product: str = "all",
    q: str | None = None,
    connection_profile_id: str | None = None,
) -> dict[str, Any]:
    profile_ids = None
    if connection_profile_id:
        profile_ids = [str(connection_profile_id).strip()]
    overview, candidates = discover_remote_marketing_templates(
        db,
        name_contains=q,
        profile_ids=profile_ids,
        service_code="survey",
    )
    prod = str(product or "all").strip().lower()
    rows: list[dict[str, Any]] = []
    used_was_names: set[str] | None = None
    used_cfs_names: set[str] | None = None
    for c in candidates:
        p = str(c.get("product") or "").lower()
        if prod in ("survey", "feedback") and p != prod:
            continue
        if not c.get("actionable") and not c.get("id"):
            # Still show orphans so ops can see Meta-only MARKETING names
            rows.append(
                {
                    **c,
                    "suggested_next_name": None,
                    "header": None,
                    "body": None,
                    "footer": None,
                    "buttons": [],
                }
            )
            continue
        if p == "survey" and c.get("id"):
            row = db.get(TelnyxWhatsappTemplate, int(c["id"]))
            if row is None:
                continue
            if used_was_names is None:
                used_was_names = {
                    str(r[0]).strip().lower()
                    for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
                    if r[0]
                }
            nxt = None
            if is_was_survey_name(row.name):
                nxt = suggest_next_was_seq_name(row.name, used_names=used_was_names)
            else:
                nxt = suggest_utility_clone_template_name(row.name) or f"{row.name}_utu"
            # List stays light — full body/buttons load on select via get_convert_template
            rows.append(
                {
                    **c,
                    "suggested_next_name": nxt,
                    "header": None,
                    "body": None,
                    "footer": None,
                    "buttons": [],
                    "language": row.language,
                    "db_id": row.id,
                    "local_name": row.name,
                    "body_preview": (c.get("body_preview") or "")[:160],
                }
            )
        elif p == "feedback" and c.get("id"):
            from app.models.customer_feedback import FeedbackWaTemplate
            from app.services.customer_feedback.feedback_telnyx_push_service import (
                collect_used_cfs_meta_names,
                suggest_next_cfs_version_name,
            )
            from app.services.customer_feedback.feedback_telnyx_push_service import feedback_meta_template_name

            frow = db.get(FeedbackWaTemplate, str(c["id"]))
            if frow is None:
                continue
            meta_name = str(c.get("remote_name") or feedback_meta_template_name(frow) or "")
            if used_cfs_names is None:
                used_cfs_names = collect_used_cfs_meta_names(db)
            nxt = suggest_next_cfs_version_name(meta_name, used_names=used_cfs_names) if meta_name else None
            rows.append(
                {
                    **c,
                    "suggested_next_name": nxt,
                    "header": None,
                    "body": None,
                    "footer": None,
                    "buttons": [],
                    "language": frow.language,
                    "db_id": frow.id,
                    "local_name": meta_name,
                    "body_preview": str(frow.body_text or "")[:160],
                }
            )

    orphan_rows = _orphan_cleanup_from_candidates(db, candidates=candidates, product=prod, q=q)
    # Mark list rows that are safe to purge (old Meta version, newer local exists)
    orphan_names = {str(o.get("remote_name") or "").strip().lower() for o in orphan_rows}
    for row in rows:
        rn = str(row.get("remote_name") or row.get("name") or "").strip().lower()
        if rn in orphan_names:
            row["cleanup_eligible"] = True
            match = next((o for o in orphan_rows if str(o.get("remote_name") or "").lower() == rn), None)
            if match:
                row["superseded_by_local"] = match.get("superseded_by_local")
                row["superseded_by_db_id"] = match.get("superseded_by_db_id")
        else:
            row["cleanup_eligible"] = False

    return {
        "ok": True,
        "overview": {
            **(overview or {}),
            "orphan_cleanup_count": len(orphan_rows),
        },
        "count": len(rows),
        "templates": rows,
        "orphan_cleanup_count": len(orphan_rows),
        "llm": _safe_llm_hint(db),
    }


def _safe_llm_hint(db: Session) -> dict[str, Any]:
    try:
        cfg = resolve_convert_llm_config(db)
        return {
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "source": cfg.get("source"),
            "api_key_set": bool(cfg.get("api_key_set")),
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc), "api_key_set": False}


def get_convert_template(db: Session, *, product: str, template_id: str) -> dict[str, Any]:
    prod = str(product or "survey").strip().lower()
    if prod == "feedback":
        from app.models.customer_feedback import FeedbackWaTemplate
        from app.services.customer_feedback.feedback_telnyx_push_service import (
            collect_used_cfs_meta_names,
            feedback_meta_template_name,
            parse_feedback_buttons,
            suggest_next_cfs_version_name,
        )

        frow = db.get(FeedbackWaTemplate, str(template_id))
        if frow is None:
            raise SurveyWhatsappTemplateError("Feedback template not found")
        meta_name = feedback_meta_template_name(frow)
        used = collect_used_cfs_meta_names(db)
        nxt = suggest_next_cfs_version_name(meta_name, used_names=used) if meta_name else None
        return {
            "ok": True,
            "product": "feedback",
            "db_id": frow.id,
            "local_name": meta_name,
            "suggested_next_name": nxt,
            "language": frow.language,
            "category": frow.meta_category,
            "header": None,
            "body": frow.body_text,
            "footer": None,
            "buttons": parse_feedback_buttons(frow.buttons_json),
            "status": frow.telnyx_sync_status,
        }

    row = db.get(TelnyxWhatsappTemplate, int(template_id))
    if row is None:
        raise SurveyWhatsappTemplateError("Survey template not found")
    comps = _effective_components(row)
    body, buttons = _extract_body_and_buttons(comps if isinstance(comps, list) else [])
    header = footer = None
    for comp in comps or []:
        if not isinstance(comp, dict):
            continue
        t = str(comp.get("type") or "").upper()
        if t == "HEADER":
            header = str(comp.get("text") or "") or None
        elif t == "FOOTER":
            footer = str(comp.get("text") or "") or None
    return {
        "ok": True,
        "product": "survey",
        "db_id": row.id,
        "local_name": row.name,
        "suggested_next_name": _suggest_survey_next_name(db, row),
        "language": row.language,
        "category": row.category,
        "header": header,
        "body": body,
        "footer": footer,
        "buttons": buttons,
        "status": row.status,
        "row": survey_template_to_dict(row),
    }


def regenerate_convert_template(
    db: Session,
    *,
    product: str,
    template_id: str,
    llm_provider: str | None = None,
) -> dict[str, Any]:
    llm = resolve_convert_llm_config(db)
    provider = str(llm_provider or llm.get("provider") or "deepseek").strip().lower()
    model = str(llm.get("model") or "") or None
    prod = str(product or "survey").strip().lower()

    if prod == "feedback":
        from app.models.customer_feedback import FeedbackWaTemplate
        from app.services.customer_feedback.feedback_wa_utility_rewrite_service import (
            apply_utility_rewrite_to_feedback_row,
        )

        frow = db.get(FeedbackWaTemplate, str(template_id))
        if frow is None:
            raise SurveyWhatsappTemplateError("Feedback template not found")
        old_body, new_body = apply_utility_rewrite_to_feedback_row(
            db, frow, use_llm=True, llm_provider=provider, llm_model=model
        )
        detail = get_convert_template(db, product="feedback", template_id=str(frow.id))
        detail["old_body"] = old_body
        detail["new_body"] = new_body
        detail["changed"] = str(old_body or "").strip() != str(new_body or "").strip()
        detail["rewrite_mode"] = "llm_or_rule"
        detail["lint"] = _lint_to_dict(
            lint_utility_template(
                body=new_body,
                buttons=detail.get("buttons") or [],
                language=detail.get("language"),
                meta_category="utility",
            )
        )
        detail["llm"] = {"provider": provider, "model": model, "source": llm.get("source")}
        return detail

    row = db.get(TelnyxWhatsappTemplate, int(template_id))
    if row is None:
        raise SurveyWhatsappTemplateError("Survey template not found")
    from app.services.survey_wa_utility_rewrite_service import _extract_body_and_buttons, _effective_components

    _pre_body, old_buttons = _extract_body_and_buttons(_effective_components(row) or [])
    # Convert always force-rewrites with rule-based Utility copy (no LLM).
    # LLM previously rewrote satisfaction → NPS "recommend" and local lint wrongly PASSed.
    old_body, new_body = apply_utility_rewrite_to_row(
        db,
        row,
        use_llm=False,
        llm_provider=provider,
        llm_model=model,
        force_rewrite=True,
    )
    detail = get_convert_template(db, product="survey", template_id=str(row.id))
    new_buttons = list(detail.get("buttons") or [])
    detail["old_body"] = old_body
    detail["new_body"] = new_body
    detail["old_buttons"] = old_buttons
    detail["new_buttons"] = new_buttons
    detail["changed"] = str(old_body or "").strip() != str(new_body or "").strip() or old_buttons != new_buttons
    detail["buttons_changed"] = old_buttons != new_buttons
    detail["rewrite_mode"] = "force_utility_rule"
    detail["lint"] = _lint_to_dict(
        lint_utility_template(
            body=new_body,
            buttons=detail.get("buttons") or [],
            language=detail.get("language"),
            meta_category="utility",
        )
    )
    detail["llm"] = {"provider": provider, "model": model, "source": llm.get("source")}
    return detail


def _lint_to_dict(lint: Any) -> dict[str, Any]:
    issues = []
    for item in getattr(lint, "issues", None) or []:
        if hasattr(item, "code"):
            issues.append(
                {
                    "code": getattr(item, "code", None),
                    "message": getattr(item, "message", str(item)),
                    "field": getattr(item, "field", None),
                }
            )
        elif isinstance(item, dict):
            issues.append(item)
        else:
            issues.append({"message": str(item)})
    return {"ok": bool(getattr(lint, "ok", False)), "issues": issues}


def save_convert_template(
    db: Session,
    *,
    product: str,
    template_id: str,
    header: str | None = None,
    body: str | None = None,
    footer: str | None = None,
    buttons: list[str] | None = None,
) -> dict[str, Any]:
    prod = str(product or "survey").strip().lower()
    if prod == "feedback":
        from app.models.customer_feedback import FeedbackWaTemplate
        import json

        frow = db.get(FeedbackWaTemplate, str(template_id))
        if frow is None:
            raise SurveyWhatsappTemplateError("Feedback template not found")
        if body is not None:
            frow.body_text = str(body).strip()
        if buttons is not None:
            frow.buttons_json = json.dumps([str(b).strip() for b in buttons if str(b).strip()])
        frow.meta_category = "utility"
        frow.telnyx_sync_status = "draft"
        db.add(frow)
        db.commit()
        db.refresh(frow)
        return get_convert_template(db, product="feedback", template_id=str(frow.id))

    row = db.get(TelnyxWhatsappTemplate, int(template_id))
    if row is None:
        raise SurveyWhatsappTemplateError("Survey template not found")
    comps = list(_effective_components(row) or [])
    body_text = str(body if body is not None else "").strip()
    if body is None:
        body_text, _btns = _extract_body_and_buttons(comps)
    btn_labels = [str(b).strip() for b in (buttons or []) if str(b).strip()]
    if buttons is None:
        _b, btn_labels = _extract_body_and_buttons(comps)

    lint = lint_utility_template(
        body=body_text,
        buttons=btn_labels,
        language=row.language,
        meta_category="utility",
    )
    if not lint.ok:
        msgs = "; ".join(i.message for i in lint.issues[:5])
        raise SurveyWhatsappTemplateError(f"Utility lint failed: {msgs}")

    from app.services.survey_wa_md_seed_service import _build_abc_choice_components
    from app.services.survey_wa_utility_rewrite_service import (
        _dumps,
        _normalize_draft_components,
        _persist_normalized_draft,
        _refresh_local_sync_status,
    )
    from app.services.survey_whatsapp_template_service import (
        SYNC_LOCAL_CHANGES,
        normalize_wa_template_category,
    )
    from app.services.wa_template_utility_lint import clamp_utility_button_labels

    btn_labels = clamp_utility_button_labels(btn_labels)
    if btn_labels:
        draft = _build_abc_choice_components(body=body_text, options=btn_labels)
    else:
        draft = _normalize_draft_components(comps)
        for comp in draft:
            if str(comp.get("type") or "").upper() == "BODY":
                comp["text"] = body_text
            if header is not None and str(comp.get("type") or "").upper() == "HEADER":
                comp["text"] = str(header or "")
            if footer is not None and str(comp.get("type") or "").upper() == "FOOTER":
                comp["text"] = str(footer or "")
        if header is not None and not any(str(c.get("type") or "").upper() == "HEADER" for c in draft if isinstance(c, dict)):
            if str(header).strip():
                draft.insert(0, {"type": "HEADER", "format": "TEXT", "text": str(header).strip()})
        if footer is not None and not any(str(c.get("type") or "").upper() == "FOOTER" for c in draft if isinstance(c, dict)):
            if str(footer).strip():
                draft.append({"type": "FOOTER", "text": str(footer).strip()})

    row.category = normalize_wa_template_category("UTILITY", required=True)
    row.draft_components_json = _dumps(draft)
    row.local_sync_status = SYNC_LOCAL_CHANGES
    _persist_normalized_draft(db, row, draft)
    row.local_sync_status = _refresh_local_sync_status(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return get_convert_template(db, product="survey", template_id=str(row.id))


def push_convert_template(
    db: Session,
    *,
    product: str,
    template_id: str,
    targets: ConvertTarget = "all",
    force_push: bool = True,
) -> dict[str, Any]:
    """Rename same DB id → push new name → delete old MARKETING name on selected profiles."""
    prod = str(product or "survey").strip().lower()
    tgt: ConvertTarget = targets if targets in ("99", "55", "all") else "all"
    steps: list[dict[str, Any]] = []

    if prod == "feedback":
        return _push_convert_feedback(db, template_id=str(template_id), targets=tgt, steps=steps, force_push=force_push)

    row = db.get(TelnyxWhatsappTemplate, int(template_id))
    if row is None:
        raise SurveyWhatsappTemplateError("Survey template not found")

    from app.services.survey_whatsapp_template_service import _has_remote_telnyx_id

    current_name = str(row.name or "").strip()
    language = row.language
    next_name = _suggest_survey_next_name(db, row)
    if not next_name:
        raise SurveyWhatsappTemplateError(f"Could not compute next name for {current_name}")

    # Retry after a prior Convert rename: local is already 002, remote still has 001 MARKETING.
    # Do not bump again to 003 — push current name and delete previous seq.
    prev_name = _previous_was_seq_name(current_name)
    already_renamed = bool(
        prev_name
        and not _has_remote_telnyx_id(row)
        and current_name.lower() != next_name.lower()
    )
    if already_renamed:
        old_name = prev_name
        next_name = current_name
    else:
        old_name = current_name

    comps = _effective_components(row)
    body, buttons = _extract_body_and_buttons(comps if isinstance(comps, list) else [])
    lint = lint_utility_template(body=body, buttons=buttons, language=row.language, meta_category="utility")
    if not lint.ok:
        msgs = "; ".join(i.message for i in lint.issues[:5])
        raise SurveyWhatsappTemplateError(f"Utility lint failed before push: {msgs}")

    steps.append({"id": "lint", "title": "Utility lint", "status": "done", "detail": "ok"})

    if already_renamed or old_name.lower() == next_name.lower():
        cleared = _clear_profile_status_for_template(db, int(row.id))
        steps.append(
            {
                "id": "rename",
                "title": "Rename local (same DB id)",
                "status": "done",
                "detail": f"already {row.name} (retry — skip bump, cleared_profile_status={cleared})",
            }
        )
    else:
        row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, next_name)
        cleared = _clear_profile_status_for_template(db, int(row.id))
        steps.append(
            {
                "id": "rename",
                "title": "Rename local (same DB id)",
                "status": "done",
                "detail": f"{old_name} → {row.name} (id={row.id}, cleared_profile_status={cleared})",
            }
        )

    profile_pairs = _profile_ids_for_targets(db, targets=tgt, service_code="survey")
    if not profile_pairs:
        raise SurveyWhatsappTemplateError("No connection profiles resolved for push targets")

    push_results: list[dict[str, Any]] = []
    for pid, label in profile_pairs:
        try:
            result = SurveyWhatsappTemplateService.push_to_telnyx(
                db,
                row,
                connection_profile_id=pid,
                service_code="survey",
                force_approved_update=False,
                skip_remote_link=True,
            )
            push_results.append({"target": label, "ok": True, "message": result.get("sync_message") or result.get("message")})
            steps.append(
                {
                    "id": f"push_{label}",
                    "title": f"Push new name to {label}",
                    "status": "done",
                    "detail": str(result.get("sync_message") or result.get("message") or "pushed"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            push_results.append({"target": label, "ok": False, "error": str(exc)})
            steps.append(
                {
                    "id": f"push_{label}",
                    "title": f"Push new name to {label}",
                    "status": "error",
                    "detail": str(exc)[:400],
                }
            )

    any_push_ok = any(r.get("ok") for r in push_results)
    deleted_on: list[str] = []
    if any_push_ok and old_name and old_name.lower() != str(row.name or "").lower():
        try:
            deleted_on = delete_remote_template_by_name(
                db,
                name=old_name,
                language=language,
                service_code="survey",
                profile_ids=[pid for pid, label in profile_pairs if any(
                    r.get("target") == label and r.get("ok") for r in push_results
                )] or None,
            )
            failed_deletes = [d for d in deleted_on if str(d).endswith("_failed")]
            steps.append(
                {
                    "id": "delete_old",
                    "title": "Delete old MARKETING name",
                    "status": "error" if failed_deletes and not any(
                        not str(d).endswith("_failed") for d in deleted_on
                    ) else "done",
                    "detail": f"{old_name} → deleted on {deleted_on or ['none']}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                {
                    "id": "delete_old",
                    "title": "Delete old MARKETING name",
                    "status": "error",
                    "detail": f"Push OK; old-name cleanup failed: {str(exc)[:300]}",
                }
            )
    elif not any_push_ok:
        steps.append(
            {
                "id": "delete_old",
                "title": "Delete old MARKETING name",
                "status": "error",
                "detail": "Skipped — push failed; old name kept on Meta",
            }
        )

    db.refresh(row)
    return {
        "ok": any_push_ok,
        "product": "survey",
        "db_id": row.id,
        "old_name": old_name,
        "new_name": row.name,
        "targets": tgt,
        "push_results": push_results,
        "deleted_remote": deleted_on,
        "steps": steps,
        "status": row.status,
    }


def _push_convert_feedback(
    db: Session,
    *,
    template_id: str,
    targets: ConvertTarget,
    steps: list[dict[str, Any]],
    force_push: bool,
) -> dict[str, Any]:
    from app.models.customer_feedback import FeedbackWaTemplate
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        collect_used_cfs_meta_names,
        feedback_meta_template_name,
        parse_feedback_buttons,
        push_feedback_template_to_telnyx,
        suggest_next_cfs_version_name,
    )
    from app.services.wa_marketing_purge_service import _rename_feedback_for_utility_push

    frow = db.get(FeedbackWaTemplate, str(template_id))
    if frow is None:
        raise SurveyWhatsappTemplateError("Feedback template not found")

    old_name = str(feedback_meta_template_name(frow) or "").strip()
    language = frow.language
    used = collect_used_cfs_meta_names(db)
    next_name = suggest_next_cfs_version_name(old_name, used_names=used) if old_name else None
    if not next_name:
        raise SurveyWhatsappTemplateError(f"Could not compute next CFS name for {old_name}")

    buttons = parse_feedback_buttons(frow.buttons_json)
    lint = lint_utility_template(
        body=str(frow.body_text or ""),
        buttons=buttons,
        language=frow.language,
        meta_category="utility",
        template_key=frow.template_key,
    )
    if not lint.ok:
        msgs = "; ".join(i.message for i in lint.issues[:5])
        raise SurveyWhatsappTemplateError(f"Utility lint failed before push: {msgs}")
    steps.append({"id": "lint", "title": "Utility lint", "status": "done", "detail": "ok"})

    frow = _rename_feedback_for_utility_push(db, frow, next_name)
    steps.append(
        {
            "id": "rename",
            "title": "Rename meta name (same DB id)",
            "status": "done",
            "detail": f"{old_name} → {frow.meta_template_name} (id={frow.id})",
        }
    )

    # Feedback often shares WABA via survey or customer_feedback service codes
    profile_pairs = _profile_ids_for_targets(db, targets=targets, service_code="customer_feedback")
    if not profile_pairs:
        profile_pairs = _profile_ids_for_targets(db, targets=targets, service_code="survey")
    if not profile_pairs:
        raise SurveyWhatsappTemplateError("No connection profiles resolved for push targets")

    push_results: list[dict[str, Any]] = []
    for pid, label in profile_pairs:
        try:
            result = push_feedback_template_to_telnyx(
                db,
                frow,
                connection_profile_id=pid,
                service_code="customer_feedback",
                force_push=force_push,
            )
            push_results.append({"target": label, "ok": True, "message": result.get("message")})
            steps.append(
                {
                    "id": f"push_{label}",
                    "title": f"Push new name to {label}",
                    "status": "done",
                    "detail": str(result.get("message") or "pushed"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            # Retry under survey service_code (shared WABA setups)
            try:
                result = push_feedback_template_to_telnyx(
                    db,
                    frow,
                    connection_profile_id=pid,
                    service_code="survey",
                    force_push=force_push,
                )
                push_results.append({"target": label, "ok": True, "message": result.get("message")})
                steps.append(
                    {
                        "id": f"push_{label}",
                        "title": f"Push new name to {label}",
                        "status": "done",
                        "detail": str(result.get("message") or "pushed"),
                    }
                )
            except Exception as exc2:  # noqa: BLE001
                push_results.append({"target": label, "ok": False, "error": str(exc2) or str(exc)})
                steps.append(
                    {
                        "id": f"push_{label}",
                        "title": f"Push new name to {label}",
                        "status": "error",
                        "detail": str(exc2)[:400],
                    }
                )

    any_push_ok = any(r.get("ok") for r in push_results)
    deleted_on: list[str] = []
    if any_push_ok and old_name and old_name.lower() != str(frow.meta_template_name or "").lower():
        try:
            for sc in ("customer_feedback", "survey"):
                deleted_on.extend(
                    delete_remote_template_by_name(
                        db, name=old_name, language=language, service_code=sc
                    )
                )
            steps.append(
                {
                    "id": "delete_old",
                    "title": "Delete old MARKETING name",
                    "status": "done",
                    "detail": f"{old_name} → deleted on {deleted_on or ['none']}",
                }
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(
                {
                    "id": "delete_old",
                    "title": "Delete old MARKETING name",
                    "status": "error",
                    "detail": f"Push OK; old-name cleanup failed: {str(exc)[:300]}",
                }
            )
    elif not any_push_ok:
        steps.append(
            {
                "id": "delete_old",
                "title": "Delete old MARKETING name",
                "status": "error",
                "detail": "Skipped — push failed; old name kept on Meta",
            }
        )

    return {
        "ok": any_push_ok,
        "product": "feedback",
        "db_id": frow.id,
        "old_name": old_name,
        "new_name": frow.meta_template_name,
        "targets": targets,
        "push_results": push_results,
        "deleted_remote": deleted_on,
        "steps": steps,
        "status": frow.telnyx_sync_status,
    }


def _parse_was_stem_seq(name: str) -> tuple[str, int, str] | None:
    base = str(name or "").strip().lower()
    while base.endswith("_utu"):
        base = base[:-4]
    match = _WAS_SEQ_RE.match(base)
    if not match:
        return None
    return match.group(1), int(match.group(2)), match.group(3).lower()


def _parse_cfs_stem_ver(name: str) -> tuple[str, int] | None:
    match = _CFS_VER_RE.match(str(name or "").strip().lower())
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2))


def _local_was_max_by_stem(db: Session) -> dict[tuple[str, str], dict[str, Any]]:
    """Map (stem_prefix, lang) -> {seq, name, id} for highest local was_* seq."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    rows = db.execute(select(TelnyxWhatsappTemplate.id, TelnyxWhatsappTemplate.name)).all()
    for row_id, name in rows:
        parsed = _parse_was_stem_seq(str(name or ""))
        if not parsed:
            continue
        stem, seq, lang = parsed
        key = (stem, lang)
        cur = out.get(key)
        if cur is None or seq > int(cur["seq"]):
            out[key] = {"seq": seq, "name": name, "id": row_id}
    return out


def _local_cfs_max_by_stem(db: Session) -> dict[str, dict[str, Any]]:
    """Map cfs stem -> highest local version (meta_template_name only — fast path)."""
    from app.models.customer_feedback import FeedbackWaTemplate

    out: dict[str, dict[str, Any]] = {}
    rows = db.execute(
        select(FeedbackWaTemplate.id, FeedbackWaTemplate.meta_template_name)
    ).all()
    for row_id, stored in rows:
        name = str(stored or "").strip()
        if not name:
            continue
        parsed = _parse_cfs_stem_ver(name)
        if not parsed:
            continue
        stem, ver = parsed
        cur = out.get(stem)
        if cur is None or ver > int(cur["ver"]):
            out[stem] = {"ver": ver, "name": name, "id": str(row_id)}
    return out


def _orphan_cleanup_from_candidates(
    db: Session,
    *,
    candidates: list[dict[str, Any]],
    product: str = "all",
    q: str | None = None,
) -> list[dict[str, Any]]:
    """Remote MARKETING names with no local row, superseded by a newer local version."""
    prod = str(product or "all").strip().lower()
    needle = str(q or "").strip().lower()
    need_survey = prod in ("all", "survey")
    need_feedback = prod in ("all", "feedback")
    was_max = _local_was_max_by_stem(db) if need_survey else {}
    cfs_max = _local_cfs_max_by_stem(db) if need_feedback else {}
    orphans: list[dict[str, Any]] = []

    for c in candidates:
        if c.get("actionable") or c.get("id"):
            continue
        p = str(c.get("product") or "").lower()
        if prod in ("survey", "feedback") and p != prod:
            continue
        remote_name = str(c.get("remote_name") or c.get("name") or "").strip().lower()
        if not remote_name:
            continue
        if needle and needle not in remote_name:
            continue
        lang = str(c.get("language") or c.get("remote_language") or "en_GB").strip().lower()

        if need_survey and (p == "survey" or remote_name.startswith("was_")):
            parsed = _parse_was_stem_seq(remote_name)
            if not parsed:
                continue
            stem, seq, name_lang = parsed
            local = was_max.get((stem, name_lang))
            if local is None or int(local["seq"]) <= seq:
                continue
            orphans.append(
                {
                    "remote_name": remote_name,
                    "language": lang or name_lang,
                    "product": "survey",
                    "remote_seq": seq,
                    "superseded_by_local": local["name"],
                    "superseded_by_db_id": local["id"],
                    "superseded_seq": local["seq"],
                    "remote_profiles": c.get("remote_profiles") or [],
                    "reason": "old_meta_version_newer_local_exists",
                }
            )
        elif need_feedback and (p == "feedback" or remote_name.startswith("cfs_")):
            parsed = _parse_cfs_stem_ver(remote_name)
            if not parsed:
                continue
            stem, ver = parsed
            local = cfs_max.get(stem)
            if local is None or int(local["ver"]) <= ver:
                continue
            orphans.append(
                {
                    "remote_name": remote_name,
                    "language": lang,
                    "product": "feedback",
                    "remote_seq": ver,
                    "superseded_by_local": local["name"],
                    "superseded_by_db_id": local["id"],
                    "superseded_seq": local["ver"],
                    "remote_profiles": c.get("remote_profiles") or [],
                    "reason": "old_meta_version_newer_local_exists",
                }
            )

    orphans.sort(key=lambda item: str(item.get("remote_name") or ""))
    return orphans


def list_convert_orphan_cleanup_candidates(
    db: Session,
    *,
    product: str = "all",
    q: str | None = None,
    connection_profile_id: str | None = None,
) -> dict[str, Any]:
    profile_ids = [str(connection_profile_id).strip()] if connection_profile_id else None
    overview, candidates = discover_remote_marketing_templates(
        db,
        name_contains=q,
        profile_ids=profile_ids,
        service_code="survey",
    )
    orphans = _orphan_cleanup_from_candidates(db, candidates=candidates, product=product, q=q)
    return {
        "ok": True,
        "overview": overview,
        "count": len(orphans),
        "orphans": orphans,
    }


def purge_convert_orphan_templates(
    db: Session,
    *,
    product: str = "all",
    q: str | None = None,
    connection_profile_id: str | None = None,
    targets: ConvertTarget = "all",
    dry_run: bool = True,
    names: list[str] | None = None,
) -> dict[str, Any]:
    """Delete Meta/Telnyx MARKETING names that are old versions superseded by local DB."""
    listed = list_convert_orphan_cleanup_candidates(
        db,
        product=product,
        q=q,
        connection_profile_id=connection_profile_id,
    )
    orphans = list(listed.get("orphans") or [])
    if names:
        allow = {str(n).strip().lower() for n in names if str(n or "").strip()}
        orphans = [o for o in orphans if str(o.get("remote_name") or "").lower() in allow]

    profile_pairs = _profile_ids_for_targets(db, targets=targets, service_code="survey")
    # Also try customer_feedback service code profiles when deleting cfs_*
    fb_pairs = _profile_ids_for_targets(db, targets=targets, service_code="customer_feedback")
    profile_ids = list(dict.fromkeys([pid for pid, _ in profile_pairs + fb_pairs if pid]))
    if connection_profile_id:
        profile_ids = [str(connection_profile_id).strip()]

    results: list[dict[str, Any]] = []
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "targets": targets,
            "count": len(orphans),
            "orphans": orphans,
            "results": [],
            "message": f"Would delete {len(orphans)} old Meta/Telnyx version(s) not in local DB.",
        }

    for orphan in orphans:
        name = str(orphan.get("remote_name") or "").strip()
        language = str(orphan.get("language") or "en_GB")
        product_code = str(orphan.get("product") or "survey")
        service_code = "customer_feedback" if product_code == "feedback" else "survey"
        try:
            deleted_on = delete_remote_template_by_name(
                db,
                name=name,
                language=language,
                service_code=service_code,
                profile_ids=profile_ids or None,
            )
            # Feedback templates sometimes live under survey WABA too
            if product_code == "feedback" and service_code == "customer_feedback":
                extra = delete_remote_template_by_name(
                    db,
                    name=name,
                    language=language,
                    service_code="survey",
                    profile_ids=profile_ids or None,
                )
                deleted_on = list(dict.fromkeys([*deleted_on, *extra]))
            results.append(
                {
                    "remote_name": name,
                    "ok": True,
                    "deleted_on": deleted_on,
                    "superseded_by_local": orphan.get("superseded_by_local"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("convert_orphan_purge_failed name=%s", name)
            results.append(
                {
                    "remote_name": name,
                    "ok": False,
                    "error": str(exc)[:400],
                    "superseded_by_local": orphan.get("superseded_by_local"),
                }
            )

    ok_count = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_count == len(results),
        "dry_run": False,
        "targets": targets,
        "count": len(results),
        "deleted": ok_count,
        "failed": len(results) - ok_count,
        "results": results,
        "message": f"Deleted {ok_count}/{len(results)} old Meta/Telnyx version(s).",
    }
