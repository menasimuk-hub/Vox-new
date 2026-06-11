from app.core.database import get_sessionmaker
from app.models.organisation import Organisation
from app.services.billing_currency import (
    EU_MEMBER_STATES,
    SUPPORTED_CURRENCIES,
    billing_currency_is_locked,
    currency_for_country_code,
    currency_symbol,
    normalize_currency,
    resolve_org_currency,
)
from app.services.recovery_service import OrganisationService


def test_supported_currencies_include_eur():
    assert "EUR" in SUPPORTED_CURRENCIES


def test_eu_countries_map_to_eur():
    assert currency_for_country_code("DE") == "EUR"
    assert currency_for_country_code("IE") == "EUR"
    assert len(EU_MEMBER_STATES) == 27


def test_primary_markets():
    assert currency_for_country_code("GB") == "GBP"
    assert currency_for_country_code("US") == "USD"
    assert currency_for_country_code("CA") == "CAD"
    assert currency_for_country_code("AU") == "AUD"


def test_rest_of_world_defaults_usd():
    assert currency_for_country_code("AE") == "USD"
    assert currency_for_country_code("IN") == "USD"
    assert currency_for_country_code("JP") == "USD"
    assert currency_for_country_code("ZZ") == "USD"


def test_normalize_currency_unknown_defaults_usd():
    assert normalize_currency("CHF") == "USD"
    assert normalize_currency("EUR") == "EUR"


def test_currency_symbol_eur():
    assert currency_symbol("EUR") == "€"


def test_profile_country_updates_currency_when_unlocked():
    with get_sessionmaker()() as db:
        org = Organisation(name="Currency Test", country="United Kingdom")
        db.add(org)
        db.commit()
        db.refresh(org)
        assert resolve_org_currency(db, org) == "GBP"
        OrganisationService.update_org_profile(db, org.id, country="Germany")
        db.refresh(org)
        assert org.billing_currency == "EUR"
        assert resolve_org_currency(db, org) == "EUR"


def test_profile_country_updates_to_cad_when_unlocked():
    with get_sessionmaker()() as db:
        org = Organisation(name="Canada Test", country="United Kingdom")
        db.add(org)
        db.commit()
        OrganisationService.update_org_profile(db, org.id, country="Canada")
        db.refresh(org)
        assert org.billing_currency == "CAD"


def test_profile_country_does_not_change_currency_when_locked():
    with get_sessionmaker()() as db:
        from app.models.wallet_transaction import WalletTransaction  # noqa: PLC0415

        org = Organisation(name="Locked Test", country="United Kingdom", billing_currency="GBP")
        db.add(org)
        db.flush()
        db.add(
            WalletTransaction(
                org_id=org.id,
                direction="credit",
                amount_minor=100,
                balance_after_minor=100,
                kind="topup",
                currency="GBP",
                description="seed",
            )
        )
        db.commit()
        assert billing_currency_is_locked(db, org)
        OrganisationService.update_org_profile(db, org.id, country="Germany")
        db.refresh(org)
        assert org.billing_currency == "GBP"
