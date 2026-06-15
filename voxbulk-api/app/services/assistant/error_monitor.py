"""Passive failure counter + admin email alerts for the dashboard assistant."""

from __future__ import annotations

import logging
import time
from threading import Lock

from sqlalchemy.orm import Session

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_memory_counters: dict[str, list[float]] = {}
_memory_alert_at: dict[str, float] = {}
_memory_lock = Lock()


def _redis_client():
    try:
        import redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=0.5)
    except Exception:
        return None


def _oncall_emails() -> list[str]:
    settings = get_settings()
    raw = str(settings.assistant_oncall_admin_emails or "").strip()
    if not raw:
        raw = str(settings.invoice_company_email or "").strip()
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def record_assistant_failure(*, endpoint_label: str) -> None:
    settings = get_settings()
    threshold = max(1, int(settings.assistant_error_alert_threshold))
    window_sec = max(60, int(settings.assistant_error_alert_window_sec))
    key = f"assistant:fail:{endpoint_label or 'unknown'}"
    now = time.time()

    count = 0
    client = _redis_client()
    if client is not None:
        try:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, now - window_sec)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_sec + 30)
            _, _, count, _ = pipe.execute()
            count = int(count or 0)
        except Exception:
            client = None

    if client is None:
        with _memory_lock:
            bucket = [t for t in _memory_counters.get(key, []) if t >= now - window_sec]
            bucket.append(now)
            _memory_counters[key] = bucket
            count = len(bucket)

    if count < threshold:
        return

    debounce_key = f"{key}:alert"
    should_alert = False
    if client is not None:
        try:
            should_alert = bool(client.set(debounce_key, "1", nx=True, ex=window_sec))
        except Exception:
            client = None

    if client is None:
        with _memory_lock:
            last = _memory_alert_at.get(debounce_key, 0)
            if now - last >= window_sec:
                _memory_alert_at[debounce_key] = now
                should_alert = True

    if not should_alert:
        return

    _queue_ops_alert(
        endpoint_label=endpoint_label,
        failure_count=count,
        window_sec=window_sec,
    )


def _queue_ops_alert(*, endpoint_label: str, failure_count: int, window_sec: int) -> None:
    emails = _oncall_emails()
    if not emails:
        logger.warning("assistant_ops_alert_skipped_no_recipients endpoint=%s", endpoint_label)
        return

    subject = f"[VoxBulk] Assistant failures: {endpoint_label}"
    body = (
        f"The dashboard AI assistant recorded {failure_count} failures for '{endpoint_label}' "
        f"within the last {window_sec // 60} minute(s).\n\n"
        "Check API logs and provider health."
    )

    try:
        from app.workers.assistant_tasks import send_assistant_ops_alert

        send_assistant_ops_alert.delay(emails, subject, body)
    except Exception:
        logger.warning("assistant_ops_alert_celery_fallback endpoint=%s", endpoint_label, exc_info=True)
        _send_ops_alert_sync(emails, subject, body)


def _send_ops_alert_sync(emails: list[str], subject: str, body: str) -> None:
    from app.core.database import get_sessionmaker
    from app.services.smtp_mailer_service import SmtpMailerService

    try:
        with get_sessionmaker()() as db:
            for addr in emails:
                SmtpMailerService.send_plain(db, to_addr=addr, subject=subject, body=body)
    except Exception:
        logger.exception("assistant_ops_alert_sync_failed")


def send_ops_alert_now(db: Session, *, to_emails: list[str], subject: str, body: str) -> None:
    from app.services.smtp_mailer_service import SmtpMailerService

    for addr in to_emails:
        SmtpMailerService.send_plain(db, to_addr=addr, subject=subject, body=body)
