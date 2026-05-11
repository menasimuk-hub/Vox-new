from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.plan import Plan
from app.models.subscription import Subscription


@dataclass(frozen=True)
class AdminBillingOverview:
    plans_total: int
    subscriptions_total: int
    subscriptions_active: int
    subscriptions_trial: int
    subscriptions_past_due: int
    subscriptions_pending_payment: int
    subscriptions_test_mode: int
    subscriptions_production_mode: int
    latest_subscription_created_at: datetime | None


class AdminBillingService:
    @staticmethod
    def list_plans(db: Session) -> list[Plan]:
        return list(db.execute(select(Plan).order_by(Plan.price_gbp_pence.asc(), Plan.name.asc())).scalars())

    @staticmethod
    def subscriptions_overview(db: Session, *, limit_window: int = 500) -> AdminBillingOverview:
        plans_total = db.execute(select(func.count()).select_from(Plan)).scalar_one()

        ids = [
            r[0]
            for r in db.execute(select(Subscription.id).order_by(Subscription.created_at.desc()).limit(limit_window)).all()
        ]
        if not ids:
            return AdminBillingOverview(
                plans_total=int(plans_total),
                subscriptions_total=0,
                subscriptions_active=0,
                subscriptions_trial=0,
                subscriptions_past_due=0,
                subscriptions_pending_payment=0,
                subscriptions_test_mode=0,
                subscriptions_production_mode=0,
                latest_subscription_created_at=None,
            )

        counts = dict(
            db.execute(
                select(Subscription.status, func.count()).where(Subscription.id.in_(ids)).group_by(Subscription.status)
            ).all()
        )
        modes = dict(
            db.execute(
                select(Subscription.payment_mode, func.count()).where(Subscription.id.in_(ids)).group_by(Subscription.payment_mode)
            ).all()
        )
        latest = db.execute(select(func.max(Subscription.created_at)).where(Subscription.id.in_(ids))).scalar_one()
        return AdminBillingOverview(
            plans_total=int(plans_total),
            subscriptions_total=len(ids),
            subscriptions_active=int(counts.get("active", 0)),
            subscriptions_trial=int(counts.get("trial", 0)),
            subscriptions_past_due=int(counts.get("past_due", 0)),
            subscriptions_pending_payment=int(counts.get("pending_payment", 0)),
            subscriptions_test_mode=int(modes.get("test", 0)),
            subscriptions_production_mode=int(modes.get("production", 0)),
            latest_subscription_created_at=latest,
        )

