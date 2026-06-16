"""Waiter pipeline integration tests."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.abuu.services.order_draft_service import AbuuOrderDraftService
from app.abuu.services.seed_service import AbuuSeedService
from app.abuu.waiter.pipeline import WaiterPipeline


@pytest.fixture
def abuu_seeded(app_client):
    from app.core.abuu_database import get_abuu_sessionmaker

    with get_abuu_sessionmaker()() as db:
        AbuuSeedService.seed_restaurants_if_empty(db)
        AbuuSeedService.seed_offers_if_empty(db)
        db.commit()
        yield db


def test_waiter_pipeline_greet_no_internal_ids(abuu_seeded):
    from app.core.abuu_database import get_abuu_sessionmaker
    from app.core.database import get_sessionmaker

    phone = "+972509991201"
    with get_abuu_sessionmaker()() as abuu_db, get_sessionmaker()() as main_db:
        AbuuOrderDraftService.get_or_create_customer(abuu_db, phone, lang="ar")
        abuu_db.commit()
        with patch.dict(
            os.environ,
            {
                "ABUU_AGENT_ENABLED": "true",
                "ABUU_CONVERSATION_MODE": "waiter_v2",
                "ABUU_DEEPSEEK_ENABLED": "false",
            },
        ):
            from app.core.config import get_settings

            get_settings.cache_clear()
            assert WaiterPipeline.enabled_for_phone(phone) is True
            result = WaiterPipeline.handle(
                abuu_db,
                main_db,
                phone=phone,
                text="yallasay",
            )
            abuu_db.commit()
    assert result.get("handled")
    reply = result.get("reply", "")
    assert "[id=" not in reply
    assert "abuu-rest-" not in reply


def test_waiter_enabled_respects_allowlist():
    with patch.dict(
        os.environ,
        {
            "ABUU_AGENT_ENABLED": "true",
            "ABUU_CONVERSATION_MODE": "waiter_v2",
            "ABUU_WAITER_V2_ALLOWLIST": "+972500000001",
        },
    ):
        from app.core.config import get_settings

        get_settings.cache_clear()
        assert WaiterPipeline.enabled_for_phone("+972500000001") is True
        assert WaiterPipeline.enabled_for_phone("+972500000002") is False
        get_settings.cache_clear()
