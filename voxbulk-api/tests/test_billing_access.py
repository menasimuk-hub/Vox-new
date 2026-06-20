"""Phase 3 billing access control — credit limits, mandate blocks, first payment."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_access_service import BillingAccessService
from app.services.platform_catalog_service import PlatformCatalogService


def _seed_org(*, credit_limit_minor: int = 0) -> str:
    with get_sessionmaker()() as db:
        from app.services.gocardless_service import BillingService

        PlatformCatalogService.ensure_defaults(db)
        BillingService.ensure_default_plans(db)
        org = Organisation(name="Access Org", credit_limit_minor=credit_limit_minor)
        db.add(org)
        db.flush()
        user = User(
            email=f"access-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id


def test_access_summary_includes_allow_overage():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        org.allow_overage = False
        db.add(org)
        db.commit()
        summary = BillingAccessService.access_summary(db, org)
        assert summary["allow_overage"] is False


def test_credit_limit_blocks_launch():
    org_id = _seed_org(credit_limit_minor=5000)
    with get_sessionmaker()() as db:
        org = db.get(Organisation, org_id)
        db.add(
            BillingInvoice(
                org_id=org_id,
                provider="gocardless",
                external_invoice_id="outstanding-1",
                client_email="a@example.com",
                amount_gbp_pence=8000,
                subtotal_pence=8000,
                currency="GBP",
                status="past_due",
            )
        )
        db.commit()
        reason = BillingAccessService.launch_block_reason(db, org)
        assert reason is not None
        assert "credit limit" in reason.lower()


def test_mandate_cancelled_blocks_launch():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        from app.models.plan import Plan
        from sqlalchemy import select

        PlatformCatalogService.ensure_defaults(db)
        plan = db.execute(select(Plan).limit(1)).scalar_one()
        db.add(
            Subscription(
                org_id=org_id,
                plan_id=plan.id,
                status="active",
                payment_provider="gocardless",
                mandate_id="MD123",
                mandate_status="cancelled",
            )
        )
        db.commit()
        org = db.get(Organisation, org_id)
        reason = BillingAccessService.launch_block_reason(db, org)
        assert reason is not None
        assert "mandate" in reason.lower()


def test_deferred_scheme_sets_pending_first_payment():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        from app.models.plan import Plan
        from sqlalchemy import select

        plan = db.execute(select(Plan).limit(1)).scalar_one()
        sub = Subscription(org_id=org_id, plan_id=plan.id, status="pending_payment", payment_provider="gocardless")
        db.add(sub)
        db.commit()
        BillingAccessService.apply_mandate_setup_access(db, sub=sub, mandate_id="MD_ACH", scheme="ach")
        db.refresh(sub)
        assert sub.status == "pending_first_payment"
        assert sub.mandate_status == "active"


def test_first_payment_failure_suspends_within_grace():
    org_id = _seed_org()
    with get_sessionmaker()() as db:
        from app.models.plan import Plan
        from sqlalchemy import select

        plan = db.execute(select(Plan).limit(1)).scalar_one()
        sub = Subscription(
            org_id=org_id,
            plan_id=plan.id,
            status="pending_first_payment",
            payment_provider="gocardless",
            created_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add(sub)
        db.commit()
        suspended = BillingAccessService.handle_first_payment_failure(db, org_id=org_id)
        assert suspended is True
        db.refresh(sub)
        assert sub.status == "suspended"


def test_ghost_voxbulk_feedback_plan_does_not_block_launch():
    from app.models.customer_feedback import FEEDBACK_SERVICE_CODE
    from app.models.plan import Plan
    from app.services.customer_feedback.seed_service import FeedbackSeedService
    from app.services.subscription_cancellation_service import CANCELLATION_CANCELLED
    from sqlalchemy import select

    org_id = _seed_org()
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        cf_plan = db.execute(
            select(Plan).where(Plan.code == "cf_starter_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        db.add(
            Subscription(
                org_id=org_id,
                plan_id=cf_plan.id,
                service_code="voxbulk",
                status="active",
                cancellation_status=CANCELLATION_CANCELLED,
            )
        )
        db.add(
            Subscription(
                org_id=org_id,
                plan_id=cf_plan.id,
                service_code="customer_feedback",
                status="active",
            )
        )
        db.commit()
        org = db.get(Organisation, org_id)
        reason = BillingAccessService.launch_block_reason(db, org)
        assert reason is None


def test_remove_ghost_voxbulk_subscription():
    from app.models.customer_feedback import FEEDBACK_SERVICE_CODE
    from app.models.plan import Plan
    from app.services.customer_feedback.seed_service import FeedbackSeedService
    from app.services.customer_feedback.repair_service import FeedbackSubscriptionRepairService
    from sqlalchemy import select

    org_id = _seed_org()
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        cf_plan = db.execute(
            select(Plan).where(Plan.code == "cf_starter_gb", Plan.service_kind == FEEDBACK_SERVICE_CODE)
        ).scalar_one()
        ghost = Subscription(
            org_id=org_id,
            plan_id=cf_plan.id,
            service_code="voxbulk",
            status="cancelled",
        )
        active = Subscription(
            org_id=org_id,
            plan_id=cf_plan.id,
            service_code="customer_feedback",
            status="active",
        )
        db.add(ghost)
        db.add(active)
        db.commit()
        ghost_id = ghost.id

        removed = FeedbackSubscriptionRepairService.remove_ghost_voxbulk_subscriptions(db, org_id)
        assert ghost_id in removed
        assert db.get(Subscription, ghost_id) is None
        assert BillingAccessService.get_feedback_subscription(db, org_id) is not None
