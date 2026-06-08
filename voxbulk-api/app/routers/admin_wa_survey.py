"""Admin API — Platform Settings → WA Survey."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.survey_flow_definition_service import SurveyFlowDefinitionService, flow_definition_to_dict
from app.services.survey_outcome_template_service import SurveyOutcomeTemplateService
from app.services.survey_generation_service import SurveyGenerationService
from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import IndustryService, industry_to_dict
from app.services.survey_type_service import SurveyTypeService, survey_type_to_dict
from app.services.survey_type_template_service import SurveyTypeTemplateError, SurveyTypeTemplateService
from app.services.survey_picker_settings_service import SurveyPickerSettingsService
from app.services.survey_simulator_service import SurveySimulatorService
from app.services.survey_system_template_service import (
    SurveySystemTemplateError,
    SurveySystemTemplateService,
)
from app.services.survey_wa_observability_service import SurveyWaObservabilityService
from app.services.survey_wa_readiness_service import SurveyWaReadinessService
from app.services.survey_wa_test_pack_seed_service import SurveyWaTestPackSeedService
from app.services.survey_wa_template_pack_service import (
    SurveyWaTemplatePackError,
    SurveyWaTemplatePackService,
    clamp_pack_count,
)
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    survey_template_to_dict,
)

from app.services.wa_template_meta_sync import http_status_for_template_sync_error

router = APIRouter(prefix="/admin/wa-survey", tags=["admin-wa-survey"])


def _raise_wa_survey_error(exc: SurveyWhatsappTemplateError, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
    payload = exc.payload or {"message": str(exc)}
    if payload.get("meta_error_kind") or payload.get("requires_language_fix") or payload.get("requires_rename"):
        code = http_status_for_template_sync_error(payload)
    elif payload.get("provider_error") and status_code == status.HTTP_400_BAD_REQUEST:
        code = http_status_for_template_sync_error(payload)
    else:
        code = status_code
    raise HTTPException(status_code=code, detail=payload) from exc


@router.get("/overview")
def wa_survey_overview(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return IndustryService.wa_survey_overview(db)


@router.post("/templates/cleanup-retained-scopes")
def cleanup_wa_survey_templates(
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """Delete WA Survey templates except Global System Templates + Hospitality & food."""
    from app.services.survey_wa_template_cleanup_service import cleanup_wa_survey_templates

    body = payload or {}
    dry_run = bool(body.get("dry_run", True))
    return cleanup_wa_survey_templates(
        db,
        dry_run=dry_run,
        update_category_to_utility=bool(body.get("update_category_to_utility", True)),
    )


@router.get("/industries")
def list_industries(
    include_inactive: bool = False,
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    if include_inactive or include_hidden:
        return {
            "ok": True,
            "industries": IndustryService.list_industries_admin(
                db,
                include_inactive=include_inactive,
                include_hidden=include_hidden,
            ),
        }
    return {"ok": True, "industries": IndustryService.list_industries_selectable(db)}


@router.post("/industries")
def create_industry(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        row = IndustryService.create_industry(db, payload or {})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {
        "ok": True,
        "industry": industry_to_dict(row, survey_type_count=0),
    }


@router.get("/industries/{industry_id}")
def get_industry(
    industry_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = IndustryService.get_industry(db, industry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry not found")
    return {
        "ok": True,
        "industry": industry_to_dict(
            row,
            survey_type_count=IndustryService.survey_type_count(db, row.id),
        ),
    }


@router.put("/industries/{industry_id}")
def update_industry(
    industry_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = IndustryService.get_industry(db, industry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry not found")
    try:
        updated = IndustryService.update_industry(db, row, payload or {})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {
        "ok": True,
        "industry": industry_to_dict(
            updated,
            survey_type_count=IndustryService.survey_type_count(db, updated.id),
        ),
    }


@router.delete("/industries/{industry_id}")
def delete_industry(
    industry_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = IndustryService.get_industry(db, industry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry not found")
    try:
        return IndustryService.delete_industry(db, row)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/industries/{industry_id}/status")
def set_industry_status(
    industry_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = IndustryService.get_industry(db, industry_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Industry not found")
    body = payload or {}
    if "is_active" not in body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="is_active is required")
    try:
        updated = IndustryService.set_active(db, row, is_active=bool(body["is_active"]))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {
        "ok": True,
        "industry": industry_to_dict(
            updated,
            survey_type_count=IndustryService.survey_type_count(db, updated.id),
        ),
    }


@router.get("/types")
def list_survey_types(
    industry_id: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {"ok": True, "types": SurveyTypeService.list_types(db, industry_id=industry_id)}


@router.post("/types")
def create_survey_type(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        row = SurveyTypeService.create_type(db, payload or {})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except IntegrityError as e:
        if "survey_types" in str(e).lower() and "slug" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Survey type slug conflicts with an existing row. "
                    "Run database migrations (alembic upgrade head) so slugs are unique per industry, "
                    "or choose a different name."
                ),
            ) from e
        raise
    counts = SurveyTypeService._template_counts(db, row.id)
    industry = db.get(Industry, row.industry_id) if row.industry_id else None
    return {"ok": True, "type": survey_type_to_dict(row, template_counts=counts, industry=industry)}


@router.get("/types/{type_id}")
def get_survey_type(
    type_id: str,
    privacy_mode: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    counts = SurveyTypeService._template_counts(db, row.id)
    industry = db.get(Industry, row.industry_id) if row.industry_id else None
    templates = SurveyWhatsappTemplateService.list_for_survey_type(db, row.id, privacy_mode=privacy_mode)
    return {
        "ok": True,
        "type": survey_type_to_dict(row, template_counts=counts, industry=industry),
        "templates": templates,
    }


@router.put("/types/{type_id}")
def update_survey_type(
    type_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    updated = SurveyTypeService.update_type(db, row, payload)
    counts = SurveyTypeService._template_counts(db, updated.id)
    return {"ok": True, "type": survey_type_to_dict(updated, template_counts=counts)}


@router.post("/types/{type_id}/cleanup-template-links")
def cleanup_survey_type_template_links(
    type_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.survey_type_template_service import SurveyTypeTemplateService

    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    body = payload or {}
    dry_run = bool(body.get("dry_run"))
    result = SurveyTypeTemplateService.cleanup_mistaken_links(db, survey_type_id=type_id, dry_run=dry_run)
    counts = SurveyTypeService._template_counts(db, row.id)
    return {
        "ok": True,
        "survey_type_id": type_id,
        "dry_run": dry_run,
        **result,
        "template_count": int(counts.get("standard", 0) + counts.get("anonymous", 0)),
    }


@router.post("/types/{type_id}/templates/generate-pack")
def generate_template_pack(
    type_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    body = payload or {}
    template_count = clamp_pack_count(body.get("template_count") or body.get("count"))
    try:
        return SurveyWaTemplatePackService.generate_pack(
            db,
            survey_type=row,
            purpose=str(body.get("purpose") or body.get("template_purpose") or "").strip(),
            instruction=str(body.get("instruction") or body.get("admin_instruction") or "").strip(),
            privacy_mode=str(body.get("privacy_mode") or "off"),
            theme_variant=str(body.get("theme_variant") or body.get("category") or "").strip(),
            template_count=template_count,
            industry_id=str(body.get("industry_id") or "").strip() or None,
            org_id=str(body.get("org_id") or body.get("organisation_id") or "").strip() or None,
        )
    except SurveyWaTemplatePackError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/types/{type_id}/templates/save-pack")
def save_template_pack(
    type_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    templates = payload.get("templates") or payload.get("selected") or []
    if not isinstance(templates, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="templates must be an array")
    try:
        return SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=row,
            templates=templates,
            privacy_mode=str(payload.get("privacy_mode") or "off"),
            theme_variant=str(payload.get("theme_variant") or "").strip(),
            purpose=str(payload.get("purpose") or "").strip(),
            instruction=str(payload.get("instruction") or "").strip(),
            industry_id=str(payload.get("industry_id") or "").strip() or None,
            replace_step_bank=bool(payload.get("replace_step_bank")),
        )
    except SurveyWaTemplatePackError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/types/{type_id}/templates/regenerate-pack-item")
def regenerate_template_pack_item(
    type_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    body = payload or {}
    try:
        return SurveyWaTemplatePackService.regenerate_pack_item(
            db,
            survey_type=row,
            index=int(body.get("index", 0)),
            purpose=str(body.get("purpose") or body.get("template_purpose") or "").strip(),
            instruction=str(body.get("instruction") or body.get("admin_instruction") or "").strip(),
            slot_hint=str(body.get("slot_hint") or body.get("style") or "").strip(),
            current_template=body.get("current_template") if isinstance(body.get("current_template"), dict) else None,
            sibling_summaries=body.get("sibling_summaries") if isinstance(body.get("sibling_summaries"), list) else None,
            seen_names=body.get("seen_names") if isinstance(body.get("seen_names"), list) else None,
            privacy_mode=str(body.get("privacy_mode") or "off"),
            industry_id=str(body.get("industry_id") or "").strip() or None,
            org_id=str(body.get("org_id") or body.get("organisation_id") or "").strip() or None,
        )
    except SurveyWaTemplatePackError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e


@router.post("/types/{type_id}/templates/standard")
def create_standard_template(
    type_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    body = payload or {}
    template = SurveyWhatsappTemplateService.create_standard_draft(
        db,
        survey_type=row,
        language=str(body.get("language") or "en_US"),
        category=str(body.get("category") or "UTILITY"),
    )
    return {"ok": True, "template": survey_template_to_dict(template)}


@router.get("/templates")
def list_template_library(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, "templates": SurveyWhatsappTemplateService.list_library(db)}


@router.get("/templates/{template_id}")
def get_template_detail(template_id: int, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    detail = SurveyWhatsappTemplateService.get_template_detail(db, template_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {"ok": True, **detail}


@router.put("/templates/{template_id}/mappings")
def update_template_mappings(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return SurveyWhatsappTemplateService.update_template_mappings(
            db,
            template_id,
            list(payload.get("mappings") or payload.get("survey_types") or []),
        )
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e)


@router.post("/types/{type_id}/templates/link")
def link_existing_template(
    type_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.survey_type_template_service import SurveyTypeTemplateService

    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    try:
        template_id = int(payload.get("template_id"))
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="template_id is required") from e
    tpl = SurveyWhatsappTemplateService.get_template(db, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    usable_standard = bool(payload.get("usable_as_standard", True))
    usable_anonymous = bool(payload.get("usable_as_anonymous", False))
    mapping = SurveyTypeTemplateService.upsert_mapping(
        db,
        survey_type_id=type_id,
        template_id=template_id,
        usable_as_standard=usable_standard,
        usable_as_anonymous=usable_anonymous,
        is_default_standard=bool(payload.get("is_default_standard")),
        is_default_anonymous=bool(payload.get("is_default_anonymous")),
    )
    return {
        "ok": True,
        "template": survey_template_to_dict(
            tpl,
            mapping=mapping,
            linked_survey_type_count=SurveyTypeTemplateService.linked_survey_type_count(db, template_id),
        ),
    }


def _unlink_survey_type_template_impl(
    db: Session,
    *,
    type_id: str,
    template_id: int,
) -> dict:
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    tpl = db.get(TelnyxWhatsappTemplate, int(template_id))
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    mapping = db.execute(
        select(SurveyTypeTemplate).where(
            SurveyTypeTemplate.survey_type_id == type_id,
            SurveyTypeTemplate.template_id == int(template_id),
        )
    ).scalar_one_or_none()
    if mapping is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template is not linked to this survey type")
    try:
        result = SurveyWhatsappTemplateService.delete_template(db, tpl)
        from app.services.uk_compliance_audit_service import UkComplianceAuditService

        UkComplianceAuditService.record(
            db,
            event_type="template.deleted",
            resource_type="wa_survey_template",
            resource_id=str(template_id),
            detail={"survey_type_id": type_id, "telnyx_deleted": True},
        )
        return result
    except SurveyWhatsappTemplateError as e:
        payload = e.payload or {"message": str(e)}
        code = status.HTTP_502_BAD_GATEWAY if payload.get("provider_error") else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=payload) from e


@router.delete("/types/{type_id}/templates/{template_id}")
def delete_survey_type_template(
    type_id: str,
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return _unlink_survey_type_template_impl(db, type_id=type_id, template_id=template_id)


@router.post("/types/{type_id}/templates/{template_id}/unlink")
def unlink_survey_type_template(
    type_id: str,
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """POST alias for delete — same behaviour (remove from survey type step bank)."""
    return _unlink_survey_type_template_impl(db, type_id=type_id, template_id=template_id)


@router.put("/templates/{template_id}")
def save_template_draft(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    updated = SurveyWhatsappTemplateService.save_draft(db, row, payload)
    tpl = survey_template_to_dict(updated)
    return {
        "ok": True,
        "message": "Template saved",
        "local_status": tpl.get("local_status"),
        "sync_status": tpl.get("sync_status"),
        "template": tpl,
    }


@router.post("/templates/{template_id}/set-active")
def set_template_active_for_survey(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """Hide/show template in survey flows. Hidden templates can still sync to Telnyx."""
    row = SurveyWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    body = payload or {}
    if "active" in body:
        active = bool(body.get("active"))
    elif "active_for_survey" in body:
        active = bool(body.get("active_for_survey"))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Provide active or active_for_survey (boolean)."},
        )
    updated = SurveyWhatsappTemplateService.save_draft(db, row, {"active_for_survey": active})
    tpl = survey_template_to_dict(updated)
    message = (
        "Template enabled for surveys."
        if active
        else "Template hidden from surveys — you can still sync it to Telnyx."
    )
    return {"ok": True, "message": message, "template": tpl}


@router.post("/templates/{template_id}/refresh-telnyx-status")
def refresh_template_telnyx_status(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        return SurveyWhatsappTemplateService.refresh_telnyx_status(db, row)
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e)


@router.post("/templates/{template_id}/clone-anonymous")
def clone_anonymous_template(
    template_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    parent = SurveyWhatsappTemplateService.get_template(db, template_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    body = payload or {}
    try:
        cloned = SurveyWhatsappTemplateService.clone_as_anonymous(
            db,
            parent,
            survey_type_id=str(body.get("survey_type_id") or "").strip() or None,
        )
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e)
    return {"ok": True, "template": survey_template_to_dict(cloned)}


@router.post("/templates/{template_id}/send-test")
def send_template_test(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Template not found"})
    body = payload or {}
    try:
        return SurveyWhatsappTemplateService.send_test_template(
            db,
            row,
            to_number=str(body.get("to_number") or body.get("mobile") or ""),
            first_name=str(body.get("first_name") or "Alex"),
            business_name=str(body.get("business_name") or "Northgate Dental"),
        )
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e)


@router.post("/templates/{template_id}/push")
def push_template_to_telnyx(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e)
    return result


@router.post("/templates/{template_id}/rename-for-sync")
def rename_template_for_sync(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    new_name = str((payload or {}).get("new_name") or (payload or {}).get("name") or "").strip()
    if not new_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Provide new_name (lowercase Meta template name)."},
        )
    try:
        updated = SurveyWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e)
    tpl = survey_template_to_dict(updated)
    return {
        "ok": True,
        "message": f"Template renamed to {updated.name}. Save any edits, then sync to Telnyx.",
        "template": tpl,
        "template_name": updated.name,
    }


@router.post("/types/{type_id}/templates/push-all")
def push_all_templates_to_telnyx(
    type_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return SurveyWhatsappTemplateService.push_all_for_survey_type(db, type_id)
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e)


@router.post("/sync")
def sync_survey_templates(
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    summary = SurveyWhatsappTemplateService.sync_from_telnyx(
        db,
        survey_type_id=str(body.get("survey_type_id") or "").strip() or None,
    )
    return summary


@router.get("/templates/{template_id}/preview")
def preview_template(
    template_id: int,
    business_name: str = "Northgate Dental",
    first_name: str = "Alex",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = SurveyWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    preview = SurveyWhatsappTemplateService.build_preview(db, row, business_name=business_name, first_name=first_name)
    return {"ok": True, **preview}


@router.post("/generate-preview")
def generate_survey_preview(payload: dict, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    try:
        page_count = payload.get("page_count")
        selected = payload.get("selected_step_roles")
        branches = payload.get("flow_branches")
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=str(payload.get("survey_type_id") or ""),
            variant=str(payload.get("variant") or "standard"),
            length=str(payload.get("length") or "standard"),
            page_count=int(page_count) if page_count is not None else None,
            auto_select_steps=bool(payload.get("auto_select_steps", True)),
            selected_step_roles=[str(r) for r in selected] if isinstance(selected, list) else None,
            goal=str(payload.get("goal") or ""),
            organisation_name=str(payload.get("organisation_name") or "Your business"),
            client_name=str(payload.get("client_name") or ""),
            flow_engine=str(payload.get("flow_engine") or "").strip() or None,
            flow_definition_id=str(payload.get("flow_definition_id") or "").strip() or None,
            flow_branches=branches if isinstance(branches, list) else None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return result


@router.get("/types/{type_id}/outcome-templates")
def list_outcome_templates(
    type_id: str,
    privacy_mode: str = "off",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {
        "ok": True,
        "templates": SurveyOutcomeTemplateService.list_for_survey_type(
            db, survey_type_id=type_id, privacy_mode=privacy_mode
        ),
    }


@router.get("/types/{type_id}/flows")
def list_survey_flows(
    type_id: str,
    privacy_mode: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {
        "ok": True,
        "flows": SurveyFlowDefinitionService.list_for_survey_type(db, type_id, privacy_mode=privacy_mode),
    }


@router.post("/types/{type_id}/flows")
def create_survey_flow(
    type_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = dict(payload or {})
    body["survey_type_id"] = type_id
    try:
        row = SurveyFlowDefinitionService.create_draft(db, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    graph = SurveyFlowDefinitionService.load_graph(db, row.id)
    return {"ok": True, "flow": flow_definition_to_dict(row), "graph": graph}


@router.get("/flows/{flow_id}")
def get_survey_flow(
    flow_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    graph = SurveyFlowDefinitionService.load_graph(db, flow_id)
    if not graph:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flow not found")
    return {"ok": True, **graph}


@router.put("/flows/{flow_id}")
def update_survey_flow(
    flow_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        graph = SurveyFlowDefinitionService.replace_graph(db, flow_id, payload or {})
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, **graph}


@router.post("/flows/{flow_id}/validate")
def validate_survey_flow(
    flow_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    mq = body.get("max_question_visits")
    try:
        max_visits = int(mq) if mq is not None else 6
    except (TypeError, ValueError):
        max_visits = 6
    return SurveyFlowDefinitionService.validate(db, flow_id, max_question_visits=max_visits)


@router.post("/flows/{flow_id}/publish")
def publish_survey_flow(
    flow_id: str,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    try:
        mq = int(body.get("max_question_visits") or 6)
    except (TypeError, ValueError):
        mq = 6
    try:
        return SurveyFlowDefinitionService.publish(db, flow_id, max_question_visits=mq)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/test-pack/ensure")
def ensure_wa_survey_test_pack(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    """Seed Services / General / off local APPROVED templates (no OpenAI)."""
    return SurveyWaTestPackSeedService.ensure_test_pack(db)


@router.get("/picker-settings")
def get_picker_settings(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {"ok": True, **SurveyPickerSettingsService.get_settings(db)}


@router.put("/picker-settings")
def update_picker_settings(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    return {
        "ok": True,
        **SurveyPickerSettingsService.update_settings(
            db,
            ai_picker_enabled=bool(body.get("ai_picker_enabled", True)),
        ),
    }


@router.get("/types/{type_id}/readiness")
def get_survey_type_readiness(
    type_id: str,
    privacy_mode: str = "off",
    variant: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    st = SurveyTypeService.get_type(db, type_id)
    if st is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    return {
        "ok": True,
        **SurveyWaReadinessService.readiness(
            db,
            survey_type_id=type_id,
            privacy_mode=privacy_mode,
            variant=variant,
        ),
    }


@router.get("/types/{type_id}/outcome-matrix")
def get_survey_outcome_matrix(
    type_id: str,
    privacy_mode: str = "off",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    st = SurveyTypeService.get_type(db, type_id)
    if st is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    return {
        "ok": True,
        "survey_type_id": type_id,
        "privacy_mode": privacy_mode,
        "matrix": SurveyWaReadinessService.build_outcome_matrix(
            db, survey_type=st, privacy_mode=privacy_mode
        ),
    }


@router.get("/sessions")
def list_wa_survey_sessions(
    order_id: str | None = None,
    org_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {
        "ok": True,
        **SurveyWaObservabilityService.list_sessions(
            db,
            order_id=order_id,
            org_id=org_id,
            status=status,
            limit=limit,
        ),
    }


@router.get("/sessions/{session_id}")
def get_wa_survey_session(
    session_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    detail = SurveyWaObservabilityService.get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"ok": True, **detail}


@router.post("/voice-notes/{job_id}/retry")
def retry_voice_note_transcription(
    job_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from app.services.survey_wa_voice_note_service import SurveyWaVoiceNoteService

    try:
        return {"ok": True, **SurveyWaVoiceNoteService.retry_job(db, job_id)}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/voice-notes/{job_id}/audio")
def download_voice_note_audio(
    job_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    from pathlib import Path

    from fastapi.responses import FileResponse

    from app.models.survey_voice_note_job import SurveyVoiceNoteJob

    job = db.get(SurveyVoiceNoteJob, job_id)
    if job is None or not job.audio_file_path or job.audio_deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note audio not found")
    path = Path(str(job.audio_file_path))
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice note audio file missing")
    media_type = str(job.audio_mime_type or "audio/ogg")
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.get("/observability/overview")
def wa_survey_observability_overview(
    order_id: str | None = None,
    org_id: str | None = None,
    survey_type_id: str | None = None,
    since_days: int = 7,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return {
        "ok": True,
        **SurveyWaObservabilityService.overview(
            db,
            order_id=order_id,
            org_id=org_id,
            survey_type_id=survey_type_id,
            since_days=since_days,
        ),
    }


@router.get("/types/{type_id}/simulator-prefill")
def simulator_prefill_for_type(
    type_id: str,
    privacy_mode: str = "off",
    industry_id: str | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return SurveySimulatorService.prefill_for_survey_type(
            db,
            survey_type_id=type_id,
            privacy_mode=privacy_mode,
            industry_id=industry_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/simulator/options")
def simulator_options(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return SurveySimulatorService.list_options(db)


@router.post("/simulator/start")
def simulator_start(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    try:
        roles = body.get("selected_step_roles")
        branches = body.get("flow_branches")
        return SurveySimulatorService.start(
            db,
            survey_type_id=str(body.get("survey_type_id") or ""),
            privacy_mode=str(body.get("privacy_mode") or "off"),
            flow_engine=str(body.get("flow_engine") or "linear"),
            page_count=int(body.get("page_count") or 6),
            selected_step_roles=[str(r) for r in roles] if isinstance(roles, list) else None,
            flow_branches=branches if isinstance(branches, list) else None,
            force_outcome_text_fallback=bool(body.get("force_outcome_text_fallback")),
            ai_picker_enabled=bool(body.get("ai_picker_enabled")),
            simulator_mock_picker=bool(body.get("simulator_mock_picker", True)),
            flow_definition_id=str(body.get("flow_definition_id") or "").strip() or None,
            skip_test_pack_seed=bool(body.get("skip_test_pack_seed", True)),
            test_phone=str(body.get("test_phone") or body.get("mobile_number") or "").strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.post("/simulator/answer")
def simulator_answer(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    try:
        return SurveySimulatorService.answer(
            db,
            recipient_id=str(body.get("recipient_id") or ""),
            answer=str(body.get("answer") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.get("/simulator/state/{recipient_id}")
def simulator_state(
    recipient_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return SurveySimulatorService.get_state(db, recipient_id=recipient_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/system-templates")
def list_system_templates(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        return SurveySystemTemplateService.list_grouped_admin(db)
    except SurveySystemTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported system_template_kind configuration: {e}",
        ) from e


@router.post("/system-templates")
def create_system_template(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    kind = str(body.get("system_template_kind") or body.get("kind") or "").strip()
    if not kind:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="system_template_kind is required (welcome, thank_you, tell_us_more, final_feedback).",
        )
    try:
        return SurveySystemTemplateService.create_draft(db, kind=kind, payload=body)
    except SurveySystemTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported system_template_kind configuration: {e}",
        ) from e


@router.post("/system-templates/generate")
def generate_system_templates(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    kind = str(body.get("system_template_kind") or body.get("kind") or "").strip()
    if not kind:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system_template_kind is required.")
    try:
        count = int(body.get("count") or body.get("template_count") or 1)
    except (TypeError, ValueError):
        count = 1
    try:
        return SurveySystemTemplateService.generate_with_openai(
            db,
            kind=kind,
            instruction=str(body.get("instruction") or body.get("admin_instruction") or "").strip(),
            count=count,
        )
    except SurveySystemTemplateError as e:
        msg = str(e)
        status_code = (
            status.HTTP_400_BAD_REQUEST
            if "invalid_json_schema" in msg or "strict schema invalid" in msg
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(status_code=status_code, detail=msg) from e
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported system_template_kind configuration: {e}",
        ) from e


@router.post("/system-templates/save-generated")
def save_generated_system_templates(
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    kind = str(body.get("system_template_kind") or body.get("kind") or "").strip()
    if not kind:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="system_template_kind is required.")
    templates = body.get("templates") or body.get("selected") or []
    if not isinstance(templates, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="templates must be an array.")
    try:
        return SurveySystemTemplateService.save_generated(
            db,
            kind=kind,
            templates=templates,
            instruction=str(body.get("instruction") or "").strip(),
        )
    except SurveySystemTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


@router.delete("/system-templates/{template_id}")
def delete_system_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    try:
        tpl = SurveySystemTemplateService.template_belongs_to_kind(db, template_id)
        st = db.get(SurveyType, str(tpl.survey_type_id or ""))
        result = SurveySystemTemplateService.delete_template(db, template_id)
        result["system_template_kind"] = st.system_template_kind if st else None
        return result
    except SurveySystemTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except SurveyWhatsappTemplateError as e:
        _raise_wa_survey_error(e, status_code=status.HTTP_502_BAD_GATEWAY)
