"""Inbound WhatsApp message persistence for Abuu."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.abuu.models.entities import AbuuInboundMessage


class AbuuInboundMessageService:
    @staticmethod
    def save(
        db: Session,
        *,
        customer_phone: str,
        customer_id: str | None,
        source_message_id: str | None,
        message_type: str,
        body_text: str | None = None,
        transcript_text: str | None = None,
        transcript_confidence: float | None = None,
        voice_media_url: str | None = None,
        voice_content_type: str | None = None,
        voice_storage_path: str | None = None,
        payload: dict | None = None,
    ) -> AbuuInboundMessage:
        row = AbuuInboundMessage(
            customer_phone=customer_phone,
            customer_id=customer_id,
            source_message_id=source_message_id,
            message_type=message_type,
            body_text=body_text,
            transcript_text=transcript_text,
            transcript_confidence=transcript_confidence,
            voice_media_url=voice_media_url,
            voice_content_type=voice_content_type,
            voice_storage_path=voice_storage_path,
            payload_json=json.dumps(payload or {}),
            created_at=datetime.utcnow(),
        )
        db.add(row)
        db.flush()
        return row
