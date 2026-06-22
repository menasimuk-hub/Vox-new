def test_bootstrap_requires_token(app_client):
    r = app_client.post(
        "/admin/bootstrap?organisation_name=Org&admin_email=a%40b.com&admin_password=pass123",
    )
    assert r.status_code in (401, 403)


def test_bootstrap_one_time(app_client):
    headers = {"X-Bootstrap-Token": "bootstrap-test-token"}
    r = app_client.post(
        "/admin/bootstrap?organisation_name=Org&admin_email=admin%40example.com&admin_password=pass123",
        headers=headers,
    )
    assert r.status_code == 200

    r2 = app_client.post(
        "/admin/bootstrap?organisation_name=Org2&admin_email=admin2%40example.com&admin_password=pass123",
        headers=headers,
    )
    assert r2.status_code == 409


def test_admin_webhook_events_requires_superuser(app_client):
    # no auth -> 401/403
    r = app_client.get("/admin/webhook-events")
    assert r.status_code in (401, 403)


def test_admin_provider_settings_encrypt_and_hide_secrets(app_client):
    from app.core.database import get_sessionmaker
    from app.core.security import hash_password
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    with get_sessionmaker()() as db:
        org = Organisation(name="Org")
        db.add(org); db.flush()
        admin = User(email="admin2@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(admin); db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=admin.id))
        db.commit()

    tok = app_client.post("/auth/token", data={"username": "admin2@example.com", "password": "pass123", "org_id": org.id}).json()["access_token"]
    headers = {"Authorization": f"Bearer {tok}"}

    secret = "super-secret"
    r = app_client.put(
        "/admin/integrations/openai",
        json={
            "is_enabled": True,
            "config": {
                "api_key": secret,
                "default_model": "gpt-4o-mini",
                "realtime_model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_output_tokens": 256,
            },
        },
        headers=headers,
    )
    assert r.status_code == 200
    assert secret not in str(r.json()).lower()

    from app.models.provider_config import ProviderConfig
    from sqlalchemy import select

    with get_sessionmaker()() as db:
        obj = db.execute(select(ProviderConfig).where(ProviderConfig.provider == "openai")).scalar_one()
        assert secret not in obj.encrypted_json


def test_admin_org_list_and_detail_are_superuser_only(app_client):
    from app.core.database import get_sessionmaker
    from app.core.security import hash_password
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User
    from app.models.branch import Branch
    from app.models.patient import Patient
    from app.models.dentally_appointment import DentallyAppointment
    from app.models.recovery_job import RecoveryJob
    from datetime import datetime, timezone

    with get_sessionmaker()() as db:
        org1 = Organisation(name="Org One")
        org2 = Organisation(name="Org Two")
        db.add_all([org1, org2])
        db.flush()

        # Tenant user (not superuser) in org1
        u = User(email="tenant@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=False)
        db.add(u)
        db.flush()
        db.add(OrganisationMembership(org_id=org1.id, user_id=u.id))

        # Superuser (membership still required by current auth dependency)
        su = User(email="su@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(su)
        db.flush()
        db.add(OrganisationMembership(org_id=org1.id, user_id=su.id))

        # Data counts for org2 (to validate admin sees non-tenant orgs)
        br = Branch(org_id=org2.id, name="B")
        db.add(br)
        db.flush()
        p = Patient(org_id=org2.id, branch_id=br.id, first_name="A", last_name="B")
        db.add(p)
        db.flush()
        appt = Appointment(org_id=org2.id, branch_id=br.id, patient_id=p.id, scheduled_start=datetime.now(timezone.utc))
        db.add(appt)
        db.flush()
        job = RecoveryJob(org_id=org2.id, appointment_id=appt.id, idempotency_key="k1", state="queued")
        db.add(job)
        db.commit()

    tenant_tok = app_client.post("/auth/token", data={"username": "tenant@example.com", "password": "pass123", "org_id": org1.id}).json()[
        "access_token"
    ]
    su_tok = app_client.post("/auth/token", data={"username": "su@example.com", "password": "pass123", "org_id": org1.id}).json()[
        "access_token"
    ]

    # Non-superuser forbidden
    r = app_client.get("/admin/organisations", headers={"Authorization": f"Bearer {tenant_tok}"})
    assert r.status_code == 403

    # Superuser can list all orgs
    r2 = app_client.get("/admin/organisations", headers={"Authorization": f"Bearer {su_tok}"})
    assert r2.status_code == 200
    items = r2.json()
    assert any(x["name"] == "Org One" for x in items)
    org2_item = next(x for x in items if x["name"] == "Org Two")
    assert org2_item["branch_count"] == 1
    assert org2_item["patient_count"] == 1
    assert org2_item["appointment_count"] == 1
    assert org2_item["recovery_job_count"] == 1

    # Detail
    r3 = app_client.get(f"/admin/organisations/{org2.id}", headers={"Authorization": f"Bearer {su_tok}"})
    assert r3.status_code == 200
    detail = r3.json()
    assert detail["id"] == org2.id
    assert detail["branch_count"] == 1


def test_admin_operations_and_billing_overviews(app_client):
    from app.core.database import get_sessionmaker
    from app.core.security import hash_password
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.plan import Plan
    from app.models.subscription import Subscription
    from app.models.user import User
    from app.models.webhook_event import WebhookEvent
    from datetime import datetime, timezone
    import json

    with get_sessionmaker()() as db:
        org = Organisation(name="Org")
        db.add(org)
        db.flush()
        su = User(email="su2@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(su)
        db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=su.id))

        # Webhook events
        db.add(WebhookEvent(provider="twilio", external_event_id="e1", dedupe_key="d1", org_id=org.id, raw_body=json.dumps({"a": 1}), status="received"))
        db.add(WebhookEvent(provider="twilio", external_event_id="e2", dedupe_key="d2", org_id=org.id, raw_body=json.dumps({"a": 2}), status="failed"))

        # Billing
        plan = Plan(code="solo", name="Solo", price_gbp_pence=9900, interval="monthly")
        db.add(plan)
        db.flush()
        db.add(Subscription(org_id=org.id, plan_id=plan.id, status="active", current_period_end=datetime.now(timezone.utc)))
        db.commit()

    tok = app_client.post("/auth/token", data={"username": "su2@example.com", "password": "pass123", "org_id": org.id}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    ops = app_client.get("/admin/operations/overview", headers=h)
    assert ops.status_code == 200
    body = ops.json()
    assert "webhooks" in body and "recovery_jobs" in body
    assert body["webhooks"]["total_recent"] >= 2

    bill = app_client.get("/admin/billing/overview", headers=h)
    assert bill.status_code == 200
    b = bill.json()
    assert b["plans_total"] >= 1
    assert b["subscriptions_total"] >= 1

    plans = app_client.get("/admin/billing/plans", headers=h)
    assert plans.status_code == 200
    assert any(p["code"] == "solo" for p in plans.json())


def test_self_serve_creates_active_account_immediately(app_client):
    r = app_client.post(
        "/auth/self-serve",
        json={
            "email": "selfserve@example.com",
            "password": "pass1234",
            "organisation_name": "Self Serve Clinic",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("access_token")
    assert body.get("org_id")

    r2 = app_client.post("/auth/token", data={"username": "selfserve@example.com", "password": "pass1234"})
    assert r2.status_code == 200


def test_admin_can_approve_legacy_onboarding_request(app_client):
    from app.core.database import get_sessionmaker
    from app.core.security import hash_password
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    # Seed superuser + membership for admin endpoints
    with get_sessionmaker()() as db:
        org = Organisation(name="Admin Org")
        db.add(org); db.flush()
        su = User(email="su-approve@example.com", password_hash=hash_password("pass123"), is_active=True, is_superuser=True)
        db.add(su); db.flush()
        db.add(OrganisationMembership(org_id=org.id, user_id=su.id))
        db.commit()

    tok = app_client.post("/auth/token", data={"username": "su-approve@example.com", "password": "pass123", "org_id": org.id}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    from app.core.database import get_sessionmaker
    from app.models.onboarding_request import OnboardingRequest
    from datetime import datetime

    with get_sessionmaker()() as db:
        pending_org = Organisation(name="Pending Clinic")
        db.add(pending_org)
        db.flush()
        pending_user = User(
            email="pending@example.com",
            password_hash=hash_password("pass1234"),
            is_active=False,
            is_superuser=False,
        )
        db.add(pending_user)
        db.flush()
        db.add(OrganisationMembership(org_id=pending_org.id, user_id=pending_user.id))
        req = OnboardingRequest(
            org_id=pending_org.id,
            user_id=pending_user.id,
            plan_code="starter",
            payment_method="bank_transfer",
            status="pending",
            created_at=datetime.utcnow(),
        )
        db.add(req)
        db.commit()
        req_id = req.id

    r2 = app_client.post("/auth/token", data={"username": "pending@example.com", "password": "pass1234"})
    assert r2.status_code == 401

    r3 = app_client.post(f"/admin/onboarding/requests/{req_id}/approve", headers=h)
    assert r3.status_code == 200

    r4 = app_client.post("/auth/token", data={"username": "pending@example.com", "password": "pass1234"})
    assert r4.status_code == 200

