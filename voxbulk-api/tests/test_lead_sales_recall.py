from __future__ import annotations

from datetime import datetime

from app.core.database import get_sessionmaker
from app.models.lead_sales_task import LeadSalesTask
from app.models.organisation import Organisation
from app.services.lead_sales_service import reset_sales_task_for_recall


def test_reset_sales_task_for_recall_clears_previous_call():
    with get_sessionmaker()() as db:
        org = Organisation(name="Recall Org")
        db.add(org)
        db.flush()
        task = LeadSalesTask(
            lead_id=org.id,
            status="completed",
            contact_name="Alex",
            phone="+447700900123",
            provider_call_id="cc-123",
            telnyx_conversation_id="conv-456",
            call_started_at=datetime.utcnow(),
            call_completed_at=datetime.utcnow(),
            sales_transcript_text="Agent: Hello",
            outcome_json='{"deal_stage":"follow_up"}',
            offer_promo_code="SALE123",
            offer_sent_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(task)
        db.commit()

        reset = reset_sales_task_for_recall(db, task)

        assert reset.status == "scheduled"
        assert reset.provider_call_id is None
        assert reset.telnyx_conversation_id is None
        assert reset.sales_transcript_text is None
        assert reset.outcome_json is None
        assert reset.offer_promo_code == "SALE123"
        assert reset.offer_sent_at is not None
