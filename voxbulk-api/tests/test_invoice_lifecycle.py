"""Invoice lifecycle edit/void policy tests."""

from __future__ import annotations

import uuid

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.invoice_lifecycle_service import InvoiceLifecycleError, InvoiceLifecycleService
from app.services.invoice_service import InvoiceService


def _seed() -> tuple[str, str]:
    email = f"lifecycle-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        org = Organisation(name="Lifecycle Org", wallet_balance_pence=0, contact_email=email)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, user.id


def _due_invoice(org_id: str, email: str, *, status: str = "due") -> str:
    with get_sessionmaker()() as db:
        inv = InvoiceService.create_from_payment(
            db,
            org_id=org_id,
            client_email=email,
            subtotal_pence=1000,
            currency="GBP",
            description="Test invoice",
            provider="internal",
            external_invoice_id=f"test-{uuid.uuid4().hex[:8]}",
            status=status,
            kind="manual",
        )
        return inv.id


def test_editable_due_invoice():
    org_id, _ = _seed()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        inv_id = _due_invoice(org_id, org.contact_email or "a@b.com")
        invoice = db.get(BillingInvoice, inv_id)
        assert invoice is not None
        policy = InvoiceLifecycleService.policy(invoice)
        assert policy["can_edit"] is True
        assert policy["can_void"] is True
        updated = InvoiceLifecycleService.edit_invoice(
            db,
            invoice,
            description="Updated description",
            amount_minor=1500,
        )
        assert "Updated" in (updated.description or "")


def test_paid_invoice_locked():
    org_id, _ = _seed()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        inv_id = _due_invoice(org_id, org.contact_email or "a@b.com", status="paid")
        invoice = db.get(BillingInvoice, inv_id)
        assert invoice is not None
        policy = InvoiceLifecycleService.policy(invoice)
        assert policy["can_edit"] is False
        assert policy["can_void"] is False
        with pytest.raises(InvoiceLifecycleError):
            InvoiceLifecycleService.void_invoice(db, invoice, reason="test")


def test_void_unpaid_invoice():
    org_id, _ = _seed()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        inv_id = _due_invoice(org_id, org.contact_email or "a@b.com")
        invoice = db.get(BillingInvoice, inv_id)
        assert invoice is not None
        voided = InvoiceLifecycleService.void_invoice(db, invoice, reason="Duplicate")
        assert voided.status == "void"


def test_collecting_invoice_locked():
    org_id, _ = _seed()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        inv_id = _due_invoice(org_id, org.contact_email or "a@b.com", status="collecting")
        invoice = db.get(BillingInvoice, inv_id)
        assert invoice is not None
        invoice.dd_payment_id = "PM123"
        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        policy = InvoiceLifecycleService.policy(invoice)
        assert policy["can_void"] is False
        assert policy["suggested_action"] == "stop_collection"
