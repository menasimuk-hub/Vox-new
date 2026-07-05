"""System survey templates — welcome, thank-you, tell-us-more under hidden industry."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.industry import Industry
from app.models.survey_type import SurveyType
from app.models.survey_type_template import SurveyTypeTemplate
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.industry_service import SYSTEM_SURVEY_INDUSTRY_SLUG, IndustryService
from app.services.providers.openai_service import OpenAIProviderService
from app.services.survey_type_service import survey_type_to_dict
from app.services.survey_whatsapp_template_service import (
    SurveyWhatsappTemplateError,
    SurveyWhatsappTemplateService,
    survey_template_to_dict,
)
from app.services.survey_wa_template_pack_service import (
    SurveyWaTemplatePackError,
    SurveyWaTemplatePackService,
    _build_pack_item_row,
    _meta_compliance_rules_block,
    _NAME_RE,
    _normalize_button_type,
    _normalize_category,
    _slug_token,
    assert_openai_strict_json_schema,
    build_system_template_json_schema,
)
from app.services.survey_type_template_service import SurveyTypeTemplateService
import logging

from app.services.wa_template_privacy import PRIVACY_MODE_OFF, PRIVACY_MODE_ON, normalize_privacy_mode, resolve_row_privacy_mode

logger = logging.getLogger(__name__)

WELCOME_TEMPLATE_ANONYMOUS_NAME = "voxbulk_survey_welcome_templates_global_welcome_anonymous_start_2"
WELCOME_TEMPLATE_NAMED_NAME = "voxbulk_survey_welcome_templates_standard"

# WA_FINAL_FEEDBACK_SYSTEM_TEMPLATE_ACTIVE — health/build deploy marker (runtime_build_info).
FINAL_FEEDBACK_SYSTEM_TEMPLATE_MARKER = "WA_FINAL_FEEDBACK_SYSTEM_TEMPLATE_ACTIVE"

SYSTEM_TEMPLATE_KINDS = ("welcome", "thank_you", "tell_us_more", "final_feedback")

KIND_LABELS: dict[str, str] = {
    "welcome": "Welcome templates",
    "thank_you": "Thank-you templates",
    "tell_us_more": "Tell us more templates",
    "final_feedback": "Closing question templates",
}

SYSTEM_SURVEY_TYPES: list[dict[str, Any]] = [
    {
        "slug": "welcome_templates",
        "name": "Welcome templates",
        "system_template_kind": "welcome",
        "description": "Survey opening templates — customer picks one when creating a survey.",
        "sort_order": 10,
    },
    {
        "slug": "thank_you_template",
        "name": "Thank you templates",
        "system_template_kind": "thank_you",
        "description": "Survey closing templates — customer picks one when creating a survey.",
        "sort_order": 20,
    },
    {
        "slug": "tell_us_more",
        "name": "Tell us more",
        "system_template_kind": "tell_us_more",
        "description": "Low-rating follow-up prompt — applied automatically when score is low.",
        "sort_order": 30,
    },
    {
        "slug": "final_feedback",
        "name": "Closing question",
        "system_template_kind": "final_feedback",
        "description": "Optional closing open-text prompt after Yes on final feedback step.",
        "sort_order": 35,
    },
]


class SurveySystemTemplateError(ValueError):
    pass


def normalize_system_template_kind(raw: str | None) -> str:
    kind = str(raw or "").strip().lower()
    if kind not in SYSTEM_TEMPLATE_KINDS:
        raise SurveySystemTemplateError(
            f"system_template_kind must be one of: {', '.join(SYSTEM_TEMPLATE_KINDS)}"
        )
    return kind


def _step_role_for_kind(kind: str) -> str:
    if kind == "welcome":
        return "start"
    if kind == "thank_you":
        return "completion"
    if kind == "final_feedback":
        return "final_feedback_text"
    return "reason"


def _variant_label(row: TelnyxWhatsappTemplate) -> str:
    variant = str(row.variant_type or "standard").strip().lower()
    privacy = resolve_row_privacy_mode(row)
    if variant == "anonymous" or privacy == PRIVACY_MODE_ON:
        return "Anonymous"
    return "Named"


def _body_text_from_template(row: TelnyxWhatsappTemplate) -> str:
    preview = str(row.body_preview or "").strip()
    if preview:
        return preview
    return str(row.display_name or row.name or "").strip()


def _default_components_for_kind(kind: str, *, privacy_mode: str = PRIVACY_MODE_OFF) -> list[dict[str, Any]]:
    privacy = normalize_privacy_mode(privacy_mode)
    if kind == "welcome":
        if privacy == PRIVACY_MODE_ON:
            return [
                {
                    "type": "BODY",
                    "text": (
                        "👋 Tap below to start a short anonymous survey — "
                        "it only takes a minute and is not linked to you."
                    ),
                },
                {"type": "FOOTER", "text": "Reply STOP to opt out"},
                {
                    "type": "BUTTONS",
                    "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}],
                },
            ]
        return [
            {
                "type": "BODY",
                "text": (
                    "Hi {{1}}, we'd love your feedback. "
                    "Tap below to start a short survey — it only takes a minute."
                ),
                "example": {"body_text": [["Alex"]]},
            },
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
            {
                "type": "BUTTONS",
                "buttons": [{"type": "QUICK_REPLY", "text": "Start survey"}],
            },
        ]
    if kind == "thank_you":
        body = (
            "🙏 Thank you — your anonymous feedback has been recorded."
            if privacy == PRIVACY_MODE_ON
            else "🙏 Thank you for sharing your feedback. We really appreciate your time."
        )
        return [
            {"type": "BODY", "text": body},
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
        ]
    if kind == "final_feedback":
        return [
            {
                "type": "BODY",
                "text": "📝 Please share anything else you'd like us to know.",
            },
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
        ]
    # tell_us_more — no buttons; session free-form reply
    return [
        {
            "type": "BODY",
            "text": (
                "We're sorry to hear that. Could you tell us a bit more about what went wrong? "
                "Your reply helps us improve."
            ),
        },
        {"type": "FOOTER", "text": "Reply STOP to opt out"},
    ]


def _system_template_seed(*, kind: str, idx: int) -> dict[str, Any]:
    """Sensible defaults when OpenAI returns incomplete system-template drafts."""
    step_role = _step_role_for_kind(kind)
    if kind == "welcome":
        body = (
            "Hi {{1}}, we'd love your feedback. "
            "Tap below to start a short survey — it only takes a minute."
        )
        seed = {
            "template_name": f"welcome_variant_{idx + 1}",
            "title": f"Welcome variant {idx + 1}",
            "body": body,
            "button_type": "quick_reply",
            "buttons": [{"text": "Start survey", "url": "", "phone_number": ""}],
            "example_values": ["Alex"],
            "step_role": step_role,
            "purpose": "welcome",
            "outcome_key": None,
        }
    elif kind == "thank_you":
        body = "Thank you {{1}} for sharing your feedback. We really appreciate your time."
        seed = {
            "template_name": f"thank_you_variant_{idx + 1}",
            "title": f"Thank you variant {idx + 1}",
            "body": body,
            "button_type": "none",
            "buttons": [],
            "example_values": ["Alex"],
            "step_role": step_role,
            "purpose": "thank_you",
            "outcome_key": "neutral",
        }
    elif kind == "final_feedback":
        body = "Please share anything else you'd like us to know."
        seed = {
            "template_name": f"final_feedback_variant_{idx + 1}",
            "title": f"Closing question variant {idx + 1}",
            "body": body,
            "button_type": "none",
            "buttons": [],
            "example_values": ["there"],
            "step_role": step_role,
            "purpose": "final_feedback",
            "outcome_key": None,
        }
    else:
        body = (
            "We're sorry to hear that. Could you tell us a bit more about what went wrong? "
            "Your reply helps us improve."
        )
        seed = {
            "template_name": f"tell_us_more_variant_{idx + 1}",
            "title": f"Tell us more variant {idx + 1}",
            "body": body,
            "button_type": "none",
            "buttons": [],
            "example_values": ["there"],
            "step_role": step_role,
            "purpose": "tell_us_more",
            "outcome_key": None,
        }

    seed["header"] = ""
    seed["footer"] = "Reply STOP to opt out"
    seed["language"] = "en_US"
    seed["category"] = "UTILITY"
    seed["variant_type"] = "standard"
    seed["privacy_mode"] = PRIVACY_MODE_OFF

    name = _slug_token(seed["template_name"], fallback="")
    if not name or not _NAME_RE.match(name):
        seed["template_name"] = _slug_token(f"{kind}_{idx + 1}", fallback=f"{kind}_tpl")
    if _normalize_button_type(seed.get("button_type")) == "none" and kind == "welcome":
        seed["button_type"] = "quick_reply"
        seed["buttons"] = [{"text": "Start survey", "url": "", "phone_number": ""}]
    seed["category"] = _normalize_category(seed.get("category"))
    return seed


def normalize_system_generated_item(
    item: dict[str, Any],
    *,
    kind: str,
    idx: int,
) -> dict[str, Any]:
    """Merge OpenAI output with Meta-safe defaults so admin drafts are viewable and savable."""
    kind = normalize_system_template_kind(kind)
    seed = _system_template_seed(kind=kind, idx=idx)
    merged: dict[str, Any] = {**seed}
    for key, value in item.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip() and key not in {"header", "outcome_key"}:
            continue
        merged[key] = value

    body = str(merged.get("body") or "").strip()
    if not body:
        merged["body"] = seed["body"]

    name = _slug_token(merged.get("template_name"), fallback="")
    if not name or not _NAME_RE.match(name):
        merged["template_name"] = seed["template_name"]

    if not str(merged.get("title") or "").strip():
        merged["title"] = seed["title"]

    merged["step_role"] = _step_role_for_kind(kind)
    merged["variant_type"] = "standard"
    merged["privacy_mode"] = PRIVACY_MODE_OFF
    if kind == "thank_you":
        merged["outcome_key"] = "neutral"
        merged["button_type"] = merged.get("button_type") or "none"
        merged["buttons"] = merged.get("buttons") if isinstance(merged.get("buttons"), list) else []
    else:
        merged.pop("outcome_key", None)
    if kind == "welcome" and str(merged.get("button_type") or "none").strip().lower() == "none":
        merged["button_type"] = "quick_reply"
        if not merged.get("buttons"):
            merged["buttons"] = seed["buttons"]

    return merged


class SurveySystemTemplateService:
    @staticmethod
    def _admin_template_row(
        db: Session,
        tpl: TelnyxWhatsappTemplate,
        *,
        kind: str,
        survey_type: SurveyType,
        mapping: SurveyTypeTemplate | None = None,
    ) -> dict[str, Any]:
        payload = survey_template_to_dict(tpl, mapping=mapping)
        payload.update(
            {
                "system_template_kind": kind,
                "kind_label": KIND_LABELS[kind],
                "survey_type_id": survey_type.id,
                "survey_type_name": survey_type.name,
                "step_role": tpl.step_role or _step_role_for_kind(kind),
                "variant_label": _variant_label(tpl),
                "variant_type": tpl.variant_type or "standard",
                "privacy_mode": resolve_row_privacy_mode(tpl),
                "body_text": _body_text_from_template(tpl),
                "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
            }
        )
        return payload

    @staticmethod
    def _ensure_system_mapping(
        db: Session,
        *,
        survey_type: SurveyType,
        template: TelnyxWhatsappTemplate,
    ) -> SurveyTypeTemplate:
        is_anonymous = str(template.variant_type or "").lower() == "anonymous" or resolve_row_privacy_mode(
            template
        ) == PRIVACY_MODE_ON
        return SurveyTypeTemplateService.upsert_mapping(
            db,
            survey_type_id=survey_type.id,
            template_id=int(template.id),
            usable_as_standard=not is_anonymous,
            usable_as_anonymous=is_anonymous,
            privacy_mode=PRIVACY_MODE_ON if is_anonymous else PRIVACY_MODE_OFF,
        )

    @staticmethod
    def _templates_for_kind(db: Session, survey_type: SurveyType, kind: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[int] = set()
        mappings = list(
            db.execute(
                select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == survey_type.id)
            ).scalars()
        )
        for mapping in mappings:
            tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
            if tpl is None:
                continue
            seen.add(int(tpl.id))
            rows.append(
                SurveySystemTemplateService._admin_template_row(
                    db,
                    tpl,
                    kind=kind,
                    survey_type=survey_type,
                    mapping=mapping,
                )
            )

        orphans = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.survey_type_id == survey_type.id
                )
            ).scalars()
        )
        for tpl in orphans:
            tid = int(tpl.id)
            if tid in seen:
                continue
            SurveySystemTemplateService._ensure_system_mapping(db, survey_type=survey_type, template=tpl)
            seen.add(tid)
            rows.append(
                SurveySystemTemplateService._admin_template_row(
                    db,
                    tpl,
                    kind=kind,
                    survey_type=survey_type,
                )
            )

        rows.sort(
            key=lambda item: (
                str(item.get("updated_at") or item.get("created_at") or ""),
                str(item.get("display_name") or item.get("name") or ""),
            ),
            reverse=True,
        )
        return rows

    @staticmethod
    def ensure_system_industry(db: Session) -> Industry:
        IndustryService.ensure_defaults(db)
        row = db.execute(
            select(Industry).where(Industry.slug == SYSTEM_SURVEY_INDUSTRY_SLUG)
        ).scalar_one_or_none()
        now = datetime.utcnow()
        if row is None:
            row = Industry(
                id=str(uuid.uuid4()),
                slug=SYSTEM_SURVEY_INDUSTRY_SLUG,
                name="System survey templates",
                description="Hidden industry for welcome, thank-you, and low-rating templates.",
                is_active=True,
                is_hidden=True,
                sort_order=9999,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            try:
                db.commit()
                db.refresh(row)
            except IntegrityError:
                db.rollback()
                row = db.execute(
                    select(Industry).where(Industry.slug == SYSTEM_SURVEY_INDUSTRY_SLUG)
                ).scalar_one_or_none()
                if row is None:
                    raise
        elif not bool(getattr(row, "is_hidden", False)):
            row.is_hidden = True
            row.updated_at = now
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def ensure_system_survey_types(db: Session) -> list[SurveyType]:
        industry = SurveySystemTemplateService.ensure_system_industry(db)
        now = datetime.utcnow()
        created: list[SurveyType] = []
        for item in SYSTEM_SURVEY_TYPES:
            existing = db.execute(
                select(SurveyType).where(
                    SurveyType.industry_id == industry.id,
                    SurveyType.slug == item["slug"],
                )
            ).scalar_one_or_none()
            if existing is not None:
                if not existing.system_template_kind:
                    existing.system_template_kind = item["system_template_kind"]
                    existing.updated_at = now
                    db.add(existing)
                created.append(existing)
                continue
            row = SurveyType(
                id=str(uuid.uuid4()),
                industry_id=industry.id,
                slug=item["slug"],
                name=item["name"],
                description=item.get("description"),
                is_active=True,
                default_length="standard",
                min_length=4,
                max_length=6,
                supports_anonymous=True,
                system_template_kind=item["system_template_kind"],
                sort_order=int(item.get("sort_order") or 100),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            created.append(row)
        db.commit()
        return created

    @staticmethod
    def _system_survey_type_ids_for_kind(db: Session, kind: str) -> list[str]:
        kind = normalize_system_template_kind(kind)
        return list(
            db.execute(select(SurveyType.id).where(SurveyType.system_template_kind == kind)).scalars()
        )

    @staticmethod
    def template_mapped_to_system_kind(db: Session, template_id: int, kind: str) -> bool:
        """True when template is linked (or is the sendable row for a link) to a system kind."""
        try:
            tid = int(template_id)
        except (TypeError, ValueError):
            return False
        st_ids = SurveySystemTemplateService._system_survey_type_ids_for_kind(db, kind)
        if not st_ids:
            return False
        direct = db.execute(
            select(SurveyTypeTemplate.id).where(
                SurveyTypeTemplate.survey_type_id.in_(st_ids),
                SurveyTypeTemplate.template_id == tid,
            )
        ).scalar_one_or_none()
        if direct is not None:
            return True
        tpl = db.get(TelnyxWhatsappTemplate, tid)
        if tpl is not None and tpl.survey_type_id:
            st = db.get(SurveyType, str(tpl.survey_type_id))
            if st is not None and str(st.system_template_kind or "") == kind:
                return True
        if tpl is not None:
            parent_id = int(tpl.parent_template_id or 0)
            if parent_id and SurveySystemTemplateService.template_mapped_to_system_kind(db, parent_id, kind):
                return True
        from app.services.survey_whatsapp_template_service import resolve_sendable_template_row

        for st_id in st_ids:
            mappings = list(
                db.execute(
                    select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == st_id)
                ).scalars()
            )
            for mapping in mappings:
                mapped = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if mapped is None or not mapped.active_for_survey:
                    continue
                sendable = resolve_sendable_template_row(db, mapped)
                if sendable is not None and int(sendable.id) == tid:
                    return True
        return False

    @staticmethod
    def picker_row_for_mapped_system_template(
        db: Session,
        tpl: TelnyxWhatsappTemplate,
    ) -> TelnyxWhatsappTemplate | None:
        """Dashboard picker row: one mapped row — enabled and Meta-approved only."""
        if not tpl.active_for_survey:
            return None
        from app.services.survey_whatsapp_template_service import template_row_is_sendable_on_meta

        if not template_row_is_sendable_on_meta(tpl):
            return None
        return tpl

    @staticmethod
    def is_builder_listed_system_template_id(db: Session, template_id: int, kind: str) -> bool:
        """True when template id appears in dashboard system-templates list for kind."""
        try:
            tid = int(template_id)
        except (TypeError, ValueError):
            return False
        listed_ids: set[int] = set()
        for st_id in SurveySystemTemplateService._system_survey_type_ids_for_kind(db, kind):
            mappings = list(
                db.execute(
                    select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == st_id)
                ).scalars()
            )
            for mapping in mappings:
                tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if tpl is None:
                    continue
                listed = SurveySystemTemplateService.picker_row_for_mapped_system_template(db, tpl)
                if listed is not None:
                    listed_ids.add(int(listed.id))
        return tid in listed_ids

    @staticmethod
    def list_templates_for_builder(db: Session) -> dict[str, Any]:
        """Templates grouped by kind for dashboard survey builder."""
        SurveySystemTemplateService.ensure_system_survey_types(db)
        grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in SYSTEM_TEMPLATE_KINDS}
        seen_ids: dict[str, set[int]] = {k: set() for k in SYSTEM_TEMPLATE_KINDS}
        from app.services.survey_whatsapp_template_service import template_row_is_sendable_on_meta

        types = list(
            db.execute(
                select(SurveyType).where(SurveyType.system_template_kind.in_(SYSTEM_TEMPLATE_KINDS))
            ).scalars()
        )
        for st in types:
            kind = str(st.system_template_kind or "").strip()
            if kind not in grouped:
                continue
            mappings = list(
                db.execute(
                    select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == st.id)
                ).scalars()
            )
            for mapping in mappings:
                tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if tpl is None:
                    continue
                listed = SurveySystemTemplateService.picker_row_for_mapped_system_template(db, tpl)
                if listed is None:
                    continue
                tid = int(listed.id)
                if tid in seen_ids[kind]:
                    continue
                seen_ids[kind].add(tid)
                status = str(listed.status or "").upper()
                grouped[kind].append(
                    {
                        **survey_template_to_dict(listed),
                        "survey_type_id": st.id,
                        "survey_type_name": st.name,
                        "survey_type_slug": st.slug,
                        "is_approved": template_row_is_sendable_on_meta(listed),
                    }
                )
        return {"ok": True, "templates": grouped}

    @staticmethod
    def resolve_order_welcome_template_row(
        db: Session,
        config: dict[str, Any],
    ) -> TelnyxWhatsappTemplate | None:
        """Welcome for send: wizard/runtime selection first, system resolver only as fallback."""
        from app.services.survey_builder_runtime_service import load_builder_runtime
        from app.services.survey_whatsapp_template_service import template_row_is_sendable_on_meta

        runtime = load_builder_runtime(config)
        explicit_ids: list[int] = []
        if runtime and runtime.get("welcome_template_id"):
            try:
                explicit_ids.append(int(runtime["welcome_template_id"]))
            except (TypeError, ValueError):
                pass
        for key in ("welcome_template_id", "wa_template_id"):
            raw = config.get(key)
            if raw is None:
                continue
            try:
                explicit_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

        seen: set[int] = set()
        for tid in explicit_ids:
            if tid in seen:
                continue
            seen.add(tid)
            row = db.get(TelnyxWhatsappTemplate, tid)
            if row is None or not row.active_for_survey:
                continue
            if template_row_is_sendable_on_meta(row):
                return row

        return SurveySystemTemplateService.resolve_welcome_template_for_survey(db, config)

    @staticmethod
    def resolve_welcome_template_for_survey(db: Session, config: dict[str, Any]) -> TelnyxWhatsappTemplate | None:
        """Pick active welcome template by system kind + privacy mode (named vs anonymous)."""
        anonymous = bool(config.get("anonymous_responses"))
        template_name = WELCOME_TEMPLATE_ANONYMOUS_NAME if anonymous else WELCOME_TEMPLATE_NAMED_NAME
        row = SurveySystemTemplateService.resolve_system_template_for_kind(
            db,
            "welcome",
            config={"anonymous_responses": anonymous},
        )
        if row is None:
            row = db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.name == template_name,
                    TelnyxWhatsappTemplate.active_for_survey.is_(True),
                )
            ).scalar_one_or_none()
        if row is None:
            logger.error("survey_welcome_template_missing name=%s anonymous=%s", template_name, anonymous)
            return None

        from app.services.survey_whatsapp_template_service import resolve_sendable_template_row

        sendable = resolve_sendable_template_row(db, row)
        if sendable is None:
            logger.error(
                "survey_welcome_template_not_sendable name=%s status=%s telnyx_record_id=%s",
                row.name,
                row.status,
                row.telnyx_record_id,
            )
            return None
        return sendable

    @staticmethod
    def resolve_welcome_template_id_for_survey(db: Session, config: dict[str, Any]) -> int | None:
        row = SurveySystemTemplateService.resolve_welcome_template_for_survey(db, config)
        return int(row.id) if row is not None else None

    @staticmethod
    def _config_privacy_mode(config: dict[str, Any] | None) -> str:
        cfg = config or {}
        if cfg.get("privacy_mode") is not None:
            return normalize_privacy_mode(cfg.get("privacy_mode"))
        return PRIVACY_MODE_ON if bool(cfg.get("anonymous_responses")) else PRIVACY_MODE_OFF

    @staticmethod
    def resolve_system_template_for_kind(
        db: Session,
        kind: str,
        config: dict[str, Any] | None = None,
    ) -> TelnyxWhatsappTemplate | None:
        """Resolve active system template for kind, filtered by named vs anonymous survey mode."""
        kind = normalize_system_template_kind(kind)
        privacy = SurveySystemTemplateService._config_privacy_mode(config)
        SurveySystemTemplateService.ensure_system_survey_types(db)
        st = db.execute(
            select(SurveyType).where(SurveyType.system_template_kind == kind).limit(1)
        ).scalar_one_or_none()
        if st is None:
            return None
        rows = list(
            db.execute(
                select(TelnyxWhatsappTemplate)
                .join(SurveyTypeTemplate, SurveyTypeTemplate.template_id == TelnyxWhatsappTemplate.id)
                .where(
                    SurveyTypeTemplate.survey_type_id == st.id,
                    TelnyxWhatsappTemplate.active_for_survey.is_(True),
                )
                .order_by(TelnyxWhatsappTemplate.id.asc())
            ).scalars()
        )
        from app.services.survey_whatsapp_template_service import (
            resolve_sendable_template_row,
            template_row_needs_meta_approval,
        )

        matching = [row for row in rows if resolve_row_privacy_mode(row) == privacy]
        for row in matching:
            if template_row_needs_meta_approval(row):
                sendable = resolve_sendable_template_row(db, row)
                if sendable is not None:
                    return sendable
            else:
                return row
        return matching[0] if matching else None

    @staticmethod
    def resolve_tell_us_more_template_id(
        db: Session,
        config: dict[str, Any] | None = None,
    ) -> int | None:
        row = SurveySystemTemplateService.resolve_system_template_for_kind(db, "tell_us_more", config)
        return int(row.id) if row is not None else None

    @staticmethod
    def resolve_final_feedback_template_id(
        db: Session,
        config: dict[str, Any] | None = None,
    ) -> int | None:
        row = SurveySystemTemplateService.resolve_system_template_for_kind(db, "final_feedback", config)
        return int(row.id) if row is not None else None

    @staticmethod
    def resolve_final_feedback_prompt(
        db: Session,
        config: dict[str, Any] | None = None,
    ) -> str:
        from app.services.survey_wa_final_feedback_service import DEFAULT_OPEN_TEXT_PROMPT

        row = SurveySystemTemplateService.resolve_system_template_for_kind(db, "final_feedback", config)
        if row is None:
            return DEFAULT_OPEN_TEXT_PROMPT
        body = str(row.body_preview or "").strip()
        if not body:
            try:
                components = json.loads(row.components_json or "[]")
                if isinstance(components, list):
                    for comp in components:
                        if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
                            body = str(comp.get("text") or "").strip()
                            break
            except Exception:
                pass
        return body or DEFAULT_OPEN_TEXT_PROMPT

    @staticmethod
    def _system_type_meta(kind: str) -> dict[str, Any]:
        kind = normalize_system_template_kind(kind)
        for item in SYSTEM_SURVEY_TYPES:
            if item["system_template_kind"] == kind:
                return item
        raise SurveySystemTemplateError(f"Unknown system template kind: {kind}")

    @staticmethod
    def survey_type_for_kind(db: Session, kind: str) -> SurveyType:
        """Resolve the canonical hidden-industry survey type for a system template kind."""
        meta = SurveySystemTemplateService._system_type_meta(kind)
        industry = SurveySystemTemplateService.ensure_system_industry(db)
        row = db.execute(
            select(SurveyType).where(
                SurveyType.industry_id == industry.id,
                SurveyType.slug == meta["slug"],
            )
        ).scalar_one_or_none()
        if row is None:
            SurveySystemTemplateService.ensure_system_survey_types(db)
            row = db.execute(
                select(SurveyType).where(
                    SurveyType.industry_id == industry.id,
                    SurveyType.slug == meta["slug"],
                )
            ).scalar_one_or_none()
        if row is None:
            raise SurveySystemTemplateError(f"System survey type for {kind} is not configured.")
        if not row.system_template_kind:
            row.system_template_kind = meta["system_template_kind"]
            row.updated_at = datetime.utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
        return row

    @staticmethod
    def template_belongs_to_kind(db: Session, template_id: int, kind: str | None = None) -> TelnyxWhatsappTemplate:
        tpl = SurveyWhatsappTemplateService.get_template(db, template_id)
        if tpl is None:
            raise SurveySystemTemplateError("Template not found.")
        st = db.get(SurveyType, str(tpl.survey_type_id or ""))
        if st is None or not st.system_template_kind:
            raise SurveySystemTemplateError("Template is not a global system template.")
        if kind is not None and st.system_template_kind != normalize_system_template_kind(kind):
            raise SurveySystemTemplateError("Template kind does not match.")
        return tpl

    @staticmethod
    def list_grouped_admin(db: Session) -> dict[str, Any]:
        """Admin view — templates grouped by system_template_kind."""
        meta = SurveySystemTemplateService.list_admin(db)
        grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in SYSTEM_TEMPLATE_KINDS}
        SurveySystemTemplateService.ensure_system_survey_types(db)
        # Do not auto-create templates here — admin delete must stay deleted.
        type_by_kind = {
            kind: SurveySystemTemplateService.survey_type_for_kind(db, kind)
            for kind in SYSTEM_TEMPLATE_KINDS
        }
        for kind in SYSTEM_TEMPLATE_KINDS:
            grouped[kind] = SurveySystemTemplateService._templates_for_kind(db, type_by_kind[kind], kind)
        return {
            **meta,
            "kinds": [
                {
                    "kind": kind,
                    "label": KIND_LABELS[kind],
                    "survey_type_id": type_by_kind[kind].id,
                    "survey_type_slug": SurveySystemTemplateService._system_type_meta(kind)["slug"],
                    "templates": grouped[kind],
                    "count": len(grouped[kind]),
                }
                for kind in SYSTEM_TEMPLATE_KINDS
            ],
            "templates": grouped,
        }

    @staticmethod
    def set_sync_from_meta(db: Session, template_id: int, *, sync_from_meta: bool) -> dict[str, Any]:
        tpl = SurveySystemTemplateService.template_belongs_to_kind(db, template_id)
        tpl.sync_from_meta = bool(sync_from_meta)
        tpl.updated_at = datetime.utcnow()
        db.add(tpl)
        db.commit()
        db.refresh(tpl)
        st = db.get(SurveyType, str(tpl.survey_type_id or ""))
        kind = normalize_system_template_kind(st.system_template_kind if st else None)
        return SurveySystemTemplateService._admin_template_row(db, tpl, kind=kind, survey_type=st)

    @staticmethod
    def pull_one_from_meta(db: Session, template_id: int) -> dict[str, Any]:
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
        from app.services.wa_template_sync_service import _apply_live_meta_to_row

        tpl = SurveySystemTemplateService.template_belongs_to_kind(db, template_id)
        if not tpl.sync_from_meta:
            raise SurveySystemTemplateError("Enable “Sync from Meta” on this template first.")
        remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        by_record, by_name_lang = TelnyxWhatsappTemplateSyncService._live_index(remote)
        live = TelnyxWhatsappTemplateSyncService._match_live_item(
            tpl, by_record=by_record, by_name_lang=by_name_lang
        )
        if live is None:
            raise SurveySystemTemplateError("No matching Meta template found for this row.")
        before = str(tpl.draft_components_json or "")
        _apply_live_meta_to_row(db, tpl, live)
        updated = str(tpl.draft_components_json or "") != before
        db.commit()
        st = db.get(SurveyType, str(tpl.survey_type_id or ""))
        kind = normalize_system_template_kind(st.system_template_kind if st else None)
        return {
            "ok": True,
            "updated": updated,
            "template": SurveySystemTemplateService._admin_template_row(db, tpl, kind=kind, survey_type=st),
            "message": "Pulled from Meta" if updated else "Already in sync with Meta",
        }

    @staticmethod
    def pull_from_meta(db: Session) -> dict[str, Any]:
        from app.services.telnyx_whatsapp_template_sync_service import TelnyxWhatsappTemplateSyncService
        from app.services.wa_template_sync_service import _apply_live_meta_to_row

        SurveySystemTemplateService.ensure_system_survey_types(db)
        template_ids: list[int] = []
        for kind in SYSTEM_TEMPLATE_KINDS:
            st = SurveySystemTemplateService.survey_type_for_kind(db, kind)
            mappings = list(
                db.execute(
                    select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == st.id)
                ).scalars().all()
            )
            for mapping in mappings:
                template_ids.append(int(mapping.template_id))

        if not template_ids:
            return {"ok": True, "matched": 0, "updated": 0, "message": "No system templates mapped."}

        remote = TelnyxWhatsappTemplateSyncService.fetch_remote_templates(db)
        by_record, by_name_lang = TelnyxWhatsappTemplateSyncService._live_index(remote)
        matched = 0
        updated = 0
        for tid in template_ids:
            row = db.get(TelnyxWhatsappTemplate, tid)
            if row is None or not row.sync_from_meta:
                continue
            live = TelnyxWhatsappTemplateSyncService._match_live_item(
                row, by_record=by_record, by_name_lang=by_name_lang
            )
            if live is None:
                continue
            matched += 1
            before = str(row.draft_components_json or "")
            _apply_live_meta_to_row(db, row, live)
            if str(row.draft_components_json or "") != before:
                updated += 1
        db.commit()
        return {
            "ok": True,
            "matched": matched,
            "updated": updated,
            "message": f"Pulled {matched} system template(s) from Meta ({updated} draft updated)",
        }

    @staticmethod
    def _canonical_welcome_name(privacy_mode: str) -> str:
        if normalize_privacy_mode(privacy_mode) == PRIVACY_MODE_ON:
            return WELCOME_TEMPLATE_ANONYMOUS_NAME
        return WELCOME_TEMPLATE_NAMED_NAME

    @staticmethod
    def _name_is_free(db: Session, name: str, *, exclude_id: int | None = None) -> bool:
        q = select(TelnyxWhatsappTemplate).where(TelnyxWhatsappTemplate.name == name)
        row = db.execute(q).scalar_one_or_none()
        if row is None:
            return True
        return exclude_id is not None and int(row.id) == int(exclude_id)

    @staticmethod
    def create_draft(db: Session, *, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        kind = normalize_system_template_kind(kind)
        body = payload or {}
        survey_type = SurveySystemTemplateService.survey_type_for_kind(db, kind)
        language = str(body.get("language") or "en_GB").strip() or "en_GB"
        category = str(body.get("category") or "UTILITY").strip() or "UTILITY"
        privacy_mode = normalize_privacy_mode(
            body.get("privacy_mode") or body.get("variant_type") or PRIVACY_MODE_OFF
        )
        default_labels = {
            "welcome": "Anonymous survey welcome" if privacy_mode == PRIVACY_MODE_ON else "Welcome",
            "thank_you": "Thank you",
            "tell_us_more": "Tell us more",
            "final_feedback": "Closing question",
        }
        display_name = str(body.get("display_name") or "").strip() or default_labels.get(kind) or kind
        customer_description = str(body.get("customer_description") or "").strip() or None
        row = SurveyWhatsappTemplateService.create_standard_draft(
            db,
            survey_type=survey_type,
            language=language,
            category=category,
        )
        if privacy_mode == PRIVACY_MODE_ON:
            parent_id = int(row.id)
            row = SurveyWhatsappTemplateService.clone_as_anonymous(
                db,
                row,
                survey_type_id=survey_type.id,
            )
            # Detach parent link so we can remove the temporary named draft.
            row.parent_template_id = None
            db.add(row)
            db.flush()
            parent = db.get(TelnyxWhatsappTemplate, parent_id)
            if parent is not None:
                SurveyWhatsappTemplateService.delete_template_local(db, parent)
        components = _default_components_for_kind(kind, privacy_mode=privacy_mode)
        row = SurveyWhatsappTemplateService.save_draft(
            db,
            row,
            {
                "display_name": display_name,
                "customer_description": customer_description,
                "components": components,
                "category": category,
                "privacy_mode": privacy_mode,
            },
        )
        row.step_role = _step_role_for_kind(kind)
        if kind == "thank_you":
            row.outcome_key = "neutral"
        row.industry_id = survey_type.industry_id
        # Prefer canonical Meta names so live survey resolver finds them.
        if kind == "welcome":
            canonical = SurveySystemTemplateService._canonical_welcome_name(privacy_mode)
            if SurveySystemTemplateService._name_is_free(db, canonical, exclude_id=int(row.id)):
                row.name = canonical
        db.add(row)
        SurveySystemTemplateService._ensure_system_mapping(db, survey_type=survey_type, template=row)
        db.commit()
        db.refresh(row)
        return {
            "ok": True,
            "system_template_kind": kind,
            "survey_type_id": survey_type.id,
            "template": SurveySystemTemplateService._admin_template_row(
                db,
                row,
                kind=kind,
                survey_type=survey_type,
            ),
        }

    @staticmethod
    def _item_is_anonymous(item: dict[str, Any]) -> bool:
        return (
            str(item.get("privacy_mode") or "").lower() == "on"
            or str(item.get("variant_type") or "").lower() == "anonymous"
        )

    @staticmethod
    def ensure_required_system_templates(db: Session) -> dict[str, Any]:
        """Create any missing system templates (named + anonymous welcome, thank_you, etc.)."""
        SurveySystemTemplateService.ensure_system_survey_types(db)
        created: list[dict[str, Any]] = []
        existing: list[dict[str, Any]] = []

        welcome_st = SurveySystemTemplateService.survey_type_for_kind(db, "welcome")
        welcome_rows = SurveySystemTemplateService._templates_for_kind(db, welcome_st, "welcome")
        has_named = any(not SurveySystemTemplateService._item_is_anonymous(i) for i in welcome_rows)
        has_anon = any(SurveySystemTemplateService._item_is_anonymous(i) for i in welcome_rows)

        if not has_named:
            created.append(
                SurveySystemTemplateService.create_draft(
                    db,
                    kind="welcome",
                    payload={
                        "privacy_mode": PRIVACY_MODE_OFF,
                        "display_name": "Welcome",
                        "language": "en_GB",
                        "category": "UTILITY",
                    },
                )
            )
        else:
            existing.append({"kind": "welcome", "privacy_mode": PRIVACY_MODE_OFF})

        if not has_anon:
            created.append(
                SurveySystemTemplateService.create_draft(
                    db,
                    kind="welcome",
                    payload={
                        "privacy_mode": PRIVACY_MODE_ON,
                        "display_name": "Anonymous survey welcome",
                        "language": "en_GB",
                        "category": "UTILITY",
                    },
                )
            )
        else:
            existing.append({"kind": "welcome", "privacy_mode": PRIVACY_MODE_ON})

        for kind in ("thank_you", "tell_us_more", "final_feedback"):
            st = SurveySystemTemplateService.survey_type_for_kind(db, kind)
            rows = SurveySystemTemplateService._templates_for_kind(db, st, kind)
            has_named = any(not SurveySystemTemplateService._item_is_anonymous(i) for i in rows)
            has_anon = any(SurveySystemTemplateService._item_is_anonymous(i) for i in rows)
            if has_named:
                existing.append({"kind": kind, "privacy_mode": PRIVACY_MODE_OFF})
            else:
                created.append(
                    SurveySystemTemplateService.create_draft(
                        db,
                        kind=kind,
                        payload={
                            "privacy_mode": PRIVACY_MODE_OFF,
                            "language": "en_GB",
                            "category": "UTILITY",
                        },
                    )
                )
            # Anonymous surveys use anonymous system thank-you / open-text templates.
            if has_anon:
                existing.append({"kind": kind, "privacy_mode": PRIVACY_MODE_ON})
            else:
                created.append(
                    SurveySystemTemplateService.create_draft(
                        db,
                        kind=kind,
                        payload={
                            "privacy_mode": PRIVACY_MODE_ON,
                            "display_name": f"Anonymous {KIND_LABELS[kind].rstrip('s')}",
                            "language": "en_GB",
                            "category": "UTILITY",
                        },
                    )
                )

        # Keep one named + one anonymous welcome (drop accidental duplicates).
        welcome_rows = SurveySystemTemplateService._templates_for_kind(db, welcome_st, "welcome")
        for want_anon in (False, True):
            group = [
                i
                for i in welcome_rows
                if SurveySystemTemplateService._item_is_anonymous(i) is want_anon
            ]
            if len(group) <= 1:
                continue
            # Prefer APPROVED, then oldest id.
            def _score(item: dict[str, Any]) -> tuple:
                status = str(item.get("status") or "").upper()
                return (1 if status == "APPROVED" else 0, -int(item.get("id") or 0))

            group_sorted = sorted(group, key=_score, reverse=True)
            keeper = group_sorted[0]
            for item in group_sorted[1:]:
                try:
                    SurveySystemTemplateService.delete_template(db, int(item["id"]))
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

        # Align canonical welcome names when free.
        welcome_rows = SurveySystemTemplateService._templates_for_kind(db, welcome_st, "welcome")
        for privacy, canonical in (
            (PRIVACY_MODE_OFF, WELCOME_TEMPLATE_NAMED_NAME),
            (PRIVACY_MODE_ON, WELCOME_TEMPLATE_ANONYMOUS_NAME),
        ):
            if not SurveySystemTemplateService._name_is_free(db, canonical):
                continue
            for item in welcome_rows:
                is_anon = SurveySystemTemplateService._item_is_anonymous(item)
                if privacy == PRIVACY_MODE_ON and not is_anon:
                    continue
                if privacy == PRIVACY_MODE_OFF and is_anon:
                    continue
                tpl = db.get(TelnyxWhatsappTemplate, int(item["id"]))
                if tpl is None:
                    continue
                tpl.name = canonical
                db.add(tpl)
                db.commit()
                break

        return {"ok": True, "created": len(created), "existing": existing, "items": created}

    @staticmethod
    def delete_template(db: Session, template_id: int) -> dict[str, Any]:
        tpl = SurveySystemTemplateService.template_belongs_to_kind(db, template_id)
        # Clear child parent links so FK does not block delete.
        children = list(
            db.execute(
                select(TelnyxWhatsappTemplate).where(
                    TelnyxWhatsappTemplate.parent_template_id == int(template_id)
                )
            ).scalars().all()
        )
        for child in children:
            child.parent_template_id = None
            db.add(child)
        if children:
            db.flush()
        try:
            result = SurveyWhatsappTemplateService.delete_template(db, tpl)
        except SurveyWhatsappTemplateError as exc:
            result = SurveyWhatsappTemplateService.delete_template_local(db, tpl)
            result["warning"] = str(exc)
        return {**result, "system_template_kind": None}

    @staticmethod
    def _system_generate_schema(count: int, kind: str) -> dict[str, Any]:
        """Strict OpenAI json_schema — pack item schema locked to the system kind step_role."""
        kind = normalize_system_template_kind(kind)
        step_role = _step_role_for_kind(kind)
        return build_system_template_json_schema(count, step_roles=(step_role,))

    @staticmethod
    def _system_generate_prompt(kind: str, *, instruction: str = "", count: int = 1) -> str:
        kind = normalize_system_template_kind(kind)
        step_role = _step_role_for_kind(kind)
        kind_notes = {
            "welcome": (
                "GLOBAL WELCOME templates open a customer satisfaction survey on WhatsApp. "
                "Use step_role=start. Include {{1}} for first name. Usually one quick_reply "
                "button such as “Start survey”. Warm, inviting, mobile-friendly."
            ),
            "thank_you": (
                "GLOBAL THANK-YOU templates close the survey with gratitude. "
                "Use step_role=completion and outcome_key=neutral. "
                "Prefer button_type=none (no buttons). Short and sincere."
            ),
            "tell_us_more": (
                "GLOBAL TELL-US-MORE templates ask for detail after a low rating. "
                "Use step_role=reason. Prefer button_type=none — user replies with free text. "
                "Empathetic, non-defensive tone."
            ),
            "final_feedback": (
                "GLOBAL CLOSING QUESTION templates invite optional final open-text feedback "
                "after all middle survey steps. "
                "Use step_role=final_feedback_text. Prefer button_type=none — user replies with text or voice. "
                "Default body: “Please share anything else you'd like us to know.” Warm, optional tone."
            ),
        }[kind]
        extra = f"\nAdmin instructions:\n{instruction.strip()}\n" if instruction.strip() else ""
        return (
            "You write Meta/Telnyx-compatible WhatsApp Business templates for VoxBulk GLOBAL system use. "
            "These templates are NOT tied to dental, retail, or any specific industry — keep wording generic "
            "and reusable across sectors. British English. Professional and friendly.\n\n"
            f"{_meta_compliance_rules_block(privacy_mode=PRIVACY_MODE_OFF)}"
            f"TEMPLATE KIND: {kind}\n{kind_notes}\n\n"
            f"Return exactly {count} distinct template variant(s). "
            f"Each must use step_role={step_role}."
            + (" Each must include outcome_key=neutral." if kind == "thank_you" else "")
            + f"{extra}\n"
            "Make variants feel different (warm vs premium vs concise) without being repetitive."
        )

    @staticmethod
    def _system_generate_user_prompt(kind: str, *, count: int = 1) -> str:
        return (
            f"Generate {count} global {kind.replace('_', ' ')} WhatsApp template(s) "
            "for shared use across all industries."
        )

    @staticmethod
    def generate_with_openai(
        db: Session,
        *,
        kind: str,
        instruction: str = "",
        count: int = 1,
    ) -> dict[str, Any]:
        kind = normalize_system_template_kind(kind)
        survey_type = SurveySystemTemplateService.survey_type_for_kind(db, kind)
        pack_count = max(1, min(int(count or 1), 6))
        try:
            raw, meta = OpenAIProviderService.responses_json(
                db,
                system_prompt=SurveySystemTemplateService._system_generate_prompt(
                    kind,
                    instruction=instruction,
                    count=pack_count,
                ),
                user_prompt=SurveySystemTemplateService._system_generate_user_prompt(
                    kind,
                    count=pack_count,
                ),
                json_schema=SurveySystemTemplateService._system_generate_schema(pack_count, kind),
                schema_name=f"wa_system_{kind}_templates",
                max_output_tokens=8000,
                temperature=0.65,
            )
        except ValueError as exc:
            raise SurveySystemTemplateError(str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise SurveySystemTemplateError("OpenAI timed out — please try again.") from exc

        items = raw.get("templates")
        if not isinstance(items, list):
            raise SurveySystemTemplateError("OpenAI response missing templates array")

        validated: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item = normalize_system_generated_item(item, kind=kind, idx=idx)
            item = {
                **item,
                "step_role": _step_role_for_kind(kind),
                "variant_type": "standard",
                "privacy_mode": PRIVACY_MODE_OFF,
            }
            if kind == "thank_you":
                item["outcome_key"] = "neutral"
                item["button_type"] = item.get("button_type") or "none"
                item["buttons"] = item.get("buttons") or []
            row = _build_pack_item_row(
                db,
                survey_type=survey_type,
                idx=idx,
                item=item,
                seen_names=seen_names,
                privacy_mode=PRIVACY_MODE_OFF,
                instruction=instruction,
                purpose=kind,
                company_name=None,
            )
            if row.get("valid") and row.get("template"):
                validated.append({**row, "system_template_kind": kind})
            else:
                invalid.append({**row, "system_template_kind": kind})

        return {
            "ok": True,
            "system_template_kind": kind,
            "survey_type_id": survey_type.id,
            "template_count": pack_count,
            "generated_count": len(items),
            "valid_count": len(validated),
            "invalid_count": len(invalid),
            "templates": validated + invalid,
            "valid_templates": [r["template"] for r in validated if r.get("template")],
            "openai": meta,
        }

    @staticmethod
    def save_generated(
        db: Session,
        *,
        kind: str,
        templates: list[dict[str, Any]],
        instruction: str = "",
    ) -> dict[str, Any]:
        kind = normalize_system_template_kind(kind)
        survey_type = SurveySystemTemplateService.survey_type_for_kind(db, kind)
        selected = [t for t in templates if isinstance(t, dict)]
        if not selected:
            raise SurveySystemTemplateError("Select at least one template to save.")
        prepared: list[dict[str, Any]] = []
        for item in selected:
            tpl = item.get("template") if isinstance(item.get("template"), dict) else item
            if not isinstance(tpl, dict):
                continue
            prepared_item = {
                **tpl,
                "step_role": _step_role_for_kind(kind),
                "variant_type": "standard",
                "privacy_mode": PRIVACY_MODE_OFF,
            }
            if kind == "thank_you":
                prepared_item["outcome_key"] = str(prepared_item.get("outcome_key") or "neutral").strip().lower() or "neutral"
            else:
                prepared_item.pop("outcome_key", None)
            prepared.append(prepared_item)
        if not prepared:
            raise SurveySystemTemplateError("No valid templates to save.")
        try:
            result = SurveyWaTemplatePackService.save_selected_templates(
                db,
                survey_type=survey_type,
                templates=prepared,
                privacy_mode=PRIVACY_MODE_OFF,
                purpose=kind,
                instruction=instruction,
                replace_step_bank=False,
            )
        except SurveyWaTemplatePackError as exc:
            raise SurveySystemTemplateError(str(exc)) from exc
        saved_rows: list[dict[str, Any]] = []
        for item in result.get("templates") or []:
            tpl_id = item.get("id")
            if tpl_id is None:
                continue
            tpl = SurveyWhatsappTemplateService.get_template(db, int(tpl_id))
            if tpl is None:
                continue
            SurveySystemTemplateService._ensure_system_mapping(db, survey_type=survey_type, template=tpl)
            saved_rows.append(
                SurveySystemTemplateService._admin_template_row(
                    db,
                    tpl,
                    kind=kind,
                    survey_type=survey_type,
                )
            )
        db.commit()
        grouped = SurveySystemTemplateService.list_grouped_admin(db)
        return {
            **result,
            "system_template_kind": kind,
            "saved_templates": saved_rows,
            "kinds": grouped.get("kinds") or [],
        }

    @staticmethod
    def list_admin(db: Session) -> dict[str, Any]:
        industry = SurveySystemTemplateService.ensure_system_industry(db)
        types = SurveySystemTemplateService.ensure_system_survey_types(db)
        return {
            "ok": True,
            "industry": IndustryService.get_industry(db, industry.id),
            "survey_types": [survey_type_to_dict(t) for t in types],
        }
