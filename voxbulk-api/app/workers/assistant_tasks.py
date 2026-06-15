from __future__ import annotations

from app.core.database import get_sessionmaker
from app.services.assistant.error_monitor import send_ops_alert_now
from app.workers.celery_app import celery_app


@celery_app.task(name="assistant.send_ops_alert")
def send_assistant_ops_alert(to_emails: list[str], subject: str, body: str) -> dict[str, object]:
    with get_sessionmaker()() as db:
        send_ops_alert_now(db, to_emails=to_emails, subject=subject, body=body)
    return {"ok": True, "recipients": len(to_emails or [])}
