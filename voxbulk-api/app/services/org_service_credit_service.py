from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder


class OrgServiceCreditError(ValueError):
    pass


class OrgServiceCreditService:
    @staticmethod
    def balances_dict(org: Organisation) -> dict[str, int]:
        return {
            "survey_credits": int(org.survey_credits_balance or 0),
            "interview_credits": int(org.interview_credits_balance or 0),
        }

    @staticmethod
    def available_for_service(org: Organisation, service_code: str) -> int:
        if service_code == "survey":
            return int(org.survey_credits_balance or 0)
        if service_code == "interview":
            return int(org.interview_credits_balance or 0)
        return 0

    @staticmethod
    def can_cover(org: Organisation, *, service_code: str, recipient_count: int) -> bool:
        needed = max(0, int(recipient_count or 0))
        if needed <= 0:
            return False
        return OrgServiceCreditService.available_for_service(org, service_code) >= needed

    @staticmethod
    def grant(db: Session, org: Organisation, *, service_code: str, amount: int) -> Organisation:
        credits = max(0, int(amount or 0))
        if credits <= 0:
            return org
        if service_code == "survey":
            org.survey_credits_balance = int(org.survey_credits_balance or 0) + credits
        elif service_code == "interview":
            org.interview_credits_balance = int(org.interview_credits_balance or 0) + credits
        else:
            raise OrgServiceCreditError("Unsupported service for promo credits")
        db.add(org)
        db.commit()
        db.refresh(org)
        return org

    @staticmethod
    def apply_to_order(db: Session, order: ServiceOrder, org: Organisation) -> ServiceOrder:
        if order.recipient_count <= 0:
            raise OrgServiceCreditError("Upload contacts before using promo credits")
        if order.status not in {"quoted", "draft"}:
            raise OrgServiceCreditError("Order is not ready for payment")
        if not OrgServiceCreditService.can_cover(org, service_code=order.service_code, recipient_count=order.recipient_count):
            raise OrgServiceCreditError("Not enough promo credits for this order")

        now = datetime.utcnow()
        count = int(order.recipient_count or 0)
        if order.service_code == "survey":
            org.survey_credits_balance = int(org.survey_credits_balance or 0) - count
        elif order.service_code == "interview":
            org.interview_credits_balance = int(org.interview_credits_balance or 0) - count
        else:
            raise OrgServiceCreditError("Unsupported service for promo credits")

        order.payment_method = "promo_credits"
        order.payment_status = "approved"
        order.status = "paid"
        order.payment_note = f"Paid with {count} promo {order.service_code} credit(s)"
        order.updated_at = now
        db.add_all([org, order])
        db.commit()
        db.refresh(order)
        return order
