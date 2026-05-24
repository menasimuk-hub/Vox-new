from __future__ import annotations

import os

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient


@pytest.fixture()
def prod_cors_client():
    os.environ["ENV"] = "production"
    os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./.pytest-cors.db")
    os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
    os.environ.setdefault(
        "ENCRYPTION_KEY",
        "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
    )
    from app.core.config import get_settings

    get_settings.cache_clear()

    from importlib import reload
    import main

    reload(main)

    crash = APIRouter()

    @crash.get("/__test/crash")
    def _crash():
        raise RuntimeError("boom")

    main.app.include_router(crash)
    return TestClient(main.app, raise_server_exceptions=False)


ORIGIN = "https://dashboard.voxbulk.com"
PREFLIGHT_HEADERS = {
    "Origin": ORIGIN,
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "authorization,content-type,x-retover-org-id",
}


def test_cors_preflight_survey_gocardless_matches_billing(prod_cors_client):
    client = prod_cors_client
    billing = client.options("/billing/subscription/gocardless/start", headers=PREFLIGHT_HEADERS)
    survey = client.options(
        "/service-orders/00000000-0000-0000-0000-000000000001/gocardless/start",
        headers=PREFLIGHT_HEADERS,
    )
    assert billing.status_code == 200
    assert survey.status_code == 200
    assert billing.headers.get("access-control-allow-origin") == ORIGIN
    assert survey.headers.get("access-control-allow-origin") == ORIGIN
    assert "POST" in (survey.headers.get("access-control-allow-methods") or "")


def test_cors_on_unhandled_500(prod_cors_client):
    client = prod_cors_client
    res = client.get("/__test/crash", headers={"Origin": ORIGIN})
    assert res.status_code == 500
    assert res.headers.get("access-control-allow-origin") == ORIGIN
    assert res.json()["detail"] == "Internal server error"


def test_cors_on_survey_gocardless_auth_error(prod_cors_client):
    client = prod_cors_client
    res = client.post(
        "/service-orders/00000000-0000-0000-0000-000000000001/gocardless/start",
        headers={"Origin": ORIGIN, "Authorization": "Bearer invalid"},
    )
    assert res.status_code == 401
    assert res.headers.get("access-control-allow-origin") == ORIGIN
