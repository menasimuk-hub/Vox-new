from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.lead_sales_task import LeadSalesTask
from app.services.telnyx_conversation_service import (
    _collect_recording_candidates,
    _download_recording_bytes,
    _recording_download,
    _refresh_recording_row,
)


def resolve_sales_task_recording(db: Session, task: LeadSalesTask) -> dict[str, Any] | None:
    """Find Telnyx dual/single recording for outbound sales call_control_id."""
    cc = str(task.provider_call_id or "").strip()
    if not cc:
        return None
    fake_conv = {
        "id": task.telnyx_conversation_id or "",
        "metadata": {"call_control_id": cc},
        "created_at": task.call_started_at or task.scheduled_at,
        "last_message_at": task.call_completed_at,
    }
    candidates = _collect_recording_candidates(db, fake_conv)
    if not candidates and cc:
        from app.services.telnyx_conversation_service import _list_recordings

        candidates = _list_recordings(db, call_control_id=cc)

    ordered = sorted(candidates, key=lambda r: int(r.get("duration_millis") or 0), reverse=True)
    for row in ordered:
        fresh = _refresh_recording_row(db, row)
        url, fmt = _recording_download(fresh)
        if not url or not fmt:
            continue
        audio = _download_recording_bytes(url)
        if not audio:
            continue
        return {
            "id": str(fresh.get("id") or "").strip() or None,
            "format": fmt,
            "download_url": url,
            "audio_bytes": audio,
            "channels": str(fresh.get("channels") or ""),
        }
    return None
