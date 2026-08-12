"""AI Demo overhaul: spoken identity, pricing tabs, demo view-only writes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.dependencies import _assert_demo_writes_blocked
from app.services.ai_demo_org_service import (
    normalize_demo_start_path,
    packages_route_for_service,
    pricing_tab_for_service,
    resolve_demo_route,
    resolve_demo_ui_step,
)
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


def test_resolve_demo_ui_step_catalog():
    step = resolve_demo_ui_step("feedback_create")
    assert step is not None
    assert step["route"] == "/feedback/new"
    assert step["target_element_id"] == "feedback-new"
    assert "Create" in step["label"]
    assert resolve_demo_ui_step("packages_feedback")["route"] == "/account/packages?tab=feedback"
    assert resolve_demo_ui_step("nope") is None


def test_demo_highlight_intent_view_vs_click():
    from app.services.ai_demo_org_service import demo_highlight_intent

    assert demo_highlight_intent(step="home_kpis") == "view"
    assert demo_highlight_intent(target_element_id="home-live-activity") == "view"
    assert demo_highlight_intent(step="feedback_results", target_element_id="feedback-results") == "view"
    assert demo_highlight_intent(step="nav_feedback_results") == "click"
    assert demo_highlight_intent(target_element_id="nav-feedback-compare") == "click"
    assert demo_highlight_intent(step="results_overview") == "click"
    assert demo_highlight_intent(step="feedback_create", target_element_id="feedback-new") == "view"


def test_highlight_defaults_to_spotlight_without_route():
    from app.services.ai_demo_org_service import resolve_demo_ui_step

    step = resolve_demo_ui_step("home_kpis")
    assert step is not None
    assert step["target_element_id"] == "home-live-kpis"
    assert resolve_demo_ui_step("nav_feedback_results")["route"] == "/feedback/results"
    assert resolve_demo_ui_step("results_overview")["target_element_id"] == "results-tab-overview"


def test_demo_jwt_allows_feedback_location_create_only():
    _assert_demo_writes_blocked(_request("POST", "/customer-feedback/locations"), _principal(demo=True))
    _assert_demo_writes_blocked(_request("POST", "/customer-feedback/locations/preview"), _principal(demo=True))
    with pytest.raises(HTTPException):
        _assert_demo_writes_blocked(_request("PATCH", "/customer-feedback/locations/abc"), _principal(demo=True))
    with pytest.raises(HTTPException):
        _assert_demo_writes_blocked(_request("DELETE", "/customer-feedback/locations/abc"), _principal(demo=True))


def test_coach_script_mentions_home_kpis():
    from app.data.ai_demo_coach_script import COACH_TOUR_MAP

    assert "home_kpis" in COACH_TOUR_MAP
    assert "VIEW" in COACH_TOUR_MAP
    assert "Campaign dashboard" in COACH_TOUR_MAP
    assert "NEVER say" in COACH_TOUR_MAP or "never say" in COACH_TOUR_MAP.lower()


def test_opening_gate_and_consent_first_greeting():
    from app.services.ai_demo_service import OPENING_GATE

    assert "Welcome the visitor" in OPENING_GATE or "welcome" in OPENING_GATE.lower()
    assert "recorded" in OPENING_GATE.lower()
    assert "ready" in OPENING_GATE.lower()
    assert "highlight_dashboard" in OPENING_GATE


def test_normalize_demo_start_path_rejects_fake_dashboard():
    assert normalize_demo_start_path("/dashboard") == "/"
    assert normalize_demo_start_path("/dashboard?x=1") == "/?x=1"
    assert normalize_demo_start_path("/") == "/"
    assert normalize_demo_start_path("/feedback") == "/feedback"
    assert normalize_demo_start_path("/account/packages?tab=feedback") == "/account/packages?tab=feedback"
    assert normalize_demo_start_path("/nope") == "/"
    assert resolve_demo_route(section="dashboard") == "/"
    assert resolve_demo_route(section="home") == "/"
    assert resolve_demo_route(target="/dashboard") == "/"
