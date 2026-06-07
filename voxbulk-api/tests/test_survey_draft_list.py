"""Survey draft save/list and step label serialization."""

from __future__ import annotations

from pathlib import Path

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService
from app.services.survey_builder_flow_service import (
    ensure_question_display_name,
    normalize_survey_config_step_labels,
    survey_step_labels_from_config,
)


def _seed_user(app_client, *, email: str = "survey_draft_list@example.com"):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Draft List Clinic")
        db.add(org)
        db.flush()
        user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
        db.add(user)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=user.id))
        db.commit()
        org_id = org.id

    token = app_client.post(
        "/auth/token",
        data={"username": email, "password": "pass123", "org_id": org_id},
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, org_id


def test_blank_step1_uses_survey_type_name():
    step = ensure_question_display_name({"step_role": "rating"}, sequence=0, survey_type_name="Service quality")
    assert step["display_name"] == "Service quality"


def test_blank_step_uses_question_text():
    step = ensure_question_display_name(
        {"step_role": "rating", "text": "How likely are you to recommend us to a friend?"},
        sequence=1,
        survey_type_name="",
    )
    assert step["display_name"] == "How likely are you to recommend us to a friend?"


def test_order_to_dict_includes_first_step_name(app_client):
    headers, _org_id = _seed_user(app_client)
    create = app_client.post(
        "/service-orders",
        headers=headers,
        json={
            "service_code": "survey",
            "title": "Draft with blank step name",
            "config": {
                "delivery": "whatsapp",
                "builder_step_sequence": [{"step_role": "rating", "text": "Rate your visit today"}],
            },
        },
    )
    assert create.status_code == 200, create.text
    order_id = create.json()["id"]

    listed = app_client.get("/service-orders?service_code=survey", headers=headers)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert isinstance(rows, list)
    match = next((row for row in rows if row["id"] == order_id), None)
    assert match is not None, "saved survey draft missing from list endpoint"
    assert match.get("first_step_name") == "Rate your visit today"
    assert match.get("step_labels") == ["Rate your visit today"]

    detail = app_client.get(f"/service-orders/{order_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body.get("first_step_name") == "Rate your visit today"


def test_normalize_old_draft_step_labels():
    cfg = normalize_survey_config_step_labels(
        {
            "survey_type_name": "Check-in",
            "builder_step_sequence": [{"step_role": "rating"}],
        }
    )
    labels = survey_step_labels_from_config(cfg)
    assert labels == ["Check-in"]


def test_list_survey_orders_returns_non_interview_codes(app_client):
    headers, _org_id = _seed_user(app_client, email="survey_list_visibility@example.com")
    created = app_client.post(
        "/service-orders",
        headers=headers,
        json={"service_code": "survey", "title": "List visibility test", "config": {"delivery": "whatsapp"}},
    )
    assert created.status_code == 200
    order_id = created.json()["id"]

    res = app_client.get("/service-orders?service_code=survey", headers=headers)
    assert res.status_code == 200
    ids = [row["id"] for row in res.json()]
    assert order_id in ids


def test_conversation_service_has_no_legacy_final_feedback_yes_no_logs():
    path = Path(__file__).resolve().parents[1] / "app" / "services" / "survey_whatsapp_conversation_service.py"
    text = path.read_text(encoding="utf-8")
    assert "enabled_start_yes_no" not in text
    assert "yes_no_sent" not in text
    assert "yes_no_unparsed" not in text
    assert "enabled_start_open_text" in text
    assert "WA_FINAL_FEEDBACK_DIRECT_OPEN_TEXT_ACTIVE" in text
