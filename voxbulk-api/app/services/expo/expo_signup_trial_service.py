"""Silent Expo signup trial: company email → one free 3-day booth activation per domain."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.expo import ExpoBooth, ExpoPackage
from app.models.expo_signup_trial import ExpoCompanyDomainClaim, ExpoSignupEntitlement
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.services.expo.company_email import extract_email_domain, is_company_email
from app.services.org_enabled_services import (
    org_service_maps,
    parse_enabled_services,
    serialize_allowed_services,
    serialize_enabled_services,
)

logger = logging.getLogger(__name__)

TRIAL_DURATION_DAYS = 3
TRIAL_PACKAGE_CODE = "expo_day3"
TRIAL_PACKAGE_TIER = "day3"
PAYMENT_PROVIDER = "signup_trial"


class ExpoSignupTrialService:
    @staticmethod
    def maybe_grant(
        db: Session,
        *,
        org: Organisation,
        user_email: str,
        user_id: str | None = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        """Grant silent Expo trial if company email and domain not yet claimed.

        Does not raise on ineligible emails — returns granted=False.
        """
        email = str(user_email or "").strip().lower()
        if not email or not is_company_email(email):
            return {"granted": False, "reason": "free_or_invalid_email"}

        domain = extract_email_domain(email)
        if not domain:
            return {"granted": False, "reason": "invalid_domain"}

        existing_claim = db.execute(
            select(ExpoCompanyDomainClaim).where(ExpoCompanyDomainClaim.email_domain == domain)
        ).scalar_one_or_none()
        if existing_claim is not None:
            return {"granted": False, "reason": "domain_already_claimed", "domain": domain}

        existing_ent = db.execute(
            select(ExpoSignupEntitlement).where(ExpoSignupEntitlement.org_id == org.id)
        ).scalar_one_or_none()
        if existing_ent is not None:
            return {"granted": False, "reason": "org_already_has_entitlement"}

        now = datetime.utcnow()
        # Resolve service maps outside the savepoint — ensure_row/refresh must not run
        # inside begin_nested() or SQLAlchemy closes the nested transaction.
        allowed, enabled, _ = org_service_maps(org, db)
        allowed = dict(allowed)
        enabled = dict(enabled)
        allowed["expo"] = True
        enabled["expo"] = True
        allowed_json = serialize_allowed_services(allowed)
        enabled_json = serialize_enabled_services(
            {**parse_enabled_services(org.enabled_services_json), **enabled}
        )

        try:
            with db.begin_nested():
                claim = ExpoCompanyDomainClaim(
                    email_domain=domain,
                    org_id=org.id,
                    user_id=user_id,
                    claimed_email=email,
                    granted_at=now,
                )
                entitlement = ExpoSignupEntitlement(
                    org_id=org.id,
                    duration_days=TRIAL_DURATION_DAYS,
                    remaining=1,
                    source_domain=domain,
                    granted_at=now,
                )
                org.allowed_services_json = allowed_json
                org.enabled_services_json = enabled_json
                db.add(org)
                db.add(claim)
                db.add(entitlement)
                db.flush()
        except IntegrityError:
            logger.info("expo_signup_trial domain race domain=%s org=%s", domain, org.id)
            return {"granted": False, "reason": "domain_already_claimed", "domain": domain}

        if commit:
            db.commit()

        logger.info(
            "expo_signup_trial_granted org_id=%s domain=%s email=%s",
            org.id,
            domain,
            email,
        )
        return {
            "granted": True,
            "domain": domain,
            "duration_days": TRIAL_DURATION_DAYS,
            "remaining": 1,
        }

    @staticmethod
    def _enable_expo_for_org(db: Session, org: Organisation) -> None:
        allowed, enabled, _ = org_service_maps(org, db)
        allowed = dict(allowed)
        enabled = dict(enabled)
        allowed["expo"] = True
        enabled["expo"] = True
        org.allowed_services_json = serialize_allowed_services(allowed)
        org.enabled_services_json = serialize_enabled_services(
            {**parse_enabled_services(org.enabled_services_json), **enabled}
        )
        db.add(org)

    @staticmethod
    def get_entitlement(db: Session, *, org_id: str) -> ExpoSignupEntitlement | None:
        return db.execute(
            select(ExpoSignupEntitlement).where(ExpoSignupEntitlement.org_id == org_id)
        ).scalar_one_or_none()

    @staticmethod
    def package_qualifies_for_trial(db: Session, booth: ExpoBooth) -> bool:
        if not booth.package_id:
            return False
        pkg = db.get(ExpoPackage, booth.package_id)
        if pkg is None:
            return False
        if int(getattr(pkg, "duration_days", 0) or 0) == TRIAL_DURATION_DAYS:
            return True
        if str(getattr(pkg, "tier", "") or "").strip().lower() == TRIAL_PACKAGE_TIER:
            return True
        if pkg.plan_id:
            plan = db.get(Plan, pkg.plan_id)
            if plan is not None and str(plan.code or "").strip().lower() == TRIAL_PACKAGE_CODE:
                return True
        return False

    @staticmethod
    def has_usable_trial(db: Session, *, org_id: str, booth: ExpoBooth) -> bool:
        ent = ExpoSignupTrialService.get_entitlement(db, org_id=org_id)
        if ent is None or int(ent.remaining or 0) <= 0:
            return False
        return ExpoSignupTrialService.package_qualifies_for_trial(db, booth)

    @staticmethod
    def consume_for_booth(
        db: Session,
        *,
        org_id: str,
        booth: ExpoBooth,
        commit: bool = False,
    ) -> bool:
        """Decrement entitlement and mark domain claim consumed. Returns True if consumed."""
        if not ExpoSignupTrialService.package_qualifies_for_trial(db, booth):
            return False
        ent = ExpoSignupTrialService.get_entitlement(db, org_id=org_id)
        if ent is None or int(ent.remaining or 0) <= 0:
            return False

        now = datetime.utcnow()
        ent.remaining = max(0, int(ent.remaining or 0) - 1)
        ent.consumed_at = now
        ent.consumed_booth_id = booth.id
        db.add(ent)

        claim = db.execute(
            select(ExpoCompanyDomainClaim).where(ExpoCompanyDomainClaim.org_id == org_id)
        ).scalar_one_or_none()
        if claim is not None:
            claim.entitlement_consumed_at = now
            claim.consumed_booth_id = booth.id
            db.add(claim)

        if commit:
            db.commit()
        else:
            db.flush()
        logger.info(
            "expo_signup_trial_consumed org_id=%s booth_id=%s remaining=%s",
            org_id,
            booth.id,
            ent.remaining,
        )
        return True
