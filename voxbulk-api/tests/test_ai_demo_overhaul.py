"""AI Demo overhaul: spoken identity, pricing tabs, demo view-only writes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.dependencies import _assert_demo_writes_blocked
from app.services.ai_demo_org_service import packages_route_for_service, pricing_tab_for_service
from app.services.ai_demo_service import AiDemoError, resolve_spoken_display_name, sanitize_user_facing_text


def test_spoken_display_name_from_voice_label():
    assert resolve_spoken_display_name(voice_label="Leo") == "Leo"
    assert resolve_spoken_display_name(voice_label="Leo (GB)") == "Leo"
    assert resolve_spoken_display_name(voice_label="  Amira — MENA ") == "Amira"


def test_spoken_display_name_rejects_missing_and_slug():
    with pytest.raises(AiDemoError) as missing:
        resolve_spoken_display_name(voice_label=None, agent_name="AI Demo — interview_GB-Leo")
    assert missing.value.status_code == 503

    with pytest.raises(AiDemoError):
        resolve_spoken_display_name(voice_label="interview_GB-Leo", agent_name="Leo")


def test_sanitize_strips_unresolved_placeholders():
    out = sanitize_user_facing_text("Hi {contact_name}, welcome to {company}")
    assert "{" not in out
    assert "}" not in out
    assert "Hi" in out


@pytest.mark.parametrize(
    "service,tab",
    [
        ("feedback", "feedback"),
        ("customer_feedback", "feedback"),
        ("expo", "expo"),
        ("smart_card", "smartCard"),
        ("recruitment", "core"),
        ("surveys", "core"),
        ("interview", "core"),
        (None, "core"),
    ],
)
def test_pricing_tab_for_service(service, tab):
    assert pricing_tab_for_service(service) == tab
    assert packages_route_for_service(service) == f"/account/packages?tab={tab}"


def _principal(*, demo: bool) -> SimpleNamespace:
    payload = {"demo_access": True, "demo_session_id": "sess-1"} if demo else {"sub": "user-1"}
    return SimpleNamespace(token_payload=payload)


def _request(method: str, path: str) -> MagicMock:
    req = MagicMock()
    req.method = method
    req.url.path = path
    return req


def test_demo_jwt_blocks_mutating_dashboard_apis():
    with pytest.raises(HTTPException) as exc:
        _assert_demo_writes_blocked(_request("POST", "/organisations/me"), _principal(demo=True))
    assert exc.value.status_code == 403
    assert "view-only" in str(exc.value.detail).lower()


def test_demo_jwt_allows_get_and_ai_demo_writes():
    _assert_demo_writes_blocked(_request("GET", "/organisations/me"), _principal(demo=True))
    _assert_demo_writes_blocked(_request("POST", "/ai-demo/sessions/x/events"), _principal(demo=True))
    _assert_demo_writes_blocked(_request("POST", "/auth/logout"), _principal(demo=True))


def test_normal_jwt_can_mutate():
    _assert_demo_writes_blocked(_request("POST", "/organisations/me"), _principal(demo=False))
