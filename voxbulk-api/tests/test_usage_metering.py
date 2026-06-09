from __future__ import annotations

from datetime import datetime, timedelta

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.usage_wallet_service import UsageWalletService
from app.services.whatsapp_template_service import WhatsAppTemplateService


def test_call_hangup_increments_usage(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Meter Org")
        db.add(org)
        db.flush()
        user = User(email="meter@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        plan = Plan(
            code="meter_plan",
            name="Meter Plan",
            price_gbp_pence=1000,
            interval="month",
            calls_included=10,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(plan)
        db.flush()
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            current_period_end=datetime.utcnow() + timedelta(days=30),
            payment_provider="manual_cash",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(sub)
        db.flush()
        row = OrgUsagePeriod(
            org_id=org.id,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            status="active",
            plan_code=plan.code,
            calls_included=10,
            calls_used=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        org_id = org.id

    payload = {
        "data": {
            "event_type": "call.hangup",
            "payload": {
                "call_control_id": "v3:meter-call-001",
                "call_status": "completed",
            },
        }
    }
    r = app_client.post("/telnyx/webhooks/status", json=payload, headers={"X-Retover-Org-Id": org_id})
    assert r.status_code == 200

    with get_sessionmaker()() as db:
        row = UsageWalletService.get_current(db, org_id)
        assert row is not None
        assert int(row.calls_used or 0) == 1


def test_usage_80_warning_email_sent_once(monkeypatch):
    sent: list[dict] = []

    def fake_send(db, *, template_key, to_email, variables):
        sent.append({"template_key": template_key, "to_email": to_email, "variables": variables})
        return True, None

    monkeypatch.setattr(
        "app.services.transactional_email_service.TransactionalEmailService.send_templated_optional",
        fake_send,
    )

    with get_sessionmaker()() as db:
        org = Organisation(name="Warn Org")
        db.add(org)
        db.flush()
        user = User(email="warn@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        row = OrgUsagePeriod(
            org_id=org.id,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            status="active",
            plan_code="dental_1",
            calls_included=10,
            calls_used=7,
            warned_at_80=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        org_id = org.id

        UsageWalletService.record_call_usage(db, org_id=org_id, units=2)
        assert len(sent) == 1
        assert sent[0]["template_key"] == "usage_warning"

        UsageWalletService.record_call_usage(db, org_id=org_id, units=1)
        assert len(sent) == 2
        assert sent[1]["template_key"] == "usage_warning_100"


def test_whatsapp_sales_offer_system_template():
    with get_sessionmaker()() as db:
        WhatsAppTemplateService.ensure_system_templates(db)
        row = WhatsAppTemplateService.render_body(
            db,
            template_key="sales_offer",
            variables={"first_name": "Alex", "trial_line": "15-day trial", "promo_name": "Offer", "signup_url": "https://x.test/p"},
            fallback="fallback",
        )
        assert "Alex" in row
        assert "https://x.test/p" in row


def test_usage_period_rollover_opens_fresh_period():
    with get_sessionmaker()() as db:
        org = Organisation(name="Rollover Org")
        db.add(org)
        db.flush()
        plan = Plan(
            code="roll_plan",
            name="Roll Plan",
            price_gbp_pence=2000,
            interval="month",
            calls_included=50,
            whatsapp_included=100,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(plan)
        db.flush()
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            current_period_end=datetime.utcnow() - timedelta(days=1),
            payment_provider="manual_cash",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(sub)
        db.flush()
        expired = OrgUsagePeriod(
            org_id=org.id,
            period_start=datetime.utcnow() - timedelta(days=31),
            period_end=datetime.utcnow() - timedelta(hours=1),
            status="active",
            plan_code=plan.code,
            calls_included=50,
            calls_used=55,
            overage_per_min_pence=20,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(expired)
        db.commit()
        org_id = org.id

        stats = UsageWalletService.rollover_due_periods(db)
        assert stats["closed"] == 1
        assert stats["opened"] == 1

        current = UsageWalletService.get_current(db, org_id)
        assert current is not None
        assert current.status == "active"
        assert int(current.calls_used or 0) == 0
        assert int(current.calls_included or 0) == 50
        assert current.period_end > datetime.utcnow()


def test_resolve_active_plan_from_usage_when_subscription_plan_id_stale():
    from app.services.gocardless_service import BillingService

    with get_sessionmaker()() as db:
        org = Organisation(name="Resolve Org")
        db.add(org)
        db.flush()
        plan = Plan(
            code="starter",
            name="Starter",
            price_gbp_pence=9900,
            interval="monthly",
            calls_included=100,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(plan)
        db.flush()
        stale_plan_id = "00000000-0000-0000-0000-000000000099"
        sub = Subscription(
            org_id=org.id,
            plan_id=stale_plan_id,
            status="active",
            current_period_end=datetime.utcnow() + timedelta(days=30),
            payment_provider="gocardless",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(sub)
        db.flush()
        row = OrgUsagePeriod(
            org_id=org.id,
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow() + timedelta(days=30),
            status="active",
            plan_code=plan.code,
            calls_included=100,
            calls_used=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()
        org_id = org.id

        resolved = BillingService.resolve_active_plan(db, org_id)
        assert resolved is not None
        assert resolved.id == plan.id
        assert resolved.code == "starter"

        repaired = BillingService.repair_subscription_plan_id(db, org_id)
        assert repaired is not None
        assert repaired.plan_id == plan.id
