from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.notification import Notification
from app.models.service_order import ServiceOrder
from app.models.subscription import Subscription
from app.models.support_ticket import SupportTicket


def notification_to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "type": n.type,
        "title": n.title,
        "message": n.message,
        "severity": n.severity,
        "ticket_id": n.ticket_id,
        "action_url": n.action_url,
        "read_at": n.read_at,
        "created_at": n.created_at,
    }


class NotificationService:
    @staticmethod
    def upsert(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        type: str,
        title: str,
        message: str,
        dedupe_key: str,
        severity: str = "info",
        ticket_id: int | None = None,
        action_url: str | None = None,
        created_at: datetime | None = None,
    ) -> Notification:
        now = datetime.utcnow()
        row = db.execute(select(Notification).where(Notification.dedupe_key == dedupe_key)).scalar_one_or_none()
        if row is None:
            row = Notification(
                organisation_id=org_id,
                user_id=user_id,
                type=type,
                title=title,
                message=message,
                severity=severity,
                ticket_id=ticket_id,
                action_url=action_url,
                dedupe_key=dedupe_key,
                created_at=created_at or now,
                updated_at=now,
            )
        else:
            row.title = title
            row.message = message
            row.severity = severity
            row.ticket_id = ticket_id
            row.action_url = action_url
            row.updated_at = now
        db.add(row)
        return row

    @staticmethod
    def create_ticket_reply_notification(db: Session, *, ticket: SupportTicket) -> Notification:
        return NotificationService.upsert(
            db,
            org_id=ticket.organisation_id,
            user_id=ticket.created_by_user_id,
            type="ticket_reply",
            title=f"New reply on {ticket.public_ref or f'TKT-{ticket.id:06d}'}",
            message=ticket.subject,
            severity="info",
            ticket_id=ticket.id,
            action_url=f"/account/support/tickets?ticket={ticket.id}",
            dedupe_key=f"ticket-reply:{ticket.id}:{ticket.last_message_at.isoformat() if ticket.last_message_at else ticket.updated_at.isoformat()}",
            created_at=ticket.last_message_at or ticket.updated_at,
        )

    @staticmethod
    def sync_user_notifications(db: Session, *, org_id: str, user_id: str) -> None:
        unread_tickets = list(
            db.execute(
                select(SupportTicket).where(
                    SupportTicket.organisation_id == org_id,
                    SupportTicket.created_by_user_id == user_id,
                    SupportTicket.customer_unread == True,  # noqa: E712
                )
            ).scalars()
        )
        for ticket in unread_tickets:
            NotificationService.create_ticket_reply_notification(db, ticket=ticket)

        invoices = list(
            db.execute(
                select(BillingInvoice)
                .where(BillingInvoice.org_id == org_id)
                .order_by(BillingInvoice.created_at.desc())
                .limit(10)
            ).scalars()
        )
        for inv in invoices:
            NotificationService.upsert(
                db,
                org_id=org_id,
                user_id=user_id,
                type="invoice",
                title="New invoice",
                message=f"{inv.external_invoice_id} · £{(inv.amount_gbp_pence or 0) / 100:.2f} · {inv.status}",
                severity="billing",
                action_url="/account/billing",
                dedupe_key=f"invoice:{inv.id}:{user_id}",
                created_at=inv.created_at,
            )

        now = datetime.utcnow()
        renew_cutoff = now + timedelta(days=14)
        sub = db.execute(
            select(Subscription)
            .where(
                Subscription.org_id == org_id,
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end >= now,
                Subscription.current_period_end <= renew_cutoff,
            )
            .order_by(Subscription.current_period_end.asc())
        ).scalar_one_or_none()
        if sub is not None:
            days = max((sub.current_period_end.date() - now.date()).days, 0)
            NotificationService.upsert(
                db,
                org_id=org_id,
                user_id=user_id,
                type="renewal_reminder",
                title="Renewal reminder",
                message=f"Your subscription renews in {days} day{'s' if days != 1 else ''}.",
                severity="warning",
                action_url="/account/billing",
                dedupe_key=f"renewal:{sub.id}:{sub.current_period_end.date().isoformat()}:{user_id}",
                created_at=sub.current_period_end,
            )

    @staticmethod
    def list_user_notifications(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Notification]:
        NotificationService.sync_user_notifications(db, org_id=org_id, user_id=user_id)
        db.commit()
        stmt = select(Notification).where(Notification.organisation_id == org_id, Notification.user_id == user_id)
        if unread_only:
            stmt = stmt.where(Notification.read_at.is_(None))
        return list(
            db.execute(
                stmt.order_by(Notification.created_at.desc())
                .limit(min(max(int(limit or 50), 1), 100))
                .offset(max(int(offset or 0), 0))
            ).scalars()
        )

    @staticmethod
    def unread_count(db: Session, *, org_id: str, user_id: str) -> int:
        NotificationService.sync_user_notifications(db, org_id=org_id, user_id=user_id)
        db.commit()
        return int(
            db.execute(
                select(func.count())
                .select_from(Notification)
                .where(Notification.organisation_id == org_id, Notification.user_id == user_id, Notification.read_at.is_(None))
            ).scalar_one()
            or 0
        )

    @staticmethod
    def mark_read(db: Session, *, org_id: str, user_id: str, notification_id: int) -> Notification | None:
        row = db.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.organisation_id == org_id,
                Notification.user_id == user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.read_at is None:
            row.read_at = datetime.utcnow()
            row.updated_at = row.read_at
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def create_wallet_credit_notification(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        amount_minor: int,
        currency: str,
        reason: str,
        tx_id: str,
    ) -> Notification:
        from app.services.billing_currency import money_display

        amount_label = money_display(amount_minor, currency)
        msg = f"{amount_label} added to your wallet."
        if reason.strip():
            msg += f" {reason.strip()}"
        return NotificationService.upsert(
            db,
            org_id=org_id,
            user_id=user_id,
            type="wallet_credit",
            title="Wallet credited",
            message=msg,
            severity="info",
            action_url="/account/billing",
            dedupe_key=f"wallet-credit:{tx_id}:{user_id}",
        )

    @staticmethod
    def notify_org_wallet_credit(
        db: Session,
        *,
        org_id: str,
        amount_minor: int,
        currency: str,
        reason: str,
        tx_id: str,
    ) -> None:
        members = list(
            db.execute(select(OrganisationMembership.user_id).where(OrganisationMembership.org_id == org_id)).scalars()
        )
        for user_id in members:
            NotificationService.create_wallet_credit_notification(
                db,
                org_id=org_id,
                user_id=str(user_id),
                amount_minor=amount_minor,
                currency=currency,
                reason=reason,
                tx_id=tx_id,
            )

    @staticmethod
    def create_campaign_completed_notification(db: Session, *, order: ServiceOrder) -> Notification | None:
        service = str(order.service_code or "").lower()
        if service == "interview":
            title = "Interview campaign complete"
            action_url = f"/interviews/results/{order.id}"
        elif service == "survey":
            title = "Survey campaign complete"
            action_url = f"/surveys/results?orderId={order.id}"
        else:
            return None
        label = (order.title or "").strip()
        message = label or f"Campaign {order.id[:8]}"
        return NotificationService.upsert(
            db,
            org_id=order.org_id,
            user_id=order.user_id,
            type="campaign_completed",
            title=title,
            message=message,
            severity="info",
            action_url=action_url,
            dedupe_key=f"campaign-complete:{order.id}",
            created_at=order.completed_at or datetime.utcnow(),
        )

    @staticmethod
    def create_billing_request_notification(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        title: str,
        message: str,
        dedupe_key: str,
    ) -> Notification:
        return NotificationService.upsert(
            db,
            org_id=org_id,
            user_id=user_id,
            type="billing_request",
            title=title,
            message=message,
            severity="info",
            action_url="/account/billing",
            dedupe_key=dedupe_key,
        )

    @staticmethod
    def create_billing_request_resolved_notification(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        review_status: str,
        wallet_credit_pence: int,
        external_refund_pence: int = 0,
        dedupe_key: str,
    ) -> Notification:
        from app.services.billing_currency import money_display, resolve_org_currency
        from app.models.organisation import Organisation
        from app.services.billing_refund_email_service import BillingRefundEmailService

        org = db.get(Organisation, org_id)
        currency = resolve_org_currency(db, org) if org else "GBP"
        msg = f"Your billing request was {review_status}."
        if wallet_credit_pence > 0:
            msg += f" Wallet credit: {money_display(wallet_credit_pence, currency)}."
        if external_refund_pence > 0:
            msg += f" Bank refund: {money_display(external_refund_pence, currency)}."
            notes = BillingRefundEmailService.timing_notes_for_ui(refund_type="bank")
            msg += f" {notes['processing']} {notes['reflection']}"
        return NotificationService.upsert(
            db,
            org_id=org_id,
            user_id=user_id,
            type="billing_request_resolved",
            title="Billing request update",
            message=msg,
            severity="info",
            action_url="/account/billing",
            dedupe_key=dedupe_key,
        )

    @staticmethod
    def admin_pending_count(db: Session) -> dict[str, int]:
        from app.models.billing_refund_review import BillingRefundReview
        from app.models.support_ticket import SupportTicket
        from app.services.subscription_cancellation_service import (
            CANCELLATION_REQUESTED,
            CANCELLATION_SCHEDULED,
            REVIEW_PENDING,
        )

        pending_reviews = int(
            db.scalar(
                select(func.count())
                .select_from(BillingRefundReview)
                .where(BillingRefundReview.review_status == REVIEW_PENDING)
            )
            or 0
        )
        pending_cancellations = int(
            db.scalar(
                select(func.count())
                .select_from(Subscription)
                .where(Subscription.cancellation_status.in_((CANCELLATION_SCHEDULED, CANCELLATION_REQUESTED)))
            )
            or 0
        )
        admin_unread = int(
            db.scalar(
                select(func.count())
                .select_from(SupportTicket)
                .where(SupportTicket.admin_unread == True)  # noqa: E712
            )
            or 0
        )
        return {
            "pending_billing_requests": pending_reviews + pending_cancellations,
            "pending_refund_reviews": pending_reviews,
            "pending_cancellations": pending_cancellations,
            "admin_unread_tickets": admin_unread,
            "total": pending_reviews + pending_cancellations + admin_unread,
        }

    @staticmethod
    def mark_ticket_read(db: Session, *, org_id: str, user_id: str, ticket_id: int) -> None:
        now = datetime.utcnow()
        rows = list(
            db.execute(
                select(Notification).where(
                    Notification.organisation_id == org_id,
                    Notification.user_id == user_id,
                    Notification.ticket_id == ticket_id,
                    Notification.read_at.is_(None),
                )
            ).scalars()
        )
        for row in rows:
            row.read_at = now
            row.updated_at = now
            db.add(row)
        if rows:
            db.commit()
