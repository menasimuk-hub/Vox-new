"""Shared Redis TTL cache — memory fallback only outside production."""

from __future__ import annotations

from app.services.airwallex_payment_service import AirwallexPaymentService
from app.services.redis_cache import cache_get, cache_set, reset_memory_cache


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def setex(self, key: str, _ttl: int, value: str):
        self.store[key] = value


def test_dev_falls_back_to_memory_when_redis_missing(monkeypatch):
    reset_memory_cache()
    monkeypatch.setattr("app.services.redis_cache._redis_client", lambda: None)
    monkeypatch.setattr("app.services.redis_cache.is_production_env", lambda _env=None: False)
    cache_set("survey_launch:demo", {"can_launch": True}, 5)
    assert cache_get("survey_launch:demo") == {"can_launch": True}


def test_production_does_not_use_per_worker_memory(monkeypatch):
    reset_memory_cache()
    monkeypatch.setattr("app.services.redis_cache._redis_client", lambda: None)
    monkeypatch.setattr("app.services.redis_cache.is_production_env", lambda _env=None: True)
    cache_set("survey_launch:demo", {"can_launch": True}, 5)
    assert cache_get("survey_launch:demo") is None


def test_redis_roundtrip(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr("app.services.redis_cache._redis_client", lambda: fake)
    cache_set("k", {"a": 1}, 10)
    assert cache_get("k") == {"a": 1}
    assert any(k.endswith("k") for k in fake.store)


def test_airwallex_token_shared_across_calls(monkeypatch):
    store: dict[str, str] = {}
    monkeypatch.setattr(
        "app.services.airwallex_payment_service.cache_get",
        lambda key: store.get(key),
    )
    monkeypatch.setattr(
        "app.services.airwallex_payment_service.cache_set",
        lambda key, value, _ttl: store.__setitem__(key, value),
    )
    monkeypatch.setattr(
        AirwallexPaymentService,
        "get_config",
        staticmethod(lambda _db: {"client_id": "cid", "api_key": "secret", "environment": "demo"}),
    )
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        def json(self):
            return {"token": "tok-shared"}

    def _post(*_a, **_k):
        calls["n"] += 1
        return _Resp()

    monkeypatch.setattr("app.services.airwallex_payment_service.httpx.post", _post)
    first, base = AirwallexPaymentService._bearer_token(None)
    second, _ = AirwallexPaymentService._bearer_token(None)
    assert base.endswith("airwallex.com")
    assert first == second == "tok-shared"
    assert calls["n"] == 1
