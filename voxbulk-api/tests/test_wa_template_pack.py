"""WA Survey OpenAI template pack generation, validation, and save."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core.database import get_sessionmaker
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_type_service import SurveyTypeService
from app.services.survey_wa_template_pack_service import (
    PACK_SIZE,
    WA_TEMPLATE_PACK_JSON_SCHEMA,
    SurveyWaTemplatePackService,
    build_components_from_generated,
    validate_generated_template,
)
from app.services.survey_whatsapp_template_service import (
    ANONYMOUS_BODY_SENTENCE,
    ANONYMOUS_FOOTER,
    SurveyWhatsappTemplateService,
    VARIANT_ANONYMOUS,
    VARIANT_STANDARD,
)


def _seed_survey_type(db):
    SurveyTypeService.ensure_defaults(db)
    row = SurveyTypeService.get_by_slug(db, "customer_satisfaction")
    assert row is not None
    return row


@pytest.fixture(autouse=True)
def _schema():
    from app.core.database import Base, get_engine
    import app.models  # noqa: F401

    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def _sample_item(**overrides):
    base = {
        "template_name": "std_intro",
        "variant_type": VARIANT_STANDARD,
        "title": "Standard intro",
        "step_role": "start",
        "purpose": "intro",
        "body": "Hi {{1}}, {{2}} would love your feedback 👋 Tap below to start your survey.",
        "footer": "Reply STOP to opt out",
        "header": "",
        "button_type": "quick_reply",
        "buttons": [{"text": "Start survey", "url": "", "phone_number": ""}],
        "example_values": ["Alex", "Northgate Dental", "https://example.com/s/1"],
        "language": "en_US",
        "category": "MARKETING",
        "outcome_key": None,
    }
    base.update(overrides)
    return base


def _mock_pack_response():
    templates = []
    roles_buttons = [
        ("start", "quick_reply", None),
        ("rating", "none", None),
        ("yes_no", "quick_reply", None),
        ("helpfulness", "none", None),
        ("abc_choice", "quick_reply", None),
        ("reason", "none", None),
        ("feeling_word", "quick_reply", None),
        ("follow_up", "none", None),
        ("improvement", "none", None),
        ("completion", "none", "happy"),
        ("completion", "none", "neutral"),
        ("completion", "none", "unhappy"),
    ]
    for idx, (role, btn_type, outcome_key) in enumerate(roles_buttons):
        name = role if role != "start" else "std_intro"
        variant = VARIANT_STANDARD
        body = f"Hi {{{{1}}}}, {{{{2}}}} 👋 Share your thoughts — {role}."
        if outcome_key:
            body = f"Thanks {{{{1}}}} — {outcome_key} closing."
        footer = "Reply STOP to opt out"
        buttons = [{"text": "Start", "url": "", "phone_number": ""}]
        if btn_type == "url":
            buttons = [{"text": "Open survey", "url": "https://example.com/s/{{3}}", "phone_number": ""}]
        if btn_type == "phone":
            buttons = [{"text": "Call us", "url": "", "phone_number": "+447700900123"}]
        item = _sample_item(
            template_name=f"{name}_{idx}" if not outcome_key else f"completion_{outcome_key}",
            variant_type=variant,
            title=role.replace("_", " ").title(),
            step_role=role,
            purpose=role if not outcome_key else f"completion_{outcome_key}",
            body=body,
            footer=footer,
            button_type=btn_type,
            buttons=buttons if btn_type != "none" else [],
        )
        item["outcome_key"] = outcome_key if outcome_key else None
        templates.append(item)
    assert len(templates) == PACK_SIZE
    return {"templates": templates}


def test_pack_json_schema_includes_outcome_key_in_required():
    required = WA_TEMPLATE_PACK_JSON_SCHEMA["properties"]["templates"]["items"]["required"]
    assert "outcome_key" in required


def test_openai_chat_token_limit_for_reasoning_models():
    o3 = OpenAIProviderService._chat_token_limit_payload(provider="openai", model="o3-mini", tokens=900)
    assert o3 == {"max_completion_tokens": 900}
    gpt52 = OpenAIProviderService._chat_token_limit_payload(provider="openai", model="gpt-5.2", tokens=900)
    assert gpt52 == {"max_completion_tokens": 900}
    legacy = OpenAIProviderService._chat_token_limit_payload(provider="openai", model="gpt-4o-mini", tokens=900)
    assert legacy == {"max_completion_tokens": 900}
    deepseek = OpenAIProviderService._chat_token_limit_payload(provider="deepseek", model="deepseek-chat", tokens=900)
    assert deepseek == {"max_tokens": 900}


def test_validate_quick_reply_and_url_templates():
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        ok, errors = validate_generated_template(_sample_item(), survey_type=st)
        assert ok is not None
        assert not errors

        bad_qr, err_qr = validate_generated_template(
            _sample_item(button_type="quick_reply", buttons=[{"text": "A", "url": "", "phone_number": ""}] * 4),
            survey_type=st,
        )
        assert bad_qr is None
        assert any("3 buttons" in e for e in err_qr)

        bad_url, err_url = validate_generated_template(
            _sample_item(
                template_name="bad_url",
                button_type="url",
                buttons=[{"text": "Go", "url": "not-a-url", "phone_number": ""}],
            ),
            survey_type=st,
        )
        assert bad_url is None
        assert any("https URL" in e for e in err_url)


def test_validate_rejects_reference_copy_by_default():
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        ok, errors = validate_generated_template(
            _sample_item(body="Hi {{1}}, {{2}} — your reference number is {{3}}."),
            survey_type=st,
        )
        assert ok is None
        assert any("reference" in e.lower() for e in errors)


def test_validate_allows_reference_when_admin_instruction_requests():
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        ok, errors = validate_generated_template(
            _sample_item(body="Hi {{1}}, {{2}} — your reference number is {{3}}."),
            survey_type=st,
            instruction="Include reference number for each customer",
        )
        assert ok is not None
        assert not errors


def test_pack_system_prompt_forbids_reference_without_admin_override():
    from app.services.survey_wa_template_pack_service import _pack_system_prompt

    prompt = _pack_system_prompt()
    assert "NO REFERENCE COPY" in prompt
    assert "at least 8 of 12" in prompt
    assert "META / WHATSAPP BUSINESS APPROVAL RULES" in prompt
    assert "Reply STOP to opt out" in prompt


def test_coerce_meta_template_fields_fixes_long_footer():
    from app.services.survey_wa_template_pack_service import coerce_meta_template_fields

    long_footer = (
        "Privacy: https://www.voxbulk.com/privacy Contact: Data.Pro@voxbulk.com Reply STOP to opt out."
    )
    item = coerce_meta_template_fields(
        _sample_item(footer=long_footer),
        privacy_mode="off",
    )
    assert item["footer"] == "Reply STOP to opt out"
    assert len(item["footer"]) <= 60


def test_validate_anonymous_wording():
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        ok, errors = validate_generated_template(
            _sample_item(
                template_name="anon_intro",
                variant_type=VARIANT_ANONYMOUS,
                body=f"Please share feedback. {ANONYMOUS_BODY_SENTENCE}",
                footer=ANONYMOUS_FOOTER,
            ),
            survey_type=st,
            privacy_mode="on",
        )
        assert ok is not None
        assert not errors


def test_build_components_quick_reply_and_url():
    qr = build_components_from_generated(_sample_item(button_type="quick_reply"))
    assert any(c.get("type") == "BUTTONS" for c in qr)
    assert qr[-1]["buttons"][0]["type"] == "QUICK_REPLY"

    url_components = build_components_from_generated(
        _sample_item(
            template_name="url_cta",
            button_type="url",
            buttons=[{"text": "Open", "url": "https://example.com/s/abc", "phone_number": ""}],
        )
    )
    buttons = next(c for c in url_components if c["type"] == "BUTTONS")["buttons"]
    assert buttons[0]["type"] == "URL"


def test_generate_pack_uses_responses_api(monkeypatch):
    captured = {}

    def fake_responses_json(db, **kwargs):
        captured.update(kwargs)
        return _mock_pack_response(), {"model": "gpt-4o-mini", "api_style": "responses", "endpoint_path": "/v1/responses"}

    monkeypatch.setattr(
        "app.services.survey_wa_template_pack_service.OpenAIProviderService.responses_json",
        fake_responses_json,
    )
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        result = SurveyWaTemplatePackService.generate_pack(db, survey_type=st, instruction="Keep friendly tone")
        assert captured.get("schema_name") == "wa_survey_template_pack"
        assert "NO REFERENCE COPY" in (captured.get("system_prompt") or "")
        assert "at least 8 of 12" in (captured.get("system_prompt") or "")
        assert "META / WHATSAPP BUSINESS APPROVAL RULES" in (captured.get("system_prompt") or "")
        assert result["valid_count"] == PACK_SIZE
        assert result["openai"]["api_style"] == "responses"
        purposes = {t["template"]["purpose"] for t in result["templates"] if t.get("template")}
        roles = {t["template"]["step_role"] for t in result["templates"] if t.get("template")}
        assert len(purposes) >= 4
        assert "start" in roles
        assert "completion" in roles
        outcome_keys = {
            t["template"].get("outcome_key")
            for t in result["templates"]
            if t.get("template") and t["template"].get("step_role") == "completion"
        }
        assert outcome_keys == {"happy", "neutral", "unhappy"}


def test_save_pack_creates_local_drafts(monkeypatch):
    monkeypatch.setattr(
        "app.services.survey_wa_template_pack_service.OpenAIProviderService.responses_json",
        lambda db, **kwargs: (_mock_pack_response(), {"model": "gpt-4o-mini", "api_style": "responses"}),
    )
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        generated = SurveyWaTemplatePackService.generate_pack(db, survey_type=st)
        selected = [t["template"] for t in generated["templates"] if t.get("template")][:3]
        saved = SurveyWaTemplatePackService.save_selected_templates(
            db, survey_type=st, templates=selected, replace_step_bank=True
        )
        assert saved["saved_count"] == 3
        rows = list(db.execute(select(TelnyxWhatsappTemplate)).scalars())
        assert len(rows) == 3
        assert all(r.status == "LOCAL_DRAFT" for r in rows)


def test_save_single_template_does_not_prune_other_mappings(monkeypatch):
    monkeypatch.setattr(
        "app.services.survey_wa_template_pack_service.OpenAIProviderService.responses_json",
        lambda db, **kwargs: (_mock_pack_response(), {"model": "gpt-4o-mini", "api_style": "responses"}),
    )
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        generated = SurveyWaTemplatePackService.generate_pack(db, survey_type=st)
        selected = [t["template"] for t in generated["templates"] if t.get("template")][:3]
        SurveyWaTemplatePackService.save_selected_templates(
            db, survey_type=st, templates=selected, replace_step_bank=True
        )
        first = db.execute(select(TelnyxWhatsappTemplate)).scalars().first()
        assert first is not None
        one = generated["templates"][0]["template"]
        SurveyWaTemplatePackService.save_selected_templates(
            db,
            survey_type=st,
            templates=[{**one, "id": first.id}],
            replace_step_bank=False,
        )
        from app.models.survey_type_template import SurveyTypeTemplate

        mapping_count = db.execute(
            select(func.count()).select_from(SurveyTypeTemplate).where(
                SurveyTypeTemplate.survey_type_id == st.id
            )
        ).scalar_one()
        assert mapping_count == 3


def test_regenerate_pack_item(monkeypatch):
    calls = []

    def fake_responses_json(db, **kwargs):
        calls.append(kwargs.get("schema_name"))
        one = _mock_pack_response()["templates"][0]
        return {"template": one}, {"model": "gpt-4o-mini", "api_style": "responses"}

    monkeypatch.setattr(
        "app.services.survey_wa_template_pack_service.OpenAIProviderService.responses_json",
        fake_responses_json,
    )
    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        result = SurveyWaTemplatePackService.regenerate_pack_item(
            db,
            survey_type=st,
            index=2,
            instruction="More emoji, stronger CTA",
            current_template={"template_name": "std_intro", "purpose": "intro", "variant_type": "standard", "button_type": "quick_reply", "body": "Hi", "footer": "Reply STOP to opt out"},
            sibling_summaries=[{"template_name": "other", "purpose": "reminder", "body": "Reminder text"}],
        )
        assert calls[-1] == "wa_survey_template_single"
        assert result["item"]["index"] == 2
        assert result["item"].get("template")


def test_push_after_pack_save(monkeypatch):
    monkeypatch.setattr(
        "app.services.survey_wa_template_pack_service.OpenAIProviderService.responses_json",
        lambda db, **kwargs: (_mock_pack_response(), {"model": "gpt-4o-mini", "api_style": "responses"}),
    )

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"id": "telnyx-new", "template_id": "999", "status": "PENDING", "components": []}}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            return FakeResponse()

        def get(self, url, headers=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.survey_whatsapp_template_service.httpx.Client", lambda *a, **k: FakeClient())
    monkeypatch.setattr(
        "app.services.survey_whatsapp_template_service.SurveyWhatsappTemplateService._telnyx_config",
        lambda db: {"api_key": "test-key", "whatsapp_waba_id": "waba-123"},
    )

    with get_sessionmaker()() as db:
        st = _seed_survey_type(db)
        generated = SurveyWaTemplatePackService.generate_pack(db, survey_type=st)
        one = generated["valid_templates"][0]
        saved = SurveyWaTemplatePackService.save_selected_templates(db, survey_type=st, templates=[one])
        row = db.get(TelnyxWhatsappTemplate, saved["templates"][0]["id"])
        result = SurveyWhatsappTemplateService.push_to_telnyx(db, row)
        assert result["ok"] is True
