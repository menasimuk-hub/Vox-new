"""DEV/OPS — hard-delete dashboard users and purge related billing rows (test tooling)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.account_deletion_request import AccountDeletionRequest
from app.models.agent import AgentAssignment
from app.models.agent_service_assignment import AgentServiceAssignment
from app.models.appointment import Appointment, AppointmentLog
from app.models.billing_invoice import BillingInvoice
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.billing_refund_review import BillingRefundReview
from app.models.branch import Branch
from app.models.call_log import CallLog
from app.models.connection_profile import ConnectionProfileOrg
from app.models.credit_note import CreditNote
from app.models.crm_survey_automation_event import CrmSurveyAutomationEvent
from app.models.crm_synced_contact import CrmSyncedContact
from app.models.custom_org_profile import CustomOrgProfile
from app.models.customer_feedback import (
    FeedbackAiFollowUpJob,
    FeedbackIndustryOrganisation,
    FeedbackLocation,
    FeedbackMarketingSubscriber,
    FeedbackPromoCampaign,
    FeedbackPromoSend,
    FeedbackPromoWallet,
    FeedbackResponse,
    FeedbackResultsInsightsCache,
    FeedbackSession,
    FeedbackUsagePeriod,
    FeedbackVoiceNoteJob,
)
from app.models.dentally_appointment import DentallyAppointment
from app.models.hubspot_contact import HubspotContact
from app.models.industry_organisation import IndustryOrganisation
from app.models.interview_booking_token import InterviewBookingToken
from app.models.membership import OrganisationMembership
from app.models.notification import Notification
from app.models.oauth_identity import OAuthIdentity
from app.models.onboarding_request import OnboardingRequest
from app.models.org_audit_event import OrganisationAuditEvent
from app.models.org_opt_out import OrganisationOptOut
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.organisation_ai_config import (
    OrganisationAIIdentity,
    OrganisationComplianceConfig,
    OrganisationServiceCatalogItem,
    OrganisationWorkflowConfig,
)
from app.models.organisation_invite import OrganisationInvite
from app.models.password_reset_token import PasswordResetToken
from app.models.patient import Patient
from app.models.payment_event import PaymentEvent
from app.models.platform_compliance_audit import PlatformComplianceAuditEvent
from app.models.pricing import OrgCustomPricing
from app.models.promo_offer import PromoRedemption
from app.models.provider_config import ProviderConfig
from app.models.recovery_job import RecoveryJob
from app.models.sales_rep import SalesCommission, SalesCustomer, SalesRep
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.subscription import Subscription
from app.models.support_ticket import (
    SupportTicket,
    SupportTicketAttachment,
    SupportTicketEvent,
    SupportTicketMessage,
)
from app.models.survey_ai_follow_up_job import SurveyAiFollowUpJob
from app.models.survey_session import SurveySession, SurveySessionAnswer, SurveySessionDecision
from app.models.survey_voice_note_job import SurveyVoiceNoteJob
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.models.user import User
from app.models.wallet_transaction import WalletTransaction
from app.models.whatsapp_log import WhatsAppLog

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


def _delete_survey_sessions_for_filters(db: Session, *session_filters) -> None:
    """Delete survey sessions and FK children (answers/decisions/voice-note session links)."""
    session_ids = list(db.execute(select(SurveySession.id).where(*session_filters)).scalars().all())
    if not session_ids:
        return
    db.execute(delete(SurveySessionAnswer).where(SurveySessionAnswer.session_id.in_(session_ids)))
    db.execute(delete(SurveySessionDecision).where(SurveySessionDecision.session_id.in_(session_ids)))
    db.execute(
        update(SurveyVoiceNoteJob)
        .where(SurveyVoiceNoteJob.session_id.in_(session_ids))
        .values(session_id=None)
    )
    db.execute(delete(SurveySession).where(SurveySession.id.in_(session_ids)))


def _delete_service_orders_by_ids(db: Session, order_ids: list[str]) -> int:
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
    db.execute(delete(SurveyAiFollowUpJob).where(SurveyAiFollowUpJob.order_id.in_(order_ids)))
    db.execute(delete(CrmSurveyAutomationEvent).where(CrmSurveyAutomationEvent.order_id.in_(order_ids)))
    db.execute(delete(SurveyVoiceNoteJob).where(SurveyVoiceNoteJob.order_id.in_(order_ids)))
    db.execute(delete(InterviewBookingToken).where(InterviewBookingToken.order_id.in_(order_ids)))
    _delete_survey_sessions_for_filters(db, SurveySession.order_id.in_(order_ids))
    db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id.in_(order_ids)))
    db.execute(delete(ServiceOrder).where(ServiceOrder.id.in_(order_ids)))
    return len(order_ids)


def _delete_service_orders_for_org(db: Session, org_id: str) -> int:
    order_ids = list(
        db.execute(select(ServiceOrder.id).where(ServiceOrder.org_id == org_id)).scalars().all()
    )
    return _delete_service_orders_by_ids(db, order_ids)


def _delete_service_orders_for_user(db: Session, user_id: str) -> int:
    order_ids = list(
        db.execute(select(ServiceOrder.id).where(ServiceOrder.user_id == user_id)).scalars().all()
    )
    return _delete_service_orders_by_ids(db, order_ids)


def _delete_sales_rep_for_user(db: Session, user_id: str) -> int:
    rep = db.execute(select(SalesRep).where(SalesRep.user_id == user_id)).scalar_one_or_none()
    if rep is None:
        return 0
    db.execute(delete(SalesCommission).where(SalesCommission.sales_rep_id == rep.id))
    db.execute(delete(SalesCustomer).where(SalesCustomer.sales_rep_id == rep.id))
    db.execute(delete(SalesRep).where(SalesRep.id == rep.id))
    return 1


def _purge_org_children_for_test_delete(db: Session, org_id: str, *, delete_service_orders: bool) -> dict[str, int]:
    order_count = int(
        db.execute(select(func.count()).select_from(ServiceOrder).where(ServiceOrder.org_id == org_id)).scalar_one() or 0
    )
    if order_count and not delete_service_orders:
        raise UserHardDeleteError(
            f"Organisation has {order_count} campaign(s). Enable delete_service_orders for test purge."
        )
    orders_deleted = _delete_service_orders_for_org(db, org_id) if order_count and delete_service_orders else 0

    db.execute(delete(SurveyAiFollowUpJob).where(SurveyAiFollowUpJob.org_id == org_id))
    db.execute(delete(CrmSurveyAutomationEvent).where(CrmSurveyAutomationEvent.org_id == org_id))
    db.execute(delete(SurveyVoiceNoteJob).where(SurveyVoiceNoteJob.org_id == org_id))
    db.execute(delete(InterviewBookingToken).where(InterviewBookingToken.org_id == org_id))
    _delete_survey_sessions_for_filters(db, SurveySession.org_id == org_id)

    # Customer Feedback: delete children before locations/org to satisfy FKs.
    db.execute(delete(FeedbackAiFollowUpJob).where(FeedbackAiFollowUpJob.org_id == org_id))
    db.execute(delete(FeedbackVoiceNoteJob).where(FeedbackVoiceNoteJob.org_id == org_id))
    db.execute(delete(FeedbackResponse).where(FeedbackResponse.org_id == org_id))
    db.execute(delete(FeedbackMarketingSubscriber).where(FeedbackMarketingSubscriber.org_id == org_id))
    db.execute(delete(FeedbackSession).where(FeedbackSession.org_id == org_id))
    db.execute(delete(FeedbackResultsInsightsCache).where(FeedbackResultsInsightsCache.org_id == org_id))
    db.execute(delete(FeedbackPromoSend).where(FeedbackPromoSend.org_id == org_id))
    db.execute(delete(FeedbackPromoCampaign).where(FeedbackPromoCampaign.org_id == org_id))
    db.execute(delete(FeedbackPromoWallet).where(FeedbackPromoWallet.org_id == org_id))
    db.execute(delete(FeedbackUsagePeriod).where(FeedbackUsagePeriod.org_id == org_id))
    db.execute(delete(FeedbackLocation).where(FeedbackLocation.org_id == org_id))
    db.execute(delete(FeedbackIndustryOrganisation).where(FeedbackIndustryOrganisation.org_id == org_id))

    # Appointments: null self-FK then delete logs + rows.
    appt_ids = list(db.execute(select(Appointment.id).where(Appointment.org_id == org_id)).scalars().all())
    if appt_ids:
        db.execute(update(Appointment).where(Appointment.id.in_(appt_ids)).values(rescheduled_from_id=None))
        db.execute(delete(AppointmentLog).where(AppointmentLog.appointment_id.in_(appt_ids)))
        db.execute(delete(Appointment).where(Appointment.id.in_(appt_ids)))

    db.execute(delete(WhatsAppLog).where(WhatsAppLog.org_id == org_id))
    db.execute(delete(DentallyAppointment).where(DentallyAppointment.org_id == org_id))
    db.execute(delete(Patient).where(Patient.org_id == org_id))
    db.execute(delete(HubspotContact).where(HubspotContact.org_id == org_id))
    db.execute(delete(CrmSyncedContact).where(CrmSyncedContact.org_id == org_id))
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
    db.execute(delete(AgentAssignment).where(AgentAssignment.org_id == org_id))
    db.execute(delete(OrgCustomPricing).where(OrgCustomPricing.org_id == org_id))
    db.execute(delete(IndustryOrganisation).where(IndustryOrganisation.org_id == org_id))
    db.execute(delete(ConnectionProfileOrg).where(ConnectionProfileOrg.org_id == org_id))
    db.execute(delete(ProviderConfig).where(ProviderConfig.org_id == org_id))
    db.execute(delete(SalesCommission).where(SalesCommission.org_id == org_id))
    db.execute(update(SalesCustomer).where(SalesCustomer.org_id == org_id).values(org_id=None))
    db.execute(
        update(CustomOrgProfile).where(CustomOrgProfile.org_id == org_id).values(org_id=None)
    )
    db.execute(
        update(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.org_id == org_id).values(org_id=None)
    )
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


def find_user_id_by_email(db: Session, email: str) -> str | None:
    needle = str(email or "").strip().lower()
    if not needle:
        return None
    user = db.execute(select(User).where(func.lower(User.email) == needle)).scalar_one_or_none()
    return str(user.id) if user is not None else None


def hard_delete_user(
    db: Session,
    user_id: str,
    *,
    org_id: str | None = None,
    delete_solo_orgs: bool = True,
    delete_service_orders: bool = True,
) -> dict[str, Any]:
    """Permanently delete any non-protected dashboard user.

    - Solo-member orgs: purge billing + org data (test wipe).
    - Shared orgs: keep the org; remove membership and that user's campaigns only.
    """
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
    if org_id is not None and org_ids and org_id not in org_ids:
        raise UserHardDeleteError("User is not a member of this organisation")

    report: dict[str, Any] = {
        "user_id": user_id,
        "email": user.email,
        "org_ids": org_ids,
        "billing": {},
        "user_references": {},
        "solo_orgs": [],
        "shared_orgs_kept": [],
        "user_service_orders_deleted": 0,
        "sales_rep_deleted": 0,
    }

    solo_targets: list[str] = []
    shared_orgs: list[str] = []
    for oid in org_ids:
        ok, reason = solo_org_candidate(db, oid, user_id)
        entry: dict[str, Any] = {"org_id": oid, "deletable": ok, "reason": reason}
        report["solo_orgs"].append(entry)
        if delete_solo_orgs and ok:
            solo_targets.append(oid)
        else:
            shared_orgs.append(oid)
            if not ok:
                report["shared_orgs_kept"].append({"org_id": oid, "reason": reason})

    # Only wipe billing for orgs that will be fully deleted (never shared tenants).
    for oid in solo_targets:
        org = db.get(Organisation, oid)
        org_name = org.name if org else "?"
        report["billing"][oid] = {"org_name": org_name, "deleted": purge_billing_for_org(db, oid)}

    for oid in shared_orgs:
        org = db.get(Organisation, oid)
        org_name = org.name if org else "?"
        report["billing"][oid] = {"org_name": org_name, "deleted": None, "kept": "shared_org"}

    report["user_references"] = detach_user_references(db, user_id)
    report["sales_rep_deleted"] = _delete_sales_rep_for_user(db, user_id)

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

    # Shared-org / leftover campaigns still FK to users.id — remove this user's orders only.
    if delete_service_orders:
        report["user_service_orders_deleted"] = _delete_service_orders_for_user(db, user_id)
    else:
        leftover = int(
            db.execute(
                select(func.count()).select_from(ServiceOrder).where(ServiceOrder.user_id == user_id)
            ).scalar_one()
            or 0
        )
        if leftover:
            raise UserHardDeleteError(
                f"User still owns {leftover} campaign(s). Enable delete_service_orders for test purge."
            )

    db.execute(delete(OrganisationMembership).where(OrganisationMembership.user_id == user_id))
    db.delete(user)
    report["status"] = "deleted"
    return report
