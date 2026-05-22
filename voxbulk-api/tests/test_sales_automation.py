from __future__ import annotations

from datetime import datetime, timedelta
import uuid

from app.core.database import get_sessionmaker
from app.models.lead_sales_setting import LeadSalesSetting
from app.models.lead_sales_task import LeadSalesTask
from app.models.organisation import Organisation
from app.services.sales_automation_service import SalesAutomationService, _OFFER_KEYWORD_RE, _STOP_RE


def test_offer_keyword_regex():
    assert _OFFER_KEYWORD_RE.search("send me offer")
    assert _OFFER_KEYWORD_RE.search("SEND OFFER please")
    assert _OFFER_KEYWORD_RE.search("yes send the offer")
    assert not _OFFER_KEYWORD_RE.search("hello there")


def test_stop_keyword_regex():
    assert _STOP_RE.search("stop")
    assert _STOP_RE.search("please unsubscribe")
    assert not _STOP_RE.search("send offer")


def test_handle_inbound_send_offer_keyword(app_client, monkeypatch):
    def fake_send_whatsapp(db, *, to_number, body, **kwargs):
        from app.services.telnyx_messaging_service import TelnyxMessageResult

        return TelnyxMessageResult(ok=True, status="queued", external_id="msg-1", channel="whatsapp")

    monkeypatch.setattr("app.services.sales_automation_service.TelnyxMessagingService.send_whatsapp", fake_send_whatsapp)
    monkeypatch.setattr(
        "app.services.sales_automation_service.SalesAutomationService._platform_org_id",
        lambda db: None,
    )
    monkeypatch.setattr(
        "app.services.sales_offer_send_service.TransactionalEmailService.send_templated_optional",
        lambda *a, **k: (True, None),
    )
    monkeypatch.setattr(
        "app.services.sales_whatsapp_send_service.send_sales_whatsapp",
        lambda *a, **k: __import__(
            "app.services.telnyx_messaging_service", fromlist=["TelnyxMessageResult"]
        ).TelnyxMessageResult(ok=True, status="queued", external_id="msg-1", channel="whatsapp"),
    )

    with get_sessionmaker()() as db:
        from app.models.sales_offer_template import SalesOfferTemplate

        org = Organisation(name="Auto Org")
        db.add(org)
        db.flush()
        settings = db.get(LeadSalesSetting, "default")
        if settings is None:
            settings = LeadSalesSetting(id="default", updated_at=datetime.utcnow())
            db.add(settings)
        settings.sales_automation_enabled = True
        db.add(
            SalesOfferTemplate(
                id=str(uuid.uuid4()),
                name="Test subscription offer",
                offer_type="dental_trial",
                plan_code="dental_1",
                trial_days=15,
                is_active=True,
                sort_order=1,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        task = LeadSalesTask(
            lead_id=org.id,
            status="completed",
            contact_name="Alex Test",
            phone="+447700900123",
            email="alex@example.com",
            outcome_json='{"deal_stage":"not_interested"}',
            call_completed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(task)
        db.commit()
        phone = task.phone

        result = SalesAutomationService.handle_inbound_whatsapp(db, from_phone=phone, body="send me offer")
        assert result.get("action") == "send_offer"
        db.refresh(task)
        assert task.offer_promo_code
        assert task.offer_sent_at


def test_should_auto_offer_when_demo_agreed():
    task = LeadSalesTask(
        lead_id="x",
        status="completed",
        outcome_json='{"deal_stage":"follow_up","demo_agreed":true}',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    outcome = SalesAutomationService._parse_outcome(task)
    assert SalesAutomationService._should_auto_offer(task, outcome, call_status="completed") is True


def test_should_auto_offer_after_real_conversation():
    task = LeadSalesTask(
        lead_id="x",
        status="completed",
        sales_transcript_text="Agent: Hi Alex. Prospect: Yes we want to try the dental plan for our clinic.",
        outcome_json='{"deal_stage":"no_answer"}',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    outcome = SalesAutomationService._parse_outcome(task)
    assert SalesAutomationService._should_auto_offer(task, outcome, call_status="completed") is True


def test_process_due_followups_skips_redeemed(app_client, monkeypatch):
    monkeypatch.setattr(
        "app.services.sales_automation_service.SalesAutomationService._send_whatsapp",
        lambda *a, **k: (True, None),
    )

    with get_sessionmaker()() as db:
        org = Organisation(name="Follow Org")
        db.add(org)
        db.flush()
        task = LeadSalesTask(
            lead_id=org.id,
            status="completed",
            contact_name="Redeemed Lead",
            phone="+447700900999",
            email="redeemed@example.com",
            offer_promo_code="SALETEST1",
            offer_sent_at=datetime.utcnow() - timedelta(days=8),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(task)
        db.flush()

        from app.models.promo_offer import PromoOffer

        promo = PromoOffer(
            code="SALETEST1",
            name="Test",
            offer_type="dental_trial",
            plan_code="dental_1",
            trial_days=15,
            max_redemptions=1,
            redemption_count=1,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(promo)
        db.flush()

        state = SalesAutomationService.mark_offer_sent(db, task=task, promo=promo, followup_days=7)
        state.followup_due_at = datetime.utcnow() - timedelta(hours=1)
        db.add(state)
        db.commit()

        stats = SalesAutomationService.process_due_followups(db)
        assert stats["skipped"] >= 1
