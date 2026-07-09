"""Plan and apply removal of Marketing WA templates (survey + customer feedback)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackIndustry, FeedbackSurveyType, FeedbackWaTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.customer_feedback.feedback_marketing_policy import is_marketing_wa_template
from app.services.customer_feedback.feedback_telnyx_push_service import (
    FeedbackTelnyxPushError,
    english_anchor_template,
    feedback_meta_template_name,
    push_feedback_template_to_telnyx,
)
from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateError, MetaWhatsappTemplateService
from app.services.survey_wa_utility_rewrite_service import (
    _body_has_recommend_intent,
    _extract_body_and_buttons,
    _find_template_row,
    _industry_for_template_row,
    _prepare_approved_template_for_utility_push,
    _template_body_text,
    _topic_for_template_row,
    apply_utility_rewrite_to_row,
    discover_remote_marketing_survey_templates,
    refresh_row_from_telnyx,
    rewrite_body_for_utility,
)
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _effective_components,
    _has_remote_telnyx_id,
)
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncError,
    TelnyxWhatsappTemplateSyncService,
)
from app.services.wa_template_product_scope import (
    filter_remote_for_service_code,
    is_feedback_platform_name,
    is_survey_platform_row,
)
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

logger = logging.getLogger(__name__)

ActionKind = Literal[
    "survey_rewrite_push",
    "survey_delete_remote",
    "survey_delete_local",
    "cf_delete",
    "cf_rewrite_push",
    "cf_delete_remote",
]


@dataclass
class PurgePlanItem:
    action: ActionKind
    product: str
    label: str
    old_meta_name: str | None = None
    new_meta_name: str | None = None
    local_template_id: int | str | None = None
    language: str | None = None
    dry_preview: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "product": self.product,
            "label": self.label,
            "old_meta_name": self.old_meta_name,
            "new_meta_name": self.new_meta_name,
            "local_template_id": self.local_template_id,
            "language": self.language,
            "dry_preview": self.dry_preview,
            "meta": self.meta,
        }


def _norm_lang(lang: str | None) -> str:
    return str(lang or "en_gb").strip().lower().replace("-", "_")


def delete_remote_template_by_name(
    db: Session,
    *,
    name: str,
    language: str | None,
    service_code: str,
) -> list[str]:
    """Delete a template name from Meta primary + Telnyx backup (best effort)."""
    clean_name = str(name or "").strip()
    if not clean_name:
        return []
    deleted_on: list[str] = []
    lang = _norm_lang(language)
    primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code=service_code)
    backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code=service_code)

    for pid, label in ((primary_id, "meta_primary"), (backup_id, "telnyx_backup")):
        if not pid:
            continue
        try:
            remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(
                db,
                connection_profile_id=pid,
                service_code=service_code,
                allow_account_waba_fallback=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("purge_fetch_remote_failed profile=%s err=%s", pid, str(exc)[:200])
            continue
        matches = [
            item
            for item in remote
            if isinstance(item, dict)
            and str(item.get("name") or "").strip().lower() == clean_name.lower()
            and (
                not language
                or _norm_lang(str(item.get("language") or item.get("language_code") or "")) == lang
                or _norm_lang(str(item.get("language") or "")).startswith(lang[:2])
            )
        ]
        if not matches and remote:
            matches = [
                item
                for item in remote
                if isinstance(item, dict) and str(item.get("name") or "").strip().lower() == clean_name.lower()
            ]
        for item in matches:
            record_id = str(item.get("id") or "").strip()
            try:
                if record_id:
                    TelnyxWhatsappTemplateSyncService.delete_remote_template(
                        db, record_id, template_name=clean_name
                    )
                else:
                    MetaWhatsappTemplateService.delete_message_template(
                        db,
                        name=clean_name,
                        service_code=service_code,
                        connection_profile_id=pid,
                    )
                deleted_on.append(label)
            except (TelnyxWhatsappTemplateSyncError, MetaWhatsappTemplateError) as exc:
                detail = str(exc).lower()
                if "404" in detail or "not found" in detail:
                    deleted_on.append(f"{label}_already_gone")
                else:
                    raise

    if primary_id and "meta_primary" not in deleted_on and "meta_primary_already_gone" not in deleted_on:
        try:
            MetaWhatsappTemplateService.delete_message_template(
                db,
                name=clean_name,
                service_code=service_code,
                connection_profile_id=primary_id,
            )
            deleted_on.append("meta_by_name")
        except MetaWhatsappTemplateError as exc:
            detail = str(exc).lower()
            if "404" not in detail and "not found" not in detail:
                raise
            deleted_on.append("meta_by_name_already_gone")
    return deleted_on


def _feedback_meta_name_for_row(db: Session, row: FeedbackWaTemplate) -> str | None:
    industry_slug = survey_slug = None
    if row.industry_id:
        ind = db.get(FeedbackIndustry, row.industry_id)
        industry_slug = ind.slug if ind else None
    if row.survey_type_id:
        st = db.get(FeedbackSurveyType, row.survey_type_id)
        survey_slug = st.slug if st else None
    try:
        anchor = english_anchor_template(db, row)
        return feedback_meta_template_name(
            row,
            industry_slug=industry_slug,
            survey_type_slug=survey_slug,
            name_anchor_id=anchor.id,
        )
    except Exception:
        return str(row.meta_template_name or "").strip() or None


def discover_remote_marketing_feedback_templates(
    db: Session,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    from app.services.wa_template_sync_profile import summarize_for_connection_profile

    service_code = "customer_feedback"
    primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code=service_code)
    backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code=service_code)
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
        remote = filter_remote_for_service_code(remote_all, service_code)
        provider = str(summary.get("provider") or "unknown").strip().lower()
        for item in remote:
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "").upper()
            if "MARKET" not in category:
                continue
            remote_name = str(item.get("name") or "").strip().lower()
            if not remote_name or not is_feedback_platform_name(remote_name):
                continue
            lang = _norm_lang(str(item.get("language") or item.get("language_code") or "en_gb"))
            key = (remote_name, lang)
            entry = marketing_by_key.setdefault(
                key,
                {"remote_name": remote_name, "remote_language": lang, "remote_profiles": [], "reasons": []},
            )
            entry["remote_profiles"].append({"profile_id": pid, "provider": provider})
            reason = f"remote_marketing_{provider}"
            if reason not in entry["reasons"]:
                entry["reasons"].append(reason)

    cf_rows = list(db.execute(select(FeedbackWaTemplate)).scalars().all())
    by_meta_name: dict[str, FeedbackWaTemplate] = {}
    for row in cf_rows:
        meta_name = _feedback_meta_name_for_row(db, row)
        if meta_name:
            by_meta_name[str(meta_name).strip().lower()] = row

    out: list[dict[str, Any]] = []
    for (_remote_name, _lang), entry in sorted(marketing_by_key.items()):
        local = by_meta_name.get(entry["remote_name"])
        out.append(
            {
                "remote_name": entry["remote_name"],
                "remote_language": entry["remote_language"],
                "remote_profiles": entry["remote_profiles"],
                "reasons": entry["reasons"],
                "feedback_wa_template_id": getattr(local, "id", None),
                "is_marketing_row": is_marketing_wa_template(local) if local is not None else False,
                "template_key": getattr(local, "template_key", None),
            }
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
    }
    return overview, out


def build_marketing_purge_plan(db: Session) -> tuple[dict[str, Any], list[PurgePlanItem]]:
    plan: list[PurgePlanItem] = []
    overview: dict[str, Any] = {}

    survey_overview, survey_remote = discover_remote_marketing_survey_templates(db)
    overview["survey_remote"] = survey_overview
    rewrite_names: set[str] = set()

    for item in survey_remote:
        if not item.get("actionable"):
            remote_name = str(item.get("remote_name") or item.get("name") or "")
            if remote_name:
                plan.append(
                    PurgePlanItem(
                        action="survey_delete_remote",
                        product="survey",
                        label=remote_name,
                        old_meta_name=remote_name,
                        language=item.get("remote_language"),
                        meta={"reasons": item.get("reasons"), "note": "no_local_row"},
                    )
                )
            continue

        process_name = str(item.get("process_name") or item.get("name") or "")
        remote_name = str(item.get("remote_name") or process_name)
        rewrite_names.add(process_name.lower())
        row = _find_template_row(db, process_name)
        preview: dict[str, Any] = {"body_before": item.get("body_preview")}
        if row is not None:
            components = _effective_components(row)
            old_body, buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])
            use_llm = not _body_has_recommend_intent(old_body)
            preview["body_after"] = rewrite_body_for_utility(
                db,
                original_body=old_body,
                button_labels=buttons,
                template_name=row.name,
                display_name=row.display_name,
                use_llm=use_llm,
                industry_slug=_industry_for_template_row(db, row)[0],
                industry_name=_industry_for_template_row(db, row)[1],
                topic_name=_topic_for_template_row(db, row),
            )
            from seed_data.wa_survey_template_naming import is_was_survey_name, suggest_next_was_seq_name

            if (
                str(row.status or "").upper() == "APPROVED"
                and _has_remote_telnyx_id(row)
            ):
                used = {
                    str(r[0]).strip().lower()
                    for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
                    if r[0]
                }
                next_name = None
                if is_was_survey_name(row.name):
                    next_name = suggest_next_was_seq_name(row.name, used_names=used)
                preview["new_local_name"] = next_name or f"{row.name}_utu"
            else:
                preview["new_local_name"] = row.name

        plan.append(
            PurgePlanItem(
                action="survey_rewrite_push",
                product="survey",
                label=process_name,
                old_meta_name=remote_name if remote_name.lower() != str(preview.get("new_local_name", "")).lower() else None,
                new_meta_name=str(preview.get("new_local_name") or process_name),
                local_template_id=item.get("id"),
                language=item.get("remote_language"),
                dry_preview=preview,
                meta={"reasons": item.get("reasons"), "remote_name": remote_name},
            )
        )

    local_marketing_rows = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                func.upper(TelnyxWhatsappTemplate.category) == "MARKETING",
            )
        ).scalars().all()
    )
    for row in local_marketing_rows:
        if not is_survey_platform_row(db, row):
            continue
        name_lower = str(row.name or "").strip().lower()
        if name_lower in rewrite_names:
            continue
        plan.append(
            PurgePlanItem(
                action="survey_delete_local",
                product="survey",
                label=str(row.name),
                old_meta_name=str(row.name),
                local_template_id=row.id,
                language=row.language,
                meta={"status": row.status, "note": "local_marketing_orphan"},
            )
        )

    cf_overview, cf_remote = discover_remote_marketing_feedback_templates(db)
    overview["customer_feedback_remote"] = cf_overview
    cf_delete_ids: set[str] = set()

    for row in db.execute(select(FeedbackWaTemplate)).scalars().all():
        if not is_marketing_wa_template(row):
            continue
        meta_name = _feedback_meta_name_for_row(db, row)
        cf_delete_ids.add(str(row.id))
        plan.append(
            PurgePlanItem(
                action="cf_delete",
                product="customer_feedback",
                label=meta_name or str(row.template_key),
                old_meta_name=meta_name,
                local_template_id=row.id,
                language=row.language,
                meta={"template_key": row.template_key, "step_role": row.step_role},
            )
        )

    for item in cf_remote:
        remote_name = str(item.get("remote_name") or "")
        local_id = item.get("feedback_wa_template_id")
        if local_id and str(local_id) in cf_delete_ids:
            continue
        if local_id:
            row = db.get(FeedbackWaTemplate, str(local_id))
            if row is not None and not is_marketing_wa_template(row):
                plan.append(
                    PurgePlanItem(
                        action="cf_rewrite_push",
                        product="customer_feedback",
                        label=remote_name,
                        old_meta_name=remote_name,
                        new_meta_name=remote_name,
                        local_template_id=row.id,
                        language=item.get("remote_language"),
                        dry_preview={"body_before": str(row.body_text or "")[:160]},
                        meta={"reasons": item.get("reasons")},
                    )
                )
                continue
        if remote_name:
            plan.append(
                PurgePlanItem(
                    action="cf_delete_remote",
                    product="customer_feedback",
                    label=remote_name,
                    old_meta_name=remote_name,
                    language=item.get("remote_language"),
                    meta={"reasons": item.get("reasons"), "note": "remote_orphan"},
                )
            )

    local_cf_marketing_catalog = list(
        db.execute(
            select(TelnyxWhatsappTemplate).where(
                func.upper(TelnyxWhatsappTemplate.category) == "MARKETING",
            )
        ).scalars().all()
    )
    for row in local_cf_marketing_catalog:
        if not is_feedback_platform_name(row.name):
            continue
        plan.append(
            PurgePlanItem(
                action="survey_delete_local",
                product="customer_feedback",
                label=str(row.name),
                old_meta_name=str(row.name),
                local_template_id=row.id,
                language=row.language,
                meta={"note": "feedback_catalog_marketing_row"},
            )
        )

    overview["plan_counts"] = {
        action: sum(1 for p in plan if p.action == action)
        for action in (
            "survey_rewrite_push",
            "survey_delete_remote",
            "survey_delete_local",
            "cf_delete",
            "cf_rewrite_push",
            "cf_delete_remote",
        )
    }
    overview["total_items"] = len(plan)
    overview["push_items"] = sum(1 for p in plan if p.action in {"survey_rewrite_push", "cf_rewrite_push"})
    return overview, plan


def _delete_feedback_wa_template(db: Session, row: FeedbackWaTemplate) -> dict[str, Any]:
    meta_name = _feedback_meta_name_for_row(db, row)
    deleted_on: list[str] = []
    if meta_name:
        deleted_on = delete_remote_template_by_name(
            db,
            name=meta_name,
            language=row.language,
            service_code="customer_feedback",
        )
    if meta_name:
        catalog_rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == meta_name)
            ).scalars().all()
        )
        for catalog in catalog_rows:
            db.delete(catalog)
    db.delete(row)
    db.commit()
    return {"ok": True, "meta_name": meta_name, "deleted_on": deleted_on}


def apply_purge_plan_item(
    db: Session,
    item: PurgePlanItem,
    *,
    dry_run: bool,
    push: bool,
    sync_remote: bool,
    use_llm: bool,
) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "dry_run": True, "action": item.action, "label": item.label}

    try:
        if item.action == "survey_rewrite_push":
            row = _find_template_row(db, item.label)
            if row is None:
                return {"ok": False, "error": f"Local row not found: {item.label}"}
            old_remote = str(item.meta.get("remote_name") or item.old_meta_name or row.name)
            if sync_remote and _has_remote_telnyx_id(row):
                refresh_row_from_telnyx(db, row)
                db.refresh(row)
            body_text = _template_body_text(row)
            use_llm_local = use_llm and not _body_has_recommend_intent(body_text)
            renamed_to: str | None = None
            if push:
                row, renamed_to = _prepare_approved_template_for_utility_push(db, row)
            old_body, new_body = apply_utility_rewrite_to_row(db, row, use_llm=use_llm_local)
            pushed = False
            push_msg = ""
            if push:
                result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
                pushed = True
                push_msg = str(result.get("sync_message") or result.get("message") or "pushed")
            delete_targets: list[str] = []
            new_name = str(row.name or "")
            if old_remote and old_remote.lower() != new_name.lower():
                delete_targets.append(old_remote)
            deleted_on: list[str] = []
            for target in delete_targets:
                deleted_on.extend(
                    delete_remote_template_by_name(
                        db,
                        name=target,
                        language=item.language,
                        service_code="survey",
                    )
                )
            return {
                "ok": True,
                "action": item.action,
                "label": item.label,
                "renamed_to": renamed_to,
                "new_name": new_name,
                "pushed": pushed,
                "push_message": push_msg,
                "deleted_remote": deleted_on,
                "old_body": old_body[:200],
                "new_body": new_body[:200],
            }

        if item.action == "survey_delete_remote":
            deleted_on = delete_remote_template_by_name(
                db,
                name=str(item.old_meta_name or item.label),
                language=item.language,
                service_code="survey",
            )
            return {"ok": True, "action": item.action, "deleted_remote": deleted_on}

        if item.action == "survey_delete_local":
            row = db.get(TelnyxWhatsappTemplate, int(item.local_template_id))
            if row is None:
                return {"ok": False, "error": "Local telnyx row not found"}
            deleted_on: list[str] = []
            if item.old_meta_name:
                deleted_on = delete_remote_template_by_name(
                    db,
                    name=str(item.old_meta_name),
                    language=item.language,
                    service_code="survey" if item.product == "survey" else "customer_feedback",
                )
            result = SurveyWhatsappTemplateService.delete_template_local(db, row)
            return {"ok": True, "action": item.action, "deleted_remote": deleted_on, **result}

        if item.action == "cf_delete":
            row = db.get(FeedbackWaTemplate, str(item.local_template_id))
            if row is None:
                return {"ok": False, "error": "FeedbackWaTemplate not found"}
            return {"ok": True, "action": item.action, **_delete_feedback_wa_template(db, row)}

        if item.action == "cf_rewrite_push":
            row = db.get(FeedbackWaTemplate, str(item.local_template_id))
            if row is None:
                return {"ok": False, "error": "FeedbackWaTemplate not found"}
            row.meta_category = "utility"
            db.add(row)
            db.commit()
            db.refresh(row)
            pushed = False
            push_result: dict[str, Any] = {}
            if push:
                push_result = push_feedback_template_to_telnyx(db, row, force_push=True)
                pushed = True
            # Same-name utility update on Meta — no delete after push.
            return {
                "ok": True,
                "action": item.action,
                "pushed": pushed,
                "push_result": push_result,
                "note": "in_place_utility_update",
            }

        if item.action == "cf_delete_remote":
            deleted_on = delete_remote_template_by_name(
                db,
                name=str(item.old_meta_name or item.label),
                language=item.language,
                service_code="customer_feedback",
            )
            return {"ok": True, "action": item.action, "deleted_remote": deleted_on}

        return {"ok": False, "error": f"Unknown action {item.action}"}
    except (SurveyWhatsappTemplateError, FeedbackTelnyxPushError, TelnyxWhatsappTemplateSyncError, MetaWhatsappTemplateError) as exc:
        return {"ok": False, "action": item.action, "label": item.label, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "action": item.action, "label": item.label, "error": str(exc)}


def apply_purge_plan(
    db: Session,
    plan: list[PurgePlanItem],
    *,
    dry_run: bool,
    push: bool,
    sync_remote: bool,
    use_llm: bool,
    push_delay_seconds: float = 30.0,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    push_actions = {"survey_rewrite_push", "cf_rewrite_push"}
    last_push_at = 0.0
    for index, item in enumerate(plan, start=1):
        is_push_action = item.action in push_actions
        if is_push_action and push and not dry_run and last_push_at > 0 and push_delay_seconds > 0:
            elapsed = time.time() - last_push_at
            wait = push_delay_seconds - elapsed
            if wait > 0:
                time.sleep(wait)
        result = apply_purge_plan_item(
            db,
            item,
            dry_run=dry_run,
            push=push if is_push_action else False,
            sync_remote=sync_remote,
            use_llm=use_llm,
        )
        result["index"] = index
        result["total"] = len(plan)
        results.append(result)
        if is_push_action and push and not dry_run and result.get("ok"):
            last_push_at = time.time()
    return results
