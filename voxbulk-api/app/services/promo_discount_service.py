"""Apply pending promo discounts at checkout."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.promo_offer import PromoPendingDiscount

SERVICE_KIND_ALIASES = {
    "voxbulk": "voxbulk",
    "core": "voxbulk",
    "dental": "voxbulk",
    "subscription": "voxbulk",
    "survey": "survey",
    "interview": "interview",
    "customer_feedback": "customer_feedback",
    "feedback": "customer_feedback",
    "expo": "expo",
    "smart_card": "smart_card",
    "smartcard": "smart_card",
}


def normalize_service_kind(raw: str | None) -> str:
    clean = str(raw or "").strip().lower()
    return SERVICE_KIND_ALIASES.get(clean, clean or "voxbulk")


class PromoDiscountService:
    @staticmethod
    def get_pending(db: Session, *, org_id: str, service_kind: str) -> PromoPendingDiscount | None:
        sk = normalize_service_kind(service_kind)
        return db.execute(
            select(PromoPendingDiscount)
            .where(
                PromoPendingDiscount.org_id == org_id,
                PromoPendingDiscount.service_kind == sk,
                PromoPendingDiscount.status == "pending",
            )
            .order_by(PromoPendingDiscount.created_at.asc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def compute_amount(amount_minor: int, *, discount_type: str, discount_value: int) -> int:
        amount = max(0, int(amount_minor or 0))
        dtype = str(discount_type or "").strip().lower()
        value = max(0, int(discount_value or 0))
        if dtype == "percent":
            pct = min(100, value)
            return max(0, amount - int(round(amount * pct / 100.0)))
        if dtype == "fixed_minor":
            return max(0, amount - value)
        return amount

    @staticmethod
    def peek_amount(db: Session, *, org_id: str, service_kind: str, amount_minor: int) -> dict[str, Any]:
        pending = PromoDiscountService.get_pending(db, org_id=org_id, service_kind=service_kind)
        if pending is None:
            return {
                "amount_minor": max(0, int(amount_minor or 0)),
                "discount_applied": False,
                "pending_id": None,
            }
        reduced = PromoDiscountService.compute_amount(
            amount_minor,
            discount_type=pending.discount_type,
            discount_value=int(pending.discount_value or 0),
        )
        return {
            "amount_minor": reduced,
            "discount_applied": True,
            "pending_id": pending.id,
            "discount_type": pending.discount_type,
            "discount_value": int(pending.discount_value or 0),
            "original_amount_minor": max(0, int(amount_minor or 0)),
        }

    @staticmethod
    def apply_and_consume(
        db: Session,
        *,
        org_id: str,
        service_kind: str,
        amount_minor: int,
        commit: bool = False,
    ) -> dict[str, Any]:
        peeked = PromoDiscountService.peek_amount(
            db, org_id=org_id, service_kind=service_kind, amount_minor=amount_minor
        )
        if not peeked.get("discount_applied") or not peeked.get("pending_id"):
            return peeked
        pending = db.get(PromoPendingDiscount, peeked["pending_id"])
        if pending is None or pending.status != "pending":
            return {
                "amount_minor": max(0, int(amount_minor or 0)),
                "discount_applied": False,
                "pending_id": None,
            }
        pending.status = "consumed"
        pending.consumed_at = datetime.utcnow()
        db.add(pending)
        if commit:
            db.commit()
        else:
            db.flush()
        return peeked
