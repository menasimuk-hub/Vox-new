"""Platform and order-level WA Survey AI picker settings (P4)."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.wa_survey_platform_settings import WaSurveyPlatformSettings
from app.services.survey_flow_config_service import is_graph_flow
from app.services.survey_flow_constants import MAX_PICKER_INVOCATIONS_PER_SESSION, NEXT_RESOLUTION_AI_ASSISTED


def is_ai_picker_enabled_on_order(config: dict[str, Any]) -> bool:
    return bool(config.get("ai_picker_enabled"))


class SurveyPickerSettingsService:
    @staticmethod
    def ensure_row(db: Session) -> WaSurveyPlatformSettings:
        row = db.get(WaSurveyPlatformSettings, "default")
        if row is None:
            row = WaSurveyPlatformSettings(
                id="default",
                ai_picker_enabled=True,
                updated_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def is_platform_picker_enabled(db: Session) -> bool:
        env = str(os.getenv("WA_SURVEY_AI_PICKER_ENABLED", "true")).strip().lower()
        if env in ("0", "false", "no", "off"):
            return False
        row = SurveyPickerSettingsService.ensure_row(db)
        return bool(row.ai_picker_enabled)

    @staticmethod
    def get_settings(db: Session) -> dict[str, Any]:
        row = SurveyPickerSettingsService.ensure_row(db)
        return {
            "ai_picker_enabled": bool(row.ai_picker_enabled),
            "max_invocations_per_session": MAX_PICKER_INVOCATIONS_PER_SESSION,
            "env_override": os.getenv("WA_SURVEY_AI_PICKER_ENABLED"),
        }

    @staticmethod
    def update_settings(db: Session, *, ai_picker_enabled: bool) -> dict[str, Any]:
        row = SurveyPickerSettingsService.ensure_row(db)
        row.ai_picker_enabled = bool(ai_picker_enabled)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return SurveyPickerSettingsService.get_settings(db)

    @staticmethod
    def can_invoke_picker(
        db: Session,
        *,
        config: dict[str, Any],
        session,
        current_node: dict[str, Any] | None,
    ) -> tuple[bool, str]:
        """Return (allowed, skip_reason)."""
        if not is_graph_flow(config):
            return False, "not_graph_flow"
        if not is_ai_picker_enabled_on_order(config):
            return False, "order_ai_picker_disabled"
        if not SurveyPickerSettingsService.is_platform_picker_enabled(db):
            return False, "platform_disabled"
        node = current_node or {}
        if str(node.get("next_resolution") or "").strip().lower() != NEXT_RESOLUTION_AI_ASSISTED:
            return False, "node_not_ai_assisted"
        count = int(getattr(session, "picker_invocation_count", 0) or 0)
        if count >= MAX_PICKER_INVOCATIONS_PER_SESSION:
            return False, "cap_exceeded"
        return True, ""
