"""Service order payment workflow — invoice before launch."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.user import User
from app.services.platform_catalog_service import ServiceOrderService
from app.services.service_order_payment_workflow_service import (
    ServiceOrderPaymentWorkflowError,
    ServiceOrderPaymentWorkflowService,
)


def _admin_headers(app_client):
    with get_sessionmaker()() as db:
        org = Organisation(name="Admin Org")
        db.add(org)
        db.flush()
        user = User(
            email=f"wf-admin-{uuid.uuid4().hex[:6]}@test.com",
            password_hash=hash_password("pass123"),
            is_active=True,
            is_superuser=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        email = user.email
        org_id = org.id
    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_pending_order(*, contact_email: str | None = None) -> tuple[str, str]:
    with get_sessionmaker()() as db:
        org = Organisation(
            name=f"Workflow Org {uuid.uuid4().hex[:4]}",
            contact_email=contact_email or f"wf-{uuid.uuid4().hex[:6]}@example.com",
            billing_currency="GBP",
        )
        db.add(org)
        db.flush()
        user = User(email=f"wf-{uuid.uuid4().hex[:6]}@example.com", password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="Workflow test",
            status="awaiting_payment",
            payment_status="pending_approval",
            quote_total_pence=5000,
            recipient_count=10,
        )
        db.add(order)
        db.commit()
        return org.id, order.id


@patch("app.services.org_control_center_actions_service.OrgControlCenterActionsService._send_invoice_email", return_value=True)
def test_admin_approve_payment_issues_invoice_and_allows_launch(mock_send, app_client):
    admin = _admin_headers(app_client)
    org_id, order_id = _seed_pending_order()
    approved = app_client.post(
        f"/admin/platform-services/orders/{order_id}/approve-payment",
        headers=admin,
        json={"note": "Cash received"},
    )
    assert approved.status_code == 200, approved.text
    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        assert order.payment_status == "approved"
        assert order.payment_invoice_id
        ServiceOrderPaymentWorkflowService.assert_launch_ready(db, order)


def test_launch_blocked_without_invoice_after_manual_approval(app_client):
    org_id, order_id = _seed_pending_order()
    with get_sessionmaker()() as db:
        order = db.get(ServiceOrder, order_id)
        order.payment_status = "approved"
        order.status = "paid"
        db.add(order)
        db.commit()
        with patch.object(ServiceOrderPaymentWorkflowService, "confirm_payment_and_issue_invoice", side_effect=ServiceOrderPaymentWorkflowError("no invoice")):
            try:
                ServiceOrderPaymentWorkflowService.assert_launch_ready(db, order)
                assert False, "expected error"
            except ServiceOrderPaymentWorkflowError:
                pass
