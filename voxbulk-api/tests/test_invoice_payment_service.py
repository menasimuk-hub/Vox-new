"""Invoice payment and order workflow state tests."""

from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.invoice_payment_service import InvoicePaymentError, InvoicePaymentService
from app.services.invoice_service import InvoiceService
from app.services.service_order_workflow_service import ServiceOrderWorkflowService
from app.services.wallet_service import WalletService


def _seed_org(*, wallet_minor: int = 5000) -> tuple[str, str]:
    email = f"inv-pay-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        org = Organisation(name="Invoice Pay Org", wallet_balance_pence=wallet_minor, contact_email=email)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, user.id


def test_invoice_payable_context_and_wallet_payment():
    org_id, user_id = _seed_org(wallet_minor=12_00)
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        assert org is not None
        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org_id,
            client_email=org.contact_email or "test@example.com",
            subtotal_pence=500,
            currency="GBP",
            description="Manual test invoice",
            provider="internal",
            external_invoice_id=f"manual-test-{uuid.uuid4().hex[:8]}",
            status="due",
            kind="manual",
        )
        invoice_id = invoice.id

    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        invoice = db.get(BillingInvoice, invoice_id)
        assert org is not None and invoice is not None
        ctx = InvoicePaymentService.payment_context(db, org, invoice)
        assert ctx["payable"] is True
        assert ctx["amount_due_minor"] == 500
        assert any(m["method"] == "wallet" for m in ctx["methods"])

        result = InvoicePaymentService.pay_with_wallet(db, org, invoice, user_id=user_id)
        assert result["ok"] is True
        assert result["method"] == "wallet"
        db.refresh(invoice)
        assert invoice.status == "paid"
        assert int(org.wallet_balance_pence or 0) == 700


def test_invoice_wallet_payment_insufficient_balance():
    org_id, user_id = _seed_org(wallet_minor=100)
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        assert org is not None
        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org_id,
            client_email=org.contact_email or "test@example.com",
            subtotal_pence=500,
            currency="GBP",
            description="Too expensive",
            provider="internal",
            external_invoice_id=f"manual-test-{uuid.uuid4().hex[:8]}",
            status="due",
            kind="manual",
        )
        invoice_id = invoice.id

    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        invoice = db.get(BillingInvoice, invoice_id)
        assert org is not None and invoice is not None
        ctx = InvoicePaymentService.payment_context(db, org, invoice)
        assert ctx["payable"] is True
        assert ctx["partial_wallet_supported"] is False
        wallet_method = next((m for m in ctx["methods"] if m["method"] == "wallet"), None)
        assert wallet_method is not None
        assert wallet_method["available"] is False
        assert ctx["wallet_shortfall_minor"] > 0
        try:
            InvoicePaymentService.pay_with_wallet(db, org, invoice, user_id=user_id)
            raise AssertionError("expected insufficient balance")
        except InvoicePaymentError:
            pass


def test_invoice_payment_approves_linked_order():
    org_id, user_id = _seed_org(wallet_minor=5000)
    with get_sessionmaker()() as db:
        order = ServiceOrder(
            org_id=org_id,
            user_id=user_id,
            service_code="survey",
            title="Linked order",
            status="quoted",
            payment_status="unpaid",
            quote_total_pence=400,
        )
        db.add(order)
        db.flush()
        org = db.get(Organisation, org_id)
        assert org is not None
        invoice = InvoiceService.create_from_payment(
            db,
            org_id=org_id,
            client_email=org.contact_email or "test@example.com",
            subtotal_pence=400,
            currency="GBP",
            description="Campaign invoice",
            provider="internal",
            external_invoice_id=f"order-{order.id}",
            status="due",
            kind="campaign",
            order_id=order.id,
        )
        order_id = order.id
        invoice_id = invoice.id

    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        invoice = db.get(BillingInvoice, invoice_id)
        order = db.get(ServiceOrder, order_id)
        assert org and invoice and order
        InvoicePaymentService.pay_with_wallet(db, org, invoice, user_id=user_id)
        db.refresh(order)
        assert order.payment_status == "approved"


def test_service_order_workflow_states():
    order = ServiceOrder(status="draft", payment_status="unpaid", quote_total_pence=1000)
    wf = ServiceOrderWorkflowService.visible_state(order)
    assert wf["workflow_state"] == "quoted"
    assert wf["pay_action"] == "pay_quote"

    order.payment_status = "pending_approval"
    order.status = "awaiting_payment"
    wf = ServiceOrderWorkflowService.visible_state(order)
    assert wf["workflow_state"] == "payment_pending"

    order.payment_status = "approved"
    order.status = "draft"
    wf = ServiceOrderWorkflowService.visible_state(order)
    assert wf["workflow_state"] == "launch_ready"

    order.status = "running"
    wf = ServiceOrderWorkflowService.visible_state(order)
    assert wf["workflow_state"] == "launched"
