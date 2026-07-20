"""Celery ops health helpers (unit-level, no live broker required)."""

from __future__ import annotations


def test_celery_ops_collect_status_shape(monkeypatch):
    from app.services import celery_ops_service as svc

    monkeypatch.setattr(
        svc,
        "supervisor_program_status",
        lambda program: {"program": program, "state": "RUNNING", "ok": True, "detail": "RUNNING", "raw": "RUNNING"},
    )
    monkeypatch.setattr(svc, "_process_running", lambda _pattern: True)
    monkeypatch.setattr(svc, "redis_ok", lambda: {"ok": True, "detail": "PONG"})
    monkeypatch.setattr(svc, "worker_ping", lambda: {"ok": True, "nodes": ["celery@test"], "detail": None})
    monkeypatch.setattr(
        svc,
        "registered_tasks",
        lambda: {
            "ok": True,
            "count": 4,
            "missing_critical": [],
            "has_critical": list(svc.CRITICAL_TASKS),
            "detail": None,
        },
    )
    monkeypatch.setattr(
        svc,
        "beat_schedule_ok",
        lambda: {"ok": True, "entries": list(svc.CRITICAL_BEAT_ENTRIES), "missing_critical": [], "detail": None},
    )

    status = svc.collect_status()
    assert status["ok"] is True
    assert status["issues"] == []
    assert status["worker"]["supervisor"]["state"] == "RUNNING"
    assert status["beat"]["supervisor"]["state"] == "RUNNING"
    assert "survey.retry_deferred_wa_starts" in status["critical_tasks"]


def test_celery_ops_detects_missing_task(monkeypatch):
    from app.services import celery_ops_service as svc

    monkeypatch.setattr(
        svc,
        "supervisor_program_status",
        lambda program: {"program": program, "state": "RUNNING", "ok": True, "detail": "RUNNING", "raw": "RUNNING"},
    )
    monkeypatch.setattr(svc, "_process_running", lambda _pattern: True)
    monkeypatch.setattr(svc, "redis_ok", lambda: {"ok": True, "detail": "PONG"})
    monkeypatch.setattr(svc, "worker_ping", lambda: {"ok": True, "nodes": ["celery@test"], "detail": None})
    monkeypatch.setattr(
        svc,
        "registered_tasks",
        lambda: {
            "ok": False,
            "count": 3,
            "missing_critical": ["survey.retry_deferred_wa_starts"],
            "has_critical": [],
            "detail": "missing",
        },
    )
    monkeypatch.setattr(
        svc,
        "beat_schedule_ok",
        lambda: {"ok": True, "entries": list(svc.CRITICAL_BEAT_ENTRIES), "missing_critical": [], "detail": None},
    )

    status = svc.collect_status()
    assert status["ok"] is False
    assert status["stale_code"] is True
    assert any("Missing tasks" in i for i in status["issues"])
