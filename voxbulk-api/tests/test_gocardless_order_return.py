"""GoCardless service-order browser return must not 404 (route ordering)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService


def test_gocardless_order_browser_return_is_not_shadowed_by_order_id_route(app_client):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="GC Return Org")
        db.add(org)
        db.flush()
        user = User(email=f"gc-return-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="interview",
            title="Engineer",
            status="quoted",
            payment_status="unpaid",
            quote_total_pence=5000,
            config_json="{}",
        )
        db.add(order)
        db.flush()
        row = BillingRedirectFlow(
            org_id=org.id,
            user_id=user.id,
            plan_id=None,
            service_order_id=order.id,
            redirect_flow_id="RE_TEST_RETURN",
            session_token="session-token-test",
            environment="sandbox",
            status="created",
            authorization_url="https://pay-sandbox.example/flow",
        )
        db.add(row)
        db.commit()

    res = app_client.get(
        "/service-orders/gocardless/browser-return",
        params={"session_token": "session-token-test", "order_billing": "success"},
        follow_redirects=False,
    )
    assert res.status_code == 302, res.text
    location = res.headers.get("location") or ""
    assert "order_billing=success" in location
    assert "redirect_flow_id=RE_TEST_RETURN" in location
    assert f"order_id={order.id}" in location
    assert "interviews/new" in location


def test_gocardless_survey_order_browser_return_targets_surveys_new(app_client):
    order_id = ""
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="GC Survey Return Org")
        db.add(org)
        db.flush()
        user = User(email=f"gc-survey-return-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="WA Survey",
            status="quoted",
            payment_status="unpaid",
            quote_total_pence=5000,
            config_json='{"delivery":"whatsapp"}',
        )
        db.add(order)
        db.flush()
        order_id = order.id
        row = BillingRedirectFlow(
            org_id=org.id,
            user_id=user.id,
            plan_id=None,
            service_order_id=order.id,
            redirect_flow_id="RE_SURVEY_RETURN",
            session_token="survey-session-token",
            environment="sandbox",
            status="created",
            authorization_url="https://pay-sandbox.example/flow",
        )
        db.add(row)
        db.commit()

    res = app_client.get(
        "/service-orders/gocardless/browser-return",
        params={"session_token": "survey-session-token", "order_billing": "success"},
        follow_redirects=False,
    )
    assert res.status_code == 302, res.text
    location = res.headers.get("location") or ""
    assert "surveys/new" in location
    assert "order_billing=success" in location
    assert "redirect_flow_id=RE_SURVEY_RETURN" in location
    assert f"order_id={order_id}" in location
    assert "interviews/new" not in location
