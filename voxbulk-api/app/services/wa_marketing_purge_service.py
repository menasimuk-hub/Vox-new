"""Plan and apply removal of Marketing WA templates (survey + customer feedback)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateError, MetaWhatsappTemplateService
from app.services.survey_wa_utility_rewrite_service import (
    DEFAULT_UTILITY_LLM_MODEL,
    DEFAULT_UTILITY_LLM_PROVIDER,
    _body_has_recommend_intent,
    _extract_body_and_buttons,
    _find_template_row,
    _industry_for_template_row,
    _normalize_leading_emoji_text,
    _prepare_approved_template_for_utility_push,
    _rule_based_utility_body,
    _template_body_text,
    _topic_for_template_row,
    _topic_from_template_name,
    apply_utility_rewrite_to_row,
    discover_remote_marketing_survey_templates,
    discover_remote_marketing_templates,
    refresh_row_from_telnyx,
)
from app.services.wa_template_meta_sync import suggest_utility_clone_template_name
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
from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

logger = logging.getLogger(__name__)

ActionKind = Literal[
    "survey_rewrite_push",
    "survey_delete_remote",
    "feedback_rewrite_push",
    "feedback_delete_remote",
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
    profile_ids: list[str] | None = None,
) -> list[str]:
    """Delete a template name from Meta primary + Telnyx backup (best effort)."""
    clean_name = str(name or "").strip()
    if not clean_name:
        return []
    deleted_on: list[str] = []
    lang = _norm_lang(language)
    primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(db, service_code=service_code)
    backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(db, service_code=service_code)
    if profile_ids:
        pairs = [(str(pid).strip(), f"profile:{str(pid).strip()[:8]}") for pid in profile_ids if str(pid or "").strip()]
    else:
        pairs = [(pid, label) for pid, label in ((primary_id, "meta_primary"), (backup_id, "telnyx_backup")) if pid]

    from app.services.whatsapp_provider_service import is_meta_whatsapp_primary

    for pid, label in pairs:
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
        if not matches:
            continue

        use_meta = is_meta_whatsapp_primary(db, service_code=service_code, connection_profile_id=pid)
        for item in matches:
            record_id = str(item.get("id") or "").strip()
            try:
                if use_meta:
                    # Meta: name + hsm_id required together for single-language delete
                    MetaWhatsappTemplateService.delete_message_template(
                        db,
                        name=clean_name,
                        hsm_id=record_id or None,
                        service_code=service_code,
                        connection_profile_id=pid,
                    )
                elif record_id:
                    TelnyxWhatsappTemplateSyncService.delete_remote_template(
                        db, record_id, template_name=clean_name
                    )
                else:
                    continue
                deleted_on.append(label)
            except (TelnyxWhatsappTemplateSyncError, MetaWhatsappTemplateError) as exc:
                detail = str(exc).lower()
                if "404" in detail or "not found" in detail:
                    deleted_on.append(f"{label}_already_gone")
                else:
                    raise

    if (
        not profile_ids
        and primary_id
        and "meta_primary" not in deleted_on
        and "meta_primary_already_gone" not in deleted_on
    ):
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


def _build_preview_for_survey_row(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    remote_name: str,
    body_preview: str,
    local_row_id: Any,
) -> dict[str, Any]:
    components = _effective_components(row)
    old_body, _buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])
    industry_slug, industry_name = _industry_for_template_row(db, row)
    topic_name = _topic_for_template_row(db, row) or _topic_from_template_name(row.name)
    preview: dict[str, Any] = {
        "body_before": body_preview or old_body,
        "keeps_local_db_row": True,
        "local_row_id": local_row_id,
        "body_after": _rule_based_utility_body(
            old_body,
            topic_hint=topic_name,
            industry_slug=industry_slug,
            industry_name=industry_name,
            language=row.language,
        ),
    }
    from seed_data.wa_survey_template_naming import is_was_survey_name, suggest_next_was_seq_name

    if str(row.status or "").upper() in {"APPROVED", "PENDING"} and _has_remote_telnyx_id(row):
        used = {
            str(r[0]).strip().lower()
            for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
            if r[0]
        }
        if is_was_survey_name(row.name):
            preview["new_local_name"] = suggest_next_was_seq_name(row.name, used_names=used) or row.name
        else:
            preview["new_local_name"] = suggest_utility_clone_template_name(row.name) or f"{row.name}_utu"
    else:
        preview["new_local_name"] = row.name
    return preview


def _build_preview_for_feedback_row(
    db: Session,
    row: Any,
    *,
    remote_name: str,
    body_preview: str,
) -> dict[str, Any]:
    from app.services.customer_feedback.feedback_telnyx_push_service import (
        collect_used_cfs_meta_names,
        suggest_next_cfs_version_name,
    )

    from app.services.survey_wa_utility_rewrite_service import parse_cfs_meta_name

    old_body = str(row.body_text or body_preview or "").strip()
    cfs = parse_cfs_meta_name(remote_name)
    preview: dict[str, Any] = {
        "body_before": old_body,
        "keeps_local_db_row": True,
        "local_row_id": str(row.id),
        "body_after": _rule_based_utility_body(
            old_body,
            topic_hint=str(row.template_key or (cfs.get("topic") if cfs else "") or ""),
            industry_slug=cfs.get("industry") if cfs else None,
            language=str(getattr(row, "language", "") or (f"{cfs['lang']}_gb" if cfs else "")),
        ),
    }
    current = str(getattr(row, "meta_template_name", "") or remote_name).strip().lower()
    used = collect_used_cfs_meta_names(db)
    preview["new_local_name"] = suggest_next_cfs_version_name(current, used_names=used) or current
    return preview


def _append_rewrite_plan_item(
    plan: list[PurgePlanItem],
    *,
    item: dict[str, Any],
    row: TelnyxWhatsappTemplate | None,
    feedback_row: Any | None,
    preview: dict[str, Any],
) -> None:
    process_name = str(item.get("process_name") or item.get("name") or "")
    remote_name = str(item.get("remote_name") or process_name)
    product = str(item.get("product") or "survey")
    new_name = str(preview.get("new_local_name") or process_name)
    will_delete_old_remote = bool(remote_name and remote_name.lower() != new_name.lower())
    preview["delete_old_remote_name"] = remote_name if will_delete_old_remote else None
    preview["deletes"] = (
        f"Meta/Telnyx only: {remote_name}" if will_delete_old_remote else "nothing (same name update)"
    )
    if preview.get("body_after") and preview.get("body_before") == preview.get("body_after"):
        if not _body_has_recommend_intent(str(preview.get("body_before") or "")):
            preview["llm_on_apply"] = "Qwen may lightly rephrase on apply (preview is rule-based)"
    action: ActionKind = "feedback_rewrite_push" if product == "feedback" else "survey_rewrite_push"
    label = str(row.name if row is not None else (feedback_row.template_key if feedback_row else process_name))
    local_id = item.get("id") if row is not None else str(feedback_row.id) if feedback_row else item.get("id")
    plan.append(
        PurgePlanItem(
            action=action,
            product=product,
            label=label,
            old_meta_name=remote_name if will_delete_old_remote else None,
            new_meta_name=new_name,
            local_template_id=local_id,
            language=item.get("remote_language"),
            dry_preview=preview,
            meta={
                "reasons": item.get("reasons"),
                "remote_name": remote_name,
                "keeps_local_db_row": True,
            },
        )
    )


def build_marketing_purge_plan(
    db: Session,
    *,
    survey_only: bool = True,
    scope: str = "survey",
    include_customer_feedback: bool = False,
    delete_remote_orphans: bool = False,
) -> tuple[dict[str, Any], list[PurgePlanItem]]:
    """Build purge plan.

  ``scope=survey`` (default legacy): survey MARKETING templates only.
  ``scope=all_marketing``: all managed product MARKETING (was_*, voxbulk_survey_*, cfs_*).
    """
    plan: list[PurgePlanItem] = []
    all_marketing = str(scope or "").strip().lower() == "all_marketing" or (
        not survey_only and include_customer_feedback
    )
    overview: dict[str, Any] = {"survey_only": not all_marketing, "scope": scope}

    if all_marketing:
        marketing_overview, marketing_remote = discover_remote_marketing_templates(db)
        overview["marketing_remote"] = marketing_overview
    else:
        marketing_overview, marketing_remote = discover_remote_marketing_survey_templates(db)
        overview["survey_remote"] = marketing_overview

    for item in marketing_remote:
        if not item.get("actionable"):
            remote_name = str(item.get("remote_name") or item.get("name") or "")
            if delete_remote_orphans and remote_name:
                product = str(item.get("product") or "survey")
                delete_action: ActionKind = (
                    "feedback_delete_remote" if product == "feedback" else "survey_delete_remote"
                )
                plan.append(
                    PurgePlanItem(
                        action=delete_action,
                        product=product,
                        label=remote_name,
                        old_meta_name=remote_name,
                        language=item.get("remote_language"),
                        meta={
                            "reasons": item.get("reasons"),
                            "note": "remote_only_no_local_row",
                            "deletes": "meta_telnyx_only",
                        },
                    )
                )
            continue

        product = str(item.get("product") or "survey")
        process_name = str(item.get("process_name") or item.get("name") or "")
        remote_name = str(item.get("remote_name") or process_name)
        row = None
        feedback_row = None
        if product == "survey":
            if item.get("id"):
                row = db.get(TelnyxWhatsappTemplate, int(item["id"]))
            if row is None:
                row = _find_template_row(db, process_name)
            if row is None:
                continue
            preview = _build_preview_for_survey_row(
                db,
                row,
                remote_name=remote_name,
                body_preview=str(item.get("body_preview") or ""),
                local_row_id=item.get("id"),
            )
            _append_rewrite_plan_item(plan, item=item, row=row, feedback_row=None, preview=preview)
        elif product == "feedback":
            from app.models.customer_feedback import FeedbackWaTemplate
            from app.services.survey_wa_utility_rewrite_service import _find_feedback_row_for_remote_name

            fid = item.get("feedback_template_id") or item.get("id")
            if fid:
                feedback_row = db.get(FeedbackWaTemplate, str(fid))
            if feedback_row is None:
                feedback_row = _find_feedback_row_for_remote_name(db, remote_name)
            if feedback_row is None:
                continue
            preview = _build_preview_for_feedback_row(
                db,
                feedback_row,
                remote_name=remote_name,
                body_preview=str(item.get("body_preview") or ""),
            )
            _append_rewrite_plan_item(plan, item=item, row=None, feedback_row=feedback_row, preview=preview)

    overview["plan_counts"] = {
        "survey_rewrite_push": sum(1 for p in plan if p.action == "survey_rewrite_push"),
        "feedback_rewrite_push": sum(1 for p in plan if p.action == "feedback_rewrite_push"),
        "survey_delete_remote": sum(1 for p in plan if p.action == "survey_delete_remote"),
        "feedback_delete_remote": sum(1 for p in plan if p.action == "feedback_delete_remote"),
    }
    overview["total_items"] = len(plan)
    overview["push_items"] = sum(
        1 for p in plan if p.action in {"survey_rewrite_push", "feedback_rewrite_push"}
    )
    overview["local_db_rows_deleted"] = 0
    return overview, plan


def _row_for_plan_item(db: Session, item: PurgePlanItem) -> TelnyxWhatsappTemplate | None:
    if item.local_template_id is not None:
        row = db.get(TelnyxWhatsappTemplate, int(item.local_template_id))
        if row is not None:
            return row
    return _find_template_row(db, item.label)


def _ensure_meta_was_name_available(db: Session, row: TelnyxWhatsappTemplate) -> TelnyxWhatsappTemplate:
    """Bump was_* seq if this name already exists on Meta (e.g. after a prior failed push)."""
    from seed_data.wa_survey_template_naming import is_was_survey_name, suggest_next_was_seq_name

    if not is_was_survey_name(row.name):
        return row
    used = {
        str(r[0]).strip().lower()
        for r in db.execute(select(TelnyxWhatsappTemplate.name)).all()
        if r[0]
    }
    for _ in range(20):
        existing = MetaWhatsappTemplateService.find_template(
            db, name=str(row.name or ""), language=row.language
        )
        if not existing:
            return row
        nxt = suggest_next_was_seq_name(row.name, used_names=used)
        if not nxt or nxt.lower() == str(row.name or "").strip().lower():
            return row
        row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, nxt)
        used.add(nxt.lower())
    return row


def manifest_items_to_plan(manifest: dict[str, Any], *, approved_only: bool = True) -> list[PurgePlanItem]:
    plan: list[PurgePlanItem] = []
    for group in manifest.get("groups") or []:
        for item in group.get("items") or []:
            status = str(item.get("status") or "pending")
            if approved_only and status != "approved_push":
                continue
            action = str(item.get("action") or "survey_rewrite_push")
            plan.append(
                PurgePlanItem(
                    action=action,  # type: ignore[arg-type]
                    product=str(item.get("product") or "survey"),
                    label=str(item.get("label") or ""),
                    old_meta_name=item.get("delete_old_remote_name"),
                    new_meta_name=str(item.get("new_meta_name") or ""),
                    local_template_id=item.get("local_template_id"),
                    language=item.get("language"),
                    dry_preview={
                        "body_before": item.get("body_before"),
                        "body_after": item.get("body_after"),
                        "new_local_name": item.get("new_meta_name"),
                        "delete_old_remote_name": item.get("delete_old_remote_name"),
                        "rewritten": item.get("rewritten"),
                        "skip_reason": item.get("skip_reason"),
                        "keeps_local_db_row": True,
                        "local_row_id": item.get("local_template_id"),
                    },
                    meta={
                        "remote_name": item.get("remote_name"),
                        "batch_id": manifest.get("batch_id"),
                        "manifest_item": True,
                        "keeps_local_db_row": True,
                    },
                )
            )
    return plan


def _feedback_row_for_plan_item(db: Session, item: PurgePlanItem) -> Any | None:
    from app.models.customer_feedback import FeedbackWaTemplate

    if item.local_template_id is not None:
        row = db.get(FeedbackWaTemplate, str(item.local_template_id))
        if row is not None:
            return row
    from app.services.survey_wa_utility_rewrite_service import _find_feedback_row_for_remote_name

    remote = str(item.meta.get("remote_name") or item.old_meta_name or item.label)
    return _find_feedback_row_for_remote_name(db, remote)


def _rename_feedback_for_utility_push(db: Session, row: Any, new_meta_name: str) -> Any:
    from app.services.customer_feedback.feedback_telnyx_push_service import collect_used_cfs_meta_names

    target = str(new_meta_name or "").strip().lower()
    if not target or str(getattr(row, "meta_template_name", "") or "").strip().lower() == target:
        row.meta_category = "utility"
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    used = collect_used_cfs_meta_names(db)
    if target in used:
        raise SurveyWhatsappTemplateError(f"Feedback meta name already used: {target}")
    row.meta_template_name = target
    row.meta_category = "utility"
    row.telnyx_sync_status = "draft"
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _push_feedback_both_profiles(db: Session, row: Any) -> dict[str, Any]:
    from app.services.customer_feedback.feedback_telnyx_push_service import push_feedback_template_to_telnyx

    messages: list[str] = []
    for service_code in ("survey", "customer_feedback"):
        primary_id = WaTemplateProfilePushService.resolve_primary_connection_profile_id(
            db, service_code=service_code
        )
        backup_id = WaTemplateProfilePushService.resolve_backup_connection_profile_id(
            db, service_code=service_code
        )
        for pid in (primary_id, backup_id):
            if not pid:
                continue
            result = push_feedback_template_to_telnyx(
                db,
                row,
                connection_profile_id=pid,
                service_code=service_code,
                force_push=True,
            )
            messages.append(str(result.get("message") or "pushed"))
    return {"message": " | ".join(messages)}


def _rewrite_row_for_purge(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    use_llm: bool,
    llm_provider: str,
    llm_model: str | None = None,
    new_body_override: str | None = None,
) -> tuple[str, str]:
    body_text = _template_body_text(row)
    rule_only = not use_llm or _body_has_recommend_intent(body_text)
    if new_body_override is not None and str(new_body_override).strip():
        old_body, new_body = apply_utility_rewrite_to_row(
            db,
            row,
            use_llm=False,
            llm_provider=llm_provider,
            llm_model=llm_model,
            new_body_override=new_body_override,
        )
        return old_body, new_body
    old_body, new_body = apply_utility_rewrite_to_row(
        db,
        row,
        use_llm=not rule_only,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
    if use_llm and not rule_only and _normalize_leading_emoji_text(new_body) == _normalize_leading_emoji_text(old_body):
        old_body, new_body = apply_utility_rewrite_to_row(
            db,
            row,
            use_llm=True,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
    return old_body, new_body


def _format_push_error(exc: Exception) -> tuple[str, dict[str, Any]]:
    msg = str(exc)
    payload = getattr(exc, "payload", None) or {}
    if not isinstance(payload, dict):
        payload = {}
    extras: list[str] = []
    for key in ("meta_request_mode", "sync_branch", "meta_error_kind"):
        val = str(payload.get(key) or "").strip()
        if val:
            extras.append(f"{key}={val}")
    subcode = payload.get("meta_error_subcode")
    if subcode:
        extras.append(f"subcode={subcode}")
    provider_error = str(payload.get("provider_error") or "").strip()
    if provider_error:
        extras.append(provider_error[:400])
    if extras:
        msg = f"{msg} | {' | '.join(extras)}"
    return msg, payload


def apply_purge_plan_item(
    db: Session,
    item: PurgePlanItem,
    *,
    dry_run: bool,
    push: bool,
    sync_remote: bool,
    use_llm: bool,
    llm_provider: str = DEFAULT_UTILITY_LLM_PROVIDER,
    llm_model: str | None = DEFAULT_UTILITY_LLM_MODEL,
) -> dict[str, Any]:
    if dry_run:
        return {"ok": True, "dry_run": True, "action": item.action, "label": item.label}

    try:
        preview = item.dry_preview or {}
        body_override = str(preview.get("body_after") or "").strip() if item.meta.get("manifest_item") else None

        if item.action == "survey_rewrite_push":
            row = _row_for_plan_item(db, item)
            if row is None:
                return {"ok": False, "error": f"Local row not found: {item.label} (id={item.local_template_id})"}
            old_remote = str(item.meta.get("remote_name") or item.old_meta_name or row.name)
            if sync_remote and _has_remote_telnyx_id(row):
                refresh_row_from_telnyx(db, row)
                db.refresh(row)
            renamed_to: str | None = None
            if push:
                row, renamed_to = _prepare_approved_template_for_utility_push(db, row)
                if item.new_meta_name and str(row.name or "").lower() != str(item.new_meta_name).lower():
                    row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, str(item.new_meta_name))
                    renamed_to = str(item.new_meta_name)
            old_body, new_body = _rewrite_row_for_purge(
                db,
                row,
                use_llm=use_llm,
                llm_provider=llm_provider,
                llm_model=llm_model,
                new_body_override=body_override,
            )
            from app.services.wa_template_utility_lint import lint_utility_template

            components = _effective_components(row)
            _body, buttons = _extract_body_and_buttons(components if isinstance(components, list) else [])
            industry_slug, industry_name = _industry_for_template_row(db, row)
            employee = (industry_slug or "") == "employee_survey"
            lint = lint_utility_template(
                body=new_body,
                buttons=buttons,
                language=row.language,
                meta_category="utility",
                require_transaction_anchor=not employee,
            )
            if not lint.ok:
                msgs = "; ".join(i.message for i in lint.issues[:3])
                return {
                    "ok": False,
                    "action": item.action,
                    "label": item.label,
                    "error": f"Utility lint failed before push: {msgs}",
                    "new_body": new_body[:200],
                }
            pushed = False
            push_msg = ""
            if push:
                row = _ensure_meta_was_name_available(db, row)
                result = SurveyWhatsappTemplateService.push_to_telnyx(
                    db,
                    row,
                    force_approved_update=False,
                    skip_remote_link=True,
                )
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
                "local_db_deleted": False,
                "old_body": old_body,
                "new_body": new_body,
            }

        if item.action == "feedback_rewrite_push":
            from app.services.customer_feedback.feedback_wa_utility_rewrite_service import (
                apply_utility_rewrite_to_feedback_row,
            )

            row = _feedback_row_for_plan_item(db, item)
            if row is None:
                return {"ok": False, "error": f"Feedback row not found: {item.label} (id={item.local_template_id})"}
            old_remote = str(item.meta.get("remote_name") or item.old_meta_name or "")
            new_meta = str(item.new_meta_name or preview.get("new_local_name") or "")
            if push and new_meta:
                row = _rename_feedback_for_utility_push(db, row, new_meta)
            if body_override:
                row.body_text = body_override
                row.meta_category = "utility"
                db.add(row)
                db.commit()
                db.refresh(row)
                old_body = str(preview.get("body_before") or "")
                new_body = body_override
            else:
                old_body, new_body = apply_utility_rewrite_to_feedback_row(
                    db,
                    row,
                    use_llm=use_llm,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                )
            from app.services.wa_template_utility_lint import lint_utility_template
            from app.services.customer_feedback.feedback_telnyx_push_service import parse_feedback_buttons

            buttons = parse_feedback_buttons(row.buttons_json)
            lint = lint_utility_template(
                body=new_body,
                buttons=buttons,
                language=row.language,
                meta_category="utility",
                template_key=row.template_key,
            )
            if not lint.ok:
                msgs = "; ".join(i.message for i in lint.issues[:3])
                return {
                    "ok": False,
                    "action": item.action,
                    "label": item.label,
                    "error": f"Utility lint failed before push: {msgs}",
                    "new_body": new_body[:200],
                }
            pushed = False
            push_msg = ""
            if push:
                result = _push_feedback_both_profiles(db, row)
                pushed = True
                push_msg = str(result.get("message") or "pushed")
            delete_targets: list[str] = []
            current_name = str(getattr(row, "meta_template_name", "") or new_meta)
            if old_remote and old_remote.lower() != current_name.lower():
                delete_targets.append(old_remote)
            deleted_on: list[str] = []
            for target in delete_targets:
                for service_code in ("survey", "customer_feedback"):
                    deleted_on.extend(
                        delete_remote_template_by_name(
                            db,
                            name=target,
                            language=item.language,
                            service_code=service_code,
                        )
                    )
            return {
                "ok": True,
                "action": item.action,
                "label": item.label,
                "renamed_to": new_meta,
                "new_name": current_name,
                "pushed": pushed,
                "push_message": push_msg,
                "deleted_remote": deleted_on,
                "local_db_deleted": False,
                "old_body": old_body,
                "new_body": new_body,
            }

        if item.action in {"survey_delete_remote", "feedback_delete_remote"}:
            service_code = "customer_feedback" if item.action == "feedback_delete_remote" else "survey"
            deleted_on = delete_remote_template_by_name(
                db,
                name=str(item.old_meta_name or item.label),
                language=item.language,
                service_code=service_code,
            )
            if item.action == "feedback_delete_remote":
                deleted_on.extend(
                    delete_remote_template_by_name(
                        db,
                        name=str(item.old_meta_name or item.label),
                        language=item.language,
                        service_code="survey",
                    )
                )
            return {
                "ok": True,
                "action": item.action,
                "deleted_remote": deleted_on,
                "local_db_deleted": False,
            }

        return {"ok": False, "error": f"Unknown action {item.action}"}
    except (SurveyWhatsappTemplateError, TelnyxWhatsappTemplateSyncError, MetaWhatsappTemplateError) as exc:
        msg = str(exc)
        payload = getattr(exc, "payload", None) or {}
        provider_error = str(payload.get("provider_error") or "").strip()
        if provider_error:
            msg = f"{msg} | {provider_error[:500]}"
        return {"ok": False, "action": item.action, "label": item.label, "error": msg}
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
    llm_provider: str = DEFAULT_UTILITY_LLM_PROVIDER,
    llm_model: str | None = DEFAULT_UTILITY_LLM_MODEL,
    push_delay_seconds: float = 30.0,
    batch_id: str | None = None,
) -> list[dict[str, Any]]:
    from app.services.wa_marketing_review_service import update_manifest_item_status

    results: list[dict[str, Any]] = []
    push_actions = {"survey_rewrite_push", "feedback_rewrite_push"}
    last_push_at = 0.0
    total = len(plan)
    for index, item in enumerate(plan, start=1):
        is_push_action = item.action in push_actions
        if is_push_action and push and not dry_run:
            print(f"\n[{index}/{total}] START {item.label}", flush=True)
            if last_push_at > 0 and push_delay_seconds > 0:
                elapsed = time.time() - last_push_at
                wait = push_delay_seconds - elapsed
                if wait > 0:
                    print(f"    waiting {int(wait)}s before next Meta push…", flush=True)
                    time.sleep(wait)
        result = apply_purge_plan_item(
            db,
            item,
            dry_run=dry_run,
            push=push if is_push_action else False,
            sync_remote=sync_remote,
            use_llm=use_llm,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
        result["index"] = index
        result["total"] = total
        results.append(result)
        if batch_id and is_push_action and push and not dry_run:
            status = "pushed" if result.get("ok") else "failed"
            update_manifest_item_status(
                batch_id,
                local_template_id=item.local_template_id,
                label=item.label,
                status=status,
                error=str(result.get("error") or "") or None,
            )
        if is_push_action and push and not dry_run:
            if result.get("ok"):
                msg = f"OK  [{index}/{total}] {result.get('new_name') or item.label}"
                if result.get("deleted_remote"):
                    msg += f" | removed old: {item.old_meta_name}"
                print(msg, flush=True)
            else:
                print(f"FAIL [{index}/{total}] {item.label} — {result.get('error', 'unknown')}", flush=True)
        if is_push_action and push and not dry_run and result.get("ok"):
            last_push_at = time.time()
    return results
