"""Durable six-stage debug logging for Abuu voice order pipeline."""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuVoiceOrderDebug, CustomerOrder
from app.abuu.services.serializers import order_to_dict
from app.core.config import get_settings

logger = logging.getLogger(__name__)

_voice_order_debug_id: ContextVar[str | None] = ContextVar("voice_order_debug_id", default=None)


def debug_enabled() -> bool:
    return bool(get_settings().abuu_voice_order_debug)


def set_debug_request_id(order_request_id: str | None) -> None:
    _voice_order_debug_id.set(order_request_id)


def get_debug_request_id() -> str | None:
    return _voice_order_debug_id.get()


def _resolve_id(order_request_id: str | None = None) -> str | None:
    return order_request_id or get_debug_request_id()


def _load_row(db: Session, order_request_id: str) -> AbuuVoiceOrderDebug | None:
    return db.get(AbuuVoiceOrderDebug, order_request_id)


class VoiceOrderDebugService:
    @staticmethod
    def begin(
        db: Session,
        *,
        customer_phone: str,
        message_id: str | None,
        pipeline: str,
    ) -> str | None:
        if not debug_enabled():
            return None
        order_request_id = str(uuid.uuid4())
        row = AbuuVoiceOrderDebug(
            order_request_id=order_request_id,
            customer_phone=customer_phone,
            message_id=message_id,
            pipeline=str(pipeline or "agent"),
        )
        db.add(row)
        db.flush()
        set_debug_request_id(order_request_id)
        logger.info(
            "voice_order_debug_begin order_request_id=%s phone=%s pipeline=%s message_id=%s",
            order_request_id,
            customer_phone,
            pipeline,
            message_id,
        )
        return order_request_id

    @staticmethod
    def record_audio(
        db: Session,
        *,
        media_url: str | None,
        storage_path: str | None,
        content_type: str | None,
        file_size_bytes: int | None,
        duration_seconds: float | None,
        order_request_id: str | None = None,
    ) -> None:
        rid = _resolve_id(order_request_id)
        if not rid:
            return
        row = _load_row(db, rid)
        if row is None:
            return
        row.audio_media_url = media_url
        row.audio_storage_path = storage_path
        row.audio_content_type = content_type
        row.audio_file_size_bytes = file_size_bytes
        row.audio_duration_seconds = duration_seconds
        row.updated_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def record_stt(
        db: Session,
        *,
        raw_transcript: str,
        order_request_id: str | None = None,
    ) -> None:
        rid = _resolve_id(order_request_id)
        if not rid:
            return
        row = _load_row(db, rid)
        if row is None:
            return
        row.stt_raw_transcript = raw_transcript
        row.updated_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def record_llm_prompt(
        db: Session,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]] | None = None,
        session_snapshot: dict[str, Any] | None = None,
        order_request_id: str | None = None,
    ) -> None:
        rid = _resolve_id(order_request_id)
        if not rid:
            return
        row = _load_row(db, rid)
        if row is None:
            return
        row.llm_system_prompt = system_prompt
        row.llm_messages_json = json.dumps(messages or [], ensure_ascii=False)
        if session_snapshot is not None:
            row.session_snapshot_json = json.dumps(session_snapshot, ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def record_llm_raw(
        db: Session,
        *,
        raw_response: str | dict[str, Any],
        order_request_id: str | None = None,
    ) -> None:
        rid = _resolve_id(order_request_id)
        if not rid:
            return
        row = _load_row(db, rid)
        if row is None:
            return
        if isinstance(raw_response, dict):
            row.llm_raw_response = json.dumps(raw_response, ensure_ascii=False)
        else:
            row.llm_raw_response = str(raw_response or "")
        row.updated_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def record_parsed(
        db: Session,
        *,
        parsed: dict[str, Any],
        parse_status: str,
        parse_error: str | None = None,
        parse_retry_count: int = 0,
        order_request_id: str | None = None,
    ) -> None:
        rid = _resolve_id(order_request_id)
        if not rid:
            return
        row = _load_row(db, rid)
        if row is None:
            return
        row.parsed_action_json = json.dumps(parsed, ensure_ascii=False)
        row.parse_status = parse_status
        row.parse_error = parse_error
        row.parse_retry_count = max(0, int(parse_retry_count or 0))
        row.updated_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def record_final_order(
        db: Session,
        *,
        order: CustomerOrder | None,
        order_request_id: str | None = None,
    ) -> None:
        rid = _resolve_id(order_request_id)
        if not rid or order is None:
            return
        row = _load_row(db, rid)
        if row is None:
            return
        row.order_id = order.id
        row.final_order_json = json.dumps(order_to_dict(order), ensure_ascii=False)
        row.updated_at = datetime.utcnow()
        db.add(row)

    @staticmethod
    def get_bundle(db: Session, order_request_id: str) -> dict[str, Any] | None:
        row = _load_row(db, order_request_id)
        if row is None:
            return None

        def _parse_json(raw: str | None) -> Any:
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw

        return {
            "order_request_id": row.order_request_id,
            "customer_phone": row.customer_phone,
            "message_id": row.message_id,
            "pipeline": row.pipeline,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "stages": {
                "1_audio": {
                    "media_url": row.audio_media_url,
                    "storage_path": row.audio_storage_path,
                    "content_type": row.audio_content_type,
                    "file_size_bytes": row.audio_file_size_bytes,
                    "duration_seconds": row.audio_duration_seconds,
                },
                "2_stt_raw": {
                    "transcript": row.stt_raw_transcript,
                },
                "3_llm_prompt": {
                    "system_prompt": row.llm_system_prompt,
                    "messages": _parse_json(row.llm_messages_json),
                    "session_snapshot": _parse_json(row.session_snapshot_json),
                },
                "4_llm_raw": {
                    "response": _parse_json(row.llm_raw_response) if row.llm_raw_response and row.llm_raw_response.strip().startswith("{") else row.llm_raw_response,
                },
                "5_parsed": {
                    "action": _parse_json(row.parsed_action_json),
                    "parse_status": row.parse_status,
                    "parse_error": row.parse_error,
                    "parse_retry_count": row.parse_retry_count,
                },
                "6_final_order": {
                    "order_id": row.order_id,
                    "order": _parse_json(row.final_order_json),
                },
            },
        }
