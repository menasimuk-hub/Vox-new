"""Org wallet — balance plus append-only ledger.

The wallet is the only customer-funded balance. It is topped up via Stripe or Airwallex card
payments and debited at campaign launch. Mandate Direct Debits and subscription fees never
touch the wallet (they are invoiced and collected via GoCardless).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.wallet_transaction import WalletTransaction
from app.services.billing_currency import money_display, resolve_org_currency

logger = logging.getLogger(__name__)


class WalletError(ValueError):
    pass


class InsufficientWalletBalance(WalletError):
    pass


class PromoWalletRestricted(WalletError):
    pass


PROMO_RESTRICTED_DEBIT_KINDS = frozenset(
    {"launch_debit", "launch_hold", "invoice_payment", "feedback_promo", "campaign_debit"}
)


class WalletService:
    MIN_TOPUP_MINOR = 500

    @staticmethod
    def promo_balance_minor(org: Organisation) -> int:
        return max(0, int(getattr(org, "promo_wallet_balance_pence", 0) or 0))

    @staticmethod
    def unrestricted_balance_minor(org: Organisation) -> int:
        return max(0, WalletService.balance_minor(org) - WalletService.promo_balance_minor(org))

    @staticmethod
    def spendable_minor(org: Organisation, *, allow_promo: bool) -> int:
        total = WalletService.balance_minor(org)
        if allow_promo:
            return total
        return WalletService.unrestricted_balance_minor(org)

    @staticmethod
    def balance_minor(org: Organisation) -> int:
        return int(org.wallet_balance_pence or 0)

    @staticmethod
    def wallet_dict(db: Session, org: Organisation) -> dict[str, Any]:
        currency = resolve_org_currency(db, org)
        balance = WalletService.balance_minor(org)
        return {
            "wallet_balance_minor": balance,
            "wallet_balance_pence": balance,
            "wallet_balance_display": money_display(balance, currency),
            "wallet_balance_gbp": money_display(balance, currency),
            "currency": currency,
        }

    @staticmethod
    def _record(
        db: Session,
        org: Organisation,
        *,
        direction: str,
        kind: str,
        amount_minor: int,
        currency: str,
        status: str = "succeeded",
        provider: str | None = None,
        provider_reference: str | None = None,
        description: str | None = None,
        order_id: str | None = None,
        invoice_id: str | None = None,
        created_by_user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        balance_after: int | None = None,
    ) -> WalletTransaction:
        now = datetime.utcnow()
        row = WalletTransaction(
            id=str(uuid.uuid4()),
            org_id=org.id,
            direction=direction,
            kind=kind,
            amount_minor=int(amount_minor),
            currency=currency,
            balance_after_minor=balance_after,
            status=status,
            provider=provider,
            provider_reference=provider_reference,
            description=description,
            order_id=order_id,
            invoice_id=invoice_id,
            created_by_user_id=created_by_user_id,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        return row

    @staticmethod
    def credit(
        db: Session,
        org: Organisation,
        *,
        amount_minor: int,
        kind: str = "topup",
        provider: str | None = None,
        provider_reference: str | None = None,
        description: str | None = None,
        order_id: str | None = None,
        invoice_id: str | None = None,
        created_by_user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> WalletTransaction:
        amount = int(amount_minor or 0)
        if amount <= 0:
            raise WalletError("Credit amount must be positive")
        currency = resolve_org_currency(db, org, persist=True)
        org.wallet_balance_pence = WalletService.balance_minor(org) + amount
        promo_flag = bool((metadata or {}).get("restricted_spend"))
        if promo_flag:
            org.promo_wallet_balance_pence = WalletService.promo_balance_minor(org) + amount
        db.add(org)
        row = WalletService._record(
            db,
            org,
            direction="credit",
            kind=kind,
            amount_minor=amount,
            currency=currency,
            provider=provider,
            provider_reference=provider_reference,
            description=description,
            order_id=order_id,
            invoice_id=invoice_id,
            created_by_user_id=created_by_user_id,
            metadata=metadata,
            balance_after=int(org.wallet_balance_pence),
        )
        if commit:
            db.commit()
            db.refresh(row)
        logger.info(
            "wallet_credit org_id=%s amount=%s kind=%s provider=%s ref=%s balance=%s",
            org.id, amount, kind, provider, provider_reference, org.wallet_balance_pence,
        )
        return row

    @staticmethod
    def debit(
        db: Session,
        org: Organisation,
        *,
        amount_minor: int,
        kind: str = "launch_debit",
        description: str | None = None,
        order_id: str | None = None,
        invoice_id: str | None = None,
        created_by_user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        restrict_promo_spend: bool | None = None,
        commit: bool = True,
    ) -> WalletTransaction:
        amount = int(amount_minor or 0)
        if amount <= 0:
            raise WalletError("Debit amount must be positive")
        balance = WalletService.balance_minor(org)
        if restrict_promo_spend is None:
            restrict_promo_spend = kind in PROMO_RESTRICTED_DEBIT_KINDS
        spendable = WalletService.spendable_minor(org, allow_promo=not restrict_promo_spend)
        if spendable < amount:
            if restrict_promo_spend and WalletService.promo_balance_minor(org) > 0:
                raise PromoWalletRestricted(
                    "Promo wallet credit cannot be used for campaign launches or Customer feedback — "
                    "top up or use package allowance."
                )
            raise InsufficientWalletBalance(
                f"Wallet balance is insufficient ({money_display(spendable)} available, {money_display(amount)} required)"
            )
        currency = resolve_org_currency(db, org, persist=True)
        unrestricted_before = WalletService.unrestricted_balance_minor(org)
        org.wallet_balance_pence = balance - amount
        if not restrict_promo_spend:
            promo_used = max(0, amount - unrestricted_before)
            if promo_used > 0:
                org.promo_wallet_balance_pence = max(0, WalletService.promo_balance_minor(org) - promo_used)
        db.add(org)
        row = WalletService._record(
            db,
            org,
            direction="debit",
            kind=kind,
            amount_minor=amount,
            currency=currency,
            provider="internal",
            description=description,
            order_id=order_id,
            invoice_id=invoice_id,
            created_by_user_id=created_by_user_id,
            metadata=metadata,
            balance_after=int(org.wallet_balance_pence),
        )
        if commit:
            db.commit()
            db.refresh(row)
        logger.info(
            "wallet_debit org_id=%s amount=%s kind=%s order_id=%s balance=%s",
            org.id, amount, kind, order_id, org.wallet_balance_pence,
        )
        return row

    @staticmethod
    def has_transaction_for_reference(db: Session, *, provider: str, provider_reference: str) -> bool:
        if not provider_reference:
            return False
        row = db.execute(
            select(WalletTransaction.id).where(
                WalletTransaction.provider == provider,
                WalletTransaction.provider_reference == provider_reference,
                WalletTransaction.status == "succeeded",
            )
        ).first()
        return row is not None

    @staticmethod
    def list_transactions(db: Session, org_id: str, *, limit: int = 100) -> list[WalletTransaction]:
        cap = max(1, min(int(limit or 100), 500))
        return list(
            db.execute(
                select(WalletTransaction)
                .where(WalletTransaction.org_id == org_id)
                .order_by(WalletTransaction.created_at.desc())
                .limit(cap)
            )
            .scalars()
            .all()
        )

    @staticmethod
    def transaction_to_dict(row: WalletTransaction) -> dict[str, Any]:
        sign = 1 if row.direction == "credit" else -1
        return {
            "id": row.id,
            "direction": row.direction,
            "kind": row.kind,
            "amount_minor": int(row.amount_minor or 0),
            "signed_amount_minor": sign * int(row.amount_minor or 0),
            "amount_display": money_display(int(row.amount_minor or 0), row.currency),
            "currency": row.currency,
            "balance_after_minor": row.balance_after_minor,
            "balance_after_display": money_display(row.balance_after_minor, row.currency) if row.balance_after_minor is not None else None,
            "status": row.status,
            "provider": row.provider,
            "provider_reference": row.provider_reference,
            "description": row.description,
            "order_id": row.order_id,
            "invoice_id": row.invoice_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
