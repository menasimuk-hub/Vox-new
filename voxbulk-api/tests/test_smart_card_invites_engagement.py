"""Smart Card invites, member edit whitelist, and engagement KPIs."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from app.core.database import get_sessionmaker
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.smart_card import SmartCardEngagementEvent, SmartCardRepresentative
from app.models.user import User
from app.services.smart_card.engagement_service import (
    SmartCardEngagementError,
    SmartCardEngagementService,
)
from app.services.smart_card.representative_service import SmartCardRepresentativeService
from app.services.smart_card.results_service import SmartCardResultsService


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _org_user(db, *, role: str = "owner", email: str | None = None):
    org = Organisation(name=f"SC Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    user = User(
        email=email or f"admin-{uuid.uuid4().hex[:8]}@test.local",
        password_hash="x",
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role=role))
    db.flush()
    return org, user


def test_invite_skips_admin_and_links_self(db):
    org, owner = _org_user(db, role="owner")
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Owner Card",
        email=owner.email,
        qr_token=f"tok-{uuid.uuid4().hex[:12]}",
        status="active",
        created_by_user_id=owner.id,
    )
    db.add(rep)
    db.flush()

    with patch(
        "app.services.org_team_service.OrgTeamService.create_invite",
        side_effect=AssertionError("should not invite admin"),
    ):
        result = SmartCardRepresentativeService.invite_or_link_rep(
            db, org_id=org.id, actor_user_id=owner.id, rep=rep
        )
    db.commit()
    assert result["action"] == "linked_admin"
    assert rep.linked_user_id == owner.id


def test_invite_links_existing_member_without_email(db):
    org, owner = _org_user(db, role="owner")
    member = User(
        email=f"member-{uuid.uuid4().hex[:8]}@test.local",
        password_hash="x",
        is_active=True,
    )
    db.add(member)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=member.id, role="member"))
    db.flush()

    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Member Card",
        email=member.email,
        qr_token=f"tok-{uuid.uuid4().hex[:12]}",
        status="active",
        created_by_user_id=owner.id,
    )
    db.add(rep)
    db.flush()

    with patch(
        "app.services.org_team_service.OrgTeamService.create_invite",
        side_effect=AssertionError("should not invite existing member"),
    ):
        result = SmartCardRepresentativeService.invite_or_link_rep(
            db, org_id=org.id, actor_user_id=owner.id, rep=rep
        )
    db.commit()
    assert result["action"] == "linked_member"
    assert rep.linked_user_id == member.id


def test_invite_sends_member_invite_for_new_email(db):
    org, owner = _org_user(db, role="owner")
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="New Rep",
        email=f"newrep-{uuid.uuid4().hex[:8]}@test.local",
        qr_token=f"tok-{uuid.uuid4().hex[:12]}",
        status="active",
        created_by_user_id=owner.id,
    )
    db.add(rep)
    db.flush()

    with (
        patch(
            "app.services.org_team_service.OrgTeamService.create_invite",
            return_value={
                "invite_id": "inv-1",
                "signup_url": "https://dashboard.voxbulk.com/signin?invite_token=abc",
            },
        ) as create_invite,
        patch(
            "app.services.smart_card.email_service.SmartCardEmailService.send_rep_member_invite",
            return_value=True,
        ) as send_mail,
    ):
        result = SmartCardRepresentativeService.invite_or_link_rep(
            db, org_id=org.id, actor_user_id=owner.id, rep=rep
        )
    db.commit()
    assert result["action"] == "invited"
    assert rep.invite_id == "inv-1"
    create_invite.assert_called_once()
    send_mail.assert_called_once()


def test_member_safe_payload_strips_status():
    body = SmartCardRepresentativeService.member_safe_payload(
        {"name": "A", "status": "archived", "product_ids": ["1"], "evil": True}
    )
    assert body == {"name": "A", "product_ids": ["1"]}
    assert "status" not in body


def test_engagement_record_and_summary(db):
    org, owner = _org_user(db, role="owner")
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Eng Rep",
        email=f"eng-{uuid.uuid4().hex[:8]}@test.local",
        qr_token=f"tok-{uuid.uuid4().hex[:12]}",
        status="active",
        scan_count=3,
        linked_user_id=owner.id,
        created_by_user_id=owner.id,
    )
    db.add(rep)
    db.flush()

    SmartCardEngagementService.record(db, rep=rep, event_type="social_linkedin")
    SmartCardEngagementService.record(db, rep=rep, event_type="website")
    SmartCardEngagementService.record(db, rep=rep, event_type="save_contact")
    SmartCardEngagementService.record(db, rep=rep, event_type="file_open")
    db.commit()

    counts = SmartCardEngagementService.counts_for(db, org_id=org.id, representative_ids=[rep.id])
    summary = SmartCardEngagementService.engagement_summary(counts)
    assert summary["social_clicks"] == 1
    assert summary["website_clicks"] == 1
    assert summary["save_contact"] == 1
    assert summary["file_opens"] == 1

    kpi = SmartCardResultsService.customer_summary(
        db, org_id=org.id, user_id=owner.id, representative_id=rep.id
    )
    assert kpi["scans"] == 3
    assert kpi["social_clicks"] == 1
    assert kpi["website_clicks"] == 1
    assert kpi["file_opens"] == 1

    from sqlalchemy import select

    n = db.execute(
        select(SmartCardEngagementEvent.id).where(SmartCardEngagementEvent.representative_id == rep.id)
    ).scalars().all()
    assert len(n) == 4


def test_engagement_rejects_bad_type(db):
    org, owner = _org_user(db)
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Bad",
        qr_token=f"tok-{uuid.uuid4().hex[:12]}",
        status="active",
    )
    db.add(rep)
    db.flush()
    with pytest.raises(SmartCardEngagementError):
        SmartCardEngagementService.record(db, rep=rep, event_type="hack_me")
