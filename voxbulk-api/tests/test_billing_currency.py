from app.services.billing_currency import (
    EU_MEMBER_STATES,
    SUPPORTED_CURRENCIES,
    currency_for_country_code,
    currency_symbol,
    normalize_currency,
)


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
