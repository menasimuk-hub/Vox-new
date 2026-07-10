"""Tests for Meta/Telnyx template delete routing (no UUID as Meta hsm_id)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.meta_whatsapp_template_service import MetaWhatsappTemplateError, MetaWhatsappTemplateService
from app.services.wa_template_convert_service import _previous_was_seq_name


def test_previous_was_seq_name():
    assert (
        _previous_was_seq_name("was_retail_ecommerce_repeat_purchase_intent_002_en")
        == "was_retail_ecommerce_repeat_purchase_intent_001_en"
    )
    assert _previous_was_seq_name("was_retail_ecommerce_repeat_purchase_intent_001_en") is None


def test_meta_delete_drops_non_numeric_hsm_id_and_uses_name():
    db = MagicMock()
    calls: list[dict] = []

    def fake_graph(*, config, method, path, params, timeout=30.0):  # noqa: ARG001
        calls.append(dict(params))
        return {"success": True}

    with (
        patch(
            "app.services.meta_whatsapp_template_service.require_meta_whatsapp_primary",
            return_value={"waba_id": "WABA1", "access_token": "t"},
        ),
        patch(
            "app.services.meta_whatsapp_template_service.MetaWhatsappService._graph_request",
            side_effect=fake_graph,
        ),
    ):
        MetaWhatsappTemplateService.delete_message_template(
            db,
            name="was_retail_ecommerce_repeat_purchase_intent_001_en",
            hsm_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",  # Telnyx UUID — must not be sent
        )

    assert len(calls) == 1
    assert calls[0] == {"name": "was_retail_ecommerce_repeat_purchase_intent_001_en"}
    assert "hsm_id" not in calls[0]


def test_meta_delete_sends_numeric_hsm_with_name():
    db = MagicMock()
    calls: list[dict] = []

    def fake_graph(*, config, method, path, params, timeout=30.0):  # noqa: ARG001
        calls.append(dict(params))
        return {"success": True}

    with (
        patch(
            "app.services.meta_whatsapp_template_service.require_meta_whatsapp_primary",
            return_value={"waba_id": "WABA1", "access_token": "t"},
        ),
        patch(
            "app.services.meta_whatsapp_template_service.MetaWhatsappService._graph_request",
            side_effect=fake_graph,
        ),
    ):
        MetaWhatsappTemplateService.delete_message_template(
            db,
            name="was_x_001_en",
            hsm_id="meta-123456789012345",
        )

    assert calls[0]["name"] == "was_x_001_en"
    assert calls[0]["hsm_id"] == "123456789012345"
