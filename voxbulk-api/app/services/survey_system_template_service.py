"""System survey templates — welcome, thank-you, tell-us-more under hidden industry."""

from __future__ import annotations

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
    assert_openai_strict_json_schema,
    build_system_template_json_schema,
)
from app.services.wa_template_privacy import PRIVACY_MODE_OFF, normalize_privacy_mode

SYSTEM_TEMPLATE_KINDS = ("welcome", "thank_you", "tell_us_more")

KIND_LABELS: dict[str, str] = {
    "welcome": "Welcome templates",
    "thank_you": "Thank-you templates",
    "tell_us_more": "Tell us more templates",
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
    return "reason"


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


class SurveySystemTemplateService:
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
    def survey_type_for_kind(db: Session, kind: str) -> SurveyType:
        normalize_system_template_kind(kind)
        SurveySystemTemplateService.ensure_system_survey_types(db)
        row = db.execute(
            select(SurveyType).where(SurveyType.system_template_kind == kind).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise SurveySystemTemplateError(f"System survey type for {kind} is not configured.")
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
        types = list(
            db.execute(
                select(SurveyType).where(SurveyType.system_template_kind.in_(SYSTEM_TEMPLATE_KINDS))
            ).scalars()
        )
        type_by_kind = {str(t.system_template_kind): t for t in types if t.system_template_kind}
        for kind in SYSTEM_TEMPLATE_KINDS:
            st = type_by_kind.get(kind)
            if st is None:
                continue
            mappings = list(
                db.execute(
                    select(SurveyTypeTemplate).where(SurveyTypeTemplate.survey_type_id == st.id)
                ).scalars()
            )
            rows: list[dict[str, Any]] = []
            for mapping in mappings:
                tpl = db.get(TelnyxWhatsappTemplate, mapping.template_id)
                if tpl is None:
                    continue
                rows.append(
                    {
                        **survey_template_to_dict(tpl),
                        "system_template_kind": kind,
                        "survey_type_id": st.id,
                        "step_role": tpl.step_role or _step_role_for_kind(kind),
                    }
                )
            rows.sort(key=lambda item: str(item.get("display_name") or item.get("name") or ""))
            grouped[kind] = rows
        return {
            **meta,
            "kinds": [
                {
                    "kind": kind,
                    "label": KIND_LABELS[kind],
                    "survey_type_id": type_by_kind[kind].id if kind in type_by_kind else None,
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
        category = str(body.get("category") or "MARKETING").strip() or "MARKETING"
        display_name = str(body.get("display_name") or "").strip() or KIND_LABELS[kind].rstrip("s")
        row = SurveyWhatsappTemplateService.create_standard_draft(
            db,
            survey_type=survey_type,
            language=language,
            category=category,
        )
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
        db.commit()
        db.refresh(row)
        return {
            "ok": True,
            "system_template_kind": kind,
            "survey_type_id": survey_type.id,
            "template": survey_template_to_dict(row),
        }

    @staticmethod
    def delete_template(db: Session, template_id: int) -> dict[str, Any]:
        tpl = SurveySystemTemplateService.template_belongs_to_kind(db, template_id)
        try:
            result = SurveyWhatsappTemplateService.delete_template(db, tpl)
        except SurveyWhatsappTemplateError as exc:
            raise SurveySystemTemplateError(str(exc)) from exc
        return {**result, "system_template_kind": None}

    @staticmethod
    def _system_generate_schema(count: int) -> dict[str, Any]:
        """Strict OpenAI json_schema — deep-copied pack item schema with preflight validation."""
        schema = build_system_template_json_schema(count)
        assert_openai_strict_json_schema(schema)
        return schema

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
                json_schema=SurveySystemTemplateService._system_generate_schema(pack_count),
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
            prepared.append(
                {
                    **tpl,
                    "step_role": _step_role_for_kind(kind),
                    "variant_type": "standard",
                    "privacy_mode": PRIVACY_MODE_OFF,
                    **({"outcome_key": "neutral"} if kind == "thank_you" else {}),
                }
            )
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
        return {**result, "system_template_kind": kind}

    @staticmethod
    def list_admin(db: Session) -> dict[str, Any]:
        industry = SurveySystemTemplateService.ensure_system_industry(db)
        types = SurveySystemTemplateService.ensure_system_survey_types(db)
        return {
            "ok": True,
            "industry": IndustryService.get_industry(db, industry.id),
            "survey_types": [survey_type_to_dict(t) for t in types],
        }
