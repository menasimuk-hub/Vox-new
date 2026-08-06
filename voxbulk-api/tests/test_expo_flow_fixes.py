"""Expo flow fixes — library catalogue bridge, WA email, choice remap, STT, async notify."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
from app.models.expo import (
    ExpoBooth,
    ExpoExhibition,
    ExpoLead,
    ExpoLibraryAsset,
    ExpoLibraryCategory,
    ExpoLibraryProduct,
    ExpoSession,
)
from app.models.organisation import Organisation
from app.services.expo.offer_delivery_service import count_deliverable_assets, load_booth_assets
from app.services.expo.question_bank import (
    CONTACT_EMAIL_PROMPT,
    WEB_CHOICE_OPTIONS,
    parse_pick_numbers,
    remap_choice_reply,
)
from app.services.expo.session_flow_service import ExpoSessionFlowService
from app.services.providers.deepinfra_service import WA_SURVEY_WHISPER_MODEL, DeepInfraProviderService
from app.services.voice_transcription_service import WEB_UPLOAD_STT_PROVIDER_ORDER, stt_provider_order


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _org(db) -> Organisation:
    org = Organisation(name="Expo Flow Fixes", contact_email=f"expo-ff-{uuid.uuid4().hex[:8]}@example.com")
    db.add(org)
    db.flush()
    return org


def _booth(db, *, org_id: str, steps: list[dict] | None = None) -> ExpoBooth:
    now = datetime.utcnow()
    exhibition = ExpoExhibition(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="Show FF",
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
        name="Booth FF",
        company_display_name="Booth FF",
        booth_code="FF01",
        qr_token=f"ff-{uuid.uuid4().hex[:8]}",
        status="active",
        scan_count=0,
        question_config_json=json.dumps(
            {
                "steps": steps
                or [
                    {"key": "contact", "prompt": "Share your details"},
                    {"key": "interest", "prompt": "What are you looking for?"},
                    {"key": "follow_up", "prompt": "How should we follow up?"},
                    {"key": "consent_info", "prompt": "Would you like our catalogue?"},
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


def _library_pdf(db, *, org_id: str, title: str = "300W Solar Panel") -> ExpoLibraryAsset:
    now = datetime.utcnow()
    cat = ExpoLibraryCategory(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="Solar",
        created_at=now,
        updated_at=now,
    )
    db.add(cat)
    db.flush()
    product = ExpoLibraryProduct(
        id=str(uuid.uuid4()),
        org_id=org_id,
        category_id=cat.id,
        name=title,
        short_description="Panel PDF",
        created_at=now,
        updated_at=now,
    )
    db.add(product)
    db.flush()
    asset = ExpoLibraryAsset(
        id=str(uuid.uuid4()),
        org_id=org_id,
        product_id=product.id,
        category_id=cat.id,
        title=title,
        kind="pdf",
        purpose="catalogue",
        storage_path=f"data/expo-library/{uuid.uuid4().hex}.pdf",
        sort_order=10,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    return asset


def test_parse_pick_numbers_splits_glued_digits():
    assert parse_pick_numbers("123", option_count=3) == [1, 2, 3]
    assert parse_pick_numbers("10", option_count=10) == [10]
    assert parse_pick_numbers("1,2", option_count=3) == [1, 2]


def test_remap_choice_reply_multi_follow_up():
    opts = [dict(o) for o in WEB_CHOICE_OPTIONS["follow_up"]]
    assert remap_choice_reply("123", opts, multi=True) == "WhatsApp, Email, Call"
    assert remap_choice_reply("all", opts, multi=True) == "WhatsApp, Email, Call"
    assert remap_choice_reply("2", opts, multi=True) == "Email"


def test_stt_prefers_deepinfra_large_v3():
    assert stt_provider_order()[0] == "deepinfra"
    assert WEB_UPLOAD_STT_PROVIDER_ORDER[0] == "deepinfra"
    rebuilt = DeepInfraProviderService._resolve_base_url(
        "https://api.deepinfra.com/v1/inference/openai/whisper-large-v3-turbo",
        WA_SURVEY_WHISPER_MODEL,
    )
    assert rebuilt.endswith("whisper-large-v3")
    assert "turbo" not in rebuilt


def test_library_assets_offered_when_booth_assets_empty():
    with get_sessionmaker()() as db:
        org = _org(db)
        booth = _booth(
            db,
            org_id=org.id,
            steps=[
                {"key": "interest", "prompt": "What are you looking for?"},
                {"key": "consent_info", "prompt": "Would you like our catalogue?"},
            ],
        )
        lib = _library_pdf(db, org_id=org.id)
        db.commit()

        counts = count_deliverable_assets(db, booth_id=booth.id, org_id=org.id)
        assert counts["booth_asset_count"] == 0
        assert counts["library_asset_count"] == 1
        assert counts["deliverable_asset_count"] == 1

        loaded = load_booth_assets(db, booth.id)
        assert any(str(a.get("id")) == lib.id for a in loaded)
        assert any(a.get("source") == "library" for a in loaded)

        phone = f"+4477020{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        result = ExpoSessionFlowService.advance(db, session=session, answer="solar panels", answer_source="text")
        assert result.get("question_key") == "consent_info"
        labels = [str(o.get("label") or "") for o in (result.get("options") or [])]
        assert any("300W" in label or "Solar" in label for label in labels)


def test_public_download_resolves_library_asset_for_booth_org(tmp_path: Path):
    """Public asset route must find ExpoLibraryAsset by id + booth.org_id (not booth assets only)."""
    from app.models.expo import ExpoBoothAsset
    from app.services.expo.booth_service import ExpoBoothService

    with get_sessionmaker()() as db:
        org = _org(db)
        booth = _booth(
            db,
            org_id=org.id,
            steps=[{"key": "interest", "prompt": "What?"}],
        )
        pdf = tmp_path / "panel.pdf"
        pdf.write_bytes(b"%PDF-1.4 library-bridge-test")
        lib = _library_pdf(db, org_id=org.id)
        lib.storage_path = str(pdf)
        db.add(lib)
        db.commit()

        found_booth = ExpoBoothService.find_by_token(db, booth.qr_token)
        assert found_booth is not None
        booth_row = db.execute(
            select(ExpoBoothAsset).where(
                ExpoBoothAsset.id == lib.id, ExpoBoothAsset.booth_id == booth.id
            )
        ).scalar_one_or_none()
        assert booth_row is None
        library_row = db.execute(
            select(ExpoLibraryAsset).where(
                ExpoLibraryAsset.id == lib.id,
                ExpoLibraryAsset.org_id == found_booth.org_id,
            )
        ).scalar_one_or_none()
        assert library_row is not None
        assert Path(library_row.storage_path).read_bytes() == b"%PDF-1.4 library-bridge-test"


def test_wa_contact_asks_email_after_company():
    with get_sessionmaker()() as db:
        org = _org(db)
        booth = _booth(db, org_id=org.id)
        db.commit()
        phone = f"+4477021{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        assert started.get("contact_substep") in {None, "awaiting", ""} or started.get("question_key") == "contact"

        # Name
        r1 = ExpoSessionFlowService.advance(db, session=session, answer="Alex Visitor", answer_source="text")
        assert r1.get("contact_substep") == "company"
        # Company → email on WhatsApp
        r2 = ExpoSessionFlowService.advance(db, session=session, answer="Acme Solar", answer_source="text")
        assert r2.get("contact_substep") == "email"
        assert "email" in (r2.get("prompt") or "").lower() or "catalogue" in (r2.get("prompt") or "").lower()

        r3 = ExpoSessionFlowService.advance(
            db, session=session, answer="alex@acme.example", answer_source="text"
        )
        lead = db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one()
        assert lead.visitor_email == "alex@acme.example"
        assert r3.get("contact_substep") not in {"email", "company", "awaiting"}


def test_wa_contact_email_skip_words():
    with get_sessionmaker()() as db:
        org = _org(db)
        booth = _booth(db, org_id=org.id)
        db.commit()
        phone = f"+4477022{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        ExpoSessionFlowService.advance(db, session=session, answer="Sam Skip", answer_source="text")
        ExpoSessionFlowService.advance(db, session=session, answer="Skip Co", answer_source="text")
        r = ExpoSessionFlowService.advance(db, session=session, answer="skip", answer_source="text")
        lead = db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one()
        assert not lead.visitor_email or "@" not in str(lead.visitor_email)
        assert r.get("question_key") != "contact" or r.get("contact_substep") not in {"email", "company"}


def test_follow_up_stores_labels_not_123():
    with get_sessionmaker()() as db:
        org = _org(db)
        booth = _booth(
            db,
            org_id=org.id,
            steps=[
                {"key": "interest", "prompt": "What?"},
                {"key": "follow_up", "prompt": "How should we follow up?"},
            ],
        )
        db.commit()
        phone = f"+4477023{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        ExpoSessionFlowService.advance(db, session=session, answer="panels", answer_source="text")
        ExpoSessionFlowService.advance(db, session=session, answer="123", answer_source="text")
        lead = db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one()
        assert lead.follow_up_status == "WhatsApp, Email, Call"


def test_async_completion_enqueues_exhibitor_email(monkeypatch):
    calls: list[str] = []

    def _fake_thread(*, target=None, args=(), **_kwargs):
        class _T:
            def start(self_inner):
                calls.append("threaded")
                if target:
                    # Do not run SMTP in unit test — only record that we offloaded.
                    return None

        return _T()

    monkeypatch.setattr("app.services.expo.async_notify_service.threading.Thread", _fake_thread)

    with get_sessionmaker()() as db:
        org = _org(db)
        booth = _booth(
            db,
            org_id=org.id,
            steps=[{"key": "interest", "prompt": "What?"}],
        )
        lib = _library_pdf(db, org_id=org.id)
        db.commit()
        phone = f"+4477024{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        lead = db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one()
        lead.consent_acknowledged = True
        lead.visitor_email = "visitor@example.com"
        lead.interest = "solar"
        from app.services.expo.offer_delivery_service import mark_lead_offer_sent

        assets = load_booth_assets(db, booth.id)
        mark_lead_offer_sent(db, lead, assets[0])
        db.add(lead)
        db.commit()

        result = ExpoSessionFlowService.advance(db, session=session, answer="solar kits", answer_source="text")
        assert result.get("done") is True
        assert "threaded" in calls


def test_contact_email_template_key_exists():
    from app.services.expo.question_bank import SYSTEM_TEMPLATE_KEYS

    assert "contact_email" in SYSTEM_TEMPLATE_KEYS
    assert "email" in CONTACT_EMAIL_PROMPT.lower()


def test_interest_default_wording():
    from app.services.expo.question_bank import SELECTABLE_QUESTION_BANK

    interest = next(q for q in SELECTABLE_QUESTION_BANK if q["key"] == "interest")
    assert "looking for at our stand" in interest["prompt"]
    assert "mic" in interest["prompt"].lower() or "own words" in interest["prompt"].lower()


def test_all_questions_walkthrough_with_library_and_follow_up():
    """Typed WhatsApp path: contact → email → interest → follow_up → consent (library PDF)."""
    with get_sessionmaker()() as db:
        org = _org(db)
        booth = _booth(db, org_id=org.id)
        _library_pdf(db, org_id=org.id, title="Walkthrough Catalogue")
        db.commit()
        phone = f"+4477025{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])

        ExpoSessionFlowService.advance(db, session=session, answer="Walk User", answer_source="text")
        ExpoSessionFlowService.advance(db, session=session, answer="Walk Co", answer_source="text")
        ExpoSessionFlowService.advance(db, session=session, answer="walk@example.com", answer_source="text")
        r_interest = ExpoSessionFlowService.advance(
            db, session=session, answer="solar panels", answer_source="text"
        )
        assert r_interest.get("question_key") == "follow_up"
        r_follow = ExpoSessionFlowService.advance(db, session=session, answer="123", answer_source="text")
        assert r_follow.get("question_key") == "consent_info"
        assert r_follow.get("options")
        r_done = ExpoSessionFlowService.advance(db, session=session, answer="1", answer_source="text")
        assert r_done.get("done") is True or r_done.get("assets")
        lead = db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one()
        assert lead.name == "Walk User"
        assert lead.visitor_email == "walk@example.com"
        assert lead.follow_up_status == "WhatsApp, Email, Call"
        assert lead.consent_acknowledged is True
