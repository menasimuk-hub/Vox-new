from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.admin_rbac import CAP_EMAIL, require_cap
from app.core.database import get_db
from app.models.sms_template import SmsTemplate
from app.models.whatsapp_template import WhatsAppTemplate
from app.schemas.email_admin import ChannelTemplateCreate, ChannelTemplateUpdate
from app.services.channel_template_service import ChannelTemplateError, ChannelTemplateService

router = APIRouter(prefix="/admin/messaging", tags=["admin-messaging"])


def _wa_dict(row):
    return ChannelTemplateService.to_dict(row)


def _sms_dict(row):
    return ChannelTemplateService.to_dict(row)


@router.get("/whatsapp/templates")
def list_whatsapp_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    return ChannelTemplateService.list_all(db, model=WhatsAppTemplate)


@router.post("/whatsapp/templates")
def create_whatsapp_template(
    payload: ChannelTemplateCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        row = ChannelTemplateService.create(
            db,
            model=WhatsAppTemplate,
            key=payload.template_key,
            name=payload.name,
            body=payload.body,
            is_enabled=payload.is_enabled,
        )
    except ChannelTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _wa_dict(row)


@router.get("/whatsapp/templates/{template_key}")
def get_whatsapp_template(template_key: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    row = ChannelTemplateService.get(db, model=WhatsAppTemplate, key=template_key)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return _wa_dict(row)


@router.put("/whatsapp/templates/{template_key}")
def put_whatsapp_template(
    template_key: str,
    payload: ChannelTemplateUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        row = ChannelTemplateService.upsert(
            db,
            model=WhatsAppTemplate,
            key=template_key,
            name=payload.name,
            body=payload.body,
            is_enabled=payload.is_enabled,
        )
    except ChannelTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _wa_dict(row)


@router.delete("/whatsapp/templates/{template_key}")
def delete_whatsapp_template(
    template_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        ChannelTemplateService.delete(db, model=WhatsAppTemplate, key=template_key)
    except ChannelTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True}


@router.get("/sms/templates")
def list_sms_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    return ChannelTemplateService.list_all(db, model=SmsTemplate)


@router.post("/sms/templates")
def create_sms_template(
    payload: ChannelTemplateCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        row = ChannelTemplateService.create(
            db,
            model=SmsTemplate,
            key=payload.template_key,
            name=payload.name,
            body=payload.body,
            is_enabled=payload.is_enabled,
        )
    except ChannelTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _sms_dict(row)


@router.get("/sms/templates/{template_key}")
def get_sms_template(template_key: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    row = ChannelTemplateService.get(db, model=SmsTemplate, key=template_key)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return _sms_dict(row)


@router.put("/sms/templates/{template_key}")
def put_sms_template(
    template_key: str,
    payload: ChannelTemplateUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        row = ChannelTemplateService.upsert(
            db,
            model=SmsTemplate,
            key=template_key,
            name=payload.name,
            body=payload.body,
            is_enabled=payload.is_enabled,
        )
    except ChannelTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _sms_dict(row)


@router.delete("/sms/templates/{template_key}")
def delete_sms_template(
    template_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        ChannelTemplateService.delete(db, model=SmsTemplate, key=template_key)
    except ChannelTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True}
