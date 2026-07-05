"""Per-template Meta sync routing for Survey + Customer Feedback system templates."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import FeedbackWaTemplate
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.survey_system_template_service import SYSTEM_TEMPLATE_KINDS


class WaSystemTemplateRoutingError(ValueError):
    pass


class WaSystemTemplateRoutingService:
    @staticmethod
    def is_survey_system_template_row(db: Session, row: TelnyxWhatsappTemplate | None) -> bool:
        if row is None:
            return False
        st_ids = list(
            db.execute(
                select(SurveyTypeTemplate.survey_type_id).where(
                    SurveyTypeTemplate.template_id == int(row.id)
                )
            ).scalars().all()
        )
        if not st_ids:
            return False
        kinds = list(
            db.execute(
                select(SurveyType.system_template_kind).where(
                    SurveyType.id.in_(st_ids),
                    SurveyType.system_template_kind.in_(SYSTEM_TEMPLATE_KINDS),
                )
            ).scalars().all()
        )
        return bool(kinds)

    @staticmethod
    def is_feedback_system_template_row(row: FeedbackWaTemplate | None) -> bool:
        if row is None:
            return False
        return row.industry_id is None and row.survey_type_id is None

    @staticmethod
    def survey_uses_meta_sync(db: Session, row: TelnyxWhatsappTemplate) -> bool:
        return bool(row.sync_from_meta) and WaSystemTemplateRoutingService.is_survey_system_template_row(
            db, row
        )

    @staticmethod
    def feedback_uses_meta_sync(row: FeedbackWaTemplate) -> bool:
        return bool(row.sync_from_meta) and WaSystemTemplateRoutingService.is_feedback_system_template_row(
            row
        )

    @staticmethod
    def survey_effective_components(
        db: Session | None,
        row: TelnyxWhatsappTemplate,
        *,
        draft_list: list[Any],
        remote_list: list[Any],
    ) -> list[Any]:
        from app.services.survey_whatsapp_template_service import (
            _merge_draft_with_remote_components,
            template_row_is_sendable_on_meta,
        )

        if (
            db is not None
            and WaSystemTemplateRoutingService.survey_uses_meta_sync(db, row)
            and remote_list
            and template_row_is_sendable_on_meta(row)
        ):
            return list(remote_list)
        return _merge_draft_with_remote_components(draft_list, remote_list)

    @staticmethod
    def apply_survey_remote_content_to_row(
        db: Session,
        row: TelnyxWhatsappTemplate,
        remote_components: list[Any],
    ) -> bool:
        if not WaSystemTemplateRoutingService.survey_uses_meta_sync(db, row):
            return False
        if not isinstance(remote_components, list) or not remote_components:
            return False
        from app.services.survey_whatsapp_template_service import _dumps, _normalize_draft_components

        normalized = _normalize_draft_components(remote_components)
        row.draft_components_json = _dumps(normalized)
        row.components_json = _dumps(remote_components)
        db.add(row)
        return True

    @staticmethod
    def extract_remote_body_text(remote: dict[str, Any]) -> str | None:
        components = remote.get("components")
        if isinstance(components, str):
            try:
                components = json.loads(components)
            except json.JSONDecodeError:
                components = None
        if not isinstance(components, list):
            return None
        for comp in components:
            if not isinstance(comp, dict):
                continue
            if str(comp.get("type") or "").upper() == "BODY":
                text = str(comp.get("text") or "").strip()
                if text:
                    return text
        return None

    @staticmethod
    def extract_remote_buttons(remote: dict[str, Any]) -> list[dict[str, str]] | None:
        components = remote.get("components")
        if isinstance(components, str):
            try:
                components = json.loads(components)
            except json.JSONDecodeError:
                components = None
        if not isinstance(components, list):
            return None
        for comp in components:
            if not isinstance(comp, dict):
                continue
            if str(comp.get("type") or "").upper() != "BUTTONS":
                continue
            buttons = comp.get("buttons")
            if not isinstance(buttons, list):
                continue
            out: list[dict[str, str]] = []
            for btn in buttons:
                if not isinstance(btn, dict):
                    continue
                text = str(btn.get("text") or btn.get("title") or "").strip()
                if not text:
                    continue
                out.append({"type": "QUICK_REPLY", "text": text[:20]})
            return out or None
        return None

    @staticmethod
    def apply_feedback_remote_content_to_row(
        db: Session,
        tpl: FeedbackWaTemplate,
        remote: dict[str, Any],
    ) -> bool:
        if not WaSystemTemplateRoutingService.feedback_uses_meta_sync(tpl):
            return False
        body = WaSystemTemplateRoutingService.extract_remote_body_text(remote)
        if not body:
            return False
        tpl.body_text = body
        buttons = WaSystemTemplateRoutingService.extract_remote_buttons(remote)
        if buttons is not None:
            tpl.buttons_json = json.dumps(buttons)
        tpl.updated_at = datetime.utcnow()
        db.add(tpl)
        return True
