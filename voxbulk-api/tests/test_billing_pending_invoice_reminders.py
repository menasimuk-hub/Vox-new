"""Pending invoice reminder emails."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import delete

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.billing_pending_invoice_reminder_service import BillingPendingInvoiceReminderService


def _seed_pending_invoice(*, age_days: int) -> str:
    with get_sessionmaker()() as db:
        org = Organisation(name="Pending Inv Org", contact_email="pending@example.com")
        db.add(org)
        db.flush()
        user = User(
            email=f"pending-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        issued = datetime.utcnow() - timedelta(days=age_days)
        inv = BillingInvoice(
            org_id=org.id,
            client_email="pending@example.com",
            external_invoice_id=f"test-pending-{uuid.uuid4().hex[:8]}",
            provider="internal",
            status="pending",
            subtotal_pence=3316,
            amount_gbp_pence=3316,
            currency="GBP",
            description="Pro-rata upgrade test",
            created_at=issued,
        )
        db.add(inv)
        db.commit()
        return inv.id


def _clear_outstanding_invoices() -> None:
    with get_sessionmaker()() as db:
        db.execute(delete(BillingInvoice))
        db.commit()


def test_pending_invoice_reminder_sent_on_day_3():
    _clear_outstanding_invoices()
    invoice_id = _seed_pending_invoice(age_days=3)
    with get_sessionmaker()() as db:
        with patch.object(BillingPendingInvoiceReminderService, "_record_sent") as record:
            with patch(
                "app.services.billing_pending_invoice_reminder_service.BillingEmailService.send_templated_optional",
                return_value=(True, None),
            ):
                stats = BillingPendingInvoiceReminderService.process_due_reminders(db)
        assert stats["sent"] >= 1
        record.assert_called()


def test_pending_invoice_reminder_skips_wrong_age():
    _clear_outstanding_invoices()
    _seed_pending_invoice(age_days=2)
    with get_sessionmaker()() as db:
        with patch(
            "app.services.billing_pending_invoice_reminder_service.BillingEmailService.send_templated_optional",
            return_value=(True, None),
        ) as send:
            stats = BillingPendingInvoiceReminderService.process_due_reminders(db)
        assert stats["sent"] == 0
        send.assert_not_called()
