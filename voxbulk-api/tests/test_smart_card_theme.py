"""Smart Card theme_id in brand_defaults and public meta."""

from __future__ import annotations

import json
import uuid

import pytest

from app.core.database import get_sessionmaker
from app.models.organisation import Organisation
from app.models.smart_card import SmartCardCompany, SmartCardRepresentative
from app.services.smart_card.company_service import (
    SmartCardCompanyService,
    normalize_brand_defaults,
    normalize_smart_card_theme_id,
)


@pytest.fixture()
def db():
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def test_normalize_theme_id():
    assert normalize_smart_card_theme_id("smartcard2") == "smartcard2"
    assert normalize_smart_card_theme_id("nope") == "smartcard"
    assert normalize_brand_defaults({"theme_id": "smartcard4", "address": "London"})["theme_id"] == "smartcard4"


def test_company_update_persists_theme_id(db):
    org = Organisation(name=f"Theme Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    SmartCardCompanyService.update(db, org.id, {"name": "Acme", "theme_id": "smartcard3"})
    db.commit()
    company = SmartCardCompanyService.get_or_create(db, org.id)
    ser = SmartCardCompanyService.serialize(company)
    assert ser["theme_id"] == "smartcard3"
    assert ser["brand_defaults"]["theme_id"] == "smartcard3"


def test_public_meta_includes_theme_id(db):
    from app.routers.public_smart_card import get_card

    org = Organisation(name=f"Pub Theme {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    company = SmartCardCompany(
        org_id=org.id,
        name="Acme",
        brand_defaults_json=json.dumps({"theme_id": "smartcard1"}),
    )
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Dana",
        qr_token=f"theme-{uuid.uuid4().hex[:12]}",
        status="active",
    )
    db.add_all([company, rep])
    db.commit()

    meta = get_card(rep.qr_token, db)
    assert meta.get("theme_id") == "smartcard1"
