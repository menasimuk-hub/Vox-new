"""Platform Settings → WA Appointment Manager templates."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_INTEGRATION, require_cap
from app.core.database import get_db
from app.services.appointment_whatsapp_template_service import AppointmentWhatsappTemplateService

router = APIRouter(prefix="/admin/wa-appointment", tags=["admin-wa-appointment"])


@router.get("/templates")
def list_appointment_templates(
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    templates = AppointmentWhatsappTemplateService.list_admin_templates(db)
    return {"ok": True, "templates": templates}


@router.post("/templates/{template_id}/set-active")
def set_appointment_template_active(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_INTEGRATION)),
):
    row = AppointmentWhatsappTemplateService.get_template(db, template_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    body = payload or {}
    if "active" in body:
        active = bool(body.get("active"))
    elif "active_for_appointment" in body:
        active = bool(body.get("active_for_appointment"))
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Provide active or active_for_appointment (boolean)."},
        )
    updated = AppointmentWhatsappTemplateService.save_draft(db, row, {"active_for_appointment": active})
    tpl = AppointmentWhatsappTemplateService.row_to_admin_dict(updated)
    message = (
        "Template enabled for Appointment Manager."
        if active
        else "Template hidden from customers — you can still sync it to Telnyx."
    )
    return {"ok": True, "message": message, "template": tpl}
