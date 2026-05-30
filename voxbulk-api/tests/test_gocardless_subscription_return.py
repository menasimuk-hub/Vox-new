"""GoCardless subscription return URLs use /account/packages, not legacy /packages."""

from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.gocardless_service import BillingService


def test_subscription_browser_return_uses_account_packages(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="GC Sub Return")
        db.add(org)
        db.flush()
        user = User(email=f"gc-sub-{uuid.uuid4().hex[:8]}@test.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.add(
            BillingRedirectFlow(
                org_id=org.id,
                user_id=user.id,
                plan_id=None,
                redirect_flow_id="RE_SUB_RETURN",
                session_token="sub-session-token",
                environment="sandbox",
                status="created",
                authorization_url="https://pay-sandbox.example/flow",
            )
        )
        db.commit()

    res = app_client.get(
        "/billing/subscription/gocardless/browser-return",
        params={"session_token": "sub-session-token", "billing": "success"},
        follow_redirects=False,
    )
    assert res.status_code == 302, res.text
    location = res.headers.get("location") or ""
    assert "/account/packages" in location
    assert "/packages?" not in location.replace("/account/packages", "")
    assert "redirect_flow_id=RE_SUB_RETURN" in location


def test_normalize_legacy_packages_return_url():
    fixed = BillingService._normalize_dashboard_return_url(
        "https://dashboard.voxbulk.com/packages?billing=success"
    )
    assert fixed == "https://dashboard.voxbulk.com/account/packages?billing=success"
