"""Hard-delete must purge Expo signup trial + Smart Card FK children."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.expo_signup_trial import ExpoCompanyDomainClaim, ExpoSignupEntitlement
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.smart_card import SmartCardCompany
from app.models.user import User
from app.services.user_hard_delete_service import HARD_DELETE_CONFIRM, hard_delete_user
from sqlalchemy import select


def test_hard_delete_purges_expo_trial_and_smart_card():
    with get_sessionmaker()() as db:
        org = Organisation(name="Hard Delete SC Expo Org")
        db.add(org)
        db.flush()
        user = User(
            email="hard-delete-sc-expo@example.com",
            password_hash=hash_password("pass1234"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        db.add(
            ExpoCompanyDomainClaim(
                email_domain="hard-delete-sc-expo.example",
                org_id=org.id,
                user_id=user.id,
                claimed_email="hard-delete-sc-expo@example.com",
            )
        )
        db.add(
            ExpoSignupEntitlement(
                org_id=org.id,
                duration_days=3,
                remaining=1,
                source_domain="hard-delete-sc-expo.example",
            )
        )
        db.add(SmartCardCompany(org_id=org.id, name="Test Co"))
        db.commit()
        user_id = user.id
        org_id = org.id

        report = hard_delete_user(db, user_id, delete_solo_orgs=True, delete_service_orders=True)
        db.commit()

        assert report["status"] == "deleted"
        assert db.get(User, user_id) is None
        assert db.get(Organisation, org_id) is None
        assert (
            db.execute(
                select(ExpoCompanyDomainClaim).where(ExpoCompanyDomainClaim.org_id == org_id)
            ).scalar_one_or_none()
            is None
        )
        assert (
            db.execute(
                select(ExpoSignupEntitlement).where(ExpoSignupEntitlement.org_id == org_id)
            ).scalar_one_or_none()
            is None
        )
        assert (
            db.execute(select(SmartCardCompany).where(SmartCardCompany.org_id == org_id)).scalar_one_or_none()
            is None
        )
        assert HARD_DELETE_CONFIRM == "HARD_DELETE"
