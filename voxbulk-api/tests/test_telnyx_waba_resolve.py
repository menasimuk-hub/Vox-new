"""Resolve Telnyx WhatsApp Business Account id for template push."""

from __future__ import annotations

from app.core.database import get_sessionmaker
from app.services.telnyx_voice_service import resolve_telnyx_whatsapp_waba_id


def test_resolve_waba_from_config():
    with get_sessionmaker()() as db:
        waba = resolve_telnyx_whatsapp_waba_id(
            db,
            {"api_key": "KEY_test", "whatsapp_waba_id": "2019979452207634"},
        )
        assert waba == "2019979452207634"


def test_resolve_waba_from_telnyx_api(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"id": "uuid-internal", "waba_id": "2019979452207634", "status": "APPROVED"},
                ]
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None, params=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.telnyx_voice_service.httpx.Client", lambda *a, **k: FakeClient())

    with get_sessionmaker()() as db:
        waba = resolve_telnyx_whatsapp_waba_id(db, {"api_key": "KEY_test"})
        assert waba == "2019979452207634"


def test_resolve_waba_prefers_template_row_id():
    with get_sessionmaker()() as db:
        waba = resolve_telnyx_whatsapp_waba_id(
            db,
            {"api_key": "KEY_test"},
            template_waba_id="row-stored-waba",
        )
        assert waba == "row-stored-waba"


def test_resolve_waba_filter_maps_meta_numeric_to_telnyx_uuid(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {
                        "id": "04904dc8-681e-4860-ab34-147f79dc9a10",
                        "waba_id": "959487190007928",
                        "status": "APPROVED",
                    },
                ]
            }

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url, headers=None, params=None):
            return FakeResponse()

    monkeypatch.setattr("app.services.telnyx_voice_service.httpx.Client", lambda *a, **k: FakeClient())

    with get_sessionmaker()() as db:
        from app.services.telnyx_voice_service import resolve_telnyx_whatsapp_waba_filter_id

        waba = resolve_telnyx_whatsapp_waba_filter_id(
            db,
            {"api_key": "KEY_test", "waba_id": "959487190007928"},
        )
        assert waba == "04904dc8-681e-4860-ab34-147f79dc9a10"
