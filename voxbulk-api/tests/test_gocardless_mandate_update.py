"""GoCardless mandate update redirect flow."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.subscription import Subscription
from app.models.user import User
from app.services.gocardless_service import BillingService, GoCardlessProviderError
from app.services.platform_catalog_service import PlatformCatalogService, ServiceOrderService


@pytest.fixture(autouse=True)
def _fresh_schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _seed_gc_org(*, mandate_id: str = "MD_OLD") -> tuple[str, str]:
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        BillingService.ensure_default_plans(db)
        from app.models.plan import Plan
        from sqlalchemy import select

        plan = db.execute(select(Plan).limit(1)).scalar_one()
        org = Organisation(name="Mandate Org")
        db.add(org)
        db.flush()
        user = User(
            email=f"mandate-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            mandate_id=mandate_id,
            mandate_status="active",
            external_subscription_id="SB123",
        )
        db.add(sub)
        db.commit()
        return org.id, user.id


def test_start_mandate_update_requires_existing_mandate():
    org_id, user_id = _seed_gc_org(mandate_id="")
    with get_sessionmaker()() as db:
        sub = BillingService.get_subscription(db, org_id)
        sub.mandate_id = None
        sub.mandate_status = None
        db.add(sub)
        db.commit()
        with patch.object(BillingService, "resolve_org_mandate_id", return_value=None):
            with pytest.raises(ValueError, match="No active Direct Debit mandate"):
                BillingService.start_mandate_update_redirect_flow(db, org_id=org_id, user_id=user_id)


@patch("app.services.gocardless_service.BillingService._get_gocardless_config")
@patch("app.services.gocardless_service.httpx.Client")
def test_complete_mandate_update_applies_new_and_cancels_old(mock_client_cls, mock_gc_config):
    mock_gc_config.return_value = {"access_token": "tok", "api_base": "https://api.gocardless.com", "environment": "sandbox"}
    org_id, user_id = _seed_gc_org(mandate_id="MD_OLD")
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    complete_resp = MagicMock()
    complete_resp.status_code = 200
    complete_resp.json.return_value = {
        "redirect_flows": {"links": {"mandate": "MD_NEW", "customer": "CU1"}},
    }

    mandate_resp = MagicMock()
    mandate_resp.status_code = 200
    mandate_resp.json.return_value = {"mandates": {"status": "active", "scheme": "bacs"}}

    mock_client.post.return_value = complete_resp
    mock_client.get.return_value = mandate_resp

    with get_sessionmaker()() as db:
        flow = BillingRedirectFlow(
            org_id=org_id,
            user_id=user_id,
            plan_id=BillingService.get_subscription(db, org_id).plan_id,
            redirect_flow_id="RE123",
            session_token="tok",
            environment="sandbox",
            status="created",
            flow_purpose="mandate_update",
            previous_mandate_id="MD_OLD",
        )
        db.add(flow)
        db.commit()

        with patch.object(BillingService, "_cancel_gocardless_mandate", return_value=True) as cancel_mock:
            res = BillingService.complete_mandate_update_redirect_flow(
                db,
                org_id=org_id,
                user_id=user_id,
                redirect_flow_id="RE123",
            )
        assert res["status"] == "completed"
        sub = BillingService.get_subscription(db, org_id)
        assert sub.mandate_id == "MD_NEW"
        cancel_mock.assert_called_once_with(db, "MD_OLD")


@patch("app.services.gocardless_service.BillingService._get_gocardless_config")
@patch("app.services.gocardless_service.httpx.Client")
def test_complete_mandate_update_rejects_inactive_mandate(mock_client_cls, mock_gc_config):
    mock_gc_config.return_value = {"access_token": "tok", "api_base": "https://api.gocardless.com", "environment": "sandbox"}
    org_id, user_id = _seed_gc_org()
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client

    complete_resp = MagicMock()
    complete_resp.status_code = 200
    complete_resp.json.return_value = {
        "redirect_flows": {"links": {"mandate": "MD_NEW", "customer": "CU1"}},
    }
    mandate_resp = MagicMock()
    mandate_resp.status_code = 200
    mandate_resp.json.return_value = {"mandates": {"status": "failed", "scheme": "bacs"}}
    mock_client.post.return_value = complete_resp
    mock_client.get.return_value = mandate_resp

    with get_sessionmaker()() as db:
        sub = BillingService.get_subscription(db, org_id)
        flow = BillingRedirectFlow(
            org_id=org_id,
            user_id=user_id,
            plan_id=sub.plan_id,
            redirect_flow_id="RE456",
            session_token="tok2",
            environment="sandbox",
            status="created",
            flow_purpose="mandate_update",
            previous_mandate_id="MD_OLD",
        )
        db.add(flow)
        db.commit()
        old_mandate = sub.mandate_id
        with pytest.raises(GoCardlessProviderError):
            BillingService.complete_mandate_update_redirect_flow(
                db,
                org_id=org_id,
                user_id=user_id,
                redirect_flow_id="RE456",
            )
        db.refresh(sub)
        assert sub.mandate_id == old_mandate


def test_survey_csv_parser_accepts_language_column():
    csv_text = "name,phone,language\nAlex,+447700900123,en\n"
    rows = ServiceOrderService.parse_recipient_file(csv_text.encode(), "contacts.csv")
    assert len(rows) == 1
    assert rows[0]["language"] == "en"


def test_billing_monitor_next_invoice_shape():
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        BillingService.ensure_default_plans(db)
        from app.models.plan import Plan
        from app.services.billing_monitor_service import BillingMonitorService
        from sqlalchemy import select

        plan = db.execute(select(Plan).limit(1)).scalar_one()
        org = Organisation(name="Next Invoice Org", wallet_balance_pence=500)
        db.add(org)
        db.flush()
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            status="active",
            payment_provider="gocardless",
            mandate_id="MD1",
            mandate_status="active",
            current_period_end=datetime.utcnow() + timedelta(days=10),
        )
        db.add(sub)
        db.commit()
        monitor = BillingMonitorService.build_for_org(db, org)
        ni = (monitor.get("status") or {}).get("next_invoice") or {}
        assert "amount_display" in ni
        assert "can_update_mandate" in ni
