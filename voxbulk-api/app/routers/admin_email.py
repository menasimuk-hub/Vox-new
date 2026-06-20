from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.admin_rbac import CAP_EMAIL, require_cap
from app.schemas.email_admin import (
    BillingMailboxSettingsUpdate,
    CareerMailboxSettingsUpdate,
    EmailTemplateCreate,
    EmailTemplateTestSendRequest,
    EmailTemplateUpdate,
    SmtpSettingsUpdate,
    SmtpTestSendRequest,
    TemplatedNotifySendRequest,
)
from app.services.email_template_service import EMAIL_TEMPLATE_KEYS, EmailTemplateService, EmailTemplateError, EmailTemplateUnknown
from app.services.smtp_mailer_service import SmtpMailerError, SmtpMailerService
from app.services.smtp_settings_service import SmtpSettingsService
from app.services.transactional_email_service import TransactionalEmailService

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


@router.get("/career-mailbox")
def get_career_mailbox_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    from app.services.career_mailbox_settings_service import CareerMailboxSettingsService

    row = CareerMailboxSettingsService.get_row(db)
    return CareerMailboxSettingsService.to_public_dict(db, row)


@router.put("/career-mailbox")
def put_career_mailbox_settings(
    payload: CareerMailboxSettingsUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    from app.services.career_mailbox_settings_service import CareerMailboxSettingsService

    password = str(payload.password).strip() if payload.password else None
    CareerMailboxSettingsService.upsert(
        db,
        mailbox_email=payload.mailbox_email,
        imap_host=payload.imap_host,
        imap_port=payload.imap_port,
        imap_use_ssl=payload.imap_use_ssl,
        imap_use_tls=payload.imap_use_tls,
        imap_username=payload.imap_username,
        sync_interval_minutes=payload.sync_interval_minutes,
        is_enabled=payload.is_enabled,
        password=password,
    )
    row = CareerMailboxSettingsService.get_row(db)
    return CareerMailboxSettingsService.to_public_dict(db, row)


@router.post("/career-mailbox/test")
def post_career_mailbox_test(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    from app.services.career_mailbox_sync_service import test_imap_connection

    ok, message = test_imap_connection(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return {"ok": True, "detail": message}


@router.post("/career-mailbox/sync-now")
def post_career_mailbox_sync_now(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    from app.services.career_mailbox_sync_service import sync_career_mailbox

    result = sync_career_mailbox(db)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message") or "Sync failed")
    return result


@router.get("/billing-mailbox")
def get_billing_mailbox_settings(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    from app.services.billing_mailbox_settings_service import BillingMailboxSettingsService

    row = BillingMailboxSettingsService.get_row(db)
    return BillingMailboxSettingsService.to_public_dict(db, row)


@router.put("/billing-mailbox")
def put_billing_mailbox_settings(
    payload: BillingMailboxSettingsUpdate,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    from app.services.billing_mailbox_settings_service import BillingMailboxSettingsService

    password = str(payload.password).strip() if payload.password else None
    BillingMailboxSettingsService.upsert(
        db,
        mailbox_email=payload.mailbox_email,
        imap_host=payload.imap_host,
        imap_port=payload.imap_port,
        imap_use_ssl=payload.imap_use_ssl,
        imap_use_tls=payload.imap_use_tls,
        imap_username=payload.imap_username,
        sync_interval_minutes=payload.sync_interval_minutes,
        is_enabled=payload.is_enabled,
        password=password,
    )
    row = BillingMailboxSettingsService.get_row(db)
    return BillingMailboxSettingsService.to_public_dict(db, row)


@router.post("/billing-mailbox/test")
def post_billing_mailbox_test(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    from app.services.billing_mailbox_sync_service import verify_billing_imap_connection

    ok, message = verify_billing_imap_connection(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return {"ok": True, "detail": message}


@router.post("/billing-mailbox/sync-now")
def post_billing_mailbox_sync_now(db: Session = Depends(get_db), _admin=Depends(require_cap(CAP_EMAIL))):
    from app.services.billing_mailbox_sync_service import sync_billing_mailbox

    result = sync_billing_mailbox(db)
    if not result.get("ok"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("message") or "Sync failed")
    return result


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
    ok, err = TransactionalEmailService.send_templated_optional(
        db,
        template_key=key,
        to_email=str(payload.to),
        variables=vars_plain,
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=err or "Test email was not sent.",
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
            lawful_basis=payload.lawful_basis,
            privacy_notice_url=payload.privacy_notice_url,
            contact_email=payload.contact_email,
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
            lawful_basis=payload.lawful_basis,
            privacy_notice_url=payload.privacy_notice_url,
            contact_email=payload.contact_email,
        )
    except EmailTemplateError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return EmailTemplateService.to_dict(row)


@router.post("/templates/{template_key}/send-test")
def post_email_template_send_test(
    template_key: str,
    payload: EmailTemplateTestSendRequest,
    db: Session = Depends(get_db),
    _admin=Depends(require_cap(CAP_EMAIL)),
):
    """Send the current template (draft subject/body optional) with dummy placeholder data."""
    vars_plain = {str(k): "" if v is None else str(v) for k, v in (payload.variables or {}).items()}
    key_norm = EmailTemplateService.normalize_key(template_key)
    if key_norm.startswith("interview_"):
        from app.services.career_email_service import CareerEmailService

        ok, err = CareerEmailService.send_template_test(
            db,
            template_key=key_norm,
            to_email=str(payload.to),
            variables=vars_plain,
        )
    elif key_norm.startswith("billing_") or key_norm in {"new_invoice", "payment_failed", "payment_receipt"}:
        from app.services.billing_email_service import BillingEmailService

        ok, err = BillingEmailService.send_template_test(
            db,
            template_key=key_norm,
            to_email=str(payload.to),
            variables=vars_plain,
            subject=payload.subject,
            body=payload.body,
        )
    else:
        ok, err = TransactionalEmailService.send_template_test(
            db,
            template_key=template_key,
            to_email=str(payload.to),
            subject=payload.subject,
            body=payload.body,
            variables=vars_plain,
        )
    if not ok:
        code = status.HTTP_404_NOT_FOUND if err == "Template not found" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=err or "Test email was not sent.")
    return {"ok": True, "detail": f"Test email sent to {payload.to}."}


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
