"""User-triggered clone + push when Meta blocks in-place updates on APPROVED templates."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.models.survey_flow import SurveyFlowNode, SurveyFlowOutcome
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_whatsapp_template_service import (
    SYNC_BRANCH_APPROVED_UPDATE,
    SYNC_DRAFT,
    SYNC_LOCAL_CHANGES,
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    _body_preview,
    _dumps,
    _effective_components,
    _loads,
    _now,
    resolve_template_sync_branch,
    survey_template_to_dict,
)
from app.services.wa_template_meta_sync import (
    META_ERROR_CANNOT_UPDATE_CATEGORY,
    parse_meta_error_from_provider_detail,
    suggest_utility_clone_template_name,
)

logger = logging.getLogger(__name__)

_LOCAL_ID_PREFIX = "local-"


def _unique_clone_name(db: Session, base_name: str) -> str:
    candidate = suggest_utility_clone_template_name(base_name)
    if not db.execute(
        select(TelnyxWhatsappTemplate.id).where(TelnyxWhatsappTemplate.name == candidate).limit(1)
    ).scalar_one_or_none():
        return candidate
    stem = candidate[:100].rstrip("_")
    for idx in range(2, 100):
        alt = f"{stem}_{idx}"[:128]
        if not db.execute(
            select(TelnyxWhatsappTemplate.id).where(TelnyxWhatsappTemplate.name == alt).limit(1)
        ).scalar_one_or_none():
            return alt
    raise SurveyWhatsappTemplateError(f"Could not allocate a unique clone name for {base_name!r}")


def relink_template_references(db: Session, old_id: int, new_id: int) -> dict[str, int]:
    counts = {"mappings": 0, "flow_nodes": 0, "flow_outcomes": 0, "service_orders": 0}

    for mapping in db.execute(
        select(SurveyTypeTemplate).where(SurveyTypeTemplate.template_id == old_id)
    ).scalars().all():
        mapping.template_id = new_id
        counts["mappings"] += 1

    for node in db.execute(
        select(SurveyFlowNode).where(SurveyFlowNode.template_id == old_id)
    ).scalars().all():
        node.template_id = new_id
        counts["flow_nodes"] += 1

    for outcome in db.execute(
        select(SurveyFlowOutcome).where(SurveyFlowOutcome.template_id == old_id)
    ).scalars().all():
        outcome.template_id = new_id
        counts["flow_outcomes"] += 1

    for order in db.execute(select(ServiceOrder).where(ServiceOrder.config_json.isnot(None))).scalars().all():
        raw = str(order.config_json or "").strip()
        if not raw:
            continue
        try:
            config = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(config, dict):
            continue
        changed = False
        for key in ("wa_template_id", "welcome_template_id"):
            val = config.get(key)
            if val is not None and int(val) == int(old_id):
                config[key] = int(new_id)
                changed = True
        if changed:
            order.config_json = json.dumps(config, ensure_ascii=False)
            counts["service_orders"] += 1

    return counts


def _clone_row_from_draft(
    db: Session,
    source: TelnyxWhatsappTemplate,
    *,
    clone_name: str,
) -> TelnyxWhatsappTemplate:
    components = _effective_components(source)
    if not components:
        raise SurveyWhatsappTemplateError("Template has no draft content to clone")
    now = _now()
    local_id = f"{_LOCAL_ID_PREFIX}{uuid.uuid4().hex}"
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=local_id,
        template_id=local_id,
        name=clone_name,
        display_name=source.display_name or source.name,
        customer_description=source.customer_description,
        language=source.language,
        category="UTILITY",
        status="LOCAL_DRAFT",
        sales_template_key=source.sales_template_key,
        body_preview=_body_preview(components) or source.body_preview,
        draft_components_json=_dumps(components),
        example_values_json=source.example_values_json,
        waba_id=source.waba_id,
        industry_id=source.industry_id,
        survey_type_id=source.survey_type_id,
        variant_type=source.variant_type,
        step_role=source.step_role,
        outcome_key=source.outcome_key,
        outcome_variables_json=source.outcome_variables_json,
        privacy_mode=source.privacy_mode,
        pack_id=source.pack_id,
        parent_template_id=int(source.id),
        local_sync_status=SYNC_LOCAL_CHANGES,
        active_for_survey=True,
        active_for_interview=source.active_for_interview,
        active_for_appointment=source.active_for_appointment,
        created_at=now,
        updated_at=now,
        synced_at=now,
    )
    db.add(row)
    db.flush()
    return row


def deactivate_superseded_row(db: Session, old_row: TelnyxWhatsappTemplate) -> None:
    old_row.active_for_survey = False
    old_row.local_sync_status = SYNC_DRAFT
    old_row.updated_at = _now()
    db.add(old_row)


def needs_clone_for_push(row: TelnyxWhatsappTemplate, raw_components: list[Any]) -> bool:
    branch, _ = resolve_template_sync_branch(row, raw_components)
    return branch == SYNC_BRANCH_APPROVED_UPDATE


def clone_and_push_survey_template(
    db: Session,
    row: TelnyxWhatsappTemplate,
    *,
    force_push: bool = True,
) -> dict[str, Any]:
    """Clone from DB draft, relink references, push new row to Meta; deactivate old row."""
    raw_components = _effective_components(row)
    if not raw_components:
        raise SurveyWhatsappTemplateError("Template has no components to push")

    old_id = int(row.id)
    old_name = str(row.name or "")
    clone_name = _unique_clone_name(db, old_name)
    new_row = _clone_row_from_draft(db, row, clone_name=clone_name)
    relink_counts = relink_template_references(db, old_id, int(new_row.id))
    deactivate_superseded_row(db, row)
    db.commit()
    db.refresh(new_row)
    db.refresh(row)

    try:
        push_result = SurveyWhatsappTemplateService.push_to_telnyx(
            db,
            new_row,
            force_approved_update=force_push,
            allow_clone=False,
        )
    except SurveyWhatsappTemplateError:
        db.rollback()
        raise

    return {
        "ok": True,
        "action": "cloned_and_pushed",
        "message": (
            f"Cloned to {new_row.name} and submitted to Meta. "
            "The previous template will be removed when Meta approves the new one."
        ),
        "superseded_template_id": old_id,
        "superseded_template_name": old_name,
        "template": survey_template_to_dict(new_row),
        "push": push_result,
        "relink": relink_counts,
    }


def maybe_clone_and_push_on_meta_error(
    db: Session,
    row: TelnyxWhatsappTemplate,
    exc: SurveyWhatsappTemplateError,
    *,
    force_push: bool = True,
) -> dict[str, Any] | None:
    """Never create a second DB row — fix-and-sync uses same-row rename instead."""
    _ = (db, row, exc, force_push)
    return None
