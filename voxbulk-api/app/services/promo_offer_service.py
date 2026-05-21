from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.plan import Plan
from app.models.organisation import Organisation
from app.models.promo_offer import PromoOffer, PromoRedemption
from app.models.subscription import Subscription
from app.services.gocardless_service import BillingService
from app.services.usage_wallet_service import UsageWalletService

_CODE_RE = re.compile(r"[^A-Z0-9]+")

SUBSCRIPTION_OFFER_TYPES = {"dental_trial", "subscription_trial"}
SERVICE_CREDIT_OFFER_TYPES = {"survey_credits", "interview_credits"}


class PromoOfferError(ValueError):
    pass


class PromoOfferService:
    @staticmethod
    def is_subscription_offer(offer_type: str | None) -> bool:
        clean = str(offer_type or "dental_trial").strip() or "dental_trial"
        return clean in SUBSCRIPTION_OFFER_TYPES

    @staticmethod
    def is_service_credit_offer(offer_type: str | None) -> bool:
        clean = str(offer_type or "").strip()
        return clean in SERVICE_CREDIT_OFFER_TYPES

    @staticmethod
    def normalize_offer_type(raw: str | None) -> str:
        clean = str(raw or "dental_trial").strip() or "dental_trial"
        if clean in SUBSCRIPTION_OFFER_TYPES | SERVICE_CREDIT_OFFER_TYPES:
            return clean
        if clean in {"subscription", "plan"}:
            return "dental_trial"
        if clean in {"survey", "survey_contacts"}:
            return "survey_credits"
        if clean in {"interview", "interview_sessions"}:
            return "interview_credits"
        return clean

    @staticmethod
    def normalize_code(raw: str) -> str:
        code = _CODE_RE.sub("", str(raw or "").strip().upper())
        if len(code) < 4:
            raise PromoOfferError("Promo code must be at least 4 characters")
        return code[:32]

    @staticmethod
    def signup_url(code: str) -> str:
        origin = get_settings().public_app_origin.rstrip("/")
        return f"{origin}/signin?promo={code}"

    @staticmethod
    def get_by_code(db: Session, code: str) -> PromoOffer | None:
        clean = PromoOfferService.normalize_code(code)
        return db.execute(select(PromoOffer).where(PromoOffer.code == clean)).scalar_one_or_none()

    @staticmethod
    def validate_public(db: Session, code: str) -> dict:
        row = PromoOfferService.get_by_code(db, code)
        if row is None or not row.is_active:
            raise PromoOfferError("Promo code not found")
        now = datetime.utcnow()
        if row.expires_at and row.expires_at < now:
            raise PromoOfferError("Promo code expired")
        if row.redemption_count >= row.max_redemptions:
            raise PromoOfferError("Promo code already used")
        return PromoOfferService.to_public_dict(row)

    @staticmethod
    def to_public_dict(row: PromoOffer) -> dict:
        return {
            "code": row.code,
            "name": row.name,
            "offer_type": row.offer_type,
            "plan_code": row.plan_code,
            "service_kind": row.service_kind,
            "trial_days": int(row.trial_days or 0),
            "free_call_credits": int(row.free_call_credits or 0),
            "calls_included": int(row.calls_included or 0),
            "whatsapp_included": int(row.whatsapp_included or 0),
            "sms_included": int(row.sms_included or 0),
            "price_gbp_pence": int(row.price_gbp_pence or 0),
            "overage_per_min_pence": int(row.overage_per_min_pence or 0),
            "survey_contacts_included": int(row.survey_contacts_included or 0),
            "interview_contacts_included": int(row.interview_contacts_included or 0),
            "signup_url": PromoOfferService.signup_url(row.code),
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        }

    @staticmethod
    def list_all(db: Session) -> list[PromoOffer]:
        return list(db.execute(select(PromoOffer).order_by(PromoOffer.created_at.desc())).scalars().all())

    @staticmethod
    def to_admin_dict(row: PromoOffer) -> dict:
        return {
            **PromoOfferService.to_public_dict(row),
            "id": row.id,
            "prospect_email": row.prospect_email,
            "prospect_phone": row.prospect_phone,
            "prospect_name": row.prospect_name,
            "redemption_count": int(row.redemption_count or 0),
            "max_redemptions": int(row.max_redemptions or 1),
            "is_active": bool(row.is_active),
            "lead_sales_task_id": row.lead_sales_task_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def create_admin(db: Session, payload: dict) -> PromoOffer:
        raw_code = str(payload.get("code") or "").strip()
        if raw_code:
            code = PromoOfferService.normalize_code(raw_code)
            if PromoOfferService.get_by_code(db, code):
                raise PromoOfferError("Promo code already exists")
        else:
            code = PromoOfferService.normalize_code(f"PROMO{secrets.token_hex(3).upper()}")

        offer_type = PromoOfferService.normalize_offer_type(payload.get("offer_type"))
        now = datetime.utcnow()
        expires_days = max(1, int(payload.get("expires_in_days") or 30))
        max_redemptions = max(1, int(payload.get("max_redemptions") or 1))

        plan = None
        plan_code = str(payload.get("plan_code") or "").strip().lower()
        survey_contacts = max(0, int(payload.get("survey_contacts_included") or 0))
        interview_contacts = max(0, int(payload.get("interview_contacts_included") or 0))

        if offer_type == "survey_credits":
            if survey_contacts <= 0:
                raise PromoOfferError("Enter how many free survey contacts this promo includes")
            default_name = f"Promo · {survey_contacts} survey contact{'s' if survey_contacts != 1 else ''}"
            plan_code = None
        elif offer_type == "interview_credits":
            if interview_contacts <= 0:
                raise PromoOfferError("Enter how many free interviews this promo includes")
            default_name = f"Promo · {interview_contacts} interview{'s' if interview_contacts != 1 else ''}"
            plan_code = None
        else:
            if not plan_code:
                plan_code = "starter"
            plan = db.execute(select(Plan).where(Plan.code == plan_code)).scalar_one_or_none()
            if plan is None:
                raise PromoOfferError("Unknown plan code")
            default_name = f"Promo · {plan.name}"

        display_name = str(payload.get("name") or default_name).strip() or default_name

        row = PromoOffer(
            code=code,
            name=display_name,
            offer_type=offer_type,
            plan_code=plan.code if plan else None,
            service_kind=(
                "survey"
                if offer_type == "survey_credits"
                else "interview"
                if offer_type == "interview_credits"
                else str(payload.get("service_kind") or (plan.service_kind if plan else "dental")).strip() or "dental"
            ),
            trial_days=int(payload.get("trial_days") if payload.get("trial_days") is not None else (plan.trial_days_default if plan else 0)),
            free_call_credits=int(payload.get("free_call_credits") or 0),
            survey_contacts_included=survey_contacts,
            interview_contacts_included=interview_contacts,
            calls_included=int(payload.get("calls_included") if payload.get("calls_included") is not None else (plan.calls_included if plan else 0)),
            whatsapp_included=int(payload.get("whatsapp_included") if payload.get("whatsapp_included") is not None else (plan.whatsapp_included if plan else 0)),
            sms_included=int(payload.get("sms_included") if payload.get("sms_included") is not None else (plan.sms_included if plan else 0)),
            price_gbp_pence=int(payload.get("price_gbp_pence") if payload.get("price_gbp_pence") is not None else (plan.price_gbp_pence if plan else 0)),
            overage_per_min_pence=int(payload.get("overage_per_min_pence") if payload.get("overage_per_min_pence") is not None else (plan.overage_per_min_pence if plan else 0)),
            prospect_email=(str(payload.get("prospect_email") or "").strip() or None),
            prospect_phone=(str(payload.get("prospect_phone") or "").strip() or None),
            prospect_name=(str(payload.get("prospect_name") or "").strip() or None),
            max_redemptions=max_redemptions,
            redemption_count=0,
            expires_at=now + timedelta(days=expires_days),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update_admin(db: Session, promo_id: str, payload: dict) -> PromoOffer:
        row = db.get(PromoOffer, promo_id)
        if row is None:
            raise PromoOfferError("Promo not found")

        now = datetime.utcnow()
        if "is_active" in payload:
            row.is_active = bool(payload["is_active"])
        if "name" in payload and str(payload["name"] or "").strip():
            row.name = str(payload["name"]).strip()
        if "max_redemptions" in payload:
            row.max_redemptions = max(1, int(payload["max_redemptions"] or 1))
        if "expires_in_days" in payload:
            days = max(1, int(payload["expires_in_days"] or 30))
            row.expires_at = now + timedelta(days=days)
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def create_for_sales_task(
        db: Session,
        *,
        task_id: str,
        contact_name: str | None,
        email: str | None,
        phone: str | None,
        offer_type: str = "dental_trial",
        plan_code: str = "dental_1",
        trial_days: int = 15,
        free_call_credits: int = 0,
    ) -> PromoOffer:
        existing = db.execute(
            select(PromoOffer).where(PromoOffer.lead_sales_task_id == task_id, PromoOffer.is_active.is_(True))
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        plan = db.execute(select(Plan).where(Plan.code == plan_code.strip().lower())).scalar_one_or_none()
        code = PromoOfferService.normalize_code(f"SALE{secrets.token_hex(3).upper()}")
        now = datetime.utcnow()
        row = PromoOffer(
            code=code,
            name=f"Sales offer · {contact_name or plan_code}",
            offer_type=offer_type,
            plan_code=plan.code if plan else plan_code,
            service_kind="dental" if offer_type.startswith("dental") else offer_type.replace("_trial", ""),
            trial_days=int(trial_days),
            free_call_credits=int(free_call_credits),
            calls_included=int(plan.calls_included if plan else 0),
            whatsapp_included=int(plan.whatsapp_included if plan else 0),
            sms_included=int(plan.sms_included if plan else 0),
            price_gbp_pence=int(plan.price_gbp_pence if plan else 0),
            overage_per_min_pence=int(plan.overage_per_min_pence if plan else 20),
            prospect_email=(email or "").strip() or None,
            prospect_phone=(phone or "").strip() or None,
            prospect_name=(contact_name or "").strip() or None,
            lead_sales_task_id=task_id,
            max_redemptions=1,
            redemption_count=0,
            expires_at=now + timedelta(days=30),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def redeem_for_org(db: Session, *, org_id: str, user_id: str | None, promo_code: str) -> PromoOffer:
        row = PromoOfferService.get_by_code(db, promo_code)
        if row is None or not row.is_active:
            raise PromoOfferError("Invalid promo code")
        now = datetime.utcnow()
        if row.expires_at and row.expires_at < now:
            raise PromoOfferError("Promo code expired")
        if row.redemption_count >= row.max_redemptions:
            raise PromoOfferError("Promo code already used")

        org = db.get(Organisation, org_id)
        if org is None:
            raise PromoOfferError("Organisation not found")

        if PromoOfferService.is_service_credit_offer(row.offer_type):
            if row.offer_type == "survey_credits":
                org.survey_credits_balance = int(org.survey_credits_balance or 0) + int(row.survey_contacts_included or 0)
            else:
                org.interview_credits_balance = int(org.interview_credits_balance or 0) + int(row.interview_contacts_included or 0)
            db.add(org)
        else:
            plan_code = (row.plan_code or "starter").strip().lower()
            try:
                sub = BillingService.assign_plan_cash(db, org_id=org_id, plan_code=plan_code)
            except ValueError:
                sub = BillingService.assign_plan_cash(db, org_id=org_id, plan_code="starter")

            if int(row.trial_days or 0) > 0:
                sub.status = "trial"
                sub.current_period_end = now + timedelta(days=int(row.trial_days))
                sub.updated_at = now
                db.add(sub)

            UsageWalletService.bootstrap_from_promo(db, org_id=org_id, promo=row, subscription=sub)

        row.redemption_count = int(row.redemption_count or 0) + 1
        row.updated_at = now
        db.add(row)
        db.add(
            PromoRedemption(
                promo_offer_id=row.id,
                org_id=org_id,
                user_id=user_id,
                redeemed_at=now,
            )
        )
        db.commit()
        db.refresh(row)
        try:
            from app.services.sales_automation_service import SalesAutomationService

            SalesAutomationService.mark_signed_up(db, promo_offer_id=row.id)
        except Exception:
            pass
        return row
