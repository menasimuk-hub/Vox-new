"""Public Smart Card shell/reveal + rate limit + marketing consent proof."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.database import get_sessionmaker
from app.models.organisation import Organisation
from app.models.smart_card import SmartCardCompany, SmartCardLead, SmartCardRepresentative
from app.services.smart_card_public_rate_limit import _memory_buckets, check_smart_card_rate_limit


@pytest.fixture()
def db():
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def test_check_smart_card_rate_limit_unit():
    _memory_buckets.clear()
    scope = f"unit-{uuid.uuid4().hex[:8]}"
    for _ in range(2):
        d = check_smart_card_rate_limit(scope=scope, identity="ip-1", limit=2, window_sec=60)
        assert d.allowed
    d = check_smart_card_rate_limit(scope=scope, identity="ip-1", limit=2, window_sec=60)
    assert not d.allowed
    assert d.retry_after_sec >= 1


def test_get_card_shell_omits_contact_pii(db):
    from app.routers.public_smart_card import _build_card_payload

    org = Organisation(name=f"Shell Org {uuid.uuid4().hex[:6]}")
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
        email="dana@example.com",
        mobile="+447700900123",
        qr_token=f"shell-{uuid.uuid4().hex[:12]}",
        status="active",
        social_links_json=json.dumps({"linkedin": "https://linkedin.com/in/dana"}),
    )
    db.add_all([company, rep])
    db.commit()

    shell = _build_card_payload(db, token=rep.qr_token, rep=rep, full=False)
    assert shell.get("theme_id") == "smartcard1"
    assert shell["representative"]["name"] == "Dana"
    assert "email" not in shell["representative"]
    assert "mobile" not in shell["representative"]
    assert "social_links" not in shell["representative"]
    assert "whatsapp_url" not in shell

    full = _build_card_payload(db, token=rep.qr_token, rep=rep, full=True)
    assert full["representative"]["email"] == "dana@example.com"
    assert full["representative"]["mobile"] == "+447700900123"
    assert full["representative"]["social_links"]["linkedin"]


def test_reveal_rejects_missing_origin():
    from app.routers.public_smart_card import _origin_allowed

    req = MagicMock()
    req.headers = {}
    assert _origin_allowed(req) is False

    req2 = MagicMock()
    req2.headers = {"origin": "https://voxbulk.com"}
    assert _origin_allowed(req2) is True


def test_marketing_consent_csv_columns(db):
    from sqlalchemy import text

    from app.services.smart_card import results_service as rs
    from app.services.smart_card.results_service import SmartCardResultsService

    # Local sqlite test DBs may predate this migration — add columns if missing.
    cols = {c["name"] for c in db.execute(text("PRAGMA table_info(smart_card_leads)")).mappings()}
    if "marketing_consent" not in cols:
        db.execute(text("ALTER TABLE smart_card_leads ADD COLUMN marketing_consent VARCHAR(16)"))
    if "marketing_consent_proof_json" not in cols:
        db.execute(text("ALTER TABLE smart_card_leads ADD COLUMN marketing_consent_proof_json TEXT"))
    db.commit()

    org = Organisation(name=f"Consent Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Rep",
        qr_token=f"mc-{uuid.uuid4().hex[:12]}",
        status="active",
    )
    db.add(rep)
    db.flush()
    lead = SmartCardLead(
        org_id=org.id,
        representative_id=rep.id,
        name="Visitor",
        visitor_email="v@example.com",
        marketing_consent="yes",
        marketing_consent_proof_json=json.dumps(
            {
                "answered_at": "2026-08-09T12:00:00Z",
                "channel": "web",
                "prompt_snapshot": "Can we contact you?",
                "answer_text": "Yes",
                "session_id": "sess-1",
            }
        ),
        channel="web",
    )
    db.add(lead)
    db.commit()

    orig = rs.SmartCardResultsService._rep_scope
    rs.SmartCardResultsService._rep_scope = staticmethod(lambda *a, **k: None)
    try:
        csv_text = SmartCardResultsService.export_marketing_consent_csv(
            db, org_id=org.id, user_id="any"
        )
    finally:
        rs.SmartCardResultsService._rep_scope = orig

    assert "marketing_consent" in csv_text.splitlines()[0]
    assert "prompt_snapshot" in csv_text
    assert "yes" in csv_text
    assert "Can we contact you?" in csv_text


def test_enforce_rate_limit_raises():
    from app.routers import public_smart_card as mod

    _memory_buckets.clear()
    scope = f"enf-{uuid.uuid4().hex[:8]}"
    mod._enforce_sc_rate_limit(scope=scope, identity="x", limit=1, window_sec=60)
    with pytest.raises(HTTPException) as ei:
        mod._enforce_sc_rate_limit(scope=scope, identity="x", limit=1, window_sec=60)
    assert ei.value.status_code == 429
