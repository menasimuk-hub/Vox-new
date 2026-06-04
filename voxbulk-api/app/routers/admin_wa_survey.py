"""Admin API — Platform Settings → WA Survey."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.survey_generation_service import SurveyGenerationService
from app.services.survey_type_service import SurveyTypeService, survey_type_to_dict
from app.services.survey_wa_template_pack_service import SurveyWaTemplatePackError, SurveyWaTemplatePackService
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    survey_template_to_dict,
)

router = APIRouter(prefix="/admin/wa-survey", tags=["admin-wa-survey"])


def _raise_wa_survey_error(exc: SurveyWhatsappTemplateError, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
    payload = exc.payload or {"message": str(exc)}
    code = status.HTTP_502_BAD_GATEWAY if payload.get("provider_error") and status_code == status.HTTP_400_BAD_REQUEST else status_code
    raise HTTPException(status_code=code, detail=payload) from exc


@router.get("/types")
def list_survey_types(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, "types": SurveyTypeService.list_types(db)}


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
    counts = SurveyTypeService._template_counts(db, row.id)
    return {"ok": True, "type": survey_type_to_dict(row, template_counts=counts)}


@router.get("/types/{type_id}")
def get_survey_type(type_id: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    row = SurveyTypeService.get_type(db, type_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Survey type not found")
    counts = SurveyTypeService._template_counts(db, row.id)
    templates = SurveyWhatsappTemplateService.list_for_survey_type(db, row.id)
    return {
        "ok": True,
        "type": survey_type_to_dict(row, template_counts=counts),
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
    try:
        return SurveyWaTemplatePackService.generate_pack(
            db,
            survey_type=row,
            purpose=str(body.get("purpose") or body.get("template_purpose") or "").strip(),
            instruction=str(body.get("instruction") or body.get("admin_instruction") or "").strip(),
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
        return SurveyWaTemplatePackService.save_selected_templates(db, survey_type=row, templates=templates)
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
        category=str(body.get("category") or "MARKETING"),
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
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return result
