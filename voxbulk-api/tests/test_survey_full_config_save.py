"""Survey draft full-config persistence and launch billing codes."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.core.security import hash_password
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.platform_catalog_service import PlatformCatalogService


def _seed_user(app_client, *, email: str = "survey_full_config@example.com"):
    with get_sessionmaker()() as db:
        PlatformCatalogService.ensure_defaults(db)
        org = Organisation(name="Full Config Clinic")
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
    return {"Authorization": f"Bearer {token}"}


def test_full_survey_config_survives_name_only_patch(app_client):
    headers = _seed_user(app_client)
    survey_name = "Patient satisfaction follow-up"
    goal = "Measure satisfaction with our new hygienist team."
    builder_sequence = [{"step_role": "rating", "text": "Rate your visit today"}]
    create = app_client.post(
        "/service-orders",
        headers=headers,
        json={
            "service_code": "survey",
            "config": {
                "delivery": "whatsapp",
                "survey_channel": "whatsapp",
                "survey_name": survey_name,
                "goal": goal,
                "industry_id": "1",
                "selected_survey_type_ids": ["svc_checkin"],
                "selected_service_template_ids": {"svc_checkin": 42},
                "welcome_template_id": 10,
                "thank_you_template_id": 11,
                "page_count": 5,
                "privacy_mode": "off",
                "allow_final_additional_feedback": True,
                "builder_step_sequence": builder_sequence,
                "builder_template_ids": [10, 42, 11],
                "package_id": "payg_whatsapp",
            },
        },
    )
    assert create.status_code == 200, create.text
    order_id = create.json()["id"]

    patched = app_client.patch(
        f"/service-orders/{order_id}",
        headers=headers,
        json={"config": {"survey_name": "Renamed campaign", "delivery": "whatsapp", "goal": goal}},
    )
    assert patched.status_code == 200, patched.text

    reload = app_client.get(f"/service-orders/{order_id}", headers=headers).json()
    cfg = reload["config"]
    assert reload.get("survey_name") == "Renamed campaign"
    assert cfg.get("goal") == goal
    assert cfg.get("selected_survey_type_ids") == ["svc_checkin"]
    assert cfg.get("selected_service_template_ids") == {"svc_checkin": 42}
    assert cfg.get("welcome_template_id") == 10
    assert cfg.get("thank_you_template_id") == 11
    assert cfg.get("page_count") == 5
    assert cfg.get("allow_final_additional_feedback") is True
    seq = cfg.get("builder_step_sequence") or []
    assert len(seq) == 1
    assert seq[0].get("step_role") == "rating"
    assert seq[0].get("text") == "Rate your visit today"
    assert cfg.get("builder_template_ids") == [10, 42, 11]
    assert cfg.get("package_id") == "payg_whatsapp"


def test_full_survey_config_patch_updates_wizard_fields(app_client):
    headers = _seed_user(app_client, email="survey_full_patch@example.com")
    create = app_client.post(
        "/service-orders",
        headers=headers,
        json={
            "service_code": "survey",
            "config": {
                "delivery": "whatsapp",
                "survey_name": "Initial",
                "goal": "Old goal",
                "privacy_mode": "off",
            },
        },
    )
    assert create.status_code == 200
    order_id = create.json()["id"]

    patched = app_client.patch(
        f"/service-orders/{order_id}",
        headers=headers,
        json={
            "config": {
                "survey_name": "Updated campaign",
                "delivery": "whatsapp",
                "survey_channel": "whatsapp",
                "goal": "New goal",
                "privacy_mode": "on",
                "allow_final_additional_feedback": True,
                "selected_survey_type_ids": ["svc_nps"],
                "page_count": 4,
                "auto_select_steps": False,
                "selected_step_roles": ["start", "rating", "completion"],
            },
        },
    )
    assert patched.status_code == 200, patched.text
    cfg = app_client.get(f"/service-orders/{order_id}", headers=headers).json()["config"]
    assert cfg["survey_name"] == "Updated campaign"
    assert cfg["goal"] == "New goal"
    assert cfg["privacy_mode"] == "on"
    assert cfg["allow_final_additional_feedback"] is True
    assert cfg["selected_survey_type_ids"] == ["svc_nps"]
    assert cfg["page_count"] == 4
    assert cfg["selected_step_roles"] == ["start", "rating", "completion"]


def test_launch_eligibility_no_recipients_has_block_code(app_client):
    headers = _seed_user(app_client, email="survey_block_code@example.com")
    create = app_client.post(
        "/service-orders",
        headers=headers,
        json={"service_code": "survey", "config": {"delivery": "whatsapp", "survey_name": "Empty"}},
    )
    assert create.status_code == 200
    order_id = create.json()["id"]

    res = app_client.get(f"/service-orders/{order_id}/launch-eligibility", headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["block_reason_code"] == "no_recipients"
    assert body["launch_action"] == "blocked"
