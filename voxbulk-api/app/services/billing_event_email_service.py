from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.payment_event import PaymentEvent
from app.services.product_email_triggers import ProductEmailTriggers


class BillingEventEmailService:
    """
    Minimal internal billing event sink.

    - Stores idempotency in DB (unique provider/external id).
    - Calls existing email hooks exactly once per meaningful event.
    """

    FAILED_STATUSES = {"failed", "declined", "canceled", "cancelled", "past_due"}

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

        # Email only once, and only if status is a failure.
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
    ) -> tuple[BillingInvoice, bool, bool]:
        """
        Returns: (invoice_row, created_row, sent_email)
        """
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

        vars_plain = {str(k): "" if v is None else str(v) for k, v in (variables or {}).items()}
        vars_plain.setdefault("invoice_id", row.external_invoice_id)
        vars_plain.setdefault("amount_gbp_pence", str(row.amount_gbp_pence))
        vars_plain.setdefault("currency", row.currency)
        vars_plain.setdefault("invoice_status", row.status)

        ok, _err = ProductEmailTriggers.notify_new_invoice(db, to_email=row.client_email, extra_variables=vars_plain)
        if ok:
            row.emailed_at = datetime.utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
            return row, created, True
        return row, created, False

