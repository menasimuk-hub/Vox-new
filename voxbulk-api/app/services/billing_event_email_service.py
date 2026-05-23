from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.payment_event import PaymentEvent
from app.services.invoice_service import InvoiceDocumentService
from app.services.product_email_triggers import ProductEmailTriggers
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)


class BillingEventEmailService:
    """
    Minimal internal billing event sink.

    - Stores idempotency in DB (unique provider/external id).
    - Calls existing email hooks exactly once per meaningful event.
    """

    FAILED_STATUSES = {"failed", "declined", "canceled", "cancelled", "past_due"}

    @staticmethod
    def _invoice_pdf_attachment(db: Session, invoice: BillingInvoice) -> list[dict[str, Any]] | None:
        try:
            org = db.get(Organisation, invoice.org_id)
            pdf_bytes = InvoiceDocumentService.render_pdf(db, invoice=invoice, org=org)
            number = invoice.invoice_number or invoice.external_invoice_id or invoice.id
            return [
                {
                    "filename": f"invoice-{number}.pdf",
                    "content": pdf_bytes,
                    "maintype": "application",
                    "subtype": "pdf",
                }
            ]
        except Exception as exc:
            logger.warning("invoice_pdf_attachment_failed", extra={"invoice_id": invoice.id, "error": str(exc)})
            return None

    @staticmethod
    def record_payment_status(
        db: Session,
        *,
        provider: str,
        external_event_id: str,
        org_id: str,
        client_email: str,
        status: str,
        failure_reason: str | None = None,
        variables: dict[str, Any] | None = None,
    ) -> tuple[PaymentEvent, bool, bool]:
        """
        Returns: (event_row, created_row, sent_email)
        """
        prov = (provider or "internal").strip().lower()
        ext = (external_event_id or "").strip()
        st = (status or "").strip().lower()
        em = (client_email or "").strip().lower()
        if not ext:
            raise ValueError("external_event_id required")
        if not org_id:
            raise ValueError("org_id required")
        if not em:
            raise ValueError("client_email required")

        row = PaymentEvent(
            provider=prov,
            external_event_id=ext,
            org_id=str(org_id),
            client_email=em,
            status=st or "unknown",
            failure_reason=(failure_reason or "").strip() or None,
            created_at=datetime.utcnow(),
        )
        db.add(row)
        created = True
        try:
            db.commit()
            db.refresh(row)
        except IntegrityError:
            db.rollback()
            created = False
            row = (
                db.execute(
                    select(PaymentEvent).where(PaymentEvent.provider == prov, PaymentEvent.external_event_id == ext)
                )
                .scalars()
                .one()
            )

        if row.emailed_at is not None:
            return row, created, False
        if (row.status or "").lower() not in BillingEventEmailService.FAILED_STATUSES:
            return row, created, False

        vars_plain = {str(k): "" if v is None else str(v) for k, v in (variables or {}).items()}
        vars_plain.setdefault("payment_status", row.status)
        if row.failure_reason:
            vars_plain.setdefault("failure_reason", row.failure_reason)
        vars_plain.setdefault("external_event_id", row.external_event_id)

        ok, _err = ProductEmailTriggers.notify_payment_failed(db, to_email=row.client_email, extra_variables=vars_plain)
        if ok:
            row.emailed_at = datetime.utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
            return row, created, True
        return row, created, False

    @staticmethod
    def _deliver_new_invoice_email(
        db: Session,
        *,
        to_email: str,
        variables: dict[str, str],
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str | None]:
        vars_plain = {str(k): "" if v is None else str(v) for k, v in (variables or {}).items()}
        subject_tpl, body_tpl, is_enabled = TransactionalEmailService.load_template_fields(db, template_key="new_invoice")
        logger.info(
            "invoice_email_prepare",
            extra={
                "to_email": to_email,
                "template": "new_invoice",
                "is_enabled": is_enabled,
                "subject_len": len(subject_tpl),
                "body_len": len(body_tpl),
            },
        )
        ok, err = ProductEmailTriggers.notify_new_invoice(
            db,
            to_email=to_email,
            extra_variables=variables,
            attachments=attachments,
        )
        if ok:
            logger.info(
                "invoice_email_sent",
                extra={"to_email": to_email, "invoice_number": variables.get("invoice_number"), "template": "new_invoice"},
            )
            return True, None
        logger.warning(
            "invoice_email_failed",
            extra={
                "to_email": to_email,
                "invoice_number": variables.get("invoice_number"),
                "template": "new_invoice",
                "error": err or "template_disabled_or_empty",
            },
        )
        return False, err

    @staticmethod
    def send_invoice_email(db: Session, *, invoice: BillingInvoice) -> tuple[bool, str | None]:
        org = db.get(Organisation, invoice.org_id)
        vars_plain = InvoiceDocumentService.build_variables(db, invoice=invoice, org=org)
        attachments = BillingEventEmailService._invoice_pdf_attachment(db, invoice)
        return BillingEventEmailService._deliver_new_invoice_email(
            db,
            to_email=invoice.client_email,
            variables=vars_plain,
            attachments=attachments,
        )

    @staticmethod
    def create_invoice(
        db: Session,
        *,
        provider: str,
        external_invoice_id: str,
        org_id: str,
        client_email: str,
        amount_gbp_pence: int = 0,
        currency: str = "GBP",
        status: str = "issued",
        variables: dict[str, Any] | None = None,
        invoice_row: BillingInvoice | None = None,
    ) -> tuple[BillingInvoice, bool, bool]:
        """
        Returns: (invoice_row, created_row, sent_email)
        """
        if invoice_row is not None:
            row = invoice_row
            created = False
        else:
            prov = (provider or "internal").strip().lower()
            ext = (external_invoice_id or "").strip()
            em = (client_email or "").strip().lower()
            if not ext:
                raise ValueError("external_invoice_id required")
            if not org_id:
                raise ValueError("org_id required")
            if not em:
                raise ValueError("client_email required")

            row = BillingInvoice(
                org_id=str(org_id),
                provider=prov,
                external_invoice_id=ext,
                client_email=em,
                amount_gbp_pence=int(amount_gbp_pence or 0),
                currency=(currency or "GBP").strip().upper(),
                status=(status or "issued").strip().lower(),
                created_at=datetime.utcnow(),
            )
            db.add(row)
            created = True
            try:
                db.commit()
                db.refresh(row)
            except IntegrityError:
                db.rollback()
                created = False
                row = (
                    db.execute(
                        select(BillingInvoice).where(
                            BillingInvoice.provider == prov, BillingInvoice.external_invoice_id == ext
                        )
                    )
                    .scalars()
                    .one()
                )

        if row.emailed_at is not None:
            return row, created, False

        org = db.get(Organisation, row.org_id)
        vars_plain = InvoiceDocumentService.build_variables(db, invoice=row, org=org)
        if variables:
            for k, v in variables.items():
                vars_plain[str(k)] = "" if v is None else str(v)

        attachments = BillingEventEmailService._invoice_pdf_attachment(db, row)
        ok, err = BillingEventEmailService._deliver_new_invoice_email(
            db,
            to_email=row.client_email,
            variables=vars_plain,
            attachments=attachments,
        )
        if ok:
            row.emailed_at = datetime.utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
            logger.info(
                "invoice_created_and_emailed",
                extra={
                    "invoice_id": row.id,
                    "external_invoice_id": row.external_invoice_id,
                    "org_id": row.org_id,
                    "created": created,
                },
            )
            return row, created, True
        logger.warning(
            "invoice_created_email_failed",
            extra={
                "invoice_id": row.id,
                "external_invoice_id": row.external_invoice_id,
                "org_id": row.org_id,
                "error": err,
            },
        )
        return row, created, False

    @staticmethod
    def issue_payment_invoice(
        db: Session,
        *,
        invoice: BillingInvoice,
    ) -> tuple[BillingInvoice, bool, bool]:
        """Send invoice notification email (with PDF) once."""
        return BillingEventEmailService.create_invoice(
            db,
            provider=invoice.provider,
            external_invoice_id=invoice.external_invoice_id,
            org_id=invoice.org_id,
            client_email=invoice.client_email,
            amount_gbp_pence=invoice.amount_gbp_pence,
            currency=invoice.currency,
            status=invoice.status,
            invoice_row=invoice,
        )
