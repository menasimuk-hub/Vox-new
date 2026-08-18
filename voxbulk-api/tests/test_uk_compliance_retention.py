"""Per-org UK retention windows for messages, responses, recordings, and transcripts."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.core.security import hash_password
from app.services.uk_compliance_retention_service import ANONYMISED, UkComplianceRetentionService


def _org_user(db, *, name: str, email: str):
    from app.models.membership import OrganisationMembership
    from app.models.organisation import Organisation
    from app.models.user import User

    org = Organisation(name=name)
    db.add(org)
    db.flush()
    user = User(email=email, password_hash=hash_password("pass123"), is_active=True)
    db.add(user)
    db.flush()
    db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="owner"))
    db.flush()
    return user, org


def test_retention_honours_per_org_message_days():
    from app.core.database import get_sessionmaker
    from app.models.organisation_ai_config import OrganisationComplianceConfig
    from app.models.whatsapp_log import WhatsAppLog

    old = datetime.utcnow() - timedelta(days=40)
    with get_sessionmaker()() as db:
        _user_a, org_a = _org_user(db, name="Short retain", email="retain-a@example.com")
        _user_b, org_b = _org_user(db, name="Long retain", email="retain-b@example.com")
        db.add(
            OrganisationComplianceConfig(
                org_id=org_a.id,
                retention_days_messages=7,
                retention_days_responses=730,
                retention_days_recordings=90,
                retention_days_transcripts=365,
            )
        )
        db.add(
            OrganisationComplianceConfig(
                org_id=org_b.id,
                retention_days_messages=365,
                retention_days_responses=730,
                retention_days_recordings=90,
                retention_days_transcripts=365,
            )
        )
        log_a = WhatsAppLog(org_id=org_a.id, provider="telnyx", body="hello A", created_at=old)
        log_b = WhatsAppLog(org_id=org_b.id, provider="telnyx", body="hello B", created_at=old)
        db.add_all([log_a, log_b])
        db.commit()
        log_a_id, log_b_id = log_a.id, log_b.id

        dry = UkComplianceRetentionService.run_retention_pass(db, dry_run=True)
        assert dry["per_org_retention"] is True
        assert dry["whatsapp_logs_anonymised"] >= 1
        still_a = db.get(WhatsAppLog, log_a_id)
        still_b = db.get(WhatsAppLog, log_b_id)
        assert still_a is not None and still_a.body == "hello A"
        assert still_b is not None and still_b.body == "hello B"

        stats = UkComplianceRetentionService.run_retention_pass(db, dry_run=False)
        assert stats["whatsapp_logs_anonymised"] >= 1
        db.refresh(still_a)
        db.refresh(still_b)
        assert still_a.body == ANONYMISED
        assert still_b.body == "hello B"


def test_retention_redacts_aged_order_reports_per_org():
    from app.core.database import get_sessionmaker
    from app.models.organisation_ai_config import OrganisationComplianceConfig
    from app.models.service_order import ServiceOrder

    old = datetime.utcnow() - timedelta(days=60)
    with get_sessionmaker()() as db:
        user, org = _org_user(db, name="Transcript org", email="retain-t@example.com")
        db.add(
            OrganisationComplianceConfig(
                org_id=org.id,
                retention_days_messages=365,
                retention_days_responses=730,
                retention_days_recordings=90,
                retention_days_transcripts=14,
            )
        )
        order = ServiceOrder(
            org_id=org.id,
            user_id=user.id,
            service_code="interview",
            title="Aged interview",
            status="completed",
            completed_at=old,
            report_json='{"transcript": "keep-private"}',
        )
        db.add(order)
        db.commit()
        order_id = order.id

        UkComplianceRetentionService.run_retention_pass(db, dry_run=False)
        stored = db.get(ServiceOrder, order_id)
        assert stored is not None
        payload = json.loads(stored.report_json or "{}")
        assert payload.get("_retention_redacted") is True
        assert "keep-private" not in (stored.report_json or "")
