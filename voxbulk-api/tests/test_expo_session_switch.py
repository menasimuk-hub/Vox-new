"""Expo session isolation — new booth QR supersedes prior active session for the same phone."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
from app.models.expo import ExpoBooth, ExpoExhibition, ExpoSession
from app.models.organisation import Organisation
from app.services.expo.session_flow_service import ExpoSessionFlowService


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _booth(db, *, org_id: str, token: str, name: str) -> ExpoBooth:
    now = datetime.utcnow()
    exhibition = ExpoExhibition(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name=f"Show {name}",
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(exhibition)
    db.flush()
    booth = ExpoBooth(
        id=str(uuid.uuid4()),
        org_id=org_id,
        exhibition_id=exhibition.id,
        name=name,
        company_display_name=name,
        booth_code=name[:8],
        qr_token=token,
        status="active",
        scan_count=0,
        question_config_json=json.dumps(
            {
                "steps": [
                    {"key": "interest", "prompt": f"What are you looking for at {name}?"},
                ],
                "thank_you_message": "Thanks!",
            }
        ),
        created_at=now,
        updated_at=now,
    )
    db.add(booth)
    db.flush()
    return booth


def test_new_booth_scan_supersedes_active_session_for_same_phone():
    phone = f"+4477009{uuid.uuid4().hex[:6]}"
    with get_sessionmaker()() as db:
        org = Organisation(name="Expo Multi", contact_email=f"expo-{uuid.uuid4().hex[:8]}@example.com")
        db.add(org)
        db.flush()
        booth_a = _booth(db, org_id=org.id, token=f"storea-h01-{uuid.uuid4().hex[:6]}", name="Store A")
        booth_b = _booth(db, org_id=org.id, token=f"storeb-h02-{uuid.uuid4().hex[:6]}", name="Store B")
        db.commit()

        first = ExpoSessionFlowService.start_session(
            db, booth=booth_a, channel="whatsapp", visitor_phone=phone
        )
        assert first["done"] is False
        session_a = db.get(ExpoSession, first["session_id"])
        assert session_a is not None
        assert session_a.status == "active"
        assert session_a.booth_id == booth_a.id

        active = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
        assert active is not None
        assert active.id == session_a.id

        second = ExpoSessionFlowService.start_session(
            db, booth=booth_b, channel="whatsapp", visitor_phone=phone
        )
        assert second.get("superseded_sessions") == 1
        session_a = db.get(ExpoSession, first["session_id"])
        session_b = db.get(ExpoSession, second["session_id"])
        assert session_a is not None and session_a.status == "superseded"
        assert session_b is not None and session_b.status == "active"
        assert session_b.booth_id == booth_b.id

        active = ExpoSessionFlowService.find_active_session(db, visitor_phone=phone)
        assert active is not None
        assert active.id == session_b.id
        assert active.booth_id == booth_b.id

        # Only one active for this phone
        actives = db.execute(
            select(ExpoSession).where(
                ExpoSession.visitor_phone == phone,
                ExpoSession.status == "active",
            )
        ).scalars().all()
        assert len(actives) == 1
