"""Remind orgs about unpaid/pending invoices (3 and 7 days after issue)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.payment_event import PaymentEvent
from app.services.billing_email_service import BillingEmailService
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.email_template_service import EmailTemplateService
from app.services.invoice_service import InvoiceDocumentService
from app.services.usage_wallet_service import UsageWalletService

logger = logging.getLogger(__name__)

REMINDER_DAYS = (3, 7)
OUTSTANDING = frozenset({"pending", "issued", "collecting", "open", "due", "unpaid", "overdue", "sent", "past_due"})
DASHBOARD_BILLING_URL = "https://dashboard.voxbulk.com/account/billing"


class BillingPendingInvoiceReminderService:
    @staticmethod
    def _already_sent(db: Session, *, invoice_id: str, days: int) -> bool:
        ext = f"pending-invoice-reminder:{invoice_id}:{days}"
        row = db.execute(
            select(PaymentEvent).where(
                PaymentEvent.provider == "internal",
                PaymentEvent.external_event_id == ext,
            )
        ).scalar_one_or_none()
        return row is not None

    @staticmethod
    def _record_sent(db: Session, *, invoice: BillingInvoice, days: int, to_email: str) -> None:
        ext = f"pending-invoice-reminder:{invoice.id}:{days}"
        row = PaymentEvent(
            provider="internal",
            external_event_id=ext,
            org_id=invoice.org_id,
            client_email=to_email,
            status="sent",
            event_kind="pending_invoice_reminder",
            source="billing_pending_invoice_reminder",
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()

    @staticmethod
    def process_due_reminders(db: Session) -> dict[str, int]:
        EmailTemplateService.ensure_system_templates(db)
        now = datetime.utcnow()
        stats = {"checked": 0, "sent": 0, "skipped": 0, "errors": 0}

        rows = list(
            db.execute(
                select(BillingInvoice).where(BillingInvoice.status.in_(tuple(OUTSTANDING)))
            )
            .scalars()
            .all()
        )

        for invoice in rows:
            stats["checked"] += 1
            issued = invoice.created_at
            if issued is None:
                stats["skipped"] += 1
                continue
            age_days = (now.date() - issued.date()).days
            if age_days not in REMINDER_DAYS:
                stats["skipped"] += 1
                continue

            if BillingPendingInvoiceReminderService._already_sent(db, invoice_id=invoice.id, days=age_days):
                stats["skipped"] += 1
                continue

            org = db.get(Organisation, invoice.org_id)
            if org is None:
                stats["skipped"] += 1
                continue

            to_email = (
                (invoice.client_email or "").strip().lower()
                or UsageWalletService.get_org_billing_email(db, org.id)
                or (org.contact_email or "").strip().lower()
            )
            if not to_email:
                stats["skipped"] += 1
                continue

            currency = invoice.currency or resolve_org_currency(db, org)
            amount_minor = int(invoice.subtotal_pence if invoice.subtotal_pence is not None else invoice.amount_gbp_pence or 0)
            vars_plain = InvoiceDocumentService.build_variables(db, invoice=invoice, org=org)
            vars_plain.update(
                {
                    "organisation_name": org.name or "your organisation",
                    "billing_url": DASHBOARD_BILLING_URL,
                    "days_outstanding": str(age_days),
                    "amount_display": money_display(amount_minor, currency),
                    "invoice_description": invoice.description or vars_plain.get("invoice_description", "Invoice"),
                }
            )

            ok, err = BillingEmailService.send_templated_optional(
                db,
                template_key="billing_pending_invoice_reminder",
                to_email=to_email,
                variables=vars_plain,
            )
            if ok:
                BillingPendingInvoiceReminderService._record_sent(db, invoice=invoice, days=age_days, to_email=to_email)
                stats["sent"] += 1
            else:
                logger.warning(
                    "pending_invoice_reminder_failed invoice_id=%s days=%s err=%s",
                    invoice.id,
                    age_days,
                    err,
                )
                stats["errors"] += 1

        return stats
