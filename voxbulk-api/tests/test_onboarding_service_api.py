from __future__ import annotations

from app.core.security import hash_password


def _seed_user_org(db, *, email: str = "onboarding@example.com", superuser: bool = False):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name="Onboarding Clinic")
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True, is_superuser=superuser)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.commit()
    return user, org


def _token(app_client, user, org):
    res = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org.id})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_admin_services_api_defaults_and_crud(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_user_org(db, email="service-admin@example.com", superuser=True)
    headers = {"Authorization": f"Bearer {_token(app_client, user, org)}"}

    listed = app_client.get("/admin/services-api", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert {row["slug"] for row in rows} >= {"dentally", "carestack", "pabau", "cliniko", "optix", "ocuco"}
    dentally = next(row for row in rows if row["slug"] == "dentally")
    assert dentally["category_slug"] == "dental"
    assert dentally["status"] == "active"

    created = app_client.post(
        "/admin/services-api",
        json={
            "slug": "test-booking",
            "display_name": "Test Booking",
            "category_slug": "dental",
            "short_description": "Test booking source",
            "status": "inactive",
            "is_active": False,
        },
        headers=headers,
    )
    assert created.status_code == 200
    assert created.json()["slug"] == "test-booking"

    enabled = app_client.post("/admin/services-api/test-booking/enable", headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()["is_active"] is True
    assert enabled.json()["status"] == "active"


def test_onboarding_category_software_and_status_transitions(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_user_org(db)
    headers = {"Authorization": f"Bearer {_token(app_client, user, org)}"}

    status = app_client.get("/onboarding/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["onboarding_state"] == "account_created"
    assert status.json()["next_step"] == "select_category"

    categories = app_client.get("/onboarding/categories", headers=headers)
    assert categories.status_code == 200
    assert {row["slug"] for row in categories.json()} == {"aesthetics", "dental", "opticians"}

    selected_category = app_client.post("/onboarding/select-category", json={"category_slug": "dental"}, headers=headers)
    assert selected_category.status_code == 200
    assert selected_category.json()["onboarding_state"] == "category_selected"
    assert selected_category.json()["category_slug"] == "dental"

    software = app_client.get("/onboarding/software-options?category=dental", headers=headers)
    assert software.status_code == 200
    assert [row["slug"] for row in software.json()] == ["dentally", "carestack"]

    selected_software = app_client.post("/onboarding/select-software", json={"software_slug": "dentally"}, headers=headers)
    assert selected_software.status_code == 200
    assert selected_software.json()["onboarding_state"] == "software_selected"
    assert selected_software.json()["booking_software_slug"] == "dentally"


def test_onboarding_wizard_generates_workflow_profiles(app_client):
    from app.core.database import get_sessionmaker

    with get_sessionmaker()() as db:
        user, org = _seed_user_org(db, email="wizard@example.com")
    headers = {"Authorization": f"Bearer {_token(app_client, user, org)}"}

    app_client.post("/onboarding/select-category", json={"category_slug": "aesthetics"}, headers=headers)
    app_client.post("/onboarding/select-software", json={"software_slug": "pabau"}, headers=headers)

    payload = {
        "step": "complete",
        "services": ["consultation", "Botox"],
        "custom_services": ["skin booster"],
        "ai_identity": {
            "assistant_name": "Ava",
            "organisation_name": "Glow Clinic",
            "tone": "premium",
            "humor_level": "low",
            "languages": ["en-GB"],
            "terminology_label": "client",
            "disclose_ai": True,
        },
        "compliance": {
            "outbound_call_windows": {"weekdays": {"start": "09:30", "end": "17:30"}},
            "whatsapp_windows": {"weekdays": {"start": "09:00", "end": "18:00"}},
            "weekend_allowed": False,
            "escalation_destination": "front desk",
        },
        "workflows": [
            {
                "workflow_key": "appointment_reminder",
                "enabled": True,
                "channels": ["whatsapp"],
                "timing_rules": {"before_appointment": {"days": 2}},
            }
        ],
    }
    completed = app_client.post("/onboarding/wizard/complete", json=payload, headers=headers)
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"]["onboarding_state"] == "onboarding_completed"
    assert body["status"]["onboarding_complete"] is True
    assert body["services"] == ["Botox", "consultation", "skin booster"]
    workflow = body["workflows"][0]
    assert workflow["workflow_key"] == "appointment_reminder"
    assert workflow["generated_profile"]["booking_software_context"]["display_name"] == "Pabau"
    assert workflow["generated_profile"]["terminology_rules"]["customer_label"] == "client"
    assert "Glow Clinic" in workflow["generated_prompt_preview"]
    assert "Pabau remains the source of truth" in workflow["generated_prompt_preview"]

    me = app_client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["onboarding_complete"] is True

