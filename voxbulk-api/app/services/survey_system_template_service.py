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
from app.services.wa_template_privacy import PRIVACY_MODE_OFF, PRIVACY_MODE_ON, normalize_privacy_mode, resolve_row_privacy_mode

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
        return "Noname"
    return "Named"


def _body_text_from_template(row: TelnyxWhatsappTemplate) -> str:
    preview = str(row.body_preview or "").strip()
    if preview:
        return preview
    return str(row.display_name or row.name or "").strip()


def _default_components_for_kind(kind: str) -> list[dict[str, Any]]:
    if kind == "welcome":
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
        return [
            {
                "type": "BODY",
                "text": "Thank you {{1}} for sharing your feedback. We really appreciate your time.",
                "example": {"body_text": [["Alex"]]},
            },
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
        ]
    if kind == "final_feedback":
        return [
            {
                "type": "BODY",
                "text": "Please share anything else you'd like us to know.",
                "example": {"body_text": [["there"]]},
            },
            {"type": "FOOTER", "text": "Reply STOP to opt out"},
        ]
    return [
        {
            "type": "BODY",
            "text": (
                "We're sorry to hear that. Could you tell us a bit more about what went wrong? "
                "Your reply helps us improve."
            ),
            "example": {"body_text": [["there"]]},
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
    def list_templates_for_builder(db: Session) -> dict[str, Any]:
        """Templates grouped by kind for dashboard survey builder."""
        SurveySystemTemplateService.ensure_system_survey_types(db)
        grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in SYSTEM_TEMPLATE_KINDS}
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
                if tpl is None or not tpl.active_for_survey:
                    continue
                status = str(tpl.status or "").upper()
                grouped[kind].append(
                    {
                        **survey_template_to_dict(tpl),
                        "survey_type_id": st.id,
                        "survey_type_name": st.name,
                        "survey_type_slug": st.slug,
                        "is_approved": status == "APPROVED",
                    }
                )
        return {"ok": True, "templates": grouped}

    @staticmethod
    def resolve_tell_us_more_template_id(db: Session) -> int | None:
        SurveySystemTemplateService.ensure_system_survey_types(db)
        st = db.execute(
            select(SurveyType).where(SurveyType.system_template_kind == "tell_us_more").limit(1)
        ).scalar_one_or_none()
        if st is None:
            return None
        row = db.execute(
            select(TelnyxWhatsappTemplate)
            .join(SurveyTypeTemplate, SurveyTypeTemplate.template_id == TelnyxWhatsappTemplate.id)
            .where(
                SurveyTypeTemplate.survey_type_id == st.id,
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .order_by(TelnyxWhatsappTemplate.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        return int(row.id) if row is not None else None

    @staticmethod
    def resolve_final_feedback_template_id(db: Session) -> int | None:
        SurveySystemTemplateService.ensure_system_survey_types(db)
        st = db.execute(
            select(SurveyType).where(SurveyType.system_template_kind == "final_feedback").limit(1)
        ).scalar_one_or_none()
        if st is None:
            return None
        row = db.execute(
            select(TelnyxWhatsappTemplate)
            .join(SurveyTypeTemplate, SurveyTypeTemplate.template_id == TelnyxWhatsappTemplate.id)
            .where(
                SurveyTypeTemplate.survey_type_id == st.id,
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .order_by(TelnyxWhatsappTemplate.id.asc())
            .limit(1)
        ).scalar_one_or_none()
        return int(row.id) if row is not None else None

    @staticmethod
    def resolve_final_feedback_prompt(db: Session) -> str:
        from app.services.survey_wa_final_feedback_service import DEFAULT_OPEN_TEXT_PROMPT

        SurveySystemTemplateService.ensure_system_survey_types(db)
        st = db.execute(
            select(SurveyType).where(SurveyType.system_template_kind == "final_feedback").limit(1)
        ).scalar_one_or_none()
        if st is None:
            return DEFAULT_OPEN_TEXT_PROMPT
        row = db.execute(
            select(TelnyxWhatsappTemplate)
            .join(SurveyTypeTemplate, SurveyTypeTemplate.template_id == TelnyxWhatsappTemplate.id)
            .where(
                SurveyTypeTemplate.survey_type_id == st.id,
                TelnyxWhatsappTemplate.active_for_survey.is_(True),
            )
            .order_by(TelnyxWhatsappTemplate.id.asc())
            .limit(1)
        ).scalar_one_or_none()
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
    def create_draft(db: Session, *, kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        kind = normalize_system_template_kind(kind)
        body = payload or {}
        survey_type = SurveySystemTemplateService.survey_type_for_kind(db, kind)
        language = str(body.get("language") or "en_US").strip() or "en_US"
        category = str(body.get("category") or "UTILITY").strip() or "UTILITY"
        display_name = str(body.get("display_name") or "").strip() or KIND_LABELS[kind].rstrip("s")
        privacy_mode = normalize_privacy_mode(
            body.get("privacy_mode") or body.get("variant_type") or PRIVACY_MODE_OFF
        )
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
            parent = db.get(TelnyxWhatsappTemplate, parent_id)
            if parent is not None:
                SurveyWhatsappTemplateService.delete_template_local(db, parent)
        components = _default_components_for_kind(kind)
        row = SurveyWhatsappTemplateService.save_draft(
            db,
            row,
            {
                "display_name": display_name,
                "components": components,
                "category": category,
            },
        )
        row.step_role = _step_role_for_kind(kind)
        if kind == "thank_you":
            row.outcome_key = "neutral"
        row.industry_id = survey_type.industry_id
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
    def delete_template(db: Session, template_id: int) -> dict[str, Any]:
        tpl = SurveySystemTemplateService.template_belongs_to_kind(db, template_id)
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
                "after the respondent chooses Yes on the closing yes/no step. "
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
