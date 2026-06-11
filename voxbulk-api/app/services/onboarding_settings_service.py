from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.onboarding_request import OnboardingRequest
from app.models.onboarding_setting import OnboardingSetting
from app.models.user import User


class OnboardingSettingsService:
    @staticmethod
    def get_settings(db: Session) -> OnboardingSetting:
        row = db.get(OnboardingSetting, "default")
        if row is None:
            row = OnboardingSetting(
                id="default",
                auto_approve_promo_signups=True,
                updated_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def settings_out(row: OnboardingSetting) -> dict[str, Any]:
        return {
            "auto_approve_promo_signups": bool(row.auto_approve_promo_signups),
            "updated_at": row.updated_at,
        }

    @staticmethod
    def approve_request(
        db: Session,
        request: OnboardingRequest,
        *,
        user: User | None = None,
        note: str | None = None,
    ) -> None:
        if request.status != "pending":
            raise ValueError("Request not pending")

        if user is None:
            user = db.get(User, request.user_id)
        if user is None:
            raise ValueError("User not found")

        user.is_active = True
        request.status = "approved"
        request.decided_at = datetime.utcnow()
        request.decision_note = note or None
        db.add_all([user, request])
        db.commit()

        try:
            from app.models.organisation import Organisation
            from app.services.product_email_triggers import ProductEmailTriggers

            org = db.get(Organisation, request.org_id)
            ProductEmailTriggers.send_new_user_welcome_safe(
                db,
                to_email=str(user.email),
                organisation_name=str(org.name if org else ""),
            )
        except Exception:
            pass

        try:
            if request.promo_code:
                from app.services.promo_offer_service import PromoOfferService

                PromoOfferService.redeem_for_org(
                    db,
                    org_id=request.org_id,
                    user_id=request.user_id,
                    promo_code=request.promo_code,
                )
            else:
                from app.services.gocardless_service import BillingService
                from app.services.usage_wallet_service import UsageWalletService

                sub = BillingService.get_subscription(db, request.org_id)
                if sub is not None:
                    UsageWalletService.bootstrap_from_plan(db, org_id=request.org_id, subscription=sub)
        except Exception:
            pass
