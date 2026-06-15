"""GB + GBP VAT-inclusive invoice extraction tests."""

from __future__ import annotations

import uuid

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.country_vat_service import CountryVatService
from app.services.invoice_service import InvoiceService


def _seed_org(*, country: str = "GB") -> tuple[str, str]:
    email = f"vat-{uuid.uuid4().hex[:8]}@example.com"
    with get_sessionmaker()() as db:
        org = Organisation(name="VAT Org", wallet_balance_pence=0, contact_email=email, country=country)
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        return org.id, email


def test_gb_gbp_vat_split_from_inclusive_gross():
    with get_sessionmaker()() as db:
        org_id, email = _seed_org(country="GB")
        line_items = [
            {
                "description": "Interview launch",
                "quantity": 1,
                "unit_pence": 12400,
                "total_pence": 12400,
            }
        ]
        net, tax, total, rate, inclusive = InvoiceService.compute_invoice_amounts(
            db,
            country_code="GB",
            line_items=line_items,
            amount_pence=12400,
            currency="GBP",
        )
        assert inclusive is True
        assert rate == 20.0
        assert total == 12400
        assert net + tax == total
        assert tax == 2067 or tax == 2066  # rounding


def test_non_gb_customer_no_vat_split():
    with get_sessionmaker()() as db:
        org_id, email = _seed_org(country="AE")
        net, tax, total, rate, inclusive = InvoiceService.compute_invoice_amounts(
            db,
            country_code="AE",
            line_items=[{"description": "Service", "quantity": 1, "unit_pence": 10000, "total_pence": 10000}],
            amount_pence=10000,
            currency="AED",
        )
        assert inclusive is False
        assert rate == 0.0
        assert tax == 0
        assert total == 10000


def test_gb_customer_non_gbp_currency_no_vat_split():
    with get_sessionmaker()() as db:
        net, tax, total, rate, inclusive = InvoiceService.compute_invoice_amounts(
            db,
            country_code="GB",
            line_items=[{"description": "Service", "quantity": 1, "unit_pence": 10000, "total_pence": 10000}],
            amount_pence=10000,
            currency="USD",
        )
        assert inclusive is False
        assert rate == 0.0
        assert tax == 0


def test_is_gb_gbp_customer_helper():
    assert CountryVatService.is_gb_gbp_customer("GB", "GBP") is True
    assert CountryVatService.is_gb_gbp_customer("gb", "gbp") is True
    assert CountryVatService.is_gb_gbp_customer("GB", "USD") is False
    assert CountryVatService.is_gb_gbp_customer("AE", "GBP") is False
