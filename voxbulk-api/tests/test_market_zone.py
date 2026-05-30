from app.services.market_zone import country_to_zone, normalize_zone, zone_label


def test_country_to_zone():
    assert country_to_zone("United Kingdom") == "gb"
    assert country_to_zone("UK") == "gb"
    assert country_to_zone("United States") == "us"
    assert country_to_zone("Canada") == "ca"
    assert country_to_zone("Australia") == "au"
    assert country_to_zone(None) == "gb"


def test_normalize_zone():
    assert normalize_zone("gb") == "gb"
    assert normalize_zone("uk") == "gb"
    assert normalize_zone("US") == "us"
    assert normalize_zone("invalid") is None


def test_zone_label():
    assert "United Kingdom" in zone_label("gb")
    assert "United States" in zone_label("us")
