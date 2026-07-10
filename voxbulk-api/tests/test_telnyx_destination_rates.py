from __future__ import annotations

import pytest

from app.services.telnyx_destination_rate_service import (
    RATE_SCALE,
    TelnyxDestinationRateService,
    _parse_money_to_minor,
    serialize_rate,
)


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_sessionmaker()() as session:
        yield session


def test_parse_money_to_minor():
    assert _parse_money_to_minor("0.005") == 50
    assert _parse_money_to_minor("$0.35") == 3500
    assert _parse_money_to_minor("") is None
    assert _parse_money_to_minor("n/a") is None


def test_serialize_rate_display(db):
    from app.models.telnyx_destination_rate import TelnyxDestinationRate

    row = TelnyxDestinationRate(
        country_iso="CN",
        country_name="China",
        dial_code="86",
        voice_outbound_per_min_minor=350,
        voice_inbound_per_min_minor=80,
        sms_outbound_per_msg_minor=120,
        sms_inbound_per_msg_minor=0,
        currency="USD",
        source="seed",
        notes="test",
    )
    db.add(row)
    db.commit()

    found = TelnyxDestinationRateService.get(db, "cn")
    assert found is not None
    data = serialize_rate(found)
    assert data["country_iso"] == "CN"
    assert data["is_placeholder"] is True
    assert data["voice_outbound"]["minor"] == 350
    assert abs(data["voice_outbound"]["amount"] - 0.035) < 1e-9
    assert RATE_SCALE == 10_000


def test_search_by_name_and_iso(db):
    from app.models.telnyx_destination_rate import TelnyxDestinationRate

    db.add(
        TelnyxDestinationRate(
            country_iso="EG",
            country_name="Egypt",
            dial_code="20",
            voice_outbound_per_min_minor=1800,
            currency="USD",
            source="seed",
        )
    )
    db.commit()

    by_iso = TelnyxDestinationRateService.search(db, "EG")
    assert any(r.country_iso == "EG" for r in by_iso)

    by_name = TelnyxDestinationRateService.search(db, "egypt")
    assert any(r.country_iso == "EG" for r in by_name)


def test_import_csv(db):
    csv_text = """country_iso,country_name,dial_code,voice_outbound,voice_inbound,sms_outbound,sms_inbound,currency,notes
CN,China,86,0.04,0.01,0.02,0,USD,from sheet
XX,Invalid,,,,
"""
    result = TelnyxDestinationRateService.import_csv(db, csv_text)
    assert result["ok"] is True
    assert result["created"] >= 1

    row = TelnyxDestinationRateService.get(db, "CN")
    assert row is not None
    assert row.source == "csv_import"
    assert row.voice_outbound_per_min_minor == 400
    data = serialize_rate(row)
    assert data["is_placeholder"] is False


def test_map_for_isos(db):
    from app.models.telnyx_destination_rate import TelnyxDestinationRate

    db.add(
        TelnyxDestinationRate(
            country_iso="GB",
            country_name="United Kingdom",
            dial_code="44",
            voice_outbound_per_min_minor=50,
            currency="USD",
            source="csv_import",
        )
    )
    db.commit()
    mapped = TelnyxDestinationRateService.map_for_isos(db, ["GB", "ZZ", "gb"])
    assert "GB" in mapped
    assert mapped["GB"]["voice_outbound"]["minor"] == 50
