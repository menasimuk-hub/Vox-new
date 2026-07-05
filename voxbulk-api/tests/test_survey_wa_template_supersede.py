"""Tests for automatic WA template clone family consolidation."""

from __future__ import annotations

import json
import uuid

import pytest

from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_wa_template_supersede_service import consolidate_active_clone_families


@pytest.fixture()
def db():
    from app.core.database import Base, get_engine, get_sessionmaker
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _row(db, *, name: str, status: str, parent_id: int | None, active: bool) -> TelnyxWhatsappTemplate:
    rid = str(uuid.uuid4())
    row = TelnyxWhatsappTemplate(
        telnyx_record_id=rid,
        template_id=rid,
        name=name,
        language="en_US",
        category="UTILITY",
        body_preview="Hi",
        status=status,
        active_for_survey=active,
        components_json=json.dumps([{"type": "BODY", "text": "Hi"}]),
        parent_template_id=parent_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_consolidate_deactivates_pending_sibling_when_approved_exists(db):
    parent = _row(db, name="parent", status="APPROVED", parent_id=None, active=False)
    pending = _row(db, name="clone_utu", status="PENDING", parent_id=int(parent.id), active=True)
    approved = _row(db, name="clone_utu_2", status="APPROVED", parent_id=int(parent.id), active=True)

    result = consolidate_active_clone_families(db)
    db.refresh(pending)
    db.refresh(approved)

    assert int(pending.id) in result["deactivated_ids"]
    assert pending.active_for_survey is False
    assert approved.active_for_survey is True
