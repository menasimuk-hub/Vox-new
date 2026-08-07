"""Hard-delete must purge Expo/Smart Card and unlink salesman mail contacts."""

from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.expo_signup_trial import ExpoCompanyDomainClaim, ExpoSignupEntitlement
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.sales_mail import SalesMailContact
from app.models.sales_rep import SalesCustomer, SalesRep
from app.models.smart_card import SmartCardCompany
from app.models.user import User
from app.services.user_hard_delete_service import HARD_DELETE_CONFIRM, hard_delete_user
from sqlalchemy import select


def test_hard_delete_purges_expo_trial_smart_card_and_mail_fk():
    suffix = uuid.uuid4().hex[:8]
    email = f"hard-delete-sc-expo-{suffix}@example.com"
    with get_sessionmaker()() as db:
        org = Organisation(name=f"Hard Delete SC Expo Org {suffix}")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass1234"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
        db.add(
            ExpoCompanyDomainClaim(
                email_domain=f"hard-delete-sc-expo-{suffix}.example",
                org_id=org.id,
                user_id=user.id,
                claimed_email=email,
            )
        )
        db.add(
            ExpoSignupEntitlement(
                org_id=org.id,
                duration_days=3,
                remaining=1,
                source_domain=f"hard-delete-sc-expo-{suffix}.example",
            )
        )
        db.add(SmartCardCompany(org_id=org.id, name="Test Co"))

        rep_user = User(
            email=f"hard-delete-sc-expo-rep-{suffix}@example.com",
            password_hash=hash_password("pass1234"),
            is_active=True,
        )
        db.add(rep_user)
        db.flush()
        rep = SalesRep(user_id=rep_user.id, name="Rep", promo_code=f"HD{suffix.upper()}")
        db.add(rep)
        db.flush()
        cust = SalesCustomer(sales_rep_id=rep.id, full_name="Lead", email=email, status="lead")
        db.add(cust)
        db.flush()
        db.add(
            SalesMailContact(
                sales_rep_id=rep.id,
                sales_customer_id=cust.id,
                email=email,
                name="Lead",
            )
        )
        db.commit()
        user_id = user.id
        org_id = org.id
        cust_id = cust.id

        report = hard_delete_user(db, user_id, delete_solo_orgs=True, delete_service_orders=True)
        db.commit()

        assert report["status"] == "deleted"
        assert db.get(User, user_id) is None
        assert db.get(Organisation, org_id) is None
        assert db.get(SalesCustomer, cust_id) is None
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
        contact = db.execute(select(SalesMailContact).where(SalesMailContact.email == email)).scalar_one_or_none()
        assert contact is not None
        assert contact.sales_customer_id is None
        assert HARD_DELETE_CONFIRM == "HARD_DELETE"
