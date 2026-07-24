"""Member campaign visibility — own campaigns only; owner/manager see all."""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.customer_feedback import (
    FeedbackIndustry,
    FeedbackLocation,
    FeedbackSurveyType,
    FeedbackWaSender,
)
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.customer_feedback.location_service import FeedbackLocationService
from app.services.customer_feedback.seed_service import FeedbackSeedService
from app.services.org_enabled_services import (
    merge_admin_allowed_services,
    serialize_allowed_services,
    serialize_enabled_services,
)
from app.services.org_rbac import (
    OrgRbacService,
    can_view_all_campaigns,
    campaign_owner_filter,
    effective_role,
)
from app.services.platform_catalog_service import ServiceOrderService


def test_campaign_owner_filter_helpers():
    assert can_view_all_campaigns("owner") is True
    assert can_view_all_campaigns("manager") is True
    assert can_view_all_campaigns("member") is False
    assert can_view_all_campaigns("accountant") is False
    assert campaign_owner_filter("owner", "u1") is None
    assert campaign_owner_filter("manager", "u1") is None
    assert campaign_owner_filter("member", "u1") == "u1"
    assert campaign_owner_filter("accountant", "u1") == "u1"
    assert effective_role("receptionist") == "member"


def test_accountant_cannot_launch_campaigns():
    with get_sessionmaker()() as db:
        org = Organisation(name="Acct Vis Org")
        db.add(org)
        db.flush()
        user = User(
            email=f"acct-vis-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="accountant"))
        db.commit()
        org_id, user_id = org.id, user.id

    with get_sessionmaker()() as db:
        with pytest.raises(PermissionError, match="Campaign access denied"):
            OrgRbacService.assert_can_launch_campaigns(db, org_id=org_id, user_id=user_id)


def test_member_lists_only_own_service_orders(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Visibility Org")
        db.add(org)
        db.flush()
        owner = User(
            email=f"vis-owner-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        member_a = User(
            email=f"vis-member-a-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        member_b = User(
            email=f"vis-member-b-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add_all([owner, member_a, member_b])
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
        db.add(OrganisationMembership(org_id=org.id, user_id=member_a.id, role="member"))
        db.add(OrganisationMembership(org_id=org.id, user_id=member_b.id, role="member"))
        allowed, enabled = merge_admin_allowed_services(
            {"interview": True, "survey": True},
            {"interview": True, "survey": True},
            {"interview": True, "survey": True},
        )
        org.allowed_services_json = serialize_allowed_services(allowed)
        org.enabled_services_json = serialize_enabled_services(enabled)
        db.add(org)
        order_a = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=member_a.id,
            service_code="interview",
            title="A campaign",
            config={"draft_saved_by_user": True, "role": "Engineer"},
        )
        order_b = ServiceOrderService.create_order(
            db,
            org_id=org.id,
            user_id=member_b.id,
            service_code="interview",
            title="B campaign",
            config={"draft_saved_by_user": True, "role": "Designer"},
        )
        db.commit()
        org_id = org.id
        order_a_id = order_a.id
        order_b_id = order_b.id
        email_a = member_a.email
        email_b = member_b.email
        email_owner = owner.email

    def _headers(email: str) -> dict[str, str]:
        res = app_client.post(
            "/auth/token",
            data={"username": email, "password": "pass123", "org_id": org_id},
        )
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    headers_a = _headers(email_a)
    headers_b = _headers(email_b)
    headers_owner = _headers(email_owner)

    list_a = app_client.get("/service-orders?service_code=interview", headers=headers_a)
    assert list_a.status_code == 200, list_a.text
    ids_a = {row["id"] for row in list_a.json()}
    assert order_a_id in ids_a
    assert order_b_id not in ids_a

    list_owner = app_client.get("/service-orders?service_code=interview", headers=headers_owner)
    assert list_owner.status_code == 200
    ids_owner = {row["id"] for row in list_owner.json()}
    assert order_a_id in ids_owner and order_b_id in ids_owner

    assert app_client.get(f"/service-orders/{order_b_id}", headers=headers_a).status_code == 404
    assert app_client.get(f"/service-orders/{order_a_id}", headers=headers_a).status_code == 200
    assert app_client.get(f"/service-orders/{order_a_id}", headers=headers_b).status_code == 404
    assert app_client.get(f"/service-orders/{order_a_id}", headers=headers_owner).status_code == 200


def test_feedback_locations_scoped_by_creator(app_client):
    with get_sessionmaker()() as db:
        FeedbackSeedService.ensure_seeded(db)
        industry = db.execute(select(FeedbackIndustry).limit(1)).scalar_one()
        survey_type = db.execute(
            select(FeedbackSurveyType)
            .where(FeedbackSurveyType.industry_id == industry.id)
            .order_by(FeedbackSurveyType.sort_order)
            .limit(1)
        ).scalar_one()
        sender = db.execute(
            select(FeedbackWaSender).where(FeedbackWaSender.country_code == "gb")
        ).scalar_one_or_none()
        if sender is None:
            db.add(
                FeedbackWaSender(
                    id=str(uuid.uuid4()),
                    country_code="gb",
                    phone_e164="+447700900111",
                    is_active=True,
                    created_at=datetime.utcnow(),
                )
            )
        else:
            sender.phone_e164 = "+447700900111"
            db.add(sender)

        org = Organisation(
            name="FB Vis Org",
            allowed_services_json='{"customer_feedback": true}',
            enabled_services_json='{"customer_feedback": true}',
        )
        db.add(org)
        db.flush()
        owner = User(
            email=f"fb-vis-owner-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        member_a = User(
            email=f"fb-vis-a-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        member_b = User(
            email=f"fb-vis-b-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("pass123"),
            is_active=True,
        )
        db.add_all([owner, member_a, member_b])
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
        db.add(OrganisationMembership(org_id=org.id, user_id=member_a.id, role="member"))
        db.add(OrganisationMembership(org_id=org.id, user_id=member_b.id, role="member"))

        now = datetime.utcnow()
        loc_a = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org.id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Loc A",
            qr_token=f"a-{uuid.uuid4().hex[:10]}",
            wa_sender_country="gb",
            status="active",
            created_by_user_id=member_a.id,
            created_at=now,
            updated_at=now,
        )
        loc_b = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org.id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Loc B",
            qr_token=f"b-{uuid.uuid4().hex[:10]}",
            wa_sender_country="gb",
            status="active",
            created_by_user_id=member_b.id,
            created_at=now,
            updated_at=now,
        )
        loc_legacy = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org.id,
            industry_id=industry.id,
            survey_type_id=survey_type.id,
            name="Legacy",
            qr_token=f"l-{uuid.uuid4().hex[:10]}",
            wa_sender_country="gb",
            status="active",
            created_by_user_id=None,
            created_at=now,
            updated_at=now,
        )
        db.add_all([loc_a, loc_b, loc_legacy])
        db.commit()
        org_id = org.id
        loc_a_id, loc_b_id, loc_legacy_id = loc_a.id, loc_b.id, loc_legacy.id
        email_a, email_owner = member_a.email, owner.email
        member_a_id = member_a.id

    # Service-layer scope
    with get_sessionmaker()() as db:
        own = FeedbackLocationService.list_locations(db, org_id, created_by_user_id=member_a_id)
        assert {r["id"] for r in own} == {loc_a_id}
        all_rows = FeedbackLocationService.list_locations(db, org_id, created_by_user_id=None)
        assert {r["id"] for r in all_rows} >= {loc_a_id, loc_b_id, loc_legacy_id}

    def _headers(email: str) -> dict[str, str]:
        res = app_client.post(
            "/auth/token",
            data={"username": email, "password": "pass123", "org_id": org_id},
        )
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    headers_a = _headers(email_a)
    headers_owner = _headers(email_owner)

    list_a = app_client.get("/customer-feedback/locations", headers=headers_a)
    assert list_a.status_code == 200, list_a.text
    ids_a = {row["id"] for row in list_a.json()["items"]}
    assert ids_a == {loc_a_id}
    assert loc_legacy_id not in ids_a

    list_owner = app_client.get("/customer-feedback/locations", headers=headers_owner)
    assert list_owner.status_code == 200
    ids_owner = {row["id"] for row in list_owner.json()["items"]}
    assert loc_a_id in ids_owner and loc_b_id in ids_owner and loc_legacy_id in ids_owner

    # Direct access: members get 400/404-style ValueError mapped to 400 on update of others' / legacy rows
    deny_b = app_client.patch(
        f"/customer-feedback/locations/{loc_b_id}",
        headers=headers_a,
        json={"name": "Hijack B"},
    )
    assert deny_b.status_code == 400, deny_b.text
    deny_legacy = app_client.patch(
        f"/customer-feedback/locations/{loc_legacy_id}",
        headers=headers_a,
        json={"name": "Hijack Legacy"},
    )
    assert deny_legacy.status_code == 400, deny_legacy.text
    allow_a = app_client.patch(
        f"/customer-feedback/locations/{loc_a_id}",
        headers=headers_a,
        json={"name": "Loc A updated"},
    )
    assert allow_a.status_code == 200, allow_a.text
