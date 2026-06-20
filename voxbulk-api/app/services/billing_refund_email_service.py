"""Transactional emails for subscription cancellation and refund workflow."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.user import User
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.email_template_service import EmailTemplateService
from app.services.transactional_email_service import TransactionalEmailService
from app.services.usage_wallet_service import UsageWalletService

logger = logging.getLogger(__name__)

REFUND_PROCESSING_NOTE = "We process refunds within 2 working days."
REFUND_BANK_REFLECTION_NOTE = (
    "Refunds to your bank or card may take up to 3 additional working days to appear on your statement, depending on your bank."
)
DASHBOARD_BILLING_URL = "https://dashboard.voxbulk.com/account/billing"
DASHBOARD_PACKAGES_URL = "https://dashboard.voxbulk.com/account/packages"


class BillingRefundEmailService:
    @staticmethod
    def _recipient(db: Session, org: Organisation, user_id: str | None) -> str | None:
        if user_id:
            user = db.get(User, user_id)
            if user and user.email:
                return str(user.email).strip().lower()
        email = UsageWalletService.get_org_billing_email(db, org.id) or org.contact_email
        return str(email or "").strip().lower() or None

    @staticmethod
    def _send(
        db: Session,
        *,
        template_key: str,
        org: Organisation,
        user_id: str | None,
        variables: dict[str, str],
    ) -> bool:
        EmailTemplateService.ensure_system_templates(db)
        to_email = BillingRefundEmailService._recipient(db, org, user_id)
        if not to_email:
            logger.warning("billing_refund_email_skip_no_recipient org_id=%s template=%s", org.id, template_key)
            return False
        sent, err = TransactionalEmailService.send_templated_optional(
            db,
            template_key=template_key,
            to_email=to_email,
            variables=variables,
        )
        if err:
            logger.warning("billing_refund_email_failed template=%s org_id=%s err=%s", template_key, org.id, err)
        return bool(sent)

    @staticmethod
    def _base_vars(db: Session, org: Organisation) -> dict[str, str]:
        return {
            "organisation_name": org.name or "your organisation",
            "billing_url": DASHBOARD_BILLING_URL,
            "packages_url": DASHBOARD_PACKAGES_URL,
        }

    @staticmethod
    def product_name_for_subscription(*, service_code: str | None, plan_name: str | None = None) -> str:
        sc = str(service_code or "voxbulk").strip().lower()
        if sc == "customer_feedback":
            return "Customer Feedback"
        if plan_name:
            return f"Core platform ({plan_name})"
        return "Core platform"

    @staticmethod
    def send_subscription_ended(
        db: Session,
        *,
        org: Organisation,
        user_id: str | None,
        service_code: str | None,
        plan_name: str | None,
    ) -> bool:
        product_name = BillingRefundEmailService.product_name_for_subscription(
            service_code=service_code,
            plan_name=plan_name,
        )
        return BillingRefundEmailService._send(
            db,
            template_key="billing_subscription_ended",
            org=org,
            user_id=user_id,
            variables={
                **BillingRefundEmailService._base_vars(db, org),
                "product_name": product_name,
            },
        )

    @staticmethod
    def send_renewal_reminder(
        db: Session,
        *,
        org: Organisation,
        user_id: str | None,
        service_code: str | None,
        plan_name: str | None,
        renewal_date: str,
        days_remaining: int,
    ) -> bool:
        product_name = BillingRefundEmailService.product_name_for_subscription(
            service_code=service_code,
            plan_name=plan_name,
        )
        return BillingRefundEmailService._send(
            db,
            template_key="billing_renewal_reminder",
            org=org,
            user_id=user_id,
            variables={
                **BillingRefundEmailService._base_vars(db, org),
                "product_name": product_name,
                "renewal_date": renewal_date,
                "days_remaining": str(max(int(days_remaining), 0)),
            },
        )

    @staticmethod
    def send_cancellation_requested(
        db: Session,
        *,
        org: Organisation,
        user_id: str | None,
        effective_date: str,
        refund_preference: str,
        estimated_refund_pence: int,
    ) -> None:
        currency = resolve_org_currency(db, org)
        BillingRefundEmailService._send(
            db,
            template_key="billing_cancellation_requested",
            org=org,
            user_id=user_id,
            variables={
                **BillingRefundEmailService._base_vars(db, org),
                "effective_date": effective_date,
                "refund_preference": refund_preference.replace("_", " "),
                "estimated_refund": money_display(estimated_refund_pence, currency),
                "timing_note": "No refund is issued until our team approves a refund request.",
            },
        )

    @staticmethod
    def send_cancellation_reversed(db: Session, *, org: Organisation, user_id: str | None) -> None:
        BillingRefundEmailService._send(
            db,
            template_key="billing_cancellation_reversed",
            org=org,
            user_id=user_id,
            variables=BillingRefundEmailService._base_vars(db, org),
        )

    @staticmethod
    def send_wallet_credit_issued(
        db: Session,
        *,
        org: Organisation,
        user_id: str | None,
        amount_pence: int,
        wallet_balance_pence: int,
    ) -> None:
        currency = resolve_org_currency(db, org)
        BillingRefundEmailService._send(
            db,
            template_key="billing_wallet_credit_issued",
            org=org,
            user_id=user_id,
            variables={
                **BillingRefundEmailService._base_vars(db, org),
                "amount": money_display(amount_pence, currency),
                "wallet_balance": money_display(wallet_balance_pence, currency),
                "timing_note": "Wallet credit is usually available immediately in your VoxBulk account.",
            },
        )

    @staticmethod
    def send_bank_refund_approved(
        db: Session,
        *,
        org: Organisation,
        user_id: str | None,
        amount_pence: int,
        payment_method: str,
        payment_reference: str | None,
        stripe_refund_id: str | None = None,
    ) -> None:
        currency = resolve_org_currency(db, org)
        ref_line = payment_reference or stripe_refund_id or "—"
        BillingRefundEmailService._send(
            db,
            template_key="billing_bank_refund_approved",
            org=org,
            user_id=user_id,
            variables={
                **BillingRefundEmailService._base_vars(db, org),
                "amount": money_display(amount_pence, currency),
                "payment_method": payment_method.replace("_", " "),
                "payment_reference": ref_line,
                "processing_note": REFUND_PROCESSING_NOTE,
                "reflection_note": REFUND_BANK_REFLECTION_NOTE,
            },
        )

    @staticmethod
    def send_refund_rejected(
        db: Session,
        *,
        org: Organisation,
        user_id: str | None,
        amount_pence: int,
        admin_notes: str | None,
    ) -> None:
        currency = resolve_org_currency(db, org)
        BillingRefundEmailService._send(
            db,
            template_key="billing_refund_request_rejected",
            org=org,
            user_id=user_id,
            variables={
                **BillingRefundEmailService._base_vars(db, org),
                "amount": money_display(amount_pence, currency),
                "admin_notes": (admin_notes or "Please contact support if you have questions.").strip(),
            },
        )

    @staticmethod
    def timing_notes_for_ui(*, refund_type: str = "bank") -> dict[str, str]:
        if refund_type == "wallet":
            return {
                "processing": "Wallet credit is usually available immediately.",
                "reflection": "",
            }
        return {
            "processing": REFUND_PROCESSING_NOTE,
            "reflection": REFUND_BANK_REFLECTION_NOTE,
        }
