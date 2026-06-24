"""Zoom interview campaigns via Telnyx native Zoom integration."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.http_ssl import httpx_ssl_verify
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import ServiceOrderService
from app.services.provider_settings import ProviderSettingsService
from app.services.telnyx_api_key import require_telnyx_api_key
from app.services.transactional_email_service import TransactionalEmailService

logger = logging.getLogger(__name__)

LOG_PREFIX = "[interview-zoom]"
TELNYX_API_BASE = "https://api.telnyx.com/v2"
MIN_TRANSCRIPT_CHARS = 20

_TERMINAL_RECIPIENT = frozenset({"completed", "failed", "cancelled", "opted_out"})
_MEETING_END_EVENTS = frozenset(
    {
        "zoom.meeting.ended",
        "meeting.ended",
        "zoom.meeting.completed",
        "meeting.completed",
        "zoom.recording.available",
        "recording.available",
        "zoom.transcript.available",
        "transcript.available",
    }
)


def is_zoom_interview_order(order: ServiceOrder) -> bool:
    if order.service_code != "interview":
        return False
    config = _order_config(order)
    return str(config.get("delivery") or "").strip().lower() == "zoom"


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _set_recipient_result(db: Session, recipient: ServiceOrderRecipient, payload: dict[str, Any]) -> None:
    merged = _recipient_result(recipient)
    merged.update(payload)
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)


def _telnyx_request(
    db: Session,
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any] | list[Any] | None, str]:
    api_key, _source = require_telnyx_api_key(db)
    url = f"{TELNYX_API_BASE}{path if path.startswith('/') else '/' + path}"
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    with httpx.Client(timeout=timeout, verify=httpx_ssl_verify()) as client:
        response = client.request(method.upper(), url, headers=headers, json=json_body)
    text = response.text or ""
    parsed: dict[str, Any] | list[Any] | None = None
    if text:
        try:
            parsed = response.json()
        except Exception:
            parsed = None
    return response.status_code, parsed, text


def _telnyx_data(parsed: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    data = parsed.get("data")
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return parsed


def _optional_zoom_assistant_id(db: Session) -> str | None:
    cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
    if not enabled or not cfg:
        return None
    for key in ("zoom_interview_assistant_id", "interview_assistant_id", "default_assistant_id"):
        value = str(cfg.get(key) or "").strip()
        if value:
            return value
    return None


def _extract_transcript(payload: dict[str, Any]) -> str:
    for key in ("transcript", "transcript_text", "text", "content"):
        raw = payload.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    files = payload.get("recording_files") or payload.get("files")
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            file_type = str(item.get("file_type") or item.get("type") or "").upper()
            if "TRANSCRIPT" in file_type or file_type in {"VTT", "TXT"}:
                for key in ("download_url", "url", "play_url"):
                    if str(item.get(key) or "").strip():
                        return str(item.get("transcript") or item.get("content") or "").strip()
    return ""


def _extract_recording_url(payload: dict[str, Any]) -> str:
    for key in ("recording_url", "download_url", "play_url", "url"):
        raw = str(payload.get(key) or "").strip()
        if raw.startswith("http"):
            return raw
    files = payload.get("recording_files") or payload.get("files") or payload.get("recordings")
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            file_type = str(item.get("file_type") or item.get("type") or "").upper()
            if file_type in {"MP4", "M4A", "AUDIO", "VIDEO"} or "RECORDING" in file_type:
                for key in ("download_url", "play_url", "url"):
                    raw = str(item.get(key) or "").strip()
                    if raw.startswith("http"):
                        return raw
        for item in files:
            if not isinstance(item, dict):
                continue
            for key in ("download_url", "play_url", "url"):
                raw = str(item.get(key) or "").strip()
                if raw.startswith("http"):
                    return raw
    return ""


class InterviewZoomService:
    @staticmethod
    def create_zoom_meeting_via_telnyx(db: Session, topic: str) -> dict[str, Any]:
        """
        Create a Zoom interview meeting.

        Telnyx does not expose POST /v2/zoom/meetings on standard accounts (404).
        We try that path once for forward compatibility, then use Zoom Server-to-Server
        OAuth (Admin → Integrations → Zoom). Telnyx AI/voice remains separate.
        """
        from app.services.zoom_service import ZoomService

        clean_topic = str(topic or "Interview").strip() or "Interview"
        payload: dict[str, Any] = {"topic": clean_topic}
        assistant_id = _optional_zoom_assistant_id(db)
        if assistant_id:
            payload["assistant_id"] = assistant_id

        telnyx_error = ""
        try:
            cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="telnyx")
            if enabled:
                status, parsed, raw = _telnyx_request(db, "POST", "/zoom/meetings", json_body=payload)
                if status == 201:
                    data = _telnyx_data(parsed if isinstance(parsed, dict) else {})
                    meeting_id = data.get("id") or data.get("meeting_id")
                    join_url = data.get("join_url") or data.get("join_url_for_participant")
                    if meeting_id and join_url:
                        return {
                            "id": meeting_id,
                            "join_url": str(join_url).strip(),
                            "start_url": data.get("start_url"),
                            "topic": data.get("topic") or clean_topic,
                            "assistant_id": data.get("assistant_id") or assistant_id,
                            "meeting_provider": "telnyx_zoom",
                        }
                if status == 404:
                    telnyx_error = "Telnyx /zoom/meetings not available on this account"
                else:
                    telnyx_error = f"Telnyx HTTP {status}: {raw[:200]}"
        except ValueError:
            telnyx_error = "Telnyx API key not configured"
        except Exception as exc:
            telnyx_error = str(exc)[:200]

        if not ZoomService.is_configured(db):
            hint = (
                "Configure Zoom under Admin → Integrations → Zoom (or Telnyx → Zoom) with "
                "(account_id, client_id, client_secret), "
                "then click Test Zoom."
            )
            if telnyx_error:
                hint = f"{telnyx_error}. {hint}"
            raise ValueError(hint)

        try:
            meeting = ZoomService.create_meeting(db, topic=clean_topic)
        except ValueError as exc:
            if telnyx_error:
                raise ValueError(f"{telnyx_error}. Zoom fallback failed: {exc}") from exc
            raise

        meeting_id = meeting.get("id")
        join_url = meeting.get("join_url")
        if not meeting_id or not join_url:
            raise ValueError("Zoom returned a meeting without id or join_url")

        return {
            "id": meeting_id,
            "join_url": str(join_url).strip(),
            "start_url": meeting.get("start_url"),
            "topic": clean_topic,
            "meeting_provider": "zoom_oauth",
            "telnyx_zoom_note": telnyx_error or None,
        }

    @staticmethod
    def fetch_meeting_artifacts(db: Session, meeting_id: str, *, provider: str | None = None) -> dict[str, Any]:
        """Fetch transcript + recording (Zoom OAuth API, with optional Telnyx path)."""
        mid = str(meeting_id or "").strip()
        if not mid:
            return {"ready": False, "error": "missing meeting id"}

        prov = str(provider or "").strip().lower()
        if prov in {"", "zoom_oauth", "zoom"}:
            from app.services.zoom_service import ZoomService

            if ZoomService.is_configured(db):
                zoom_result = ZoomService.fetch_meeting_artifacts(db, mid)
                if zoom_result.get("ready"):
                    return zoom_result

        if prov in {"", "telnyx_zoom"}:
            transcript = ""
            recording_url = ""
            conversation_id = ""
            last_error = ""
            for path in (
                f"/zoom/meetings/{mid}",
                f"/zoom/meetings/{mid}/transcript",
                f"/zoom/meetings/{mid}/recordings",
            ):
                try:
                    status, parsed, raw = _telnyx_request(db, "GET", path)
                except ValueError:
                    break
                if status >= 400:
                    last_error = raw[:200]
                    continue
                data = _telnyx_data(parsed if isinstance(parsed, dict) else {})
                if not transcript:
                    transcript = _extract_transcript(data)
                if not recording_url:
                    recording_url = _extract_recording_url(data)
                if not conversation_id:
                    conversation_id = str(data.get("conversation_id") or data.get("telnyx_conversation_id") or "").strip()

            ready = bool(transcript and len(transcript) >= MIN_TRANSCRIPT_CHARS) or bool(recording_url)
            if ready:
                return {
                    "ready": True,
                    "provider": "telnyx_zoom",
                    "transcript": transcript or None,
                    "recording_url": recording_url or None,
                    "conversation_id": conversation_id or None,
                }
            if prov == "telnyx_zoom":
                return {
                    "ready": False,
                    "provider": "telnyx_zoom",
                    "error": last_error or "transcript/recording not ready",
                }

        from app.services.zoom_service import ZoomService

        if ZoomService.is_configured(db):
            return ZoomService.fetch_meeting_artifacts(db, mid)

        return {"ready": False, "error": "No Zoom or Telnyx recording source configured"}

    @staticmethod
    def _find_recipient_for_meeting(db: Session, meeting_id: str) -> ServiceOrderRecipient | None:
        needle = str(meeting_id or "").strip()
        if not needle:
            return None
        rows = list(
            db.execute(
                select(ServiceOrderRecipient)
                .join(ServiceOrder, ServiceOrder.id == ServiceOrderRecipient.order_id)
                .where(
                    ServiceOrder.service_code == "interview",
                    ServiceOrderRecipient.status.in_(("scheduled", "calling", "in_progress", "pending")),
                )
                .order_by(ServiceOrderRecipient.updated_at.desc())
                .limit(200)
            ).scalars()
        )
        for row in rows:
            parsed = _recipient_result(row)
            if str(parsed.get("zoom_meeting_id") or "") == needle:
                return row
        return None

    @staticmethod
    def finalize_recipient_artifacts(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        artifacts: dict[str, Any],
        source: str,
    ) -> bool:
        transcript = str(artifacts.get("transcript") or "").strip()
        recording_url = str(artifacts.get("recording_url") or "").strip()
        if len(transcript) < MIN_TRANSCRIPT_CHARS and not recording_url:
            return False

        now = datetime.utcnow().isoformat()
        payload: dict[str, Any] = {
            "zoom_sync_source": source,
            "zoom_synced_at": now,
            "meeting_completed_at": now,
        }
        if transcript:
            payload["transcript"] = transcript
        if recording_url:
            payload["recording_url"] = recording_url
        if artifacts.get("conversation_id"):
            payload["telnyx_conversation_id"] = artifacts["conversation_id"]

        _set_recipient_result(db, recipient, payload)
        recipient.status = "completed"
        db.add(recipient)
        db.commit()

        from app.services.interview_analysis_service import refresh_order_interview_report, run_interview_analysis_if_needed

        if transcript:
            run_interview_analysis_if_needed(db, order=order, recipient=recipient)
        InterviewZoomService._finalize_order_if_ready(db, order)
        refresh_order_interview_report(db, order)
        logger.info("%s recipient_finalized", LOG_PREFIX, extra={"recipient_id": recipient.id, "source": source})
        return True

    @staticmethod
    def _finalize_order_if_ready(db: Session, order: ServiceOrder) -> None:
        recipients = ServiceOrderService.get_recipients(db, order.id)
        if not recipients:
            return
        if any(str(r.status or "").lower() not in _TERMINAL_RECIPIENT for r in recipients):
            order.status = "running"
            order.updated_at = datetime.utcnow()
            db.add(order)
            db.commit()
            return
        order.status = "completed"
        order.completed_at = order.completed_at or datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()

    @staticmethod
    def handle_webhook(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        event_type = str(data.get("event_type") or data.get("type") or "").strip().lower()
        inner = data.get("payload") if isinstance(data.get("payload"), dict) else data
        if event_type not in _MEETING_END_EVENTS and "ended" not in event_type and "recording" not in event_type:
            return {"ok": True, "ignored": True, "event_type": event_type or None}

        meeting_id = str(
            inner.get("meeting_id")
            or inner.get("zoom_meeting_id")
            or inner.get("id")
            or data.get("meeting_id")
            or ""
        ).strip()
        if not meeting_id:
            return {"ok": True, "ignored": True, "reason": "no meeting id"}

        recipient = InterviewZoomService._find_recipient_for_meeting(db, meeting_id)
        if recipient is None:
            return {"ok": True, "ignored": True, "meeting_id": meeting_id}

        order = db.get(ServiceOrder, recipient.order_id)
        if order is None or not is_zoom_interview_order(order):
            return {"ok": True, "ignored": True, "meeting_id": meeting_id}

        artifacts = InterviewZoomService.fetch_meeting_artifacts(
            db,
            meeting_id,
            provider=str(_recipient_result(recipient).get("meeting_provider") or ""),
        )
        if not artifacts.get("ready"):
            _set_recipient_result(
                db,
                recipient,
                {"zoom_webhook_event": event_type, "zoom_pending_sync_at": datetime.utcnow().isoformat()},
            )
            return {"ok": True, "queued": True, "meeting_id": meeting_id}

        InterviewZoomService.finalize_recipient_artifacts(
            db, order=order, recipient=recipient, artifacts=artifacts, source="webhook"
        )
        return {"ok": True, "finalized": True, "meeting_id": meeting_id}

    @staticmethod
    def process_pending_sync(db: Session, *, limit: int = 10) -> int:
        """Poll Telnyx for Zoom meetings awaiting transcript/recording."""
        rows = list(
            db.execute(
                select(ServiceOrderRecipient)
                .join(ServiceOrder, ServiceOrder.id == ServiceOrderRecipient.order_id)
                .where(
                    ServiceOrder.service_code == "interview",
                    ServiceOrderRecipient.status == "scheduled",
                )
                .order_by(ServiceOrderRecipient.created_at.asc())
                .limit(max(limit * 3, 10))
            ).scalars()
        )
        processed = 0
        for recipient in rows:
            if processed >= limit:
                break
            order = db.get(ServiceOrder, recipient.order_id)
            if order is None or not is_zoom_interview_order(order):
                continue
            parsed = _recipient_result(recipient)
            if parsed.get("channel") != "zoom" or not parsed.get("zoom_meeting_id"):
                continue
            if parsed.get("transcript") and len(str(parsed.get("transcript"))) >= MIN_TRANSCRIPT_CHARS:
                continue

            artifacts = InterviewZoomService.fetch_meeting_artifacts(
                db,
                str(parsed["zoom_meeting_id"]),
                provider=str(parsed.get("meeting_provider") or ""),
            )
            if not artifacts.get("ready"):
                continue
            if InterviewZoomService.finalize_recipient_artifacts(
                db, order=order, recipient=recipient, artifacts=artifacts, source="poll"
            ):
                processed += 1
        return processed

    @staticmethod
    def start_campaign(db: Session, order: ServiceOrder) -> None:
        if order.service_code != "interview":
            raise ValueError("Not an interview order")
        config = _order_config(order)
        if str(config.get("delivery") or "").strip().lower() != "zoom":
            raise ValueError("Interview order is not configured for Zoom")

        role = str(config.get("role") or order.title or "Interview").strip()
        recipients = ServiceOrderService.get_recipients(db, order.id)
        now = datetime.utcnow()
        order.status = "running"
        order.started_at = order.started_at or now
        order.updated_at = now
        db.add(order)
        db.commit()

        for recipient in recipients:
            topic = f"{role} — {recipient.name or 'Candidate'}"
            try:
                meeting = InterviewZoomService.create_zoom_meeting_via_telnyx(db, topic=topic)
            except Exception as exc:
                recipient.status = "failed"
                merged = _recipient_result(recipient)
                merged.update({"channel": "zoom", "error": str(exc)[:500]})
                recipient.result_json = json.dumps(merged, ensure_ascii=False)
                db.add(recipient)
                continue

            join_url = str(meeting.get("join_url") or "").strip()
            recipient.status = "scheduled" if join_url else "failed"
            merged = _recipient_result(recipient)
            merged.update(
                {
                    "channel": "zoom",
                    "zoom_meeting_id": meeting.get("id"),
                    "meeting_provider": meeting.get("meeting_provider") or "zoom_oauth",
                    "join_url": join_url,
                    "scheduling_url": join_url,
                    "scheduling_url_sent_at": now.isoformat(),
                    "delivered_at": now.isoformat(),
                    "invite_sent_at": now.isoformat(),
                }
            )
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)

            if join_url and recipient.email:
                try:
                    TransactionalEmailService.send_templated_optional(
                        db,
                        template_key="interview_zoom_invite",
                        to_addr=str(recipient.email).strip(),
                        variables={
                            "candidate_name": recipient.name or "there",
                            "role": role,
                            "join_url": join_url,
                        },
                    )
                except Exception:
                    pass

        db.commit()
        InterviewZoomService._finalize_order_if_ready(db, order)
        db.refresh(order)
