"""Phase 1 billing finance foundation tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.models.payment_event import PaymentEvent
from app.models.wallet_transaction import WalletTransaction
from app.services.billing_exceptions_service import BillingExceptionsService
from app.services.billing_finance_service import BillingFinanceService, normalize_refund_status
from app.services.subscription_cancellation_service import (
    CANCELLATION_SCHEDULED,
    REVIEW_PENDING,
    SubscriptionCancellationService,
)


def _ensure_finance_columns(engine) -> None:
    """Patch sqlite test schema when tables predate migration 0117."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "subscriptions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("subscriptions")}
        with engine.begin() as conn:
            if "cancel_at_period_end" not in cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN cancel_at_period_end BOOLEAN DEFAULT 0"))
            if "next_billing_date" not in cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN next_billing_date DATETIME"))
            if "amount_next_payment_minor" not in cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN amount_next_payment_minor INTEGER"))
            if "billing_currency" not in cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN billing_currency VARCHAR(3)"))
            if "tax_rate_percent" not in cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN tax_rate_percent NUMERIC(5, 2)"))
            if "tax_country_code" not in cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN tax_country_code VARCHAR(2)"))
    if "payment_events" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("payment_events")}
        with engine.begin() as conn:
            for name, ddl in (
                ("event_kind", "VARCHAR(40)"),
                ("source", "VARCHAR(40)"),
                ("metadata_json", "TEXT"),
                ("actor_user_id", "VARCHAR(36)"),
                ("subscription_id", "VARCHAR(36)"),
            ):
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE payment_events ADD COLUMN {name} {ddl}"))


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_finance_columns(engine)


def _seed_org_with_sub(*, period_days: int = 25) -> tuple[str, str, str]:
    with get_sessionmaker()() as db:
        from app.services.gocardless_service import BillingService

        BillingService.ensure_default_plans(db)
        plan = db.execute(select(Plan).where(Plan.code != "payg").limit(1)).scalar_one()
        email = f"fin-{uuid.uuid4().hex[:8]}@example.com"
        org = Organisation(
            name="Finance Org",
            contact_email=email,
            wallet_balance_pence=0,
            country_code="GB",
            country="United Kingdom",
        )
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
        )
        db.add(sub)
        db.commit()
        return org.id, user.id, sub.id


def test_admin_wallet_credit_writes_ledger():
    org_id, _, _ = _seed_org_with_sub()
    with get_sessionmaker()() as db:
        from app.services.billing_lifecycle_service import BillingLifecycleService

        org = db.get(Organisation, org_id)
        before_tx = db.execute(
            select(WalletTransaction).where(WalletTransaction.org_id == org_id)
        ).scalars().all()
        assert len(before_tx) == 0
        BillingLifecycleService.admin_wallet_credit(
            db, org_id=org_id, amount_minor=1500, reason="Test credit"
        )
        db.refresh(org)
        txs = list(
            db.execute(
                select(WalletTransaction).where(WalletTransaction.org_id == org_id)
            ).scalars().all()
        )
        assert len(txs) == 1
        assert txs[0].direction == "credit"
        assert txs[0].amount_minor == 1500
        assert int(org.wallet_balance_pence or 0) == 1500


def test_migration_0117_columns_present():
    from sqlalchemy import inspect

    from app.core.database import get_engine

    insp = inspect(get_engine())
    sub_cols = {c["name"] for c in insp.get_columns("subscriptions")}
    for col in (
        "cancel_at_period_end",
        "next_billing_date",
        "amount_next_payment_minor",
        "billing_currency",
        "tax_rate_percent",
        "tax_country_code",
    ):
        assert col in sub_cols
    pe_cols = {c["name"] for c in insp.get_columns("payment_events")}
    for col in ("event_kind", "source", "metadata_json", "actor_user_id", "subscription_id"):
        assert col in pe_cols


def test_sync_subscription_billing_fields_tax_and_cancel_visibility():
    org_id, user_id, sub_id = _seed_org_with_sub()
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.request_cancellation(
            db,
            org_id=org_id,
            user_id=user_id,
            requested_refund_type="none",
        )
        sub = db.get(Subscription, sub_id)
        assert sub is not None
        assert sub.cancel_at_period_end is True
        assert sub.cancellation_status == CANCELLATION_SCHEDULED

    with get_sessionmaker()() as db:
        sub = db.get(Subscription, sub_id)
        org = db.get(Organisation, org_id)
        plan = db.get(Plan, sub.plan_id)
        BillingFinanceService.sync_subscription_billing_fields(db, sub, org=org, plan=plan)
        assert sub.next_billing_date == sub.cancellation_effective_at
        assert sub.tax_country_code == "GB"
        assert sub.tax_rate_percent is not None
        assert sub.amount_next_payment_minor == 0
        finance = BillingFinanceService.subscription_finance_dict(db, sub, org=org, plan=plan)
        assert finance["amount_next_payment_display"] == "No renewal (cancel scheduled)"


def test_refund_status_normalization():
    assert normalize_refund_status("completed") == "processed"
    assert normalize_refund_status("pending") == "pending"
    assert normalize_refund_status("failed") == "failed"


def test_wallet_ledger_list():
    org_id, _, _ = _seed_org_with_sub()
    with get_sessionmaker()() as db:
        from app.services.billing_lifecycle_service import BillingLifecycleService

        BillingLifecycleService.admin_wallet_credit(db, org_id=org_id, amount_minor=500, reason="x")
        rows = BillingFinanceService.list_wallet_ledger(db, org_id=org_id, limit=10)
        assert len(rows) >= 1
        assert rows[0]["org_id"] == org_id
        assert rows[0]["balance_after_minor"] is not None


def test_exceptions_detect_missing_next_billing():
    org_id, _, sub_id = _seed_org_with_sub()
    with get_sessionmaker()() as db:
        sub = db.get(Subscription, sub_id)
        sub.next_billing_date = None
        sub.current_period_end = None
        db.add(sub)
        db.commit()
        items = BillingExceptionsService.list_exceptions(db, limit=50)
        kinds = [i["kind"] for i in items if i.get("org_id") == org_id]
        assert "missing_next_billing_date" in kinds


def test_finalize_due_scheduled_cancellation_issues_wallet_credit():
    org_id, user_id, sub_id = _seed_org_with_sub(period_days=-1)
    with get_sessionmaker()() as db:
        sub = db.get(Subscription, sub_id)
        sub.current_period_end = datetime.utcnow() + timedelta(days=10)
        sub.cancellation_status = CANCELLATION_SCHEDULED
        sub.cancellation_type = "period_end"
        sub.cancellation_effective_at = datetime.utcnow() - timedelta(hours=1)
        sub.cancel_at_period_end = True
        sub.requested_refund_type = "wallet_credit"
        db.add(sub)
        db.commit()

    with get_sessionmaker()() as db:
        stats = SubscriptionCancellationService.finalize_due_scheduled_cancellations(db)
        assert stats["finalized"] >= 1
        assert stats.get("wallet_credit_issued", 0) >= 1
        sub = db.get(Subscription, sub_id)
        assert sub.status == "cancelled"
        assert sub.cancel_at_period_end is False
        txs = list(
            db.execute(
                select(WalletTransaction).where(WalletTransaction.org_id == org_id)
            ).scalars().all()
        )
        assert len(txs) >= 1
        events = list(
            db.execute(
                select(PaymentEvent).where(
                    PaymentEvent.org_id == org_id,
                    PaymentEvent.event_kind == "subscription.cancellation_closed",
                )
            ).scalars().all()
        )
        assert len(events) >= 1


def test_finalize_skips_wallet_for_payment_method_preference():
    org_id, _, sub_id = _seed_org_with_sub(period_days=-1)
    with get_sessionmaker()() as db:
        sub = db.get(Subscription, sub_id)
        sub.cancellation_status = CANCELLATION_SCHEDULED
        sub.cancellation_type = "period_end"
        sub.cancellation_effective_at = datetime.utcnow() - timedelta(hours=1)
        sub.cancel_at_period_end = True
        sub.requested_refund_type = "payment_method_refund"
        db.add(sub)
        db.commit()

    with get_sessionmaker()() as db:
        stats = SubscriptionCancellationService.finalize_due_scheduled_cancellations(db)
        assert stats["finalized"] == 1
        assert stats.get("wallet_credit_issued", 0) == 0
        txs = list(
            db.execute(
                select(WalletTransaction).where(WalletTransaction.org_id == org_id)
            ).scalars().all()
        )
        assert len(txs) == 0


def test_cancellation_request_records_payment_event():
    org_id, user_id, _ = _seed_org_with_sub()
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.request_cancellation(
            db, org_id=org_id, user_id=user_id, requested_refund_type="wallet_credit"
        )
        events = list(
            db.execute(
                select(PaymentEvent).where(
                    PaymentEvent.org_id == org_id,
                    PaymentEvent.event_kind == "subscription.cancellation_scheduled",
                )
            ).scalars().all()
        )
        assert len(events) == 1


def test_upgrade_preview_returns_pro_rata():
    org_id, _, _ = _seed_org_with_sub()
    with get_sessionmaker()() as db:
        plans = list(db.execute(select(Plan).where(Plan.code != "payg")).scalars().all())
        assert len(plans) >= 2
        sub = SubscriptionCancellationService.get_subscription(db, org_id)
        current = db.get(Plan, sub.plan_id)
        target = next(p for p in plans if p.id != current.id)
        preview = BillingFinanceService.upgrade_preview(db, org_id, new_plan_code=target.code)
        assert preview["new_plan_code"] == target.code
        assert "pro_rata_display" in preview
        assert preview["currency"] in {"GBP", "USD", "CAD", "AUD", "EUR"}


def test_cancellation_preview_endpoint_shape():
    org_id, user_id, _ = _seed_org_with_sub()
    with get_sessionmaker()() as db:
        SubscriptionCancellationService.request_cancellation(
            db, org_id=org_id, user_id=user_id, requested_refund_type="wallet_credit"
        )
        preview = BillingFinanceService.cancellation_preview(db, org_id)
        assert preview["status"] == CANCELLATION_SCHEDULED
        assert "subscription_finance" in preview
        review = SubscriptionCancellationService.get_open_refund_review(db, org_id)
        assert review is not None
        assert review.review_status == REVIEW_PENDING
