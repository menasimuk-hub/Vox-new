"""Celery worker/beat health, restart helpers, and admin email alerts."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

WORKER_PROGRAM = "voxbulk-celery"
BEAT_PROGRAM = "voxbulk-celery-beat"

CRITICAL_TASKS = (
    "survey.retry_deferred_wa_starts",
    "survey.transcribe_voice_note",
    "billing.process_monthly_subscriptions",
    "billing.rollover_usage_periods",
)

CRITICAL_BEAT_ENTRIES = (
    "survey-retry-deferred-wa-starts-10m",
    "monthly-subscription-billing-hourly",
    "rollover-usage-periods-daily",
)

_ALERT_DEBOUNCE_KEY = "ops:celery:alert"
_ALERT_DEBOUNCE_SEC = 1800


def _oncall_emails() -> list[str]:
    settings = get_settings()
    raw = str(getattr(settings, "celery_ops_alert_emails", None) or "").strip()
    if not raw:
        raw = str(settings.assistant_oncall_admin_emails or "").strip()
    if not raw:
        raw = str(settings.invoice_company_email or "").strip()
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def _run(cmd: list[str], *, timeout: float = 20.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return int(proc.returncode), (proc.stdout or "").strip(), (proc.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as exc:
        return 1, "", str(exc)


def _supervisorctl_bin() -> str | None:
    return shutil.which("supervisorctl")


def _supervisor_cmd(*args: str, prefer_sudo: bool = False) -> list[str]:
    bin_path = _supervisorctl_bin() or "supervisorctl"
    base = [bin_path, *args]
    if prefer_sudo:
        return ["sudo", "-n", *base]
    return base


def supervisor_program_status(program: str) -> dict[str, Any]:
    """Return RUNNING/STOPPED/MISSING for a supervisor program."""
    if not _supervisorctl_bin():
        return {
            "program": program,
            "state": "unavailable",
            "ok": False,
            "detail": "supervisorctl not installed",
            "raw": "",
        }

    code, out, err = _run(_supervisor_cmd("status", program))
    raw = out or err
    if code != 0 and "sudo" not in " ".join(_supervisor_cmd("status", program)):
        code2, out2, err2 = _run(_supervisor_cmd("status", program, prefer_sudo=True))
        if code2 == 0 or out2 or err2:
            code, out, err, raw = code2, out2, err2, (out2 or err2)

    text = (out or err or raw or "").strip()
    upper = text.upper()
    if "RUNNING" in upper:
        state = "RUNNING"
        ok = True
    elif "STARTING" in upper:
        state = "STARTING"
        ok = True
    elif "STOPPED" in upper or "EXITED" in upper or "FATAL" in upper or "BACKOFF" in upper:
        state = "STOPPED" if "STOPPED" in upper else ("FATAL" if "FATAL" in upper else "DOWN")
        ok = False
    elif "no such process" in text.lower() or code == 3:
        state = "MISSING"
        ok = False
    else:
        state = "unknown"
        ok = False

    return {
        "program": program,
        "state": state,
        "ok": ok,
        "detail": text[:240] or err[:240] or None,
        "raw": text[:500],
    }


def _process_running(pattern: str) -> bool:
    code, out, _ = _run(["pgrep", "-af", pattern], timeout=8.0)
    if code != 0:
        return False
    lines = [ln for ln in (out or "").splitlines() if ln.strip() and "pgrep" not in ln]
    return bool(lines)


def redis_ok() -> dict[str, Any]:
    settings = get_settings()
    url = str(settings.celery_broker_url or settings.redis_url or "").strip()
    if not url:
        return {"ok": False, "detail": "CELERY_BROKER_URL / REDIS_URL not set"}
    try:
        import redis

        client = redis.from_url(url, socket_connect_timeout=1.5, socket_timeout=1.5)
        pong = client.ping()
        return {"ok": bool(pong), "detail": "PONG" if pong else "no PONG"}
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:200]}


def worker_ping() -> dict[str, Any]:
    try:
        from app.workers.celery_app import celery_app

        replies = celery_app.control.inspect(timeout=2.0).ping() or {}
        nodes = sorted(replies.keys())
        return {"ok": bool(nodes), "nodes": nodes, "detail": None if nodes else "no workers replied"}
    except Exception as exc:
        return {"ok": False, "nodes": [], "detail": str(exc)[:200]}


def registered_tasks() -> dict[str, Any]:
    try:
        from app.workers.celery_app import celery_app

        replies = celery_app.control.inspect(timeout=3.0).registered() or {}
        names: set[str] = set()
        for tasks in replies.values():
            if isinstance(tasks, (list, tuple, set)):
                names.update(str(t) for t in tasks)
        missing = [t for t in CRITICAL_TASKS if t not in names]
        return {
            "ok": not missing and bool(names),
            "count": len(names),
            "missing_critical": missing,
            "has_critical": [t for t in CRITICAL_TASKS if t in names],
            "detail": None if not missing else f"missing: {', '.join(missing)}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "count": 0,
            "missing_critical": list(CRITICAL_TASKS),
            "has_critical": [],
            "detail": str(exc)[:200],
        }


def beat_schedule_ok() -> dict[str, Any]:
    try:
        from app.workers.celery_app import celery_app
        import app.workers.survey_wa_dispatch_tasks  # noqa: F401
        import app.workers.billing_tasks  # noqa: F401

        keys = set((celery_app.conf.beat_schedule or {}).keys())
        missing = [k for k in CRITICAL_BEAT_ENTRIES if k not in keys]
        return {
            "ok": not missing,
            "entries": sorted(keys),
            "missing_critical": missing,
            "detail": None if not missing else f"missing beat entries: {', '.join(missing)}",
        }
    except Exception as exc:
        return {"ok": False, "entries": [], "missing_critical": list(CRITICAL_BEAT_ENTRIES), "detail": str(exc)[:200]}


def collect_status() -> dict[str, Any]:
    worker_sup = supervisor_program_status(WORKER_PROGRAM)
    beat_sup = supervisor_program_status(BEAT_PROGRAM)
    worker_proc = _process_running("celery.*worker")
    beat_proc = _process_running("celery.*beat")
    redis = redis_ok()
    ping = worker_ping()
    tasks = registered_tasks()
    beat_sched = beat_schedule_ok()

    issues: list[str] = []
    if not worker_sup["ok"] and not worker_proc:
        issues.append("Celery worker not running")
    elif not worker_sup["ok"] and worker_proc:
        issues.append("Celery worker process found but Supervisor program is not RUNNING")
    if not beat_sup["ok"] and not beat_proc:
        issues.append("Celery beat not running")
    elif not beat_sup["ok"] and beat_proc:
        issues.append("Celery beat process found but Supervisor program is not RUNNING (stale schedule risk)")
    if not redis["ok"]:
        issues.append(f"Redis unavailable: {redis.get('detail')}")
    if not ping["ok"]:
        issues.append(f"Worker ping failed: {ping.get('detail')}")
    if tasks.get("missing_critical"):
        issues.append(f"Missing tasks: {', '.join(tasks['missing_critical'])}")
    if beat_sched.get("missing_critical"):
        issues.append(f"Missing beat schedule: {', '.join(beat_sched['missing_critical'])}")

    # Stale-code signal: process up for a long time but missing critical tasks
    stale_code = bool(ping.get("ok") and tasks.get("missing_critical"))
    if stale_code and "Missing tasks" not in " ".join(issues):
        issues.append("Worker is up but missing critical tasks — restart required after deploy")

    healthy = not issues
    return {
        "ok": healthy,
        "checked_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        "worker": {
            "supervisor": worker_sup,
            "process_running": worker_proc,
            "ping": ping,
            "tasks": tasks,
        },
        "beat": {
            "supervisor": beat_sup,
            "process_running": beat_proc,
            "schedule": beat_sched,
        },
        "redis": redis,
        "issues": issues,
        "stale_code": stale_code,
        "critical_tasks": list(CRITICAL_TASKS),
    }


def restart_celery(*, programs: list[str] | None = None) -> dict[str, Any]:
    """Restart Celery worker and/or beat via supervisorctl (sudo -n when needed)."""
    targets = programs or [WORKER_PROGRAM, BEAT_PROGRAM]
    targets = [p for p in targets if p in {WORKER_PROGRAM, BEAT_PROGRAM}]
    if not targets:
        targets = [WORKER_PROGRAM, BEAT_PROGRAM]

    custom = str(os.environ.get("VOXBULK_CELERY_RESTART_CMD") or "").strip()
    steps: list[dict[str, Any]] = []

    if custom:
        code, out, err = _run(["bash", "-lc", custom], timeout=90.0)
        steps.append({"cmd": custom, "ok": code == 0, "stdout": out[:400], "stderr": err[:400]})
    else:
        if not _supervisorctl_bin():
            return {
                "ok": False,
                "restarted": False,
                "steps": [],
                "detail": "supervisorctl not found — run: sudo bash scripts/vps-setup-celery.sh",
                "status": collect_status(),
            }
        for program in targets:
            code, out, err = _run(_supervisor_cmd("restart", program), timeout=60.0)
            if code != 0:
                code, out, err = _run(_supervisor_cmd("restart", program, prefer_sudo=True), timeout=60.0)
            steps.append(
                {
                    "program": program,
                    "ok": code == 0,
                    "stdout": (out or "")[:400],
                    "stderr": (err or "")[:400],
                    "code": code,
                }
            )
            # Give supervisord a moment between programs
            time.sleep(1.0)

    time.sleep(2.0)
    status = collect_status()
    restarted_ok = all(bool(s.get("ok")) for s in steps) if steps else False
    # After restart, ping may take a few seconds — treat supervisor RUNNING as success signal
    worker_up = bool(status.get("worker", {}).get("supervisor", {}).get("ok") or status.get("worker", {}).get("process_running"))
    beat_up = bool(status.get("beat", {}).get("supervisor", {}).get("ok") or status.get("beat", {}).get("process_running"))
    ok = restarted_ok and worker_up and beat_up
    return {
        "ok": ok,
        "restarted": restarted_ok,
        "steps": steps,
        "detail": None if ok else "Restart finished but health check still reports issues",
        "status": status,
    }


def _alert_allowed() -> bool:
    try:
        import redis

        settings = get_settings()
        url = str(settings.redis_url or settings.celery_broker_url or "").strip()
        if not url:
            return True
        client = redis.from_url(url, socket_connect_timeout=1.0, socket_timeout=1.0, decode_responses=True)
        return bool(client.set(_ALERT_DEBOUNCE_KEY, "1", nx=True, ex=_ALERT_DEBOUNCE_SEC))
    except Exception:
        return True


def send_celery_ops_alert(db: Session | None, *, status: dict[str, Any], action: str = "detected") -> dict[str, Any]:
    emails = _oncall_emails()
    if not emails:
        return {"ok": False, "skipped": True, "reason": "no_alert_emails"}
    if not _alert_allowed():
        return {"ok": False, "skipped": True, "reason": "debounced"}

    issues = status.get("issues") or ["unknown issue"]
    subject = f"[VoxBulk] Celery {action}: {'; '.join(issues[:2])}"
    body_lines = [
        f"Celery health check {action} at {status.get('checked_at')}.",
        "",
        "Issues:",
        *[f"- {i}" for i in issues],
        "",
        f"Worker supervisor: {status.get('worker', {}).get('supervisor', {}).get('state')}",
        f"Beat supervisor: {status.get('beat', {}).get('supervisor', {}).get('state')}",
        f"Worker ping: {status.get('worker', {}).get('ping', {}).get('ok')}",
        f"Redis: {status.get('redis', {}).get('ok')}",
        f"Missing tasks: {status.get('worker', {}).get('tasks', {}).get('missing_critical')}",
        "",
        "On VPS: sudo supervisorctl restart voxbulk-celery voxbulk-celery-beat",
        "Or Admin Dashboard → Celery monitor → Restart.",
    ]
    body = "\n".join(body_lines)

    from app.services.smtp_mailer_service import SmtpMailerService
    from app.core.database import get_sessionmaker

    sent = 0
    errors: list[str] = []
    own_session = db is None
    session = db or get_sessionmaker()()
    try:
        for addr in emails:
            try:
                SmtpMailerService.send_plain(session, to_addr=addr, subject=subject, body=body)
                sent += 1
            except Exception as exc:
                errors.append(f"{addr}: {exc}")
                logger.exception("celery_ops_alert_send_failed to=%s", addr)
    finally:
        if own_session:
            session.close()

    return {"ok": sent > 0, "sent": sent, "recipients": emails, "errors": errors}


def watchdog_tick(*, auto_restart: bool = True, send_email: bool = True) -> dict[str, Any]:
    """Cron entrypoint: check health, optionally restart, email admin on failure."""
    status = collect_status()
    result: dict[str, Any] = {"status": status, "restart": None, "alert": None}

    if status.get("ok"):
        return result

    if auto_restart:
        # Restart when process down OR stale code (missing critical tasks)
        needs_restart = True
        result["restart"] = restart_celery()
        status = result["restart"].get("status") or collect_status()
        result["status"] = status
        if not needs_restart:
            pass

    if send_email and not status.get("ok"):
        result["alert"] = send_celery_ops_alert(None, status=status, action="unhealthy")
    elif send_email and result.get("restart") and result["restart"].get("ok") and not (result["status"] or {}).get("ok"):
        result["alert"] = send_celery_ops_alert(None, status=result["status"], action="restart_incomplete")
    elif send_email and result.get("restart") and result["restart"].get("ok"):
        # Recovered after restart — still notify once so admin knows it flapped
        recovered = dict(result["status"] or {})
        recovered["issues"] = ["Celery was unhealthy; watchdog restarted worker/beat successfully"]
        result["alert"] = send_celery_ops_alert(None, status=recovered, action="auto-restarted")

    return result
