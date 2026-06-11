"""Account deletion workflow — request, cancel, auth blocks, admin complete, audit, email."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import func, select

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.account_deletion_request import AccountDeletionRequest
from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.org_audit_event import OrganisationAuditEvent
from app.models.organisation import Organisation
from app.models.user import User
from app.services.account_deletion_service import (
    AUDIT_APPROVED,
    AUDIT_CANCELLED,
    AUDIT_COMPLETED,
    AUDIT_EMAIL_SENT,
    AUDIT_REQUESTED,
)
from app.services.platform_catalog_service import PlatformCatalogService


def _admin_headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Admin Org")
        db.add(org)
        db.flush()
        user = User(
            email=f"del-admin-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id
        email = user.email

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _customer_setup(
    app_client,
    *,
    email: str | None = None,
    role: str | None = "owner",
    extra_members: list[tuple[str, str]] | None = None,
) -> tuple[dict[str, str], str, str]:
    """Returns (headers, org_id, user_id)."""
    em = email or f"del-user-{uuid.uuid4().hex[:8]}@test.com"
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name=f"Deletion Org {uuid.uuid4().hex[:6]}", contact_email=em)
        db.add(org)
        db.flush()
        user = User(email=em, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role=role))
        for mem_email, mem_role in extra_members or []:
            mu = User(email=mem_email, password_hash=hash_password("pass123"), is_active=True)
            db.add(mu)
            db.flush()
            db.add(OrganisationMembership(org_id=org.id, user_id=mu.id, role=mem_role))
        db.commit()
        org_id = org.id
        user_id = user.id

    token = app_client.post(
        "/auth/token",
        data={"username": em, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id, user_id


def test_sole_member_can_request_deletion(app_client):
    headers, org_id, _user_id = _customer_setup(
        app_client, email="sole-del@test.com", role="member", extra_members=None
    )

    blocked = app_client.get("/organisations/me", headers=headers)
    assert blocked.status_code == 200, blocked.text

    req = app_client.post(
        "/organisations/me/delete-account",
        headers=headers,
        json={"confirm": "DELETE", "reason": "Leaving platform"},
    )
    assert req.status_code == 200, req.text
    body = req.json()
    assert body["deletion_status"] == "pending"

    status = app_client.get("/organisations/me/deletion-status", headers=headers)
    assert status.status_code == 200, status.text
    st = status.json()
    assert st["deletion_status"] == "pending"
    assert st["can_cancel"] is True
    assert "2 working days" in (st.get("sla_message") or "").lower()

    with get_sessionmaker()() as db:
        events = list(
            db.execute(
                select(OrganisationAuditEvent.event_type).where(
                    OrganisationAuditEvent.org_id == org_id,
                    OrganisationAuditEvent.event_type == AUDIT_REQUESTED,
                )
            ).scalars()
        )
        assert len(events) == 1


def test_owner_with_team_can_request_deletion(app_client):
    headers, _org_id, _ = _customer_setup(
        app_client,
        email="owner-del@test.com",
        role="owner",
        extra_members=[("manager-del@test.com", "manager")],
    )

    req = app_client.post(
        "/organisations/me/delete-account",
        headers=headers,
        json={"confirm": "DELETE"},
    )
    assert req.status_code == 200, req.text
    assert req.json()["deletion_status"] == "pending"


def test_non_owner_member_blocked_from_request(app_client):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Team Org")
        db.add(org)
        db.flush()
        owner = User(email="team-owner@test.com", password_hash=hash_password("pass123"), is_active=True)
        manager = User(email="team-manager@test.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(owner)
        db.add(manager)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=owner.id, role="owner"))
        db.add(OrganisationMembership(org_id=org.id, user_id=manager.id, role="manager"))
        db.commit()
        org_id = org.id

    mgr_token = app_client.post(
        "/auth/token",
        data={"username": "team-manager@test.com", "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    mgr_headers = {"Authorization": f"Bearer {mgr_token}"}

    denied = app_client.post(
        "/organisations/me/delete-account",
        headers=mgr_headers,
        json={"confirm": "DELETE"},
    )
    assert denied.status_code == 400, denied.text
    assert "owner" in denied.json()["detail"].lower()


def test_cancel_restores_active_and_access(app_client):
    headers, org_id, user_id = _customer_setup(app_client, email="cancel-del@test.com")

    app_client.post("/organisations/me/delete-account", headers=headers, json={"confirm": "DELETE"})

    blocked = app_client.get("/organisations/me", headers=headers)
    assert blocked.status_code == 403, blocked.text

    cancel = app_client.post("/organisations/me/cancel-delete-account", headers=headers)
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["deletion_status"] == "cancelled"

    restored = app_client.get("/organisations/me", headers=headers)
    assert restored.status_code == 200, restored.text

    with get_sessionmaker()() as db:
        user = db.get(User, user_id)
        org = db.get(Organisation, org_id)
        assert user is not None and user.is_active is True
        assert user.deletion_status == "cancelled"
        assert org is not None and org.deletion_status == "cancelled"
        cancelled_events = list(
            db.execute(
                select(OrganisationAuditEvent.event_type).where(
                    OrganisationAuditEvent.org_id == org_id,
                    OrganisationAuditEvent.event_type == AUDIT_CANCELLED,
                )
            ).scalars()
        )
        assert len(cancelled_events) == 1


def test_pending_user_blocked_on_protected_routes(app_client):
    headers, _org_id, _ = _customer_setup(app_client, email="pending-auth@test.com")

    app_client.post("/organisations/me/delete-account", headers=headers, json={"confirm": "DELETE"})

    me = app_client.get("/auth/me", headers=headers)
    assert me.status_code == 403, me.text

    org_me = app_client.get("/organisations/me", headers=headers)
    assert org_me.status_code == 403, org_me.text

    status = app_client.get("/organisations/me/deletion-status", headers=headers)
    assert status.status_code == 200, status.text


def test_admin_complete_anonymizes_and_retains_invoices(app_client):
    admin = _admin_headers(app_client)
    headers, org_id, user_id = _customer_setup(app_client, email="complete-del@test.com")

    with get_sessionmaker()() as db:
        db.add(
            BillingInvoice(
                org_id=org_id,
                provider="manual",
                external_invoice_id=f"inv-{uuid.uuid4().hex[:8]}",
                client_email="complete-del@test.com",
                amount_gbp_pence=1200,
                subtotal_pence=1200,
                currency="GBP",
                status="paid",
            )
        )
        db.commit()
        invoice_count_before = int(
            db.execute(select(func.count()).select_from(BillingInvoice).where(BillingInvoice.org_id == org_id)).scalar_one()
        )

    app_client.post("/organisations/me/delete-account", headers=headers, json={"confirm": "DELETE"})

    queue = app_client.get("/admin/account-deletions?status_filter=pending", headers=admin)
    assert queue.status_code == 200, queue.text
    items = queue.json()["items"]
    req_row = next((r for r in items if r["org_id"] == org_id), None)
    assert req_row is not None
    request_id = req_row["id"]

    with patch(
        "app.services.product_email_triggers.ProductEmailTriggers.send_account_deletion_completed",
        return_value=(True, None),
    ):
        done = app_client.post(
            f"/admin/account-deletions/{request_id}/complete",
            headers=admin,
            json={"confirm": "DELETE", "admin_notes": "Processed"},
        )
    assert done.status_code == 200, done.text

    with get_sessionmaker()() as db:
        user = db.get(User, user_id)
        org = db.get(Organisation, org_id)
        assert user is not None
        assert "anonymized" in user.email
        assert user.deletion_status == "archived"
        assert org is not None
        assert org.deletion_status == "archived"
        assert "archived" in org.contact_email

        invoice_count_after = int(
            db.execute(select(func.count()).select_from(BillingInvoice).where(BillingInvoice.org_id == org_id)).scalar_one()
        )
        assert invoice_count_after == invoice_count_before

        event_types = set(
            db.execute(
                select(OrganisationAuditEvent.event_type).where(
                    OrganisationAuditEvent.org_id == org_id,
                    OrganisationAuditEvent.event_type.like("account.deletion%"),
                )
            ).scalars()
        )
        assert AUDIT_REQUESTED in event_types
        assert AUDIT_APPROVED in event_types
        assert AUDIT_COMPLETED in event_types
        assert AUDIT_EMAIL_SENT in event_types

        req = db.get(AccountDeletionRequest, request_id)
        assert req is not None and req.status == "completed"


def test_admin_list_returns_pending_request(app_client):
    admin = _admin_headers(app_client)
    headers, org_id, _ = _customer_setup(app_client, email="list-del@test.com")

    app_client.post("/organisations/me/delete-account", headers=headers, json={"confirm": "DELETE"})

    listing = app_client.get("/admin/account-deletions?status_filter=pending", headers=admin)
    assert listing.status_code == 200, listing.text
    assert listing.json()["pending_count"] >= 1
    assert any(item["org_id"] == org_id for item in listing.json()["items"])
