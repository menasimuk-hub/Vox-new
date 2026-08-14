"""Smart Card invite acceptance links QR to the invited user."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.models.organisation_invite import OrganisationInvite
from app.models.smart_card import SmartCardRepresentative
from app.models.user import User
from app.services.org_invite_service import (
    link_smart_card_reps_for_invite,
    setup_new_invited_user,
)


def test_link_smart_card_reps_by_email_and_invite_id():
    org_id = str(uuid.uuid4())
    user = User(id=str(uuid.uuid4()), email="rep@example.com", password_hash="x", is_active=True)
    rep_email = SmartCardRepresentative(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="A",
        email="rep@example.com",
        qr_token="a",
        status="active",
    )
    rep_invite = SmartCardRepresentative(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="B",
        email=None,
        invite_id="inv-1",
        qr_token="b",
        status="active",
    )
    db = MagicMock()
    db.execute.return_value.scalars.return_value.all.return_value = [rep_email, rep_invite]

    n = link_smart_card_reps_for_invite(
        db, org_id=org_id, user=user, email="rep@example.com", invite_id="inv-1"
    )
    assert n == 2
    assert rep_email.linked_user_id == user.id
    assert rep_invite.linked_user_id == user.id
    assert rep_invite.email == "rep@example.com"


def test_setup_new_member_invite_skips_personal_org():
    user = User(id=str(uuid.uuid4()), email="m@example.com", password_hash="x", is_active=True)
    inv = OrganisationInvite(
        id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        email="m@example.com",
        role="member",
        token="tok",
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = []

    with patch("app.services.org_invite_service.ensure_personal_org") as personal:
        with patch("app.services.org_invite_service.link_smart_card_reps_for_invite", return_value=0):
            setup_new_invited_user(db, user=user, email="m@example.com", inv=inv)
    personal.assert_not_called()


def test_setup_new_manager_invite_still_gets_personal_org():
    user = User(id=str(uuid.uuid4()), email="mgr@example.com", password_hash="x", is_active=True)
    inv = OrganisationInvite(
        id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        email="mgr@example.com",
        role="manager",
        token="tok",
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.execute.return_value.scalars.return_value.all.return_value = []

    with patch("app.services.org_invite_service.ensure_personal_org") as personal:
        with patch("app.services.org_invite_service.link_smart_card_reps_for_invite", return_value=0):
            setup_new_invited_user(db, user=user, email="mgr@example.com", inv=inv)
    personal.assert_called_once()
