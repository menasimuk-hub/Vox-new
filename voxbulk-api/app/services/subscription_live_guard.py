"""One live subscription per org + service, and cancel-aware billing skips."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subscription import Subscription

LIVE_SUBSCRIPTION_STATUSES = frozenset(
    {
        "active",
        "trial",
        "past_due",
        "suspended",
        "pending_first_payment",
        "pending_payment",
    }
)
CANCEL_SKIP_STATUSES = frozenset({"scheduled", "cancelled"})


def apply_live_slot(sub: Subscription) -> None:
    status = str(sub.status or "").strip().lower()
    sub.live_slot = 1 if status in LIVE_SUBSCRIPTION_STATUSES else None


def is_cancel_skip(sub: Subscription | None) -> bool:
    if sub is None:
        return False
    if bool(getattr(sub, "cancel_at_period_end", False)):
        return True
    return str(sub.cancellation_status or "").strip().lower() in CANCEL_SKIP_STATUSES


def lock_live_subscription(db: Session, org_id: str, *, service_code: str) -> Subscription | None:
    return (
        db.execute(
            select(Subscription)
            .where(
                Subscription.org_id == org_id,
                Subscription.service_code == service_code,
                Subscription.live_slot == 1,
            )
            .with_for_update()
            .limit(1)
        )
        .scalars()
        .first()
    )


def promo_service_kind(service_code: str) -> str:
    code = str(service_code or "").strip().lower()
    if code in {"customer_feedback", "feedback"}:
        return "customer_feedback"
    if code in {"smart_card", "smartcard"}:
        return "smart_card"
    return "voxbulk"
