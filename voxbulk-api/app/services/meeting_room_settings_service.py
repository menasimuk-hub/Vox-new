"""Platform-wide meeting room defaults (admin-configured)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.constants.meeting_room_languages import (
    DEFAULT_MEETING_ROOM_LANGUAGE,
    meeting_room_language_label,
    meeting_room_language_options,
    normalize_meeting_room_language_code,
)
from app.models.agent import AgentDefinition
from app.models.meeting_room_platform_settings import MeetingRoomPlatformSettings

DEFAULT_ROW_ID = "default"


class MeetingRoomSettingsService:
    @staticmethod
    def _get_or_create(db: Session) -> MeetingRoomPlatformSettings:
        row = db.get(MeetingRoomPlatformSettings, DEFAULT_ROW_ID)
        if row is None:
            row = MeetingRoomPlatformSettings(
                id=DEFAULT_ROW_ID,
                agent_id=None,
                language_code=DEFAULT_MEETING_ROOM_LANGUAGE,
                updated_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def settings_to_dict(row: MeetingRoomPlatformSettings) -> dict[str, Any]:
        code = str(row.language_code or DEFAULT_MEETING_ROOM_LANGUAGE).strip().lower()
        return {
            "agent_id": row.agent_id,
            "language_code": code,
            "language_label": meeting_room_language_label(code),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def get_settings(db: Session) -> dict[str, Any]:
        return MeetingRoomSettingsService.settings_to_dict(MeetingRoomSettingsService._get_or_create(db))

    @staticmethod
    def update_settings(
        db: Session,
        *,
        agent_id: str | None,
        language_code: str | None,
    ) -> dict[str, Any]:
        row = MeetingRoomSettingsService._get_or_create(db)
        clean_agent = str(agent_id or "").strip() or None
        if clean_agent:
            agent = db.get(AgentDefinition, clean_agent)
            if not agent or not agent.is_active or not agent.supports_interview:
                raise ValueError("Selected agent must be active and support interviews")
        row.agent_id = clean_agent
        row.language_code = normalize_meeting_room_language_code(language_code)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return MeetingRoomSettingsService.settings_to_dict(row)

    @staticmethod
    def language_options() -> list[dict[str, str]]:
        return meeting_room_language_options()
