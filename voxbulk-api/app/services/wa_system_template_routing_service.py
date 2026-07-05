"""Local vs Meta-sync routing for Survey + Customer Feedback system templates."""

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
from app.models.wa_system_template_routing_settings import (
    TEMPLATE_SOURCE_LOCAL,
    TEMPLATE_SOURCE_META_SYNC,
    WaSystemTemplateRoutingSettings,
)
from app.services.survey_system_template_service import SYSTEM_TEMPLATE_KINDS

PRODUCT_SURVEY = "survey"
PRODUCT_FEEDBACK = "feedback"
VALID_PRODUCTS = frozenset({PRODUCT_SURVEY, PRODUCT_FEEDBACK})
VALID_SOURCES = frozenset({TEMPLATE_SOURCE_LOCAL, TEMPLATE_SOURCE_META_SYNC})


class WaSystemTemplateRoutingError(ValueError):
    pass


def normalize_template_source(raw: str | None) -> str:
    value = str(raw or TEMPLATE_SOURCE_LOCAL).strip().lower()
    if value in {"meta", "sync", "meta_sync", "remote"}:
        return TEMPLATE_SOURCE_META_SYNC
    if value in {"local", "keep_local", "draft"}:
        return TEMPLATE_SOURCE_LOCAL
    if value not in VALID_SOURCES:
        raise WaSystemTemplateRoutingError(
            f"template_source must be one of: {TEMPLATE_SOURCE_LOCAL}, {TEMPLATE_SOURCE_META_SYNC}"
        )
    return value


class WaSystemTemplateRoutingService:
    @staticmethod
    def ensure_row(db: Session, product: str) -> WaSystemTemplateRoutingSettings:
        product_norm = str(product or "").strip().lower()
        if product_norm not in VALID_PRODUCTS:
            raise WaSystemTemplateRoutingError(f"Unknown product: {product!r}")
        row = db.get(WaSystemTemplateRoutingSettings, product_norm)
        if row is None:
            row = WaSystemTemplateRoutingSettings(
                product=product_norm,
                template_source=TEMPLATE_SOURCE_LOCAL,
                updated_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def get_settings(db: Session, product: str) -> dict[str, Any]:
        row = WaSystemTemplateRoutingService.ensure_row(db, product)
        source = normalize_template_source(row.template_source)
        return {
            "product": row.product,
            "template_source": source,
            "uses_meta_sync": source == TEMPLATE_SOURCE_META_SYNC,
            "label": (
                "Sync from Meta"
                if source == TEMPLATE_SOURCE_META_SYNC
                else "Keep local (Admin is source of truth)"
            ),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def update_settings(db: Session, product: str, *, template_source: str) -> dict[str, Any]:
        row = WaSystemTemplateRoutingService.ensure_row(db, product)
        row.template_source = normalize_template_source(template_source)
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return WaSystemTemplateRoutingService.get_settings(db, product)

    @staticmethod
    def uses_meta_sync(db: Session, product: str) -> bool:
        row = WaSystemTemplateRoutingService.ensure_row(db, product)
        return normalize_template_source(row.template_source) == TEMPLATE_SOURCE_META_SYNC

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
            and WaSystemTemplateRoutingService.uses_meta_sync(db, PRODUCT_SURVEY)
            and WaSystemTemplateRoutingService.is_survey_system_template_row(db, row)
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
        if not WaSystemTemplateRoutingService.uses_meta_sync(db, PRODUCT_SURVEY):
            return False
        if not WaSystemTemplateRoutingService.is_survey_system_template_row(db, row):
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
        if not WaSystemTemplateRoutingService.uses_meta_sync(db, PRODUCT_FEEDBACK):
            return False
        if not WaSystemTemplateRoutingService.is_feedback_system_template_row(tpl):
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

    @staticmethod
    def feedback_body_for_send(db: Session, tpl: FeedbackWaTemplate) -> str:
        if (
            WaSystemTemplateRoutingService.uses_meta_sync(db, PRODUCT_FEEDBACK)
            and WaSystemTemplateRoutingService.is_feedback_system_template_row(tpl)
        ):
            return str(tpl.body_text or "")
        return str(tpl.body_text or "")
