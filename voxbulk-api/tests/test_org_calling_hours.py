from __future__ import annotations

import json
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.core.database import get_sessionmaker
from app.models.organisation import Organisation
from app.models.organisation_ai_config import OrganisationComplianceConfig
from app.utils.ofcom import OfcomWindow, is_within_calling_window, org_calling_allowed, resolve_org_call_window


@pytest.fixture()
def db():
    with get_sessionmaker()() as session:
        yield session


def _org_with_compliance(db, *, weekend_allowed: bool = False) -> str:
    org_id = str(uuid.uuid4())
    db.add(Organisation(id=org_id, name="Test Clinic"))
    db.add(
        OrganisationComplianceConfig(
            org_id=org_id,
            outbound_call_windows_json=json.dumps({"weekdays": {"start": "10:00", "end": "16:00"}}),
            weekend_allowed=weekend_allowed,
        )
    )
    db.commit()
    return org_id


def test_resolve_org_call_window_intersects_platform_floor(db):
    org_id = _org_with_compliance(db)
    noon = datetime(2026, 5, 20, 12, 0, tzinfo=ZoneInfo("Europe/London"))
    window = resolve_org_call_window(db, org_id, now=noon)
    assert window.start.hour == 10
    assert window.end.hour == 16


def test_org_calling_allowed_blocks_weekend(db):
    org_id = _org_with_compliance(db, weekend_allowed=False)
    saturday = datetime(2026, 5, 23, 12, 0, tzinfo=ZoneInfo("Europe/London"))
    allowed, reason = org_calling_allowed(db, org_id, now=saturday)
    assert allowed is False
    assert "weekend" in (reason or "").lower()


def test_is_within_calling_window():
    inside = datetime(2026, 5, 20, 10, 30, tzinfo=ZoneInfo("Europe/London"))
    outside = datetime(2026, 5, 20, 22, 30, tzinfo=ZoneInfo("Europe/London"))
    window = OfcomWindow(start=inside.time().replace(hour=9), end=inside.time().replace(hour=18))
    assert is_within_calling_window(inside, window) is True
    assert is_within_calling_window(outside, window) is False
