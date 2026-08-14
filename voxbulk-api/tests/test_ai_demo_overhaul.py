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
    assert step["target_element_id"] == "wizard-industry"
    assert "industry" in step["label"].lower()
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
    assert demo_highlight_intent(step="feedback_create", target_element_id="wizard-industry") == "view"
    assert demo_highlight_intent(step="wizard_next") == "click"
    assert demo_highlight_intent(step="home_second_row") == "view"
    assert demo_highlight_intent(step="results_top_menus") == "view"


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


def test_coach_script_is_voice_gated_sales():
    from app.data.ai_demo_coach_script import COACH_TOUR_MAP, DEMO_TOUR_BEATS, memory_tour_lock

    assert DEMO_TOUR_BEATS[0]["id"] == "home_kpis"
    assert DEMO_TOUR_BEATS[0]["intent"] == "view"
    assert DEMO_TOUR_BEATS[0]["target"] == "home-live-kpis"
    assert any(b["id"] == "results_tab_overview" for b in DEMO_TOUR_BEATS)
    assert any(b["target"] == "results-tab-questions" for b in DEMO_TOUR_BEATS)
    assert any(b["id"] == "feedback_compare_title" for b in DEMO_TOUR_BEATS)
    assert any(b["id"] == "wizard_industry" for b in DEMO_TOUR_BEATS)
    assert not any(b["id"] == "results_top_menus" for b in DEMO_TOUR_BEATS)
    assert all(str(b.get("ask") or "").strip() for b in DEMO_TOUR_BEATS)
    lock = memory_tour_lock(
        {
            "current_beat": "home_kpis",
            "current_label": "Live KPIs",
            "current_talk": DEMO_TOUR_BEATS[0]["talk"],
        }
    )
    assert "Live KPIs" in lock
    assert "salesperson" in lock.lower() or "Sell this" in lock
    assert "Do not hang up" in lock
    assert "done" in lock.lower()
    assert "Click here" not in lock
    assert "voice-gated" in COACH_TOUR_MAP.lower() or "spoken" in COACH_TOUR_MAP.lower()
    assert "salesperson" in COACH_TOUR_MAP.lower() or "sales" in COACH_TOUR_MAP.lower()
    assert "done" in COACH_TOUR_MAP.lower()
    assert "silent" in COACH_TOUR_MAP.lower()
    assert "wizard" in COACH_TOUR_MAP.lower()
    assert "I clicked Next" in COACH_TOUR_MAP  # warned against as unreliable path
    assert "pricing" in COACH_TOUR_MAP.lower()
    assert "NOT hang up" in COACH_TOUR_MAP or "Do NOT hang up" in COACH_TOUR_MAP


def test_highlight_dashboard_starts_then_locks(monkeypatch):
    import json

    from app.services.ai_demo_service import AiDemoService

    session = SimpleNamespace(
        id="sess-1",
        request_id="req-1",
        active_service_code="feedback",
        language="en",
        services_explored="[]",
    )
    req = SimpleNamespace(conversation_memory="{}")
    events: list = []

    monkeypatch.setattr(AiDemoService, "_resolve_tool_session", staticmethod(lambda db, payload: session))
    monkeypatch.setattr(AiDemoService, "get_request", staticmethod(lambda db, rid: req))
    monkeypatch.setattr(AiDemoService, "update_memory", staticmethod(lambda db, r, patch: events.append(("mem", patch))))
    monkeypatch.setattr(AiDemoService, "_append_ui_event", staticmethod(lambda db, sess, ev: events.append(("ui", ev))))

    first = AiDemoService.handle_tool(
        MagicMock(),
        tool_name="highlight_dashboard",
        payload={"session_id": "sess-1", "step": "nav_feedback_results", "action": "navigate"},
    )
    assert first["target_element_id"] == "home-live-kpis"
    assert first["label"] == "Live KPIs"
    assert first["action"] == "highlight"
    ui = next(item[1] for item in events if item[0] == "ui")
    assert ui["target_element_id"] == "home-live-kpis"
    assert ui.get("route") in (None, "")

    req.conversation_memory = json.dumps(
        {
            "tour_started": True,
            "current_beat": "home_kpis",
            "current_label": "Live KPIs",
            "current_talk": "These live KPIs update as customers reply — scores, volume, and alerts in one strip.",
        }
    )
    events.clear()
    restored = AiDemoService.handle_tool(
        MagicMock(),
        tool_name="highlight_dashboard",
        payload={"session_id": "sess-1", "step": "nav_feedback_results", "action": "navigate"},
    )
    assert restored["action"] == "restore"
    assert restored["target_element_id"] == "home-live-kpis"
    assert "Live KPIs" in restored["message"]
    assert "sales" in restored["message"].lower() or "Sell" in restored["message"] or "SPEAK" in restored["message"]
    assert "done" in restored["message"].lower() or "SPEAK" in restored["message"]
    assert restored.get("force_speak", {}).get("status") == "scheduled"
    ui = next(item[1] for item in events if item[0] == "ui")
    assert ui["action"] == "restore"
    assert ui["target_element_id"] == "home-live-kpis"


def test_end_demo_refuses_after_pricing(monkeypatch):
    import json

    from app.services.ai_demo_service import AiDemoService

    session = SimpleNamespace(
        id="sess-1",
        request_id="req-1",
        active_service_code="feedback",
        language="en",
        services_explored="[]",
    )
    req = SimpleNamespace(
        conversation_memory=json.dumps({"tour_started": True, "pricing_shown": True, "current_beat": "wizard_launch"})
    )
    monkeypatch.setattr(AiDemoService, "_resolve_tool_session", staticmethod(lambda db, payload: session))
    monkeypatch.setattr(AiDemoService, "get_request", staticmethod(lambda db, rid: req))
    monkeypatch.setattr(AiDemoService, "update_memory", staticmethod(lambda *a, **k: None))
    out = AiDemoService.handle_tool(
        MagicMock(),
        tool_name="end_demo",
        payload={"session_id": "sess-1", "summary": "talked pricing"},
    )
    assert out["action"] == "stay"
    assert "hang up" in out["message"].lower()


def test_record_user_click_notifies_agent_with_trigger(monkeypatch):
    import json

    from app.services.ai_demo_service import AiDemoService

    session = SimpleNamespace(id="sess-click", request_id="req-click")
    memory = {"tour_started": True, "current_beat": "home_kpis"}
    req = SimpleNamespace(conversation_memory=json.dumps(memory))

    def _update(_db, r, patch):
        mem = json.loads(r.conversation_memory or "{}")
        mem.update(patch)
        r.conversation_memory = json.dumps(mem)

    calls: list = []

    class _FakeResult:
        ok = True
        status = "messages_added"
        detail = None

    class _FakeAdapter:
        @staticmethod
        def add_ai_assistant_messages(**kwargs):
            calls.append(kwargs)
            return _FakeResult()

    monkeypatch.setattr(AiDemoService, "get_request", staticmethod(lambda db, rid: req))
    monkeypatch.setattr(AiDemoService, "update_memory", staticmethod(_update))
    monkeypatch.setattr(
        "app.services.provider_settings.ProviderSettingsService.get_platform_config_decrypted",
        staticmethod(lambda db, provider="telnyx": ({"api_key": "KEY" + ("x" * 60)}, True)),
    )
    monkeypatch.setattr(
        "app.services.telnyx_voice_service.TelnyxVoiceAdapter",
        _FakeAdapter,
    )

    db = MagicMock()
    db.get.return_value = session
    out = AiDemoService.record_user_click(
        db,
        session_id="sess-click",
        target="home-live-kpis",
        beat_id="home_activity",
        label="Activity",
        talk="See the feed",
        intent="view",
        beat_index=1,
        call_control_id="v3:demo-cc",
        agent_message="I clicked Next. The spotlight is now Activity. Explain this now.",
        notify_agent=True,
    )
    assert out["ok"] is True
    assert out["agent_notify"]["ok"] is True
    assert len(calls) == 1
    assert calls[0]["call_control_id"] == "v3:demo-cc"
    assert calls[0]["trigger_response"] is True
    assert calls[0]["command_id"]
    assert "demo-sess-click" in str(calls[0]["command_id"]) or "home_activity" in str(calls[0]["command_id"])
    assert calls[0]["messages"][0]["role"] == "user"
    assert calls[0]["messages"][0]["content"].startswith("I clicked Next.")
    mem = json.loads(req.conversation_memory)
    assert not mem.get("pending_click_nudge")


def test_record_user_click_skips_inject_by_default(monkeypatch):
    import json

    from app.services.ai_demo_service import AiDemoService

    session = SimpleNamespace(id="sess-quiet", request_id="req-quiet")
    req = SimpleNamespace(conversation_memory=json.dumps({"tour_started": True}))

    def _update(_db, r, patch):
        mem = json.loads(r.conversation_memory or "{}")
        mem.update(patch)
        r.conversation_memory = json.dumps(mem)

    monkeypatch.setattr(AiDemoService, "get_request", staticmethod(lambda db, rid: req))
    monkeypatch.setattr(AiDemoService, "update_memory", staticmethod(_update))

    db = MagicMock()
    db.get.return_value = session
    out = AiDemoService.record_user_click(
        db,
        session_id="sess-quiet",
        target="nav-feedback-compare",
        beat_id="nav_feedback_compare",
        label="Compare locations",
        talk="Compare branches",
        intent="click",
        beat_index=7,
        call_control_id="v3:unused",
    )
    assert out["ok"] is True
    assert out["agent_notify"]["ok"] is False
    assert out["agent_notify"]["detail"] == "voice_gated_no_inject"
    mem = json.loads(req.conversation_memory)
    assert mem.get("current_beat") == "nav_feedback_compare"
    assert mem.get("pending_click_nudge")


def test_bind_call_flushes_pending_click_nudge(monkeypatch):
    import json

    from app.services.ai_demo_service import AiDemoService

    session = SimpleNamespace(id="sess-bind", request_id="req-bind")
    memory = {
        "pending_click_nudge": "I clicked Next. Spotlight is Overview. Explain now.",
        "pending_click_at": "2026-08-12T04:00:00Z",
    }
    req = SimpleNamespace(conversation_memory=json.dumps(memory))

    def _update(_db, r, patch):
        mem = json.loads(r.conversation_memory or "{}")
        mem.update(patch)
        r.conversation_memory = json.dumps(mem)

    calls: list = []

    class _FakeResult:
        ok = True
        status = "messages_added"
        detail = None

    class _FakeAdapter:
        @staticmethod
        def add_ai_assistant_messages(**kwargs):
            calls.append(kwargs)
            return _FakeResult()

    monkeypatch.setattr(AiDemoService, "get_request", staticmethod(lambda db, rid: req))
    monkeypatch.setattr(AiDemoService, "update_memory", staticmethod(_update))
    monkeypatch.setattr(
        "app.services.provider_settings.ProviderSettingsService.get_platform_config_decrypted",
        staticmethod(lambda db, provider="telnyx": ({"api_key": "KEY" + ("x" * 60)}, True)),
    )
    monkeypatch.setattr(
        "app.services.telnyx_voice_service.TelnyxVoiceAdapter",
        _FakeAdapter,
    )

    db = MagicMock()
    db.get.return_value = session
    out = AiDemoService.bind_call_control(
        db,
        session_id="sess-bind",
        call_control_id="v3:late-bind",
    )
    assert out["ok"] is True
    assert out["agent_notify"]["ok"] is True
    assert len(calls) == 1
    assert calls[0]["call_control_id"] == "v3:late-bind"
    assert calls[0]["trigger_response"] is True
    mem = json.loads(req.conversation_memory)
    assert mem.get("telnyx_call_control_id") == "v3:late-bind"
    assert not mem.get("pending_click_nudge")


def test_opening_gate_and_consent_first_greeting():
    from app.services.ai_demo_service import OPENING_GATE

    assert "welcome" in OPENING_GATE.lower()
    assert "recorded" in OPENING_GATE.lower()
    assert "highlight_dashboard" in OPENING_GATE
    assert "done" in OPENING_GATE.lower() or "tell you" in OPENING_GATE.lower()
    assert "voice" in OPENING_GATE.lower() or "spoken" in OPENING_GATE.lower() or "I clicked Next" in OPENING_GATE


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
