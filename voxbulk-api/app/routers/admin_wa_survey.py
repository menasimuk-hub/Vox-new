"""Admin API — Platform Settings → WA Survey."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.survey_generation_service import SurveyGenerationService
from app.services.survey_type_service import SurveyTypeService, survey_type_to_dict
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    survey_template_to_dict,
)

router = APIRouter(prefix="/admin/wa-survey", tags=["admin-wa-survey"])


@router.get("/types")
def list_survey_types(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_INTEGRATION))):
    return {"ok": True, "types": SurveyTypeService.list_types(db)}


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
    return {"ok": True, "template": survey_template_to_dict(updated)}


@router.post("/templates/{template_id}/clone-anonymous")
def clone_anonymous_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    parent = SurveyWhatsappTemplateService.get_template(db, template_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        cloned = SurveyWhatsappTemplateService.clone_as_anonymous(db, parent)
    except SurveyWhatsappTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, "template": survey_template_to_dict(cloned)}


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return result


@router.post("/sync")
def sync_survey_templates(
    payload: dict | None = None,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    body = payload or {}
    try:
        summary = SurveyWhatsappTemplateService.sync_from_telnyx(
            db,
            survey_type_id=str(body.get("survey_type_id") or "").strip() or None,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
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
        result = SurveyGenerationService.generate(
            db,
            survey_type_id=str(payload.get("survey_type_id") or ""),
            variant=str(payload.get("variant") or "standard"),
            length=str(payload.get("length") or "standard"),
            goal=str(payload.get("goal") or ""),
            organisation_name=str(payload.get("organisation_name") or "Your business"),
            client_name=str(payload.get("client_name") or ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return result
