from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.admin_rbac import CAP_EMAIL, require_cap
from app.schemas.email_admin import (
    EmailTemplateCreate,
    EmailTemplateUpdate,
    SmtpSettingsUpdate,
    SmtpTestSendRequest,
    TemplatedNotifySendRequest,
)
from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService, EmailTemplateError, EmailTemplateUnknown
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.product_email_triggers import ProductEmailTriggers
from app.services.smtp_settings_service import SmtpSettingsService

router = APIRouter(prefix="/admin/email", tags=["admin-email"])


@router.get("/smtp")
def get_smtp_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    row = SmtpSettingsService.get_row(db)
    return SmtpSettingsService.to_public_dict(db, row)


@router.put("/smtp")
def put_smtp_settings(
    payload: SmtpSettingsUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    raw_pwd = payload.password
    password_to_store = None
    if raw_pwd is not None and str(raw_pwd).strip():
        password_to_store = str(raw_pwd).strip()

    SmtpSettingsService.upsert(
        db,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        from_name=payload.from_name,
        from_email=payload.from_email,
        use_tls=payload.use_tls,
        use_ssl=payload.use_ssl,
        is_enabled=payload.is_enabled,
        password=password_to_store,
    )
    row = SmtpSettingsService.get_row(db)
    return SmtpSettingsService.to_public_dict(db, row)


@router.post("/smtp/test")
def post_smtp_test_send(
    payload: SmtpTestSendRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    subject = "VOXBULK / SMTP test"
    body = (
        "This is a test message from the VOXBULK admin console.\n\n"
        "If you received this email, your SMTP settings are working."
    )
    try:
        SmtpMailerService.send_plain(db, to_addr=str(payload.to), subject=subject, body=body)
    except SmtpMailerError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True, "detail": f"Test email sent to {payload.to}."}


@router.post("/notify/send-templated")
def post_send_templated_notification(
    payload: TemplatedNotifySendRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    """
    Send a real templated notification (for dev validation of payment/invoice/general templates).
    Blocks `forgot_password` (requires the public reset flow).
    """
    key = (payload.template_key or "").strip().lower()
    if not EmailTemplateService.is_system_key(key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Test send only supports system email templates")

    if key == "forgot_password":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the public /auth/forgot-password flow to exercise password reset email.",
        )

    vars_plain = {str(k): "" if v is None else str(v) for k, v in (payload.variables or {}).items()}

    if key == "new_user":
        ok, err = ProductEmailTriggers.send_new_user_welcome(db, to_email=str(payload.to), extra_variables=vars_plain)
    elif key == "payment_failed":
        ok, err = ProductEmailTriggers.notify_payment_failed(db, to_email=str(payload.to), extra_variables=vars_plain)
    elif key == "new_invoice":
        ok, err = ProductEmailTriggers.notify_new_invoice(db, to_email=str(payload.to), extra_variables=vars_plain)
    elif key == "general_notification":
        ok, err = ProductEmailTriggers.notify_general(db, to_email=str(payload.to), extra_variables=vars_plain)
    else:
        ok, err = (False, "unsupported_template")

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err or "Email was not sent (template disabled or SMTP incomplete).",
        )
    return {"ok": True, "detail": f"Templated '{key}' sent to {payload.to}."}


@router.get("/template-keys")
def get_template_keys(_admin=Depends(require_cap(CAP_EMAIL))):
    return {"keys": list(EMAIL_TEMPLATE_KEYS)}


@router.get("/templates")
def list_email_templates(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    return EmailTemplateService.list_all(db)


@router.get("/templates/{template_key}")
def get_email_template(template_key: str, db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    row = EmailTemplateService.get(db, key=template_key)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return EmailTemplateService.to_dict(row)


@router.post("/templates")
def create_email_template(
    payload: EmailTemplateCreate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        row = EmailTemplateService.create(
            db,
            key=payload.template_key,
            title=payload.title,
            subject=payload.subject,
            body=payload.body,
            is_enabled=payload.is_enabled,
        )
    except EmailTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return EmailTemplateService.to_dict(row)


@router.put("/templates/{template_key}")
def put_email_template(
    template_key: str,
    payload: EmailTemplateUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        row = EmailTemplateService.upsert(
            db,
            key=template_key,
            title=payload.title,
            subject=payload.subject,
            body=payload.body,
            is_enabled=payload.is_enabled,
        )
    except EmailTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return EmailTemplateService.to_dict(row)


@router.delete("/templates/{template_key}")
def delete_email_template(
    template_key: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    try:
        EmailTemplateService.delete(db, key=template_key)
    except EmailTemplateUnknown as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except EmailTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return {"ok": True}
