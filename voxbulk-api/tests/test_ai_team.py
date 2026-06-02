"""Basic AI Team admin API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.admin_rbac import CAP_AI_TEAM, role_has_cap
from main import app


def test_marketing_has_ai_team_cap():
    assert role_has_cap("marketing", CAP_AI_TEAM)
    assert role_has_cap("superadmin", CAP_AI_TEAM)
    assert not role_has_cap("accountant", CAP_AI_TEAM)


@pytest.fixture
def client():
    return TestClient(app)


def test_ai_team_dashboard_requires_auth(client):
    resp = client.get("/admin/ai-team/dashboard")
    assert resp.status_code in (401, 403)
