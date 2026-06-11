"""Subscription cancellation, wallet credit, and admin refund review workflow."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.org_audit_event import OrganisationAuditEvent
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction
from app.services.subscription_cancellation_service import (
    CANCELLATION_SCHEDULED,
    CANCELLATION_REVERSED,
    REVIEW_PENDING,
    SubscriptionCancellationError,
    SubscriptionCancellationService,
)


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _seed_subscription_org(*, period_days: int = 20) -> tuple[str, str, str, str]:
    with get_sessionmaker()() as db:
        from app.services.gocardless_service import BillingService

        BillingService.ensure_default_plans(db)
        plan = db.execute(select(Plan).where(Plan.code != "payg").limit(1)).scalar_one()
        email = f"cancel-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(name="Cancel Org", contact_email=email, wallet_balance_pence=0)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        period_end = datetime.utcnow() + timedelta(days=period_days)
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            current_period_end=period_end,
            mandate_id="MD_TEST",
            mandate_status="active",
        )
        db.add(sub)
        db.add(
            BillingInvoice(
                org_id=org.id,
                provider="gocardless",
                external_invoice_id=f"sub-monthly-{uuid.uuid4().hex[:8]}",
                client_email=email,
                amount_gbp_pence=plan.price_gbp_pence or 9900,
                subtotal_pence=plan.price_gbp_pence or 9900,
                currency="GBP",
                status="paid",
                description="Monthly subscription",
                payment_method="gocardless",
                payment_reference="PM123",
            )
        )
        db.commit()
        return org.id, user.id, sub.id, plan.id


def test_request_cancel_at_period_end():
    org_id, user_id, sub_id, _plan_id = _seed_subscription_org()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        result = SubscriptionCancellationService.request_cancellation(
            db,
            org_id=org_id,
            user_id=user_id,
            cancellation_type="period_end",
            reason="Too expensive",
            requested_refund_type="none",
        )
        assert result["status"] == CANCELLATION_SCHEDULED
        sub = db.get(Subscription, sub_id)
        assert sub is not None
        assert sub.cancellation_status == CANCELLATION_SCHEDULED
        assert sub.cancellation_effective_at == sub.current_period_end


def test_wallet_credit_review_and_duplicate_prevention():
    org_id, user_id, sub_id, _plan_id = _seed_subscription_org(period_days=15)
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.request_cancellation(
            db,
            org_id=org_id,
            user_id=user_id,
            requested_refund_type="wallet_credit",
        )
        review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        assert review is not None
        assert review.review_status == REVIEW_PENDING

    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        sub = db.get(Subscription, sub_id)
        review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        before = int(org.wallet_balance_pence or 0)
        wallet_result = SubscriptionCancellationService.issue_wallet_credit(
            db,
            org=org,
            sub=sub,
            amount_minor=500,
            admin_user_id=user_id,
            note="Approved cancellation credit",
            refund_review=review,
        )
        db.commit()
        db.refresh(org)
        assert wallet_result["wallet_credit_pence"] == 500
        assert int(org.wallet_balance_pence or 0) == before + 500
        txs = list(
            db.execute(
                select(WalletTransaction).where(
                    WalletTransaction.org_id == org_id,
                    WalletTransaction.kind == "subscription_cancellation_credit",
                )
            )
            .scalars()
            .all()
        )
        assert len(txs) == 1

    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        sub = db.get(Subscription, sub_id)
        review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        try:
            SubscriptionCancellationService.issue_wallet_credit(
                db,
                org=org,
                sub=sub,
                amount_minor=100,
                admin_user_id=user_id,
                note="Duplicate",
                refund_review=review,
            )
            raised = False
        except SubscriptionCancellationError:
            raised = True
        assert raised


def test_refund_review_created_for_payment_method_request():
    org_id, user_id, _sub_id, _plan_id = _seed_subscription_org()
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.request_cancellation(
            db,
            org_id=org_id,
            user_id=user_id,
            requested_refund_type="payment_method_refund",
        )
        review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        assert review is not None
        assert review.requested_refund_type == "payment_method_refund"
        assert review.source_payment_provider == "gocardless"
        assert review.source_payment_reference == "PM123"


def test_admin_immediate_cancel_and_audit_events():
    org_id, user_id, sub_id, _plan_id = _seed_subscription_org()
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.admin_approve_immediate_cancel(
            db,
            org_id=org_id,
            admin_user_id=user_id,
            issue_wallet_credit=False,
            note="Admin cancel",
        )
        sub = db.get(Subscription, sub_id)
        assert sub is not None
        assert sub.status == "cancelled"
        events = list(
            db.execute(
                select(OrganisationAuditEvent).where(
                    OrganisationAuditEvent.org_id == org_id,
                    OrganisationAuditEvent.event_type == "subscription.cancellation_approved",
                )
            )
            .scalars()
            .all()
        )
        assert len(events) >= 1


def test_finalize_due_scheduled_cancellations():
    org_id, user_id, sub_id, _plan_id = _seed_subscription_org(period_days=0)
    with get_sessionmaker()() as db:
        sub = db.get(Subscription, sub_id)
        sub.cancellation_status = CANCELLATION_SCHEDULED
        sub.cancellation_effective_at = datetime.utcnow() - timedelta(hours=1)
        db.add(sub)
        db.commit()

    with get_sessionmaker()() as db:
        stats = SubscriptionCancellationService.finalize_due_scheduled_cancellations(db)
        assert stats["finalized"] == 1
        sub = db.get(Subscription, sub_id)
        assert sub.status == "cancelled"


def test_double_compensation_guard_on_external_refund():
    org_id, user_id, sub_id, _plan_id = _seed_subscription_org(period_days=10)
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.request_cancellation(
            db,
            org_id=org_id,
            user_id=user_id,
            requested_refund_type="either",
        )
        review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        org = db.get(Organisation, org_id)
        sub = db.get(Subscription, sub_id)
        SubscriptionCancellationService.issue_wallet_credit(
            db,
            org=org,
            sub=sub,
            amount_minor=300,
            admin_user_id=user_id,
            note="Partial wallet",
            refund_review=review,
        )
        db.commit()
        review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        calculated = int(review.calculated_unused_value_pence or 0)
        try:
            SubscriptionCancellationService.resolve_refund_review(
                db,
                review_id=review.id,
                admin_user_id=user_id,
                review_status="completed",
                approved_external_refund_pence=calculated,
            )
            raised = False
        except SubscriptionCancellationError:
            raised = True
        assert raised


def test_customer_can_reverse_scheduled_cancellation():
    org_id, user_id, sub_id, _plan_id = _seed_subscription_org(period_days=20)
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.request_cancellation(
            db,
            org_id=org_id,
            user_id=user_id,
            requested_refund_type="wallet_credit",
        )
        sub = db.get(Subscription, sub_id)
        assert sub.cancellation_status == CANCELLATION_SCHEDULED

    with get_sessionmaker()() as db:
        payload = SubscriptionCancellationService.reverse_cancellation(
            db,
            org_id=org_id,
            admin_user_id=user_id,
            note="Customer changed mind",
        )
        assert payload["status"] in {CANCELLATION_REVERSED, "none"}
        sub = db.get(Subscription, sub_id)
        assert str(sub.cancellation_status or "").lower() in {CANCELLATION_REVERSED, "none"}
        assert SubscriptionCancellationService.get_open_refund_review(db, org_id) is None


def test_billing_refund_email_templates_registered():
    from app.services.email_template_service import EMAIL_TEMPLATE_KEYS

    for key in (
        "billing_cancellation_requested",
        "billing_cancellation_reversed",
        "billing_wallet_credit_issued",
        "billing_bank_refund_approved",
        "billing_refund_request_rejected",
    ):
        assert key in EMAIL_TEMPLATE_KEYS
