"""DEV/OPS — hard-delete dashboard users and purge related billing rows (test tooling)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.account_deletion_request import AccountDeletionRequest
from app.models.billing_invoice import BillingInvoice
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.billing_refund_review import BillingRefundReview
from app.models.call_log import CallLog
from app.models.credit_note import CreditNote
from app.models.agent_service_assignment import AgentServiceAssignment
from app.models.appointment import Appointment
from app.models.branch import Branch
from app.models.customer_feedback import (
    FeedbackLocation,
    FeedbackResponse,
    FeedbackSession,
    FeedbackUsagePeriod,
)
from app.models.organisation_ai_config import (
    OrganisationAIIdentity,
    OrganisationComplianceConfig,
    OrganisationServiceCatalogItem,
    OrganisationWorkflowConfig,
)
from app.models.organisation_invite import OrganisationInvite
from app.models.patient import Patient
from app.models.whatsapp_log import WhatsAppLog
from app.models.membership import OrganisationMembership
from app.models.notification import Notification
from app.models.oauth_identity import OAuthIdentity
from app.models.onboarding_request import OnboardingRequest
from app.models.org_audit_event import OrganisationAuditEvent
from app.models.org_opt_out import OrganisationOptOut
from app.models.organisation import Organisation
from app.models.org_usage_period import OrgUsagePeriod
from app.models.password_reset_token import PasswordResetToken
from app.models.payment_event import PaymentEvent
from app.models.platform_compliance_audit import PlatformComplianceAuditEvent
from app.models.promo_offer import PromoRedemption
from app.models.recovery_job import RecoveryJob
from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.survey_session import SurveySession
from app.models.survey_voice_note_job import SurveyVoiceNoteJob
from app.models.subscription import Subscription
from app.models.support_ticket import (
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketEvent,
    SupportTicketMessage,
)
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction

HARD_DELETE_CONFIRM = "HARD_DELETE"


class UserHardDeleteError(ValueError):
    pass


def _count(db: Session, model, *filters) -> int:
    q = select(func.count()).select_from(model)
    for f in filters:
        q = q.where(f)
    return int(db.execute(q).scalar_one() or 0)


def billing_counts(db: Session, org_id: str) -> dict[str, int]:
    return {
        "billing_refund_reviews": _count(db, BillingRefundReview, BillingRefundReview.org_id == org_id),
        "feedback_usage_periods": _count(db, FeedbackUsagePeriod, FeedbackUsagePeriod.org_id == org_id),
        "credit_notes": _count(db, CreditNote, CreditNote.org_id == org_id),
        "wallet_transactions": _count(db, WalletTransaction, WalletTransaction.org_id == org_id),
        "payment_events": _count(db, PaymentEvent, PaymentEvent.org_id == org_id),
        "billing_invoices": _count(db, BillingInvoice, BillingInvoice.org_id == org_id),
        "subscriptions": _count(db, Subscription, Subscription.org_id == org_id),
        "billing_redirect_flows": _count(db, BillingRedirectFlow, BillingRedirectFlow.org_id == org_id),
        "org_usage_periods": _count(db, OrgUsagePeriod, OrgUsagePeriod.org_id == org_id),
    }


def purge_billing_for_org(db: Session, org_id: str) -> dict[str, int]:
    counts = billing_counts(db, org_id)
    db.execute(
        update(Subscription)
        .where(Subscription.org_id == org_id)
        .values(cancellation_support_ticket_id=None)
    )
    for model, col in (
        (BillingRefundReview, BillingRefundReview.org_id),
        (FeedbackUsagePeriod, FeedbackUsagePeriod.org_id),
        (CreditNote, CreditNote.org_id),
        (WalletTransaction, WalletTransaction.org_id),
        (PaymentEvent, PaymentEvent.org_id),
        (BillingInvoice, BillingInvoice.org_id),
        (Subscription, Subscription.org_id),
        (BillingRedirectFlow, BillingRedirectFlow.org_id),
        (OrgUsagePeriod, OrgUsagePeriod.org_id),
    ):
        db.execute(delete(model).where(col == org_id))

    org = db.get(Organisation, org_id)
    if org is not None:
        org.wallet_balance_pence = 0
        org.survey_credits_balance = 0
        org.interview_credits_balance = 0
        org.credit_limit_minor = 0
        org.billing_currency = None
        org.allow_overage = True
        db.add(org)
    return counts


def _delete_support_tickets_for_org(db: Session, org_id: str) -> int:
    ticket_ids = list(
        db.execute(select(SupportTicket.id).where(SupportTicket.organisation_id == org_id)).scalars().all()
    )
    if not ticket_ids:
        return 0
    msg_ids = list(
        db.execute(select(SupportTicketMessage.id).where(SupportTicketMessage.ticket_id.in_(ticket_ids))).scalars().all()
    )
    if msg_ids:
        db.execute(delete(SupportTicketAttachment).where(SupportTicketAttachment.message_id.in_(msg_ids)))
    db.execute(delete(SupportTicketAttachment).where(SupportTicketAttachment.ticket_id.in_(ticket_ids)))
    db.execute(delete(SupportTicketMessage).where(SupportTicketMessage.ticket_id.in_(ticket_ids)))
    db.execute(delete(SupportTicketEvent).where(SupportTicketEvent.ticket_id.in_(ticket_ids)))
    db.execute(
        update(AccountDeletionRequest)
        .where(AccountDeletionRequest.support_ticket_id.in_(ticket_ids))
        .values(support_ticket_id=None)
    )
    db.execute(delete(SupportTicket).where(SupportTicket.id.in_(ticket_ids)))
    return len(ticket_ids)


def detach_user_references(db: Session, user_id: str) -> dict[str, int]:
    ticket_ids = list(
        db.execute(select(SupportTicket.id).where(SupportTicket.created_by_user_id == user_id)).scalars().all()
    )
    counts = {
        "organisation_audit_events_nulled": _count(
            db, OrganisationAuditEvent, OrganisationAuditEvent.actor_user_id == user_id
        ),
        "platform_compliance_audit_nulled": _count(
            db, PlatformComplianceAuditEvent, PlatformComplianceAuditEvent.actor_user_id == user_id
        ),
        "account_deletion_requests_deleted": _count(
            db, AccountDeletionRequest, AccountDeletionRequest.requested_by_user_id == user_id
        ),
        "support_tickets_deleted": len(ticket_ids),
        "notifications_deleted": _count(db, Notification, Notification.user_id == user_id),
        "onboarding_requests_deleted": _count(db, OnboardingRequest, OnboardingRequest.user_id == user_id),
    }

    db.execute(
        update(OrganisationAuditEvent)
        .where(OrganisationAuditEvent.actor_user_id == user_id)
        .values(actor_user_id=None)
    )
    db.execute(
        update(PlatformComplianceAuditEvent)
        .where(PlatformComplianceAuditEvent.actor_user_id == user_id)
        .values(actor_user_id=None)
    )
    db.execute(update(CallLog).where(CallLog.user_id == user_id).values(user_id=None))
    db.execute(
        update(OrganisationOptOut)
        .where(OrganisationOptOut.created_by_user_id == user_id)
        .values(created_by_user_id=None)
    )
    db.execute(
        update(BillingRefundReview)
        .where(BillingRefundReview.requested_by_user_id == user_id)
        .values(requested_by_user_id=None)
    )
    db.execute(
        update(BillingRefundReview)
        .where(BillingRefundReview.resolved_by_user_id == user_id)
        .values(resolved_by_user_id=None)
    )
    db.execute(update(RecoveryJob).where(RecoveryJob.requested_by_user_id == user_id).values(requested_by_user_id=None))
    db.execute(
        update(SupportTicketMessage)
        .where(SupportTicketMessage.sender_user_id == user_id)
        .values(sender_user_id=None)
    )
    db.execute(
        update(SupportTicketEvent).where(SupportTicketEvent.actor_user_id == user_id).values(actor_user_id=None)
    )
    db.execute(
        update(AccountDeletionRequest)
        .where(AccountDeletionRequest.completed_by_admin_user_id == user_id)
        .values(completed_by_admin_user_id=None)
    )
    db.execute(delete(AccountDeletionRequest).where(AccountDeletionRequest.requested_by_user_id == user_id))
    db.execute(delete(Notification).where(Notification.user_id == user_id))
    db.execute(delete(OnboardingRequest).where(OnboardingRequest.user_id == user_id))

    if ticket_ids:
        msg_ids = list(
            db.execute(select(SupportTicketMessage.id).where(SupportTicketMessage.ticket_id.in_(ticket_ids))).scalars().all()
        )
        if msg_ids:
            db.execute(delete(SupportTicketAttachment).where(SupportTicketAttachment.message_id.in_(msg_ids)))
        db.execute(delete(SupportTicketAttachment).where(SupportTicketAttachment.ticket_id.in_(ticket_ids)))
        db.execute(delete(SupportTicketMessage).where(SupportTicketMessage.ticket_id.in_(ticket_ids)))
        db.execute(delete(SupportTicketEvent).where(SupportTicketEvent.ticket_id.in_(ticket_ids)))
        db.execute(
            update(AccountDeletionRequest)
            .where(AccountDeletionRequest.support_ticket_id.in_(ticket_ids))
            .values(support_ticket_id=None)
        )
        db.execute(delete(SupportTicket).where(SupportTicket.id.in_(ticket_ids)))

    return counts


def _delete_service_orders_for_org(db: Session, org_id: str) -> int:
    order_ids = list(
        db.execute(select(ServiceOrder.id).where(ServiceOrder.org_id == org_id)).scalars().all()
    )
    if not order_ids:
        return 0
    db.execute(
        update(PlatformComplianceAuditEvent)
        .where(PlatformComplianceAuditEvent.order_id.in_(order_ids))
        .values(order_id=None)
    )
    db.execute(
        update(BillingRedirectFlow)
        .where(BillingRedirectFlow.service_order_id.in_(order_ids))
        .values(service_order_id=None)
    )
    db.execute(delete(SurveySession).where(SurveySession.order_id.in_(order_ids)))
    db.execute(delete(InterviewBookingToken).where(InterviewBookingToken.order_id.in_(order_ids)))
    db.execute(delete(SurveyVoiceNoteJob).where(SurveyVoiceNoteJob.order_id.in_(order_ids)))
    db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id.in_(order_ids)))
    db.execute(delete(ServiceOrder).where(ServiceOrder.id.in_(order_ids)))
    return len(order_ids)


def _purge_org_children_for_test_delete(db: Session, org_id: str, *, delete_service_orders: bool) -> dict[str, int]:
    order_count = int(
        db.execute(select(func.count()).select_from(ServiceOrder).where(ServiceOrder.org_id == org_id)).scalar_one() or 0
    )
    if order_count and not delete_service_orders:
        raise UserHardDeleteError(
            f"Organisation has {order_count} campaign(s). Enable delete_service_orders for test purge."
        )
    orders_deleted = _delete_service_orders_for_org(db, org_id) if order_count and delete_service_orders else 0

    db.execute(delete(SurveySession).where(SurveySession.org_id == org_id))
    db.execute(delete(InterviewBookingToken).where(InterviewBookingToken.org_id == org_id))
    db.execute(delete(FeedbackResponse).where(FeedbackResponse.org_id == org_id))
    db.execute(delete(FeedbackSession).where(FeedbackSession.org_id == org_id))
    db.execute(delete(FeedbackLocation).where(FeedbackLocation.org_id == org_id))
    db.execute(delete(WhatsAppLog).where(WhatsAppLog.org_id == org_id))
    db.execute(delete(Appointment).where(Appointment.org_id == org_id))
    db.execute(delete(Patient).where(Patient.org_id == org_id))
    db.execute(delete(CallLog).where(CallLog.org_id == org_id))
    db.execute(delete(RecoveryJob).where(RecoveryJob.org_id == org_id))
    db.execute(delete(OnboardingRequest).where(OnboardingRequest.org_id == org_id))
    db.execute(delete(Notification).where(Notification.organisation_id == org_id))
    db.execute(delete(OrganisationInvite).where(OrganisationInvite.org_id == org_id))
    db.execute(delete(Branch).where(Branch.org_id == org_id))
    db.execute(delete(OrganisationAIIdentity).where(OrganisationAIIdentity.org_id == org_id))
    db.execute(delete(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id))
    db.execute(delete(OrganisationServiceCatalogItem).where(OrganisationServiceCatalogItem.org_id == org_id))
    db.execute(delete(OrganisationWorkflowConfig).where(OrganisationWorkflowConfig.org_id == org_id))
    db.execute(delete(AgentServiceAssignment).where(AgentServiceAssignment.org_id == org_id))
    db.execute(
        update(PlatformComplianceAuditEvent)
        .where(PlatformComplianceAuditEvent.org_id == org_id)
        .values(org_id=None)
    )
    db.execute(delete(PromoRedemption).where(PromoRedemption.org_id == org_id))

    tickets = _delete_support_tickets_for_org(db, org_id)
    db.execute(delete(OrganisationAuditEvent).where(OrganisationAuditEvent.org_id == org_id))
    db.execute(delete(AccountDeletionRequest).where(AccountDeletionRequest.org_id == org_id))
    db.execute(delete(OrganisationOptOut).where(OrganisationOptOut.org_id == org_id))
    db.execute(delete(OrganisationMembership).where(OrganisationMembership.org_id == org_id))

    org = db.get(Organisation, org_id)
    org_deleted = False
    if org is not None:
        db.delete(org)
        db.flush()
        org_deleted = True

    return {
        "service_orders_deleted": orders_deleted,
        "support_tickets_deleted": tickets,
        "org_deleted": org_deleted,
    }


def purge_org_residuals_for_delete(db: Session, org_id: str, *, delete_service_orders: bool) -> dict[str, int]:
    return _purge_org_children_for_test_delete(db, org_id, delete_service_orders=delete_service_orders)


def solo_org_candidate(db: Session, org_id: str, user_id: str) -> tuple[bool, str | None]:
    members = list(
        db.execute(select(OrganisationMembership).where(OrganisationMembership.org_id == org_id)).scalars().all()
    )
    if len(members) != 1 or members[0].user_id != user_id:
        return False, f"org has {len(members)} member(s)"
    return True, None


def hard_delete_user(
    db: Session,
    user_id: str,
    *,
    org_id: str | None = None,
    delete_solo_orgs: bool = True,
    delete_service_orders: bool = True,
) -> dict[str, Any]:
    user = db.get(User, user_id)
    if user is None:
        raise UserHardDeleteError("User not found")
    if user.is_superuser:
        raise UserHardDeleteError("Cannot hard-delete platform superuser")
    email = str(user.email or "").strip().lower()
    if email.endswith("@voxbulk.internal") or email == "api-accounts@voxbulk.com":
        raise UserHardDeleteError("Cannot hard-delete protected system account")

    memberships = list(
        db.execute(select(OrganisationMembership).where(OrganisationMembership.user_id == user_id)).scalars().all()
    )
    org_ids = sorted({m.org_id for m in memberships})
    if org_id is not None:
        if org_id not in org_ids:
            raise UserHardDeleteError("User is not a member of this organisation")
        if len(org_ids) > 1:
            raise UserHardDeleteError("User belongs to multiple organisations — use the CLI purge script")
        ok, reason = solo_org_candidate(db, org_id, user_id)
        if not ok:
            raise UserHardDeleteError(reason or "Hard delete from admin requires sole membership in this org")
        org_ids = [org_id]

    report: dict[str, Any] = {
        "user_id": user_id,
        "email": user.email,
        "org_ids": org_ids,
        "billing": {},
        "user_references": {},
        "solo_orgs": [],
    }

    solo_targets: list[str] = []
    if delete_solo_orgs:
        for oid in org_ids:
            ok, reason = solo_org_candidate(db, oid, user_id)
            entry: dict[str, Any] = {"org_id": oid, "deletable": ok, "reason": reason}
            if ok:
                solo_targets.append(oid)
            report["solo_orgs"].append(entry)

    for oid in org_ids:
        org = db.get(Organisation, oid)
        org_name = org.name if org else "?"
        report["billing"][oid] = {"org_name": org_name, "deleted": purge_billing_for_org(db, oid)}

    report["user_references"] = detach_user_references(db, user_id)

    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
    db.execute(delete(OAuthIdentity).where(OAuthIdentity.user_id == user_id))
    db.execute(delete(BillingRedirectFlow).where(BillingRedirectFlow.user_id == user_id))
    db.execute(delete(PromoRedemption).where(PromoRedemption.user_id == user_id))

    for oid in solo_targets:
        for entry in report["solo_orgs"]:
            if entry.get("org_id") == oid and entry.get("deletable"):
                entry["purged"] = purge_org_residuals_for_delete(
                    db, oid, delete_service_orders=delete_service_orders
                )

    db.execute(delete(OrganisationMembership).where(OrganisationMembership.user_id == user_id))
    db.delete(user)
    report["status"] = "deleted"
    return report
