"""Admin API for AI Demo WhatsApp templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.demo_whatsapp_template_service import (
    DemoWhatsappTemplateError,
    DemoWhatsappTemplateService,
    demo_template_to_dict,
)

from app.services.wa_template_meta_sync import http_status_for_template_sync_error

router = APIRouter(prefix="/admin/wa-demo", tags=["admin-wa-demo"])


def _raise_demo_error(exc: DemoWhatsappTemplateError, *, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
    payload = exc.payload or {"message": str(exc)}
    if payload.get("meta_error_kind") or payload.get("requires_language_fix") or payload.get("requires_rename"):
        code = http_status_for_template_sync_error(payload)
    elif payload.get("provider_error") and status_code == status.HTTP_400_BAD_REQUEST:
        code = http_status_for_template_sync_error(payload)
    else:
        code = status_code
    raise HTTPException(status_code=code, detail=payload) from exc


@router.get("/templates")
def list_demo_templates(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    templates = DemoWhatsappTemplateService.list_templates(db)
    return {"ok": True, "templates": templates}


@router.get("/templates/{template_id}")
def get_demo_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    tpl = DemoWhatsappTemplateService.get_template_detail(db, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {"ok": True, "template": tpl}


@router.put("/templates/{template_id}")
def save_demo_template_draft(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = DemoWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    updated = DemoWhatsappTemplateService.save_draft(db, row, payload)
    tpl = demo_template_to_dict(updated)
    return {
        "ok": True,
        "message": "Template saved",
        "local_status": tpl.get("local_status"),
        "sync_status": tpl.get("sync_status"),
        "template": tpl,
    }


@router.post("/templates/{template_id}/set-active")
def set_demo_template_active(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = DemoWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    body = payload or {}
    if "active" in body:
        active = bool(body.get("active"))
    elif "active_for_demo" in body:
        active = bool(body.get("active_for_demo"))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Provide active or active_for_demo (boolean)."},
        )
    updated = DemoWhatsappTemplateService.save_draft(db, row, {"active_for_demo": active})
    tpl = demo_template_to_dict(updated)
    message = (
        "Template enabled for AI Demo."
        if active
        else "Template hidden from AI Demo â€” you can still push it to Meta."
    )
    return {"ok": True, "message": message, "template": tpl}


@router.post("/templates/{template_id}/push")
def push_demo_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = DemoWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        result = DemoWhatsappTemplateService.push_to_telnyx(db, row)
        tpl = demo_template_to_dict(row)
        return {**result, "template": tpl}
    except DemoWhatsappTemplateError as exc:
        _raise_demo_error(exc)


@router.post("/templates/{template_id}/rename-for-sync")
def rename_demo_template_for_sync(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = DemoWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    new_name = str((payload or {}).get("new_name") or (payload or {}).get("name") or "").strip()
    if not new_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Provide new_name (lowercase Meta template name)."},
        )
    try:
        updated = DemoWhatsappTemplateService.rename_for_meta_sync(db, row, new_name)
    except DemoWhatsappTemplateError as exc:
        _raise_demo_error(exc)
    tpl = demo_template_to_dict(updated)
    return {
        "ok": True,
        "message": f"Template renamed to {updated.name}. Save any edits, then push to Meta.",
        "template": tpl,
        "template_name": updated.name,
    }


@router.post("/templates/{template_id}/refresh-telnyx-status")
def refresh_demo_template_status(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = DemoWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        return DemoWhatsappTemplateService.refresh_telnyx_status(db, row)
    except DemoWhatsappTemplateError as exc:
        _raise_demo_error(exc)


@router.post("/sync")
def sync_demo_templates_from_telnyx(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    return DemoWhatsappTemplateService.sync_from_telnyx(db)


@router.get("/templates/{template_id}/preview")
def preview_demo_template(
    template_id: int,
    first_name: str = "James",
    business_name: str = "menasim",
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = DemoWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    preview = DemoWhatsappTemplateService.build_preview(
        db,
        row,
        first_name=first_name,
        business_name=business_name,
    )
    return {"ok": True, "preview": preview, "template": demo_template_to_dict(row)}


@router.delete("/templates/{template_id}")
def delete_demo_template(
    template_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = DemoWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    try:
        return DemoWhatsappTemplateService.delete_template(db, row)
    except DemoWhatsappTemplateError as exc:
        _raise_demo_error(exc)

