"""Append-only audit log for CRM appointments."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appointment import AppointmentLog


def append_log(
    db: Session,
    *,
    appointment_id: str,
    event_type: str,
    detail: dict[str, Any] | str | None = None,
) -> AppointmentLog:
    detail_json: str | None
    if detail is None:
        detail_json = None
    elif isinstance(detail, str):
        detail_json = detail
    else:
        detail_json = json.dumps(detail, ensure_ascii=False)
    row = AppointmentLog(
        appointment_id=appointment_id,
        event_type=str(event_type or "").strip()[:40],
        detail_json=detail_json,
    )
    db.add(row)
    db.flush()
    return row


def list_logs_for_appointment(db: Session, appointment_id: str) -> list[AppointmentLog]:
    return list(
        db.execute(
            select(AppointmentLog)
            .where(AppointmentLog.appointment_id == appointment_id)
            .order_by(AppointmentLog.created_at.asc(), AppointmentLog.id.asc())
        ).scalars()
    )
