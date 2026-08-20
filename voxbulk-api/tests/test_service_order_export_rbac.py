from __future__ import annotations

from app.core.security import hash_password


def _seed_user_org(db, *, email: str, role: str):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name=f"{role.title()} Org")
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role=role))
    db.commit()
    return user, org


def _token(app_client, user, org_id: str) -> str:
    res = app_client.post("/auth/token", data={"username": user.email, "password": "pass123", "org_id": org_id})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def test_accountant_blocked_from_service_order_pii_exports(app_client):
    from app.core.database import get_sessionmaker
    from app.models.service_order import ServiceOrder, ServiceOrderRecipient
    from app.models.survey_voice_note_job import SurveyVoiceNoteJob

    with get_sessionmaker()() as db:
        user, org = _seed_user_org(db, email="acct-pii@example.com", role="accountant")
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="survey",
            title="Survey PII",
            status="completed",
        )
        db.add(order)
        db.flush()
        recipient = ServiceOrderRecipient(
            order_id=order.id,
            row_number=1,
            name="Pat Example",
            phone="+447700900999",
            email="pat@example.com",
            status="completed",
            result_json="{}",
        )
        db.add(recipient)
        db.flush()
        voice_job = SurveyVoiceNoteJob(
            org_id=org.id,
            order_id=order.id,
            recipient_id=recipient.id,
            inbound_message_id="inb-1",
            provider_media_id="media-1",
            audio_file_path="missing.ogg",
        )
        db.add(voice_job)
        db.commit()

    headers = {"Authorization": f"Bearer {_token(app_client, user, org.id)}"}
    assert app_client.get(f"/service-orders/{order.id}/survey-results/export.csv", headers=headers).status_code == 403
    assert app_client.get(f"/service-orders/{order.id}/interview-report", headers=headers).status_code == 403
    assert (
        app_client.get(
            f"/service-orders/{order.id}/survey-voice-notes/{voice_job.id}/audio",
            headers=headers,
        ).status_code
        == 403
    )
