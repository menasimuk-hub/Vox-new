"""Phase 2 billing lifecycle — reconciliation, DD recovery, disputes, monthly billing."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.credit_note import CreditNote
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.service_order import ServiceOrder
from app.models.subscription import Subscription
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction
from app.services.billing_lifecycle_service import BillingLifecycleService
from app.services.billing_reconciliation_service import BillingReconciliationService
from app.services.platform_catalog_service import PlatformCatalogService


def _seed_org_with_wallet(*, wallet_minor: int = 5000) -> tuple[str, str, str]:
    email = f"lifecycle-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        from app.services.gocardless_service import BillingService

        PlatformCatalogService.ensure_defaults(db)
        BillingService.ensure_default_plans(db)
        org = Organisation(name="Lifecycle Org", wallet_balance_pence=wallet_minor, contact_email=email)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, user.id, email


def test_reconciliation_refunds_unused_wallet_charge_to_wallet():
    org_id, user_id, _email = _seed_org_with_wallet(wallet_minor=10_000)
    with get_sessionmaker()() as db:
        order = ServiceOrder(
            org_id=org_id,
            user_id=user_id,
            service_code="survey",
            title="WA refund test",
            status="running",
            payment_status="approved",
            recipient_count=3,
            launch_billing_json=json.dumps(
                {
                    "channel": "whatsapp",
                    "currency": "GBP",
                    "unit_rate_minor": 100,
                    "wallet_charge_minor": 300,
                    "dd_charge_minor": 0,
                    "units_billable": 3,
                }
            ),
        )
        db.add(order)
        db.commit()
        order_id = order.id

    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        org = db.get(Organisation, org_id)
        assert org is not None
        before = int(org.wallet_balance_pence or 0)
        result = BillingReconciliationService.reconcile_order(db, order, trigger="cancellation")
        assert result is not None
        assert int(result["refund_minor"]) == 300
        db.refresh(org)
        assert int(org.wallet_balance_pence or 0) == before + 300

    with get_sessionmaker()() as db:
        notes = list(db.execute(select(CreditNote).where(CreditNote.org_id == org_id)).scalars().all())
        assert len(notes) == 1
        assert notes[0].refund_method == "wallet"
        txs = list(
            db.execute(
                select(WalletTransaction).where(
                    WalletTransaction.org_id == org_id,
                    WalletTransaction.kind == "campaign_refund",
                )
            ).scalars().all()
        )
        assert len(txs) == 1


def test_reconciliation_is_idempotent():
    org_id, user_id, _email = _seed_org_with_wallet()
    with get_sessionmaker()() as db:
        order = ServiceOrder(
            org_id=org_id,
            user_id=user_id,
            service_code="survey",
            title="Idempotent",
            payment_status="approved",
            launch_billing_json=json.dumps(
                {
                    "channel": "whatsapp",
                    "currency": "GBP",
                    "unit_rate_minor": 50,
                    "wallet_charge_minor": 100,
                    "dd_charge_minor": 0,
                    "units_billable": 2,
                }
            ),
        )
        db.add(order)
        db.commit()
        order_id = order.id

    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        BillingReconciliationService.reconcile_order(db, order, trigger="completion")
        BillingReconciliationService.reconcile_order(db, order, trigger="completion")
        notes = list(db.execute(select(CreditNote).where(CreditNote.org_id == org_id)).scalars().all())
        assert len(notes) == 1


def test_dd_failure_schedules_retry_and_marks_past_due_after_max():
    org_id, _, email = _seed_org_with_wallet()
    with get_sessionmaker()() as db:
        invoice = BillingInvoice(
            org_id=org_id,
            provider="gocardless",
            external_invoice_id="launch-test-1",
            client_email=email,
            amount_gbp_pence=1500,
            subtotal_pence=1500,
            currency="GBP",
            status="collecting",
            dd_payment_id="PM_FAIL_1",
            dd_retry_count=0,
        )
        db.add(invoice)
        db.commit()
        invoice_id = invoice.id

    with get_sessionmaker()() as db:
        result = BillingLifecycleService.handle_dd_payment_failure(
            db,
            payment_id="PM_FAIL_1",
            org_id=org_id,
            client_email=email,
            failure_reason="Insufficient funds",
        )
        assert result is not None
        assert result["dd_retry_count"] == 1
        assert result["dd_next_retry_at"] is not None

    with get_sessionmaker()() as db:
        invoice = db.get(BillingInvoice, invoice_id)
        assert invoice is not None
        invoice.dd_retry_count = 3
        invoice.dd_next_retry_at = None
        db.add(invoice)
        db.commit()

    with get_sessionmaker()() as db:
        result = BillingLifecycleService.handle_dd_payment_failure(
            db,
            payment_id="PM_FAIL_1",
            org_id=org_id,
            client_email=email,
        )
        assert result is not None
        invoice = db.get(BillingInvoice, invoice_id)
        assert invoice.status == "past_due"


def test_dispute_pauses_dd_retry_scheduling():
    org_id, _, email = _seed_org_with_wallet()
    with get_sessionmaker()() as db:
        invoice = BillingInvoice(
            org_id=org_id,
            provider="gocardless",
            external_invoice_id="dispute-1",
            client_email=email,
            amount_gbp_pence=900,
            subtotal_pence=900,
            currency="GBP",
            status="failed",
            dd_payment_id="PM_DISPUTE",
            dd_retry_count=1,
            dd_next_retry_at=datetime.utcnow() + timedelta(days=2),
        )
        db.add(invoice)
        db.commit()
        invoice_id = invoice.id

    with get_sessionmaker()() as db:
        row = BillingLifecycleService.set_invoice_disputed(db, invoice_id=invoice_id, note="Customer query")
        assert row.disputed is True
        assert row.dd_next_retry_at is None
        assert row.status == "disputed"


def test_monthly_billing_skips_gocardless_managed_subscription():
    org_id, _, _email = _seed_org_with_wallet()
    with get_sessionmaker()() as db:
        plan = db.execute(select(Plan).limit(1)).scalar_one()
        sub = Subscription(
            org_id=org_id,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            external_subscription_id="SB_SKIP_TEST",
            mandate_id="MD_SKIP_TEST",
            mandate_status="active",
            current_period_end=datetime.utcnow() - timedelta(hours=1),
        )
        db.add(sub)
        db.commit()

    with patch("app.services.gocardless_service.BillingService.collect_mandate_payment") as collect_mock:
        with get_sessionmaker()() as db:
            stats = BillingLifecycleService.process_due_monthly_billing(db)
            assert stats["skipped"] >= 1
            collect_mock.assert_not_called()


def test_monthly_billing_creates_subscription_invoice():
    org_id, _, email = _seed_org_with_wallet()
    with get_sessionmaker()() as db:
        plan = db.execute(select(Plan).limit(1)).scalar_one()
        sub = Subscription(
            org_id=org_id,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            current_period_end=datetime.utcnow() - timedelta(hours=1),
        )
        db.add(sub)
        db.commit()
        sub_id = sub.id

    with patch(
        "app.services.gocardless_service.BillingService.collect_mandate_payment",
        return_value={"payment_id": "PM_MONTHLY_1", "status": "pending_submission"},
    ), patch(
        "app.services.billing_event_email_service.BillingEventEmailService.issue_payment_invoice",
        return_value=(None, False, False),
    ):
        with get_sessionmaker()() as db:
            stats = BillingLifecycleService.process_due_monthly_billing(db)
            assert stats["invoiced"] >= 1

    with get_sessionmaker()() as db:
        sub = db.get(Subscription, sub_id)
        assert sub is not None
        assert sub.current_period_end > datetime.utcnow()
        invoices = list(
            db.execute(select(BillingInvoice).where(BillingInvoice.org_id == org_id, BillingInvoice.kind == "subscription"))
            .scalars()
            .all()
        )
        assert len(invoices) >= 1
