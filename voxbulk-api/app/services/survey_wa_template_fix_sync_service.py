"""Repair, utility-rewrite, and push/link a single WA Survey template (admin Fix & Sync)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_template_guard_service import should_skip_utility_rewrite
from app.services.survey_wa_utility_rewrite_service import (
    _prepare_approved_template_for_utility_push,
    apply_utility_rewrite_to_row,
)
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _dumps,
    _example_values_for_storage,
    _loads,
    _meta_example_is_valid,
    _normalize_draft_components,
    _refresh_local_sync_status,
    _resolve_push_language,
    _try_link_existing_remote_template,
    survey_template_to_dict,
    template_row_has_buttons,
)
from app.services.wa_template_meta_sync import format_template_push_error

_LOCAL_ID_PREFIX = "local-"


def _body_example_invalid(components: list) -> bool:
    for comp in components:
        if not isinstance(comp, dict):
            continue
        if str(comp.get("type") or "").upper() != "BODY":
            continue
        example = comp.get("example")
        if example is None:
            return False
        return not _meta_example_is_valid(example, field="body_text")
    return False


def repair_template_draft_row(row: TelnyxWhatsappTemplate) -> bool:
    draft = _loads(row.draft_components_json)
    if not isinstance(draft, list) or not draft:
        return False
    normalized = _normalize_draft_components(draft)
    changed = json.dumps(normalized, sort_keys=True) != json.dumps(draft, sort_keys=True)
    had_invalid = _body_example_invalid(draft)
    if not changed and not had_invalid:
        return False
    row.draft_components_json = _dumps(normalized)
    row.example_values_json = _dumps(_example_values_for_storage(normalized))
    row.local_sync_status = _refresh_local_sync_status(row)
    return True


def _reset_stale_approved_local_row(row: TelnyxWhatsappTemplate) -> bool:
    """Clear ghost APPROVED status when telnyx_record_id is still local-only."""
    status = str(row.status or "").upper()
    rid = str(row.telnyx_record_id or "").strip()
    if status != "APPROVED":
        return False
    if rid and not rid.startswith(_LOCAL_ID_PREFIX) and not rid.startswith("local_test_"):
        return False
    row.status = "LOCAL_DRAFT"
    row.last_push_error = None
    return True


def sync_survey_template_from_sibling_meta_owner(db: Session, row: TelnyxWhatsappTemplate) -> TelnyxWhatsappTemplate | None:
    """When another row with the same Meta name already owns the remote id, mirror its Meta fields."""
    name = str(row.name or "").strip()
    if not name:
        return None
    owner = db.execute(
        select(TelnyxWhatsappTemplate)
        .where(
            TelnyxWhatsappTemplate.name == name,
            TelnyxWhatsappTemplate.id != row.id,
            TelnyxWhatsappTemplate.telnyx_record_id.isnot(None),
            ~TelnyxWhatsappTemplate.telnyx_record_id.like("local-%"),
            ~TelnyxWhatsappTemplate.telnyx_record_id.like("local_test_%"),
        )
        .limit(1)
    ).scalar_one_or_none()
    if owner is None:
        return None
    row.status = owner.status or row.status
    row.category = owner.category or row.category
    if owner.components_json:
        row.components_json = owner.components_json
    if owner.body_preview:
        row.body_preview = owner.body_preview
    row.local_sync_status = _refresh_local_sync_status(row)
    row.last_push_error = None
    db.add(row)
    db.commit()
    db.refresh(row)
    return owner


def fix_and_sync_survey_template(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    repair: bool = True,
    utility_rewrite: bool = False,
    force_push: bool = True,
) -> dict[str, Any]:
    """Repair draft, optional UTILITY rewrite, push to Meta; link or sibling-sync on conflict."""
    steps: list[str] = []
    renamed_from: str | None = None

    if repair and repair_template_draft_row(row):
        steps.append("repaired_draft")
        db.add(row)
        db.commit()
        db.refresh(row)

    if _reset_stale_approved_local_row(row):
        steps.append("reset_stale_approved")
        db.add(row)
        db.commit()
        db.refresh(row)

    if utility_rewrite and not should_skip_utility_rewrite(db, row) and template_row_has_buttons(row):
        row, renamed_to = _prepare_approved_template_for_utility_push(db, row)
        if renamed_to:
            renamed_from = str(row.name)
            steps.append(f"prepared_clone:{renamed_to}")
        apply_utility_rewrite_to_row(db, row, use_llm=True, llm_provider="openai")
        steps.append("utility_rewrite")
        db.refresh(row)

    def _push() -> dict[str, Any]:
        return SurveyWhatsappTemplateService.push_to_telnyx(db, row, force_approved_update=force_push)

    try:
        push_result = _push()
        steps.append("push")
        db.refresh(row)
        return {
            "ok": True,
            "action": "pushed",
            "message": str(push_result.get("sync_message") or push_result.get("message") or "Pushed to Meta"),
            "steps": steps,
            "renamed_from": renamed_from,
            "template": survey_template_to_dict(row),
            "push": push_result,
        }
    except SurveyWhatsappTemplateError as exc:
        from app.services.survey_wa_template_clone_push_service import maybe_clone_and_push_on_meta_error

        cloned = maybe_clone_and_push_on_meta_error(db, row, exc, force_push=force_push)
        if cloned is not None:
            cloned["steps"] = steps + ["cloned_and_pushed"]
            return cloned

        payload = getattr(exc, "payload", None) or {}
        if payload.get("requires_rename") and payload.get("suggested_template_name"):
            new_name = str(payload["suggested_template_name"]).strip()
            row = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
            renamed_from = renamed_from or new_name
            steps.append(f"renamed:{new_name}")
            push_result = _push()
            steps.append("push")
            db.refresh(row)
            return {
                "ok": True,
                "action": "renamed_and_pushed",
                "message": f"Renamed to {row.name} and pushed to Meta",
                "steps": steps,
                "renamed_from": renamed_from,
                "template": survey_template_to_dict(row),
                "push": push_result,
            }

        if payload.get("meta_error_kind") == "content_already_exists":
            lang_code, _ = _resolve_push_language(db, row)
            if lang_code and _try_link_existing_remote_template(db, row, language=lang_code):
                steps.append("linked_existing")
                db.commit()
                db.refresh(row)
                return {
                    "ok": True,
                    "action": "linked",
                    "message": "Linked to existing Meta template",
                    "steps": steps,
                    "template": survey_template_to_dict(row),
                }
            owner = sync_survey_template_from_sibling_meta_owner(db, row)
            if owner is not None:
                steps.append("synced_from_sibling_owner")
                return {
                    "ok": True,
                    "action": "synced_sibling",
                    "message": (
                        f"Template name already on Meta (row id={owner.id}); "
                        "synced approval status from sibling row"
                    ),
                    "steps": steps,
                    "sibling_template_id": owner.id,
                    "template": survey_template_to_dict(row),
                }

        err = format_template_push_error(exc)
        raise SurveyWhatsappTemplateError(
            err,
            payload={
                **payload,
                "message": err,
                "steps": steps,
                "template_name": row.name,
            },
        ) from exc
