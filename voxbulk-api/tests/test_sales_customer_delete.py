"""Sales customer delete must unlink commission / mail FKs (MySQL 1451)."""

from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.organisation import Organisation
from app.models.sales_mail import SalesMailContact
from app.models.sales_rep import SalesCommission, SalesCustomer, SalesRep
from app.models.user import User
from app.services.sales_rep_service import SalesRepService
from sqlalchemy import select


def test_delete_customer_unlinks_commission_and_mail_contact():
    suffix = uuid.uuid4().hex[:8]
    with get_sessionmaker()() as db:
        org = Organisation(name=f"Sales Delete Cust Org {suffix}")
        db.add(org)
        db.flush()
        user = User(
            email=f"rep-delete-cust-{suffix}@example.com",
            password_hash=hash_password("pass1234"),
            is_active=True,
        )
        db.add(user)
        db.flush()
        rep = SalesRep(
            user_id=user.id,
            name="Rep Delete Test",
            promo_code=f"DEL{suffix.upper()}",
            mobile="+447700900111",
        )
        db.add(rep)
        db.flush()
        cust = SalesCustomer(
            sales_rep_id=rep.id,
            full_name="Lead To Delete",
            email=f"lead-delete-{suffix}@example.com",
            mobile="+447700900222",
            status="lead",
        )
        db.add(cust)
        db.flush()
        db.add(
            SalesCommission(
                sales_rep_id=rep.id,
                sales_customer_id=cust.id,
                org_id=org.id,
                amount_minor=100,
                currency="GBP",
                kind="percent_invoice",
                status="pending",
            )
        )
        db.add(
            SalesMailContact(
                sales_rep_id=rep.id,
                sales_customer_id=cust.id,
                email=f"lead-delete-{suffix}@example.com",
                name="Lead To Delete",
            )
        )
        db.commit()
        cust_id = cust.id
        rep_id = rep.id

        SalesRepService.delete_customer(db, rep_id=rep_id, customer_id=cust_id)

        assert db.get(SalesCustomer, cust_id) is None
        commissions = list(
            db.execute(select(SalesCommission).where(SalesCommission.sales_rep_id == rep_id)).scalars().all()
        )
        assert len(commissions) == 1
        assert commissions[0].sales_customer_id is None
        contacts = list(
            db.execute(select(SalesMailContact).where(SalesMailContact.sales_rep_id == rep_id)).scalars().all()
        )
        assert len(contacts) == 1
        assert contacts[0].sales_customer_id is None
