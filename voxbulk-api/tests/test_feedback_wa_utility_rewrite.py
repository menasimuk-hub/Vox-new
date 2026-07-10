"""Feedback Convert regenerate — meta_template_name + non-English safety."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock

from app.core.database import get_sessionmaker
from app.models.customer_feedback import FeedbackWaTemplate
from app.services.customer_feedback.feedback_wa_utility_rewrite_service import (
    apply_utility_rewrite_to_feedback_row,
    rewrite_feedback_body,
)


def test_rewrite_feedback_body_preserves_spanish_without_meta_name_attr():
    """Regenerate must not read FeedbackWaTemplate.meta_name (does not exist)."""
    body = rewrite_feedback_body(
        MagicMock(),
        original_body="🌆 ¿Cómo calificarías el ambiente y la atmósfera de nuestro hotel?",
        buttons=["Malo", "Regular", "Bueno"],
        template_key="atmosphere",
        use_llm=False,
        language="es",
        industry_slug="hotel",
        template_name="cfs_hotel_atmosphere_es_v1",
        force_rewrite=True,
    )
    assert "¿Cómo calificarías" in body
    assert "how would you rate" not in body.lower()


def test_apply_utility_rewrite_feedback_uses_meta_template_name():
    Session = get_sessionmaker()
    with Session() as db:
        row = FeedbackWaTemplate(
            id=str(uuid.uuid4()),
            template_key="atmosphere",
            meta_template_name="cfs_hotel_atmosphere_es_v1",
            body_text="🌆 ¿Cómo calificarías el ambiente y la atmósfera de nuestro hotel?",
            language="es",
            buttons_json=json.dumps(["Malo", "Regular", "Bueno"]),
            meta_category="marketing",
            telnyx_sync_status="approved",
            is_active=True,
            step_order=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(row)
        db.commit()

        old_body, new_body = apply_utility_rewrite_to_feedback_row(
            db,
            row,
            use_llm=False,
            allow_marketing=True,
            force_rewrite=True,
        )
        assert "¿Cómo calificarías" in old_body
        assert "¿Cómo calificarías" in new_body
        assert str(row.meta_category).lower() == "utility"
        assert not hasattr(FeedbackWaTemplate, "meta_name")
