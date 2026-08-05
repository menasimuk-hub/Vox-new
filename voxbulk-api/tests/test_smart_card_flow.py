"""Smart Card session flow — choice contract, product menus, back navigation, channel notifications."""

import uuid

import pytest

from app.core.database import get_sessionmaker
from app.models.organisation import Organisation
from app.models.smart_card import (
    SmartCardCategory,
    SmartCardProduct,
    SmartCardRepresentative,
    SmartCardRepresentativeProduct,
    SmartCardResponse,
    SmartCardSession,
)
from app.services.smart_card.seed_service import SmartCardSeedService
from app.services.smart_card.session_flow_service import (
    NO_THANKS_VALUE,
    SmartCardSessionFlowService,
)


@pytest.fixture()
def db():
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _seed_rep(db, *, with_products: int = 0) -> SmartCardRepresentative:
    SmartCardSeedService.ensure_seeded(db)
    org = Organisation(name=f"Smart Card Org {uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    rep = SmartCardRepresentative(
        org_id=org.id,
        name="Dana Rep",
        email=f"rep-{uuid.uuid4().hex[:6]}@test.local",
        mobile="+447700900001",
        qr_token=f"org-dana-{uuid.uuid4().hex[:16]}",
        status="active",
    )
    db.add(rep)
    db.flush()

    if with_products:
        category = SmartCardCategory(org_id=org.id, name="Machines", sort_order=10)
        db.add(category)
        db.flush()
        for i in range(with_products):
            product = SmartCardProduct(
                org_id=org.id,
                category_id=category.id,
                name=f"Product {i + 1}",
                short_description=f"Spec sheet {i + 1}",
                sort_order=10 * (i + 1),
            )
            db.add(product)
            db.flush()
            db.add(
                SmartCardRepresentativeProduct(
                    org_id=org.id,
                    representative_id=rep.id,
                    product_id=product.id,
                )
            )
    db.commit()
    return rep


def _answer_until(db, session: SmartCardSession, target_step: str, *, answer: str = "ok") -> dict:
    """Advance with filler answers until ``target_step`` is the current step."""
    result: dict = {}
    for _ in range(12):
        if (session.current_step or "") == target_step:
            break
        result = SmartCardSessionFlowService.advance(db, session=session, answer=answer)
        db.commit()
        if result.get("done"):
            break
    return result


def test_start_session_marks_contact_step_as_contact_input(db):
    rep = _seed_rep(db)
    result = SmartCardSessionFlowService.start_session(db, rep=rep, channel="web")
    db.commit()

    assert result["input"] == "contact"
    assert result["options"] == []
    assert result["allow_voice"] is False
    assert result["contact"]["has_business_card"] is False


def test_closed_question_returns_button_options_and_open_question_allows_voice(db):
    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(db, rep=rep, channel="web")
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])

    # contact -> interest (open, voice allowed)
    interest = SmartCardSessionFlowService.advance(db, session=session, answer="Ana | Acme")
    db.commit()
    assert interest["step"] == "interest"
    assert interest["input"] == "text"
    assert interest["allow_voice"] is True
    assert interest["options"] == []

    # interest -> role (closed choice, no voice)
    role = SmartCardSessionFlowService.advance(db, session=session, answer="Packaging lines")
    db.commit()
    assert role["step"] == "role"
    assert role["input"] == "choice"
    assert role["allow_voice"] is False
    assert [o["value"] for o in role["options"]] == ["Buyer", "Specifier", "Influencer", "Other"]


def test_follow_up_is_multi_choice(db):
    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(db, rep=rep, channel="web")
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])
    payload = _answer_until(db, session, "follow_up")

    assert payload["step"] == "follow_up"
    assert payload["input"] == "multi_choice"
    assert payload["allow_voice"] is False


def test_whatsapp_prompt_renders_numbered_options(db):
    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(
        db, rep=rep, channel="whatsapp", visitor_phone="+447700900123"
    )
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])

    SmartCardSessionFlowService.advance(db, session=session, answer="Ana | Acme")
    db.commit()
    role = SmartCardSessionFlowService.advance(db, session=session, answer="Packaging lines")
    db.commit()

    assert "1️⃣" in role["prompt"]
    assert "Reply with the number" in role["prompt"]


def test_whatsapp_digit_reply_maps_to_option_value(db):
    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(
        db, rep=rep, channel="whatsapp", visitor_phone="+447700900124"
    )
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])
    SmartCardSessionFlowService.advance(db, session=session, answer="Ana | Acme")
    db.commit()
    SmartCardSessionFlowService.advance(db, session=session, answer="Packaging lines")
    db.commit()
    # role step — reply "2" should store "Specifier"
    SmartCardSessionFlowService.advance(db, session=session, answer="2")
    db.commit()

    stored = (
        db.query(SmartCardResponse)
        .filter(SmartCardResponse.session_id == session.id, SmartCardResponse.question_key == "role")
        .one()
    )
    assert stored.answer_text == "Specifier"


def test_consent_step_lists_only_rep_products(db):
    rep = _seed_rep(db, with_products=2)
    started = SmartCardSessionFlowService.start_session(db, rep=rep, channel="web")
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])
    payload = _answer_until(db, session, "consent_info")

    assert payload["step"] == "consent_info"
    assert payload["input"] == "multi_choice"
    values = [o["value"] for o in payload["options"]]
    assert values == ["Product 1", "Product 2", NO_THANKS_VALUE]
    assert payload["options"][0]["category"] == "Machines"


def test_product_digit_reply_selects_products_and_marks_consent(db):
    rep = _seed_rep(db, with_products=2)
    started = SmartCardSessionFlowService.start_session(
        db, rep=rep, channel="whatsapp", visitor_phone="+447700900125"
    )
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])
    _answer_until(db, session, "consent_info")

    SmartCardSessionFlowService.advance(db, session=session, answer="1,2")
    db.commit()

    stored = (
        db.query(SmartCardResponse)
        .filter(
            SmartCardResponse.session_id == session.id,
            SmartCardResponse.question_key == "consent_info",
        )
        .one()
    )
    assert stored.answer_text == "Product 1, Product 2"
    state = SmartCardSessionFlowService._load_state(session)
    assert state["consent"] == "Yes"
    assert [p["name"] for p in state["selected_products"]] == ["Product 1", "Product 2"]


def test_no_thanks_option_declines_products(db):
    rep = _seed_rep(db, with_products=2)
    started = SmartCardSessionFlowService.start_session(
        db, rep=rep, channel="whatsapp", visitor_phone="+447700900126"
    )
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])
    _answer_until(db, session, "consent_info")

    SmartCardSessionFlowService.advance(db, session=session, answer="3")
    db.commit()

    state = SmartCardSessionFlowService._load_state(session)
    assert state["consent"] == "No"
    assert state["selected_products"] == []


def test_go_back_keeps_scanned_card_and_clears_the_reopened_answer(db):
    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(db, rep=rep, channel="web")
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])

    SmartCardSessionFlowService.apply_card_ocr(
        db,
        session=session,
        name="Ana Diaz",
        company="Acme Ltd",
        email="ana@acme.test",
        phone="+447700900999",
        business_card_path="data/smart_card_cards/card.jpg",
    )
    db.commit()

    SmartCardSessionFlowService.advance(db, session=session, answer="Yes")
    db.commit()
    SmartCardSessionFlowService.advance(db, session=session, answer="Packaging lines")
    db.commit()
    assert session.current_step == "role"

    back = SmartCardSessionFlowService.go_back(db, session=session)
    db.commit()

    assert back["step"] == "interest"
    assert back["at_start"] is False
    assert back["contact"]["name"] == "Ana Diaz"
    assert back["contact"]["has_business_card"] is True
    assert back["saved_answer"] == "Packaging lines"

    remaining = (
        db.query(SmartCardResponse)
        .filter(
            SmartCardResponse.session_id == session.id,
            SmartCardResponse.question_key == "interest",
        )
        .count()
    )
    assert remaining == 0

    state = SmartCardSessionFlowService._load_state(session)
    assert state["business_card_path"] == "data/smart_card_cards/card.jpg"


def test_go_back_on_first_step_reports_at_start(db):
    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(db, rep=rep, channel="web")
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])

    back = SmartCardSessionFlowService.go_back(db, session=session)
    db.commit()
    assert back["at_start"] is True
    assert back["step"] == "contact"


def test_yes_after_card_scan_confirms_without_overwriting_name(db):
    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(db, rep=rep, channel="whatsapp")
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])

    SmartCardSessionFlowService.apply_card_ocr(
        db,
        session=session,
        name="Ana Diaz",
        company="Acme Ltd",
        email="ana@acme.test",
        phone="+447700900999",
        business_card_path="data/smart_card_cards/card.jpg",
    )
    db.commit()

    SmartCardSessionFlowService.advance(db, session=session, answer="Yes")
    db.commit()

    state = SmartCardSessionFlowService._load_state(session)
    assert state["name"] == "Ana Diaz"
    assert state["company"] == "Acme Ltd"


def test_web_completion_does_not_send_whatsapp_hot_lead(db, monkeypatch):
    calls: list[str] = []

    import app.services.smart_card.hot_lead_notify_service as hot_lead_module

    monkeypatch.setattr(
        hot_lead_module,
        "notify_hot_lead",
        lambda *a, **k: calls.append("sent"),
    )
    monkeypatch.setattr(
        "app.services.smart_card.email_service.SmartCardEmailService.notify_rep_lead",
        staticmethod(lambda *a, **k: None),
    )

    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(db, rep=rep, channel="web")
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])

    result = {}
    for _ in range(12):
        result = SmartCardSessionFlowService.advance(db, session=session, answer="This week")
        db.commit()
        if result.get("done"):
            break

    assert result.get("done") is True
    assert str(result.get("lead_score") or "").lower() == "hot"
    assert calls == []


def test_whatsapp_completion_still_sends_hot_lead(db, monkeypatch):
    calls: list[str] = []

    import app.services.smart_card.hot_lead_notify_service as hot_lead_module

    monkeypatch.setattr(
        hot_lead_module,
        "notify_hot_lead",
        lambda *a, **k: calls.append("sent"),
    )
    monkeypatch.setattr(
        "app.services.smart_card.email_service.SmartCardEmailService.notify_rep_lead",
        staticmethod(lambda *a, **k: None),
    )

    rep = _seed_rep(db)
    started = SmartCardSessionFlowService.start_session(
        db, rep=rep, channel="whatsapp", visitor_phone="+447700900127"
    )
    db.commit()
    session = db.get(SmartCardSession, started["session_id"])

    result = {}
    for _ in range(12):
        result = SmartCardSessionFlowService.advance(db, session=session, answer="This week")
        db.commit()
        if result.get("done"):
            break

    assert result.get("done") is True
    assert str(result.get("lead_score") or "").lower() == "hot"
    assert calls == ["sent"]
