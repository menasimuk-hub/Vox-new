"""Expo catalogue/consent UX — ask vs deliver split, numbered picks, and language correction."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.database import Base, get_engine, get_sessionmaker
from app.models.expo import (
    ExpoBooth,
    ExpoBoothAsset,
    ExpoExhibition,
    ExpoLead,
    ExpoQuestionTemplate,
    ExpoSession,
)
from app.models.organisation import Organisation
from app.services.expo.seed_service import ExpoSeedService
from app.services.expo.session_flow_service import ExpoSessionFlowService
from app.services.expo.voice_note_service import correct_detected_language


@pytest.fixture(scope="module", autouse=True)
def _prepare_db():
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def _org(db) -> Organisation:
    org = Organisation(name="Expo UX", contact_email=f"expo-ux-{uuid.uuid4().hex[:8]}@example.com")
    db.add(org)
    db.flush()
    return org


def _booth_with_consent(db, *, org_id: str) -> ExpoBooth:
    now = datetime.utcnow()
    exhibition = ExpoExhibition(
        id=str(uuid.uuid4()),
        org_id=org_id,
        name="Show UX",
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
        name="Booth UX",
        company_display_name="Booth UX",
        booth_code="UX01",
        qr_token=f"ux-{uuid.uuid4().hex[:8]}",
        status="active",
        scan_count=0,
        question_config_json=json.dumps(
            {
                "steps": [
                    {"key": "interest", "prompt": "What are you looking for?"},
                    {"key": "consent_info", "prompt": "Would you like our catalogue and/or price list?"},
                ],
                "thank_you_message": "Thanks!",
            }
        ),
        created_at=now,
        updated_at=now,
    )
    db.add(booth)
    db.flush()

    for idx, (key, title, purpose) in enumerate(
        [("cat", "Product Catalogue", "catalogue"), ("price", "2026 Price List", "price_list")]
    ):
        db.add(
            ExpoBoothAsset(
                id=str(uuid.uuid4()),
                org_id=org_id,
                booth_id=booth.id,
                asset_key=key,
                title=title,
                short_description=f"{title} description",
                kind="pdf",
                purpose=purpose,
                storage_path=f"data/expo-assets/{key}.pdf",
                is_default=False,
                sort_order=(idx + 1) * 10,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    return booth


def _lead_for(db, session: ExpoSession) -> ExpoLead:
    return db.execute(select(ExpoLead).where(ExpoLead.session_id == session.id)).scalar_one()


def test_consent_ask_has_no_deliverable_assets_on_whatsapp():
    with get_sessionmaker()() as db:
        org = _org(db)
        db.commit()
        booth = _booth_with_consent(db, org_id=org.id)
        db.commit()

        phone = f"+4477010{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])

        result = ExpoSessionFlowService.advance(db, session=session, answer="pumps", answer_source="text")

        assert result.get("question_key") == "consent_info"
        # Ask-time must never populate the deliverable list the WA relay sends files from.
        assert not result.get("assets")
        assert result.get("asset_options")
        assert len(result["asset_options"]) == 2
        prompt = result.get("prompt") or ""
        assert "1️⃣" in prompt
        assert "No thanks" in prompt
        # Options metadata should still be available for a web-style renderer too.
        assert any(opt.get("label") == "No thanks" for opt in result.get("options") or [])


def test_consent_ask_web_channel_includes_tracked_asset_urls():
    with get_sessionmaker()() as db:
        org = _org(db)
        db.commit()
        booth = _booth_with_consent(db, org_id=org.id)
        db.commit()

        phone = f"+4477013{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="web", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])

        result = ExpoSessionFlowService.advance(db, session=session, answer="pumps", answer_source="text")

        assert result.get("question_key") == "consent_info"
        assert result.get("asset_options")
        # Ask step: options carry tracked URLs; deliverable assets stay empty until the visitor picks.
        assert result.get("assets") == []
        assert all(str(a.get("url") or "").startswith("http") for a in result["asset_options"])


def test_deliver_numbered_pick_selects_single_asset():
    with get_sessionmaker()() as db:
        org = _org(db)
        db.commit()
        booth = _booth_with_consent(db, org_id=org.id)
        db.commit()

        phone = f"+4477011{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        ExpoSessionFlowService.advance(db, session=session, answer="pumps", answer_source="text")
        lead = _lead_for(db, session)

        delivered, clarify = ExpoSessionFlowService._deliver_consent_assets(
            db, booth=booth, lead=lead, answer="1"
        )
        assert clarify is None
        assert len(delivered) == 1
        assert delivered[0]["purpose"] == "catalogue"


def test_deliver_emoji_digit_pick_selects_first_asset():
    with get_sessionmaker()() as db:
        org = _org(db)
        db.commit()
        booth = _booth_with_consent(db, org_id=org.id)
        db.commit()

        phone = f"+4477015{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        ExpoSessionFlowService.advance(db, session=session, answer="pumps", answer_source="text")
        lead = _lead_for(db, session)

        delivered, clarify = ExpoSessionFlowService._deliver_consent_assets(
            db, booth=booth, lead=lead, answer="1️⃣"
        )
        assert clarify is None
        assert len(delivered) == 1


def test_consent_menu_shows_category_headers_when_present():
    from app.services.expo.session_flow_service import _format_consent_menu_lines

    lines = _format_consent_menu_lines(
        [
            {
                "id": "1",
                "purpose": "catalogue",
                "title": "Brochure.pdf",
                "product_name": "Pump A",
                "category_name": "Pumps",
            },
            {
                "id": "2",
                "purpose": "price_list",
                "title": "Rates.xlsx",
                "product_name": "Pump A",
                "category_name": "Pumps",
            },
        ],
        offer="files",
    )
    blob = "\n".join(lines)
    assert "📁 Pumps" in blob
    assert "Pump A — Catalogue" in blob
    assert "Pump A — Price list" in blob


def test_yes_does_not_remap_digit_one_on_consent_advance():
    """Regression: reply '1' must deliver option 1, never be treated as Yes."""
    with get_sessionmaker()() as db:
        org = _org(db)
        db.commit()
        booth = _booth_with_consent(db, org_id=org.id)
        db.commit()

        phone = f"+4477016{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        ExpoSessionFlowService.advance(db, session=session, answer="pumps", answer_source="text")

        result = ExpoSessionFlowService.advance(db, session=session, answer="1", answer_source="text")
        assert result.get("assets")
        assert len(result["assets"]) == 1
        assert "Please reply with a number" not in (result.get("prompt") or "")


def test_bare_yes_with_two_assets_does_not_deliver_all():
    with get_sessionmaker()() as db:
        org = _org(db)
        db.commit()
        booth = _booth_with_consent(db, org_id=org.id)
        db.commit()

        phone = f"+4477012{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        ExpoSessionFlowService.advance(db, session=session, answer="pumps", answer_source="text")
        lead = _lead_for(db, session)

        delivered, clarify = ExpoSessionFlowService._deliver_consent_assets(
            db, booth=booth, lead=lead, answer="Yes"
        )
        assert delivered == []
        assert clarify

        # advance() should re-show the consent step with the clarification, not send both files.
        result = ExpoSessionFlowService.advance(db, session=session, answer="Yes", answer_source="text")
        assert not result.get("done")
        assert not result.get("assets")
        assert result.get("question_key") == "consent_info"
        assert "1" in (result.get("prompt") or "")


def test_deliver_both_keyword_sends_all_assets():
    with get_sessionmaker()() as db:
        org = _org(db)
        db.commit()
        booth = _booth_with_consent(db, org_id=org.id)
        db.commit()

        phone = f"+4477014{uuid.uuid4().hex[:6]}"
        started = ExpoSessionFlowService.start_session(db, booth=booth, channel="whatsapp", visitor_phone=phone)
        session = db.get(ExpoSession, started["session_id"])
        ExpoSessionFlowService.advance(db, session=session, answer="pumps", answer_source="text")
        lead = _lead_for(db, session)

        delivered, clarify = ExpoSessionFlowService._deliver_consent_assets(
            db, booth=booth, lead=lead, answer="both"
        )
        assert clarify is None
        assert len(delivered) == 2


def test_correct_detected_language_forces_arabic_over_turkish():
    arabic_text = "مرحبا بكم في معرض التجارة"
    assert correct_detected_language(arabic_text, "tr") == "ar"
    assert correct_detected_language(arabic_text, "fa") == "ar"
    assert correct_detected_language(arabic_text, "ur") == "ar"
    assert correct_detected_language(arabic_text, "ar") == "ar"
    assert correct_detected_language("Hello there", "en") == "en"


def test_ensure_question_templates_soft_prefixes_emoji_without_rewriting_wording():
    with get_sessionmaker()() as db:
        # Fresh test DB may not have run the app-startup seed yet — seed once first.
        ExpoSeedService._ensure_question_templates(db)
        db.commit()

        custom_prompt = f"Custom admin-edited prompt {uuid.uuid4().hex[:6]}"
        row = db.execute(
            select(ExpoQuestionTemplate).where(ExpoQuestionTemplate.question_key == "interest")
        ).scalar_one_or_none()
        assert row is not None
        row.prompt = custom_prompt
        db.add(row)
        db.commit()

        ExpoSeedService._ensure_question_templates(db)
        db.commit()

        refreshed = db.execute(
            select(ExpoQuestionTemplate).where(ExpoQuestionTemplate.question_key == "interest")
        ).scalar_one_or_none()
        assert refreshed is not None
        # Soft-prefix topic emoji only — wording stays intact.
        assert refreshed.prompt == f"🎯 {custom_prompt}"

        ExpoSeedService._ensure_question_templates(db)
        db.commit()
        again = db.execute(
            select(ExpoQuestionTemplate).where(ExpoQuestionTemplate.question_key == "interest")
        ).scalar_one_or_none()
        assert again is not None
        assert again.prompt == f"🎯 {custom_prompt}"


def test_with_topic_emoji_does_not_double_prefix():
    from app.services.expo.question_bank import with_topic_emoji

    assert with_topic_emoji("interest", "What are you looking for?") == "🎯 What are you looking for?"
    assert with_topic_emoji("interest", "🎯 Already set") == "🎯 Already set"
    assert with_topic_emoji("role", "👔 Role question") == "👔 Role question"