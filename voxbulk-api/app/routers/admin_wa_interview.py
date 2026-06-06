"""Platform Settings → WA Interview templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.interview_whatsapp_template_service import (
    InterviewWhatsappTemplateError,
    InterviewWhatsappTemplateService,
    interview_template_to_dict,
)

from app.services.wa_template_meta_sync import http_status_for_template_sync_error

router = APIRouter(prefix="/admin/wa-interview", tags=["admin-wa-interview"])


def _raise_interview_error(exc: InterviewWhatsappTemplateError, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
    payload = exc.payload or {"message": str(exc)}
    if payload.get("meta_error_kind") or payload.get("requires_language_fix") or payload.get("requires_rename"):
        code = http_status_for_template_sync_error(payload)
    elif payload.get("provider_error") and status_code == status.HTTP_400_BAD_REQUEST:
        code = http_status_for_template_sync_error(payload)
    else:
        code = status_code
    raise HTTPException(status_code=code, detail=payload) from exc


@router.get("/templates")
def list_interview_templates(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    templates = InterviewWhatsappTemplateService.list_templates(db)
    return {"ok": True, "templates": templates}


@router.get("/templates/{template_id}")
def get_interview_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    tpl = InterviewWhatsappTemplateService.get_template_detail(db, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {"ok": True, "template": tpl}


@router.put("/templates/{template_id}")
def save_interview_template_draft(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = InterviewWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    updated = InterviewWhatsappTemplateService.save_draft(db, row, payload)
    tpl = interview_template_to_dict(updated)
    return {
        "ok": True,
        "message": "Template saved",
        "local_status": tpl.get("local_status"),
        "sync_status": tpl.get("sync_status"),
        "template": tpl,
    }


@router.post("/templates/{template_id}/set-active")
def set_interview_template_active(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = InterviewWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    body = payload or {}
    if "active" in body:
        active = bool(body.get("active"))
    elif "active_for_interview" in body:
        active = bool(body.get("active_for_interview"))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Provide active or active_for_interview (boolean)."},
        )
    updated = InterviewWhatsappTemplateService.save_draft(db, row, {"active_for_interview": active})
    tpl = interview_template_to_dict(updated)
    message = (
        "Template enabled for AI Interview."
        if active
        else "Template hidden from AI Interview — you can still sync it to Telnyx."
    )
    return {"ok": True, "message": message, "template": tpl}


@router.post("/templates/{template_id}/push")
def push_interview_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = InterviewWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        result = InterviewWhatsappTemplateService.push_to_telnyx(db, row)
        tpl = interview_template_to_dict(row)
        return {**result, "template": tpl}
    except InterviewWhatsappTemplateError as exc:
        _raise_interview_error(exc)


@router.post("/templates/{template_id}/rename-for-sync")
def rename_interview_template_for_sync(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = InterviewWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    new_name = str((payload or {}).get("new_name") or (payload or {}).get("name") or "").strip()
    if not new_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Provide new_name (lowercase Meta template name)."},
        )
    try:
        updated = InterviewWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
    except InterviewWhatsappTemplateError as exc:
        _raise_interview_error(exc)
    tpl = interview_template_to_dict(updated)
    return {
        "ok": True,
        "message": f"Template renamed to {updated.name}. Save any edits, then sync to Telnyx.",
        "template": tpl,
        "template_name": updated.name,
    }


@router.post("/templates/{template_id}/refresh-telnyx-status")
def refresh_interview_template_status(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = InterviewWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        return InterviewWhatsappTemplateService.refresh_telnyx_status(db, row)
    except InterviewWhatsappTemplateError as exc:
        _raise_interview_error(exc)


@router.post("/sync")
def sync_interview_templates_from_telnyx(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return InterviewWhatsappTemplateService.sync_from_telnyx(db)


@router.get("/templates/{template_id}/preview")
def preview_interview_template(
    template_id: int,
    first_name: str = "James",
    business_name: str = "menasim",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = InterviewWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    preview = InterviewWhatsappTemplateService.build_preview(
        db,
        row,
        first_name=first_name,
        business_name=business_name,
    )
    return {"ok": True, "preview": preview, "template": interview_template_to_dict(row)}


@router.delete("/templates/{template_id}")
def delete_interview_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = InterviewWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        return InterviewWhatsappTemplateService.delete_template(db, row)
    except InterviewWhatsappTemplateError as exc:
        _raise_interview_error(exc)
