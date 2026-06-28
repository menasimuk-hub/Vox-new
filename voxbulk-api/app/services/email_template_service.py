from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.email_template import EmailTemplate
from app.data.system_email_defaults import SYSTEM_EMAIL_DEFAULTS
from app.services.uk_compliance_constants import (
    DEFAULT_COMPLIANCE_CONTACT_EMAIL,
    DEFAULT_LAWFUL_BASIS,
    DEFAULT_PRIVACY_NOTICE_URL,
    LAUNCH_OUTBOUND_EMAIL_TEMPLATE_KEYS,
    LAWFUL_BASES,
    PRIMARY_LAUNCH_EMAIL_TEMPLATE_KEY,
)

EMAIL_TEMPLATE_KEYS: tuple[str, ...] = (
    "new_user",
    "account_deletion_completed",
    "forgot_password",
    "new_invoice",
    "invoice_document",
    "payment_failed",
    "general_notification",
    "team_invite",
    "weekly_digest",
    "sales_offer",
    "usage_warning",
    "usage_warning_100",
    "payment_receipt",
    "interview_scheduling_invite",
    "interview_booking_invite",
    "interview_booking_confirm",
    "interview_booking_reminder",
    "interview_booking_cancel",
    "interview_campaign_cancelled",
    "interview_meeting_missed",
    "interview_missed_call_followup",
    "billing_cancellation_requested",
    "billing_cancellation_reversed",
    "billing_wallet_credit_issued",
    "billing_bank_refund_approved",
    "billing_refund_request_rejected",
    "billing_subscription_ended",
    "billing_renewal_reminder",
    "billing_pending_invoice_reminder",
    "billing_payment_action_required",
)

_TEMPLATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")


class EmailTemplateUnknown(ValueError):
    pass


class EmailTemplateError(ValueError):
    pass


class EmailTemplateService:
    @staticmethod
    def default_compliance_fields(*, template_key: str | None = None) -> dict[str, str]:
        basis = DEFAULT_LAWFUL_BASIS
        key = str(template_key or "").strip().lower()
        if key == "sales_offer":
            basis = "consent"
        return {
            "lawful_basis": basis,
            "privacy_notice_url": DEFAULT_PRIVACY_NOTICE_URL,
            "contact_email": DEFAULT_COMPLIANCE_CONTACT_EMAIL,
        }

    @staticmethod
    def _apply_compliance_defaults(row: EmailTemplate, *, template_key: str | None = None) -> None:
        defaults = EmailTemplateService.default_compliance_fields(template_key=template_key or row.template_key)
        if not str(row.lawful_basis or "").strip():
            row.lawful_basis = defaults["lawful_basis"]
        if not str(row.privacy_notice_url or "").strip():
            row.privacy_notice_url = defaults["privacy_notice_url"]
        if not str(row.contact_email or "").strip():
            row.contact_email = defaults["contact_email"]

    @staticmethod
    def compliance_dict(row: EmailTemplate | None) -> dict[str, str]:
        if row is None:
            return {}
        out: dict[str, str] = {}
        basis = str(row.lawful_basis or "").strip().lower()
        if basis:
            out["lawful_basis"] = basis
        url = str(row.privacy_notice_url or "").strip()
        if url:
            out["privacy_notice_url"] = url
        contact = str(row.contact_email or "").strip()
        if contact:
            out["contact_email"] = contact
        return out

    @staticmethod
    def launch_outbound_compliance_defaults(db: Session, *, service_code: str | None = None) -> dict[str, str]:
        """Merge compliance from launch-relevant outbound email templates (first non-empty wins)."""
        EmailTemplateService.ensure_system_templates(db)
        keys = list(LAUNCH_OUTBOUND_EMAIL_TEMPLATE_KEYS)
        code = str(service_code or "").strip().lower()
        if code == "interview":
            keys = [k for k in keys if k.startswith("interview_")]
        elif code == "survey":
            keys = [k for k in keys if not k.startswith("interview_")]
        primary = PRIMARY_LAUNCH_EMAIL_TEMPLATE_KEY.get(code)
        if primary and primary in keys:
            keys = [primary] + [k for k in keys if k != primary]

        merged: dict[str, str] = {}
        for key in keys:
            row = EmailTemplateService.get(db, key=key)
            block = EmailTemplateService.compliance_dict(row)
            for field, value in block.items():
                if field not in merged and str(value or "").strip():
                    merged[field] = str(value).strip()
        return merged

    @staticmethod
    def normalize_compliance_payload(
        *,
        lawful_basis: str | None = None,
        privacy_notice_url: str | None = None,
        contact_email: str | None = None,
        template_key: str | None = None,
    ) -> dict[str, str]:
        defaults = EmailTemplateService.default_compliance_fields(template_key=template_key)
        basis = str(lawful_basis or defaults["lawful_basis"]).strip().lower()
        if basis not in LAWFUL_BASES:
            basis = defaults["lawful_basis"]
        url = str(privacy_notice_url or defaults["privacy_notice_url"]).strip()
        contact = str(contact_email or defaults["contact_email"]).strip()
        return {
            "lawful_basis": basis,
            "privacy_notice_url": url,
            "contact_email": contact,
        }

    @staticmethod
    def ensure_system_templates(db: Session) -> None:
        """Insert any missing system templates; refresh interview bodies with broken data: logos."""
        changed = False
        for key in EMAIL_TEMPLATE_KEYS:
            defaults = SYSTEM_EMAIL_DEFAULTS.get(key, {})
            row = EmailTemplateService.get(db, key=key)
            if row is None:
                EmailTemplateService.create(
                    db,
                    key=key,
                    title=defaults.get("title") or key.replace("_", " ").title(),
                    subject=defaults.get("subject") or key.replace("_", " ").title(),
                    body=defaults.get("body") or "",
                    is_enabled=True,
                )
                continue
            EmailTemplateService._apply_compliance_defaults(row, template_key=key)
            body = str(row.body or "")
            default_body = str(defaults.get("body") or "")
            default_subject = str(defaults.get("subject") or "")
            needs_calendar_refresh = (
                key in {"interview_booking_confirm", "interview_booking_reminder"}
                and default_body
                and "{{calendar_links_html}}" in default_body
                and "{{calendar_links_html}}" not in body
            )
            needs_cancel_refresh = (
                key in {"interview_booking_cancel", "interview_campaign_cancelled"}
                and default_body
                and (not body.strip() or not bool(row.is_enabled))
            )
            needs_invoice_document_refresh = (
                key == "invoice_document"
                and default_body
                and (
                    bool(re.search(r"\{\{#|\{\{/", body))
                    or "#0f766e" in body.lower()
                    or "{{company_logo_html}}" not in body
                )
            )
            needs_new_invoice_refresh = (
                key == "new_invoice"
                and default_body
                and "#0f766e" in body.lower()
            )
            needs_general_notification_refresh = (
                key == "general_notification"
                and default_body
                and (
                    "{{practice_name}}" in body
                    or "{{digest_" in body
                    or "{{#if" in body
                    or "{{/if}}" in body
                    or "digest_greeting" in body
                )
            )
            needs_unthemed_refresh = (
                key in {"payment_failed", "usage_warning", "usage_warning_100", "payment_receipt"}
                and default_body
                and "<!DOCTYPE html><html><body" in body
                and "wrap_brand_email" not in body
            )
            if default_body and key.startswith("interview_") and (
                "data:image" in body
                or ("data:" in body and "base64" in body)
                or needs_calendar_refresh
                or needs_cancel_refresh
            ):
                row.body = default_body
                if default_subject:
                    row.subject = default_subject
                row.updated_at = datetime.utcnow()
                db.add(row)
                changed = True
            elif needs_invoice_document_refresh:
                row.body = default_body
                if default_subject:
                    row.subject = default_subject
                row.updated_at = datetime.utcnow()
                db.add(row)
                changed = True
            elif needs_new_invoice_refresh:
                row.body = default_body
                if default_subject:
                    row.subject = default_subject
                row.updated_at = datetime.utcnow()
                db.add(row)
                changed = True
            elif needs_general_notification_refresh or needs_unthemed_refresh:
                row.body = default_body
                if default_subject:
                    row.subject = default_subject
                row.updated_at = datetime.utcnow()
                db.add(row)
                changed = True
        if changed:
            db.commit()

    @staticmethod
    def is_system_key(key: str) -> bool:
        return (key or "").strip().lower() in EMAIL_TEMPLATE_KEYS

    @staticmethod
    def normalize_key(key: str) -> str:
        k = (key or "").strip().lower().replace("-", "_").replace(" ", "_")
        if not _TEMPLATE_KEY_RE.match(k):
            raise EmailTemplateError(
                "Template key must be 3–64 chars: lowercase letters, numbers, underscores; start with a letter."
            )
        return k

    @staticmethod
    def assert_key(key: str) -> str:
        k = EmailTemplateService.normalize_key(key)
        return k

    @staticmethod
    def get_send_content(db: Session, *, key: str) -> tuple[str, str, bool]:
        """
        Load subject/body for outbound mail or PDF rendering.
        When a DB row exists, use saved admin content only (no silent merge with code defaults).
        """
        k = EmailTemplateService.normalize_key(key)
        EmailTemplateService.ensure_system_templates(db)
        row = EmailTemplateService.get(db, key=k)
        defaults = SYSTEM_EMAIL_DEFAULTS.get(k, {})
        if row is not None:
            db.refresh(row)
            subject = str(row.subject or "")
            body = str(row.body or "")
            enabled = bool(row.is_enabled)
            if k.startswith("interview_"):
                subj = str(subject or defaults.get("subject") or "").strip()
                bod = str(body or defaults.get("body") or "").strip()
                if subj or bod:
                    # Interview outreach must send when content exists — do not block on is_enabled=false.
                    return subj, bod, True
                return (
                    str(defaults.get("subject") or ""),
                    str(defaults.get("body") or ""),
                    True,
                )
            return subject, body, enabled
        return str(defaults.get("subject") or ""), str(defaults.get("body") or ""), True

    @staticmethod
    def list_all(db: Session) -> list[dict[str, Any]]:
        EmailTemplateService.ensure_system_templates(db)
        rows = db.execute(select(EmailTemplate).order_by(EmailTemplate.template_key.asc())).scalars().all()
        return [EmailTemplateService.to_dict(r) for r in rows]

    @staticmethod
    def get(db: Session, *, key: str) -> EmailTemplate | None:
        k = EmailTemplateService.normalize_key(key)
        return db.execute(select(EmailTemplate).where(EmailTemplate.template_key == k)).scalar_one_or_none()

    @staticmethod
    def to_dict(row: EmailTemplate) -> dict[str, Any]:
        return {
            "id": row.id,
            "template_key": row.template_key,
            "title": row.title or "",
            "subject": row.subject or "",
            "body": row.body or "",
            "is_enabled": bool(row.is_enabled),
            "lawful_basis": row.lawful_basis or "",
            "privacy_notice_url": row.privacy_notice_url or "",
            "contact_email": row.contact_email or "",
            "is_system": EmailTemplateService.is_system_key(row.template_key),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def create(
        db: Session,
        *,
        key: str,
        title: str,
        subject: str,
        body: str,
        is_enabled: bool,
        lawful_basis: str | None = None,
        privacy_notice_url: str | None = None,
        contact_email: str | None = None,
    ) -> EmailTemplate:
        k = EmailTemplateService.normalize_key(key)
        if EmailTemplateService.get(db, key=k) is not None:
            raise EmailTemplateError(f"Template key already exists: {k}")
        compliance = EmailTemplateService.normalize_compliance_payload(
            lawful_basis=lawful_basis,
            privacy_notice_url=privacy_notice_url,
            contact_email=contact_email,
            template_key=k,
        )
        now = datetime.utcnow()
        row = EmailTemplate(
            template_key=k,
            title=(title or k).strip(),
            subject=(subject or "").strip(),
            body=body or "",
            is_enabled=bool(is_enabled),
            lawful_basis=compliance["lawful_basis"],
            privacy_notice_url=compliance["privacy_notice_url"],
            contact_email=compliance["contact_email"],
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def upsert(
        db: Session,
        *,
        key: str,
        title: str | None = None,
        subject: str,
        body: str,
        is_enabled: bool,
        lawful_basis: str | None = None,
        privacy_notice_url: str | None = None,
        contact_email: str | None = None,
    ) -> EmailTemplate:
        k = EmailTemplateService.normalize_key(key)
        row = EmailTemplateService.get(db, key=k)
        if row is None:
            return EmailTemplateService.create(
                db,
                key=k,
                title=title or k,
                subject=subject,
                body=body,
                is_enabled=is_enabled,
                lawful_basis=lawful_basis,
                privacy_notice_url=privacy_notice_url,
                contact_email=contact_email,
            )
        if title is not None:
            row.title = title.strip()
        row.subject = (subject or "").strip()
        row.body = body or ""
        row.is_enabled = bool(is_enabled)
        if lawful_basis is not None:
            row.lawful_basis = EmailTemplateService.normalize_compliance_payload(
                lawful_basis=lawful_basis, template_key=k
            )["lawful_basis"]
        if privacy_notice_url is not None:
            row.privacy_notice_url = str(privacy_notice_url or "").strip() or None
        if contact_email is not None:
            row.contact_email = str(contact_email or "").strip() or None
        EmailTemplateService._apply_compliance_defaults(row, template_key=k)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def delete(db: Session, *, key: str) -> None:
        k = EmailTemplateService.normalize_key(key)
        if EmailTemplateService.is_system_key(k):
            raise EmailTemplateError("System templates cannot be deleted")
        row = EmailTemplateService.get(db, key=k)
        if row is None:
            raise EmailTemplateUnknown(f"Unknown template key: {k}")
        db.delete(row)
        db.commit()
