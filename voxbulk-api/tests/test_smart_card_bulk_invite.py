"""Smart Card bulk Excel/CSV invites — stubs + seat cap."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.smart_card import SmartCardRepresentative
from app.services.smart_card.representative_service import (
    SmartCardRepError,
    SmartCardRepresentativeService,
)


def test_parse_invite_csv_email_and_name():
    raw = b"email,name\nalex@example.com,Alex\nsam@example.com,\nbad-row\n"
    rows = SmartCardRepresentativeService.parse_invite_file(raw, "team.csv")
    assert rows == [
        {"email": "alex@example.com", "name": "Alex"},
        {"email": "sam@example.com", "name": ""},
    ]


def test_parse_invite_xlsx_template():
    content = SmartCardRepresentativeService.bulk_invite_template_xlsx()
    rows = SmartCardRepresentativeService.parse_invite_file(content, "template.xlsx")
    assert len(rows) >= 2
    assert rows[0]["email"] == "alex@example.com"


def test_invite_status_and_incomplete():
    rep = SmartCardRepresentative(
        id=str(uuid.uuid4()),
        org_id=str(uuid.uuid4()),
        name="Alex",
        email="alex@example.com",
        qr_token="t",
        status="active",
    )
    assert SmartCardRepresentativeService.invite_status_for(rep) == "needs_invite"
    assert SmartCardRepresentativeService.card_incomplete(rep) is True
    rep.invite_id = "inv1"
    assert SmartCardRepresentativeService.invite_status_for(rep) == "pending_invite"
    rep.linked_user_id = "u1"
    assert SmartCardRepresentativeService.invite_status_for(rep) == "linked"
    rep.mobile = "+447700900000"
    assert SmartCardRepresentativeService.card_incomplete(rep) is False
    rep.email = None
    assert SmartCardRepresentativeService.invite_status_for(rep) == "needs_email"


def test_bulk_invite_respects_seat_cap_and_skips_dups():
    org_id = str(uuid.uuid4())
    actor = str(uuid.uuid4())
    db = MagicMock()

    created_ids: list[str] = []

    def fake_create(db_, *, org_id, user_id, payload):
        rep = SmartCardRepresentative(
            id=str(uuid.uuid4()),
            org_id=org_id,
            name=payload["name"],
            email=payload["email"],
            qr_token=str(uuid.uuid4())[:12],
            status="active",
            invite_id="inv-" + payload["email"],
        )
        created_ids.append(rep.id)
        return rep

    with (
        patch(
            "app.services.smart_card.representative_service.SmartCardEntitlementService.seat_quantity",
            return_value=2,
        ),
        patch(
            "app.services.smart_card.representative_service.SmartCardEntitlementService.active_rep_count",
            return_value=0,
        ),
        patch.object(SmartCardRepresentativeService, "create", side_effect=fake_create),
    ):
        # existing active emails query
        db.execute.return_value.scalars.return_value.all.return_value = ["taken@example.com"]
        result = SmartCardRepresentativeService.bulk_invite_from_emails(
            db,
            org_id=org_id,
            actor_user_id=actor,
            rows=[
                {"email": "a@example.com", "name": "A"},
                {"email": "a@example.com", "name": "A2"},
                {"email": "taken@example.com", "name": "T"},
                {"email": "b@example.com", "name": "B"},
                {"email": "c@example.com", "name": "C"},
                {"email": "not-an-email", "name": "X"},
            ],
        )

    assert result["created_count"] == 2
    assert result["skipped_count"] == 4
    reasons = {s["email"]: s["reason"] for s in result["skipped"]}
    assert reasons["a@example.com"] == "duplicate_in_file"
    assert reasons["taken@example.com"] == "already_has_qr"
    assert reasons["c@example.com"] == "seat_limit"
    assert reasons.get("not-an-email") == "invalid_email" or any(
        s["reason"] == "invalid_email" for s in result["skipped"]
    )


def test_bulk_invite_requires_seats():
    db = MagicMock()
    with (
        patch(
            "app.services.smart_card.representative_service.SmartCardEntitlementService.seat_quantity",
            return_value=0,
        ),
        patch(
            "app.services.smart_card.representative_service.SmartCardEntitlementService.active_rep_count",
            return_value=0,
        ),
    ):
        try:
            SmartCardRepresentativeService.bulk_invite_from_emails(
                db,
                org_id=str(uuid.uuid4()),
                actor_user_id=str(uuid.uuid4()),
                rows=[{"email": "a@example.com"}],
            )
            assert False, "expected SmartCardRepError"
        except SmartCardRepError as e:
            assert "seats" in str(e).lower()
