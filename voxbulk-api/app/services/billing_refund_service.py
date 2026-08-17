"""Reverse wallet top-ups and freeze matching subscriptions after card refunds/disputes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.subscription import Subscription
from app.models.wallet_transaction import WalletTransaction
from app.services.subscription_live_guard import apply_live_slot

logger = logging.getLogger(__name__)

SUBSCRIPTION_KINDS = frozenset(
    {
        "subscription_checkout",
        "subscription_renewal",
        "pro_rata_upgrade",
        "smart_card_checkout",
    }
)


class BillingRefundService:
    @staticmethod
    def handle_provider_refund(
        db: Session,
        *,
        provider: str,
        org_id: str,
        payment_kind: str,
        payment_intent_id: str,
        refund_id: str,
        amount_minor: int,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        kind = str(payment_kind or "").strip().lower()
        pid = str(payment_intent_id or "").strip()
        rid = str(refund_id or pid or "").strip()
        if not org_id:
            return {"ok": True, "ignored": True, "reason": "missing_org"}
        org = db.get(Organisation, org_id)
        if org is None:
            return {"ok": True, "ignored": True, "reason": "org_not_found"}

        if kind == "wallet_topup":
            return BillingRefundService._reverse_wallet_topup(
                db,
                org=org,
                provider=provider,
                payment_intent_id=pid,
                refund_id=rid,
                amount_minor=amount_minor,
            )

        if kind in SUBSCRIPTION_KINDS or str((metadata or {}).get("voxbulk_plan_id") or "").strip():
            return BillingRefundService._freeze_subscription(
                db,
                org=org,
                provider=provider,
                payment_intent_id=pid,
                metadata=metadata or {},
            )

        return {"ok": True, "ignored": True, "reason": "unsupported_kind", "kind": kind}

    @staticmethod
    def _reverse_wallet_topup(
        db: Session,
        *,
        org: Organisation,
        provider: str,
        payment_intent_id: str,
        refund_id: str,
        amount_minor: int,
    ) -> dict[str, Any]:
        from app.services.billing_currency import resolve_org_currency
        from app.services.wallet_service import WalletService

        refund_ref = f"refund:{provider}:{refund_id}"
        if WalletService.has_transaction_for_reference(db, provider=provider, provider_reference=refund_ref):
            return {"ok": True, "reversed": False, "duplicate": True}

        original = None
        if payment_intent_id:
            original = db.execute(
                select(WalletTransaction).where(
                    WalletTransaction.provider == provider,
                    WalletTransaction.provider_reference == payment_intent_id,
                    WalletTransaction.direction == "credit",
                )
            ).scalar_one_or_none()
        amount = int(amount_minor or 0)
        if amount <= 0 and original is not None:
            amount = int(original.amount_minor or 0)
        if amount <= 0:
            return {"ok": True, "ignored": True, "reason": "zero_amount"}

        take = min(amount, max(0, WalletService.balance_minor(org)))
        currency = resolve_org_currency(db, org, persist=True)
        org.wallet_balance_pence = WalletService.balance_minor(org) - take
        db.add(org)
        WalletService._record(
            db,
            org,
            direction="debit",
            kind="refund_reversal",
            amount_minor=take if take > 0 else amount,
            currency=currency,
            provider=provider,
            provider_reference=refund_ref,
            description="Card refund reversed wallet top-up",
            metadata={"original_reference": payment_intent_id, "refund_id": refund_id, "requested_minor": amount},
            balance_after=int(org.wallet_balance_pence or 0),
        )
        db.commit()
        logger.info(
            "wallet_topup_refund_reversed org_id=%s amount=%s refund=%s",
            org.id,
            take,
            refund_id,
        )
        return {"ok": True, "reversed": True, "amount_minor": take}

    @staticmethod
    def _freeze_subscription(
        db: Session,
        *,
        org: Organisation,
        provider: str,
        payment_intent_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        service_code = str(metadata.get("voxbulk_service_code") or "voxbulk").strip() or "voxbulk"
        sub = None
        pid = str(payment_intent_id or "").strip()
        if pid:
            sub = db.execute(
                select(Subscription).where(
                    Subscription.org_id == org.id,
                    Subscription.external_subscription_id == pid,
                )
            ).scalar_one_or_none()
        if sub is None:
            sub = (
                db.execute(
                    select(Subscription)
                    .where(
                        Subscription.org_id == org.id,
                        Subscription.service_code == service_code,
                        Subscription.live_slot == 1,
                    )
                    .limit(1)
                )
                .scalars()
                .first()
            )
        if sub is None:
            return {"ok": True, "ignored": True, "reason": "subscription_not_found"}

        now = datetime.utcnow()
        sub.status = "suspended"
        sub.cancellation_status = "cancelled"
        sub.cancelled_at = now
        sub.updated_at = now
        apply_live_slot(sub)
        db.add(sub)
        db.commit()
        logger.warning(
            "subscription_frozen_after_refund org_id=%s sub_id=%s provider=%s",
            org.id,
            sub.id,
            provider,
        )
        return {"ok": True, "frozen": True, "subscription_id": sub.id}
