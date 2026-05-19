from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.organisation import Organisation
from app.models.organisation_ai_config import (
    OrganisationAIIdentity,
    OrganisationComplianceConfig,
    OrganisationServiceCatalogItem,
    OrganisationWorkflowConfig,
)
from app.models.provider_config import ProviderConfig
from app.models.service_api import SupportedServiceAPI


ONBOARDING_VERSION = "2026-05-dashboard-v1"
ONBOARDING_STATES = {
    "account_created",
    "category_selected",
    "software_selected",
    "wizard_in_progress",
    "onboarding_completed",
}


CATEGORY_TEMPLATES: dict[str, dict[str, Any]] = {
    "dental": {
        "display_name": "Dental clinic",
        "default_terminology": "patient",
        "default_services": ["check-up", "hygiene", "whitening", "emergency", "consultation", "treatment follow-up"],
        "tone_options": ["professional", "warm", "friendly"],
        "workflows": {
            "appointment_reminder": {"channels": ["whatsapp"], "timing_rules": {"before_appointment": {"days": 2}}},
            "cancellation_recovery": {"channels": ["ai_call", "whatsapp"], "timing_rules": {"after_cancellation_minutes": 15}},
            "no_show_follow_up": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"after_no_show_hours": 2}},
            "empty_slot_fill": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"empty_slot_window_hours": 48}},
            "recall_old_customers": {"channels": ["whatsapp"], "timing_rules": {"inactivity_months": 18}},
            "annual_review_recall": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"annual_recall_months": 12}},
            "overdue_treatment_recall": {"channels": ["ai_call", "whatsapp"], "timing_rules": {"overdue_days": 30}},
            "escalation_to_human": {"channels": ["ai_call", "whatsapp"], "timing_rules": {}},
        },
    },
    "aesthetics": {
        "display_name": "Aesthetics clinic",
        "default_terminology": "client",
        "default_services": ["consultation", "Botox", "fillers", "facial", "laser", "anti-aging review", "skin treatment"],
        "tone_options": ["warm", "premium", "professional", "friendly"],
        "workflows": {
            "appointment_reminder": {"channels": ["whatsapp"], "timing_rules": {"before_appointment": {"days": 2}}},
            "cancellation_recovery": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"after_cancellation_minutes": 20}},
            "no_show_follow_up": {"channels": ["whatsapp"], "timing_rules": {"after_no_show_hours": 3}},
            "empty_slot_fill": {"channels": ["whatsapp"], "timing_rules": {"empty_slot_window_hours": 72}},
            "recall_old_customers": {"channels": ["whatsapp"], "timing_rules": {"inactivity_months": 6}},
            "annual_review_recall": {"channels": ["whatsapp"], "timing_rules": {"annual_recall_months": 12}},
            "overdue_treatment_recall": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"overdue_days": 45}},
            "escalation_to_human": {"channels": ["ai_call", "whatsapp"], "timing_rules": {}},
        },
    },
    "opticians": {
        "display_name": "Opticians / optometry",
        "default_terminology": "patient",
        "default_services": ["eye test", "contact lens check", "contact lens renewal", "annual recall", "follow-up"],
        "tone_options": ["professional", "warm", "friendly"],
        "workflows": {
            "appointment_reminder": {"channels": ["whatsapp"], "timing_rules": {"before_appointment": {"days": 2}}},
            "cancellation_recovery": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"after_cancellation_minutes": 20}},
            "no_show_follow_up": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"after_no_show_hours": 2}},
            "empty_slot_fill": {"channels": ["whatsapp"], "timing_rules": {"empty_slot_window_hours": 48}},
            "recall_old_customers": {"channels": ["whatsapp"], "timing_rules": {"inactivity_months": 18}},
            "annual_review_recall": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"annual_recall_months": 12}},
            "overdue_treatment_recall": {"channels": ["whatsapp"], "timing_rules": {"overdue_days": 30}},
            "escalation_to_human": {"channels": ["ai_call", "whatsapp"], "timing_rules": {}},
        },
    },
}

GENERIC_CATEGORY_TEMPLATE: dict[str, Any] = {
    "display_name": "Appointment-based business",
    "default_terminology": "customer",
    "default_services": ["consultation", "appointment", "follow-up", "review"],
    "tone_options": ["professional", "warm", "friendly"],
    "workflows": {
        "appointment_reminder": {"channels": ["whatsapp"], "timing_rules": {"before_appointment": {"days": 2}}},
        "cancellation_recovery": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"after_cancellation_minutes": 20}},
        "no_show_follow_up": {"channels": ["whatsapp", "ai_call"], "timing_rules": {"after_no_show_hours": 2}},
        "empty_slot_fill": {"channels": ["whatsapp"], "timing_rules": {"empty_slot_window_hours": 48}},
        "recall_old_customers": {"channels": ["whatsapp"], "timing_rules": {"inactivity_months": 12}},
        "escalation_to_human": {"channels": ["ai_call", "whatsapp"], "timing_rules": {}},
    },
}


DEFAULT_CATEGORIES = [
    ("dental", "Dental clinic", "Dental clinics, hygiene, treatment follow-up and recall workflows."),
    ("aesthetics", "Aesthetics clinic", "Aesthetic, beauty, medspa and anti-aging clinics."),
    ("opticians", "Opticians / optometry", "Opticians, optometry and contact lens recall workflows."),
]


DEFAULT_SERVICE_APIS = [
    {
        "slug": "dentally",
        "display_name": "Dentally",
        "category_slug": "dental",
        "short_description": "Dental practice management integration for appointments and patient context.",
        "status": "active",
        "is_active": True,
        "is_recommended": True,
        "api_difficulty": "easy API",
        "docs_text": "Connect Dentally as the dental booking source of truth.",
        "sort_order": 10,
    },
    {
        "slug": "carestack",
        "display_name": "CareStack",
        "category_slug": "dental",
        "short_description": "Dental practice management integration for larger dental groups.",
        "status": "coming soon",
        "is_active": False,
        "is_recommended": False,
        "api_difficulty": "beta",
        "docs_text": "CareStack support is planned for dental groups.",
        "sort_order": 20,
    },
    {
        "slug": "pabau",
        "display_name": "Pabau",
        "category_slug": "aesthetics",
        "short_description": "Aesthetics and medspa practice software integration.",
        "status": "coming soon",
        "is_active": False,
        "is_recommended": True,
        "api_difficulty": "beta",
        "docs_text": "Pabau support will power aesthetics appointment recovery.",
        "sort_order": 10,
    },
    {
        "slug": "cliniko",
        "display_name": "Cliniko",
        "category_slug": "aesthetics",
        "short_description": "Clinic booking software integration for appointments and client context.",
        "status": "coming soon",
        "is_active": False,
        "is_recommended": False,
        "api_difficulty": "beta",
        "docs_text": "Cliniko support is planned for clinic appointment recovery.",
        "sort_order": 20,
    },
    {
        "slug": "optix",
        "display_name": "Optix",
        "category_slug": "opticians",
        "short_description": "Optician practice management integration for appointments and recalls.",
        "status": "coming soon",
        "is_active": False,
        "is_recommended": True,
        "api_difficulty": "beta",
        "docs_text": "Optix support will power optometry recall workflows.",
        "sort_order": 10,
    },
    {
        "slug": "ocuco",
        "display_name": "Ocuco",
        "category_slug": "opticians",
        "short_description": "Optometry and optical retail software integration.",
        "status": "coming soon",
        "is_active": False,
        "is_recommended": False,
        "api_difficulty": "beta",
        "docs_text": "Ocuco support is planned for opticians and optometry groups.",
        "sort_order": 20,
    },
]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _clean_slug(raw: str) -> str:
    return str(raw or "").strip().lower().replace("_", "-").replace(" ", "-")


def _category_template_for(category_slug: str, category_name: str | None = None) -> dict[str, Any]:
    slug = _clean_slug(category_slug)
    if slug in CATEGORY_TEMPLATES:
        return CATEGORY_TEMPLATES[slug]
    template = dict(GENERIC_CATEGORY_TEMPLATE)
    template["display_name"] = category_name or slug.replace("-", " ").title() or GENERIC_CATEGORY_TEMPLATE["display_name"]
    template["default_services"] = list(GENERIC_CATEGORY_TEMPLATE["default_services"])
    template["tone_options"] = list(GENERIC_CATEGORY_TEMPLATE["tone_options"])
    template["workflows"] = {
        key: {
            "channels": list(value.get("channels") or []),
            "timing_rules": dict(value.get("timing_rules") or {}),
        }
        for key, value in GENERIC_CATEGORY_TEMPLATE["workflows"].items()
    }
    return template


class SupportedServiceAPIService:
    @staticmethod
    def category_exists(db: Session, category_slug: str) -> bool:
        SupportedServiceAPIService.ensure_defaults(db)
        slug = _clean_slug(category_slug)
        if not slug:
            return False
        return db.execute(select(Category.id).where(Category.slug == slug)).scalar_one_or_none() is not None

    @staticmethod
    def ensure_defaults(db: Session) -> None:
        now = datetime.utcnow()
        changed = False
        for slug, name, description in DEFAULT_CATEGORIES:
            category = db.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()
            if category is None:
                db.add(Category(id=str(uuid.uuid4()), slug=slug, name=name, description=description, created_at=now))
                changed = True
        db.flush()
        for item in DEFAULT_SERVICE_APIS:
            row = db.execute(select(SupportedServiceAPI).where(SupportedServiceAPI.slug == item["slug"])).scalar_one_or_none()
            if row is None:
                db.add(SupportedServiceAPI(id=str(uuid.uuid4()), created_at=now, updated_at=now, **item))
                changed = True
        if changed:
            db.commit()

    @staticmethod
    def list(
        db: Session,
        *,
        category_slug: str | None = None,
        status: str | None = None,
        active_only: bool = False,
    ) -> list[SupportedServiceAPI]:
        SupportedServiceAPIService.ensure_defaults(db)
        stmt = select(SupportedServiceAPI)
        if category_slug:
            stmt = stmt.where(SupportedServiceAPI.category_slug == _clean_slug(category_slug))
        if status:
            stmt = stmt.where(SupportedServiceAPI.status == str(status).strip().lower())
        if active_only:
            stmt = stmt.where(SupportedServiceAPI.is_active.is_(True))
        stmt = stmt.order_by(SupportedServiceAPI.category_slug.asc(), SupportedServiceAPI.sort_order.asc(), SupportedServiceAPI.display_name.asc())
        return list(db.execute(stmt).scalars())

    @staticmethod
    def api_setup_exists(db: Session, service_slug: str) -> bool:
        provider_slug = _clean_slug(service_slug).replace("-", "_")
        return (
            db.execute(
                select(ProviderConfig.id).where(
                    ProviderConfig.provider == provider_slug,
                    ProviderConfig.is_enabled.is_(True),
                )
            ).scalar_one_or_none()
            is not None
        )

    @staticmethod
    def create(db: Session, payload: dict[str, Any]) -> SupportedServiceAPI:
        SupportedServiceAPIService.ensure_defaults(db)
        slug = _clean_slug(payload.get("slug", ""))
        if not slug:
            raise ValueError("slug required")
        if db.execute(select(SupportedServiceAPI.id).where(SupportedServiceAPI.slug == slug)).scalar_one_or_none():
            raise ValueError("Service API slug already exists")
        category_slug = _clean_slug(payload.get("category_slug", ""))
        if not SupportedServiceAPIService.category_exists(db, category_slug):
            raise ValueError("category_slug must match an existing admin category")
        now = datetime.utcnow()
        row = SupportedServiceAPI(
            id=str(uuid.uuid4()),
            slug=slug,
            display_name=str(payload.get("display_name") or "").strip(),
            category_slug=category_slug,
            short_description=str(payload.get("short_description") or "").strip() or None,
            status=str(payload.get("status") or "active").strip().lower(),
            is_active=bool(payload.get("is_active", True)),
            is_recommended=bool(payload.get("is_recommended", False)),
            api_difficulty=str(payload.get("api_difficulty") or "").strip() or None,
            docs_text=str(payload.get("docs_text") or "").strip() or None,
            sort_order=int(payload.get("sort_order") or 100),
            created_at=now,
            updated_at=now,
        )
        if not row.display_name:
            raise ValueError("display_name required")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def update(db: Session, slug: str, payload: dict[str, Any]) -> SupportedServiceAPI:
        row = db.execute(select(SupportedServiceAPI).where(SupportedServiceAPI.slug == _clean_slug(slug))).scalar_one_or_none()
        if row is None:
            raise ValueError("Service API not found")
        if "category_slug" in payload and payload["category_slug"] is not None:
            category_slug = _clean_slug(payload["category_slug"])
            if not SupportedServiceAPIService.category_exists(db, category_slug):
                raise ValueError("category_slug must match an existing admin category")
            row.category_slug = category_slug
        for key in ["display_name", "short_description", "status", "api_difficulty", "docs_text"]:
            if key in payload and payload[key] is not None:
                raw = str(payload[key]).strip()
                setattr(row, key, raw or None)
        for key in ["is_active", "is_recommended"]:
            if key in payload and payload[key] is not None:
                setattr(row, key, bool(payload[key]))
        if "sort_order" in payload and payload["sort_order"] is not None:
            row.sort_order = int(payload["sort_order"])
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def set_enabled(db: Session, slug: str, enabled: bool) -> SupportedServiceAPI:
        status = "active" if enabled else "inactive"
        return SupportedServiceAPIService.update(db, slug, {"is_active": enabled, "status": status})


class WorkflowPromptProfileService:
    @staticmethod
    def build_profile(
        *,
        org: Organisation,
        category_slug: str,
        software: SupportedServiceAPI,
        identity: OrganisationAIIdentity,
        compliance: OrganisationComplianceConfig,
        services: list[str],
        workflow: OrganisationWorkflowConfig,
    ) -> dict[str, Any]:
        template = _category_template_for(category_slug)
        return {
            "role": f"AI assistant for {template['display_name']}",
            "organisation_identity": {
                "assistant_name": identity.assistant_name,
                "organisation_name": identity.organisation_name or org.name,
                "tone": identity.tone,
                "humor_level": identity.humor_level,
                "languages": _json_loads(identity.languages_json, ["en-GB"]),
            },
            "category_context": category_slug,
            "terminology_rules": {"customer_label": identity.terminology_label},
            "services_offered": services,
            "workflow_objective": workflow.workflow_key.replace("_", " "),
            "allowed_channels": _json_loads(workflow.channels_json, []),
            "allowed_actions": _json_loads(workflow.allowed_actions_json, []),
            "forbidden_actions": _json_loads(workflow.forbidden_actions_json, []),
            "booking_software_context": {
                "slug": software.slug,
                "display_name": software.display_name,
                "source_of_truth": True,
            },
            "compliance_rules": {
                "disclose_ai": identity.disclose_ai,
                "ai_disclosure_wording": compliance.ai_disclosure_wording,
                "opt_out_wording": compliance.opt_out_wording,
                "outbound_call_windows": _json_loads(compliance.outbound_call_windows_json, {}),
                "whatsapp_windows": _json_loads(compliance.whatsapp_windows_json, {}),
                "weekend_allowed": compliance.weekend_allowed,
                "contact_preference_rules": _json_loads(compliance.contact_preference_rules_json, {}),
            },
            "escalation_behavior": {
                "destination": compliance.escalation_destination,
                "rules": _json_loads(workflow.escalation_rules_json, []),
                "always_escalate_for": ["complaints", "payment disputes", "clinical advice", "medical questions", "uncertainty", "human requested"],
            },
            "fallback_behavior": "If unsure, apologise briefly and escalate to the human team. Do not invent availability or clinical advice.",
        }

    @staticmethod
    def render_prompt(profile: dict[str, Any]) -> str:
        identity = profile["organisation_identity"]
        software = profile["booking_software_context"]
        compliance = profile["compliance_rules"]
        return "\n".join(
            [
                f"Role: {profile['role']}.",
                f"You are {identity['assistant_name']} for {identity['organisation_name']}. Use a {identity['tone']} tone in British English.",
                f"Category: {profile['category_context']}. Refer to people as {profile['terminology_rules']['customer_label']}s.",
                f"Services offered: {', '.join(profile['services_offered'])}.",
                f"Workflow objective: {profile['workflow_objective']}.",
                f"Allowed channels: {', '.join(profile['allowed_channels']) or 'none configured'}.",
                f"Allowed actions: {', '.join(profile['allowed_actions']) or 'none configured'}.",
                f"Forbidden actions: {', '.join(profile['forbidden_actions']) or 'none configured'}.",
                f"Booking software: {software['display_name']} remains the source of truth.",
                f"AI disclosure: {'required' if compliance['disclose_ai'] else 'not required by config'}."
                f" Use wording: {compliance.get('ai_disclosure_wording') or 'This is the VOXBULK AI assistant calling on behalf of the clinic.'}",
                f"Opt-out wording: {compliance.get('opt_out_wording') or 'Reply STOP or ask us not to contact you again.'}",
                "Escalate for complaints, payment questions, clinical or medical questions, uncertainty, or whenever the customer asks for a human.",
                profile["fallback_behavior"],
            ]
        )

    @staticmethod
    def render_summary(profile: dict[str, Any]) -> str:
        return (
            f"{profile['workflow_objective'].title()} via {', '.join(profile['allowed_channels']) or 'no channels'} "
            f"for {profile['organisation_identity']['organisation_name']} using {profile['booking_software_context']['display_name']} context."
        )


class OrganisationOnboardingService:
    @staticmethod
    def category_template(category_slug: str) -> dict[str, Any]:
        slug = _clean_slug(category_slug)
        if not slug:
            raise ValueError("Unsupported category")
        return {"category_slug": slug, **_category_template_for(slug)}

    @staticmethod
    def status(db: Session, org_id: str) -> dict[str, Any]:
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one()
        category_slug = None
        if org.category_id:
            category_slug = db.execute(select(Category.slug).where(Category.id == org.category_id)).scalar_one_or_none()
        state = org.onboarding_state or "account_created"
        next_step = {
            "account_created": "select_category",
            "category_selected": "select_software",
            "software_selected": "wizard",
            "wizard_in_progress": "wizard",
            "onboarding_completed": "dashboard",
        }.get(state, "select_category")
        return {
            "org_id": org.id,
            "onboarding_state": state,
            "onboarding_complete": state == "onboarding_completed",
            "category_slug": category_slug,
            "category_id": org.category_id,
            "booking_software_slug": org.booking_software_slug,
            "next_step": next_step,
            "completed_at": org.onboarding_completed_at,
        }

    @staticmethod
    def select_category(db: Session, org_id: str, category_slug: str, *, confirm_change: bool = False) -> dict[str, Any]:
        SupportedServiceAPIService.ensure_defaults(db)
        slug = _clean_slug(category_slug)
        category = db.execute(select(Category).where(Category.slug == slug)).scalar_one_or_none()
        if category is None:
            raise ValueError("Unsupported category")
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one()
        existing_slug = None
        if org.category_id:
            existing_slug = db.execute(select(Category.slug).where(Category.id == org.category_id)).scalar_one_or_none()
        if existing_slug and existing_slug != slug and not confirm_change:
            raise ValueError("Changing category may reset onboarding workflows. confirm_change required")
        org.category_id = category.id
        if existing_slug != slug:
            org.booking_software_slug = None
            org.onboarding_completed_at = None
        org.onboarding_state = "category_selected"
        org.onboarding_version = ONBOARDING_VERSION
        db.add(org)
        db.commit()
        return OrganisationOnboardingService.status(db, org_id)

    @staticmethod
    def select_software(db: Session, org_id: str, software_slug: str, *, confirm_change: bool = False) -> dict[str, Any]:
        SupportedServiceAPIService.ensure_defaults(db)
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one()
        if not org.category_id:
            raise ValueError("Select category first")
        category_slug = db.execute(select(Category.slug).where(Category.id == org.category_id)).scalar_one()
        service = db.execute(select(SupportedServiceAPI).where(SupportedServiceAPI.slug == _clean_slug(software_slug))).scalar_one_or_none()
        if service is None or service.category_slug != category_slug:
            raise ValueError("Software is not available for selected category")
        if org.booking_software_slug and org.booking_software_slug != service.slug and not confirm_change:
            raise ValueError("Changing software may reset integration context. confirm_change required")
        org.booking_software_slug = service.slug
        org.onboarding_state = "software_selected"
        org.onboarding_completed_at = None
        db.add(org)
        db.commit()
        return OrganisationOnboardingService.status(db, org_id)

    @staticmethod
    def get_or_create_identity(db: Session, org: Organisation, category_slug: str) -> OrganisationAIIdentity:
        row = db.execute(select(OrganisationAIIdentity).where(OrganisationAIIdentity.org_id == org.id)).scalar_one_or_none()
        if row is None:
            category_name = db.execute(select(Category.name).where(Category.slug == category_slug)).scalar_one_or_none()
            template = _category_template_for(category_slug, category_name)
            row = OrganisationAIIdentity(
                org_id=org.id,
                assistant_name="VOXBULK Assistant",
                organisation_name=org.name,
                tone="professional",
                humor_level="none",
                languages_json=_json_dumps(["en-GB"]),
                terminology_label=template["default_terminology"],
                disclose_ai=True,
            )
            db.add(row)
            db.flush()
        return row

    @staticmethod
    def get_or_create_compliance(db: Session, org_id: str) -> OrganisationComplianceConfig:
        row = db.execute(select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)).scalar_one_or_none()
        if row is None:
            row = OrganisationComplianceConfig(
                org_id=org_id,
                outbound_call_windows_json=_json_dumps({"weekdays": {"start": "09:00", "end": "18:00"}}),
                whatsapp_windows_json=_json_dumps({"weekdays": {"start": "09:00", "end": "18:00"}}),
                weekend_allowed=False,
                ai_disclosure_wording="This is the VOXBULK AI assistant calling on behalf of the clinic.",
                opt_out_wording="Reply STOP or ask us not to contact you again.",
                escalation_destination="reception team",
                contact_preference_rules_json=_json_dumps({"respect_do_not_contact": True, "prefer_existing_customer_channel": True}),
            )
            db.add(row)
            db.flush()
        return row

    @staticmethod
    def apply_wizard_payload(db: Session, org_id: str, payload: dict[str, Any], *, complete: bool = False) -> dict[str, Any]:
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one()
        if not org.category_id or not org.booking_software_slug:
            raise ValueError("Category and software must be selected before wizard setup")
        category_slug = db.execute(select(Category.slug).where(Category.id == org.category_id)).scalar_one()
        service = db.execute(select(SupportedServiceAPI).where(SupportedServiceAPI.slug == org.booking_software_slug)).scalar_one()
        category_name = db.execute(select(Category.name).where(Category.id == org.category_id)).scalar_one_or_none()
        template = _category_template_for(category_slug, category_name)
        now = datetime.utcnow()

        identity = OrganisationOnboardingService.get_or_create_identity(db, org, category_slug)
        identity_payload = payload.get("ai_identity") or {}
        for key in ["assistant_name", "organisation_name", "tone", "humor_level", "terminology_label"]:
            if identity_payload.get(key) is not None:
                setattr(identity, key, str(identity_payload[key]).strip())
        if identity_payload.get("languages") is not None:
            identity.languages_json = _json_dumps([str(v).strip() for v in identity_payload["languages"] if str(v).strip()])
        if identity_payload.get("disclose_ai") is not None:
            identity.disclose_ai = bool(identity_payload["disclose_ai"])
        identity.updated_at = now
        db.add(identity)

        compliance = OrganisationOnboardingService.get_or_create_compliance(db, org.id)
        compliance_payload = payload.get("compliance") or {}
        json_fields = {
            "outbound_call_windows": "outbound_call_windows_json",
            "whatsapp_windows": "whatsapp_windows_json",
            "contact_preference_rules": "contact_preference_rules_json",
        }
        for incoming, attr in json_fields.items():
            if compliance_payload.get(incoming) is not None:
                setattr(compliance, attr, _json_dumps(compliance_payload[incoming]))
        for key in ["ai_disclosure_wording", "opt_out_wording", "escalation_destination"]:
            if compliance_payload.get(key) is not None:
                setattr(compliance, key, str(compliance_payload[key]).strip() or None)
        if compliance_payload.get("weekend_allowed") is not None:
            compliance.weekend_allowed = bool(compliance_payload["weekend_allowed"])
        compliance.updated_at = now
        db.add(compliance)

        selected_services = [str(v).strip() for v in (payload.get("services") or template["default_services"]) if str(v).strip()]
        custom_services = [str(v).strip() for v in (payload.get("custom_services") or []) if str(v).strip()]
        services = list(dict.fromkeys(selected_services + custom_services))
        existing = {
            row.name: row
            for row in db.execute(select(OrganisationServiceCatalogItem).where(OrganisationServiceCatalogItem.org_id == org.id)).scalars()
        }
        for name in services:
            row = existing.get(name)
            if row is None:
                row = OrganisationServiceCatalogItem(org_id=org.id, name=name, category_slug=category_slug, is_default=name in template["default_services"], is_active=True)
            row.is_active = True
            row.updated_at = now
            db.add(row)

        workflow_payloads = payload.get("workflows")
        if not workflow_payloads:
            workflow_payloads = [
                {"workflow_key": key, "enabled": True, **defaults}
                for key, defaults in template["workflows"].items()
            ]

        workflow_rows: list[OrganisationWorkflowConfig] = []
        for item in workflow_payloads:
            key = str(item.get("workflow_key") or "").strip()
            if key not in template["workflows"]:
                raise ValueError(f"Unsupported workflow_key: {key}")
            row = db.execute(
                select(OrganisationWorkflowConfig).where(
                    OrganisationWorkflowConfig.org_id == org.id,
                    OrganisationWorkflowConfig.workflow_key == key,
                )
            ).scalar_one_or_none()
            defaults = template["workflows"][key]
            if row is None:
                row = OrganisationWorkflowConfig(org_id=org.id, workflow_key=key)
            row.enabled = bool(item.get("enabled", True))
            row.channels_json = _json_dumps(item.get("channels") or defaults.get("channels") or [])
            row.timing_rules_json = _json_dumps(item.get("timing_rules") or defaults.get("timing_rules") or {})
            row.allowed_actions_json = _json_dumps(item.get("allowed_actions") or ["confirm_booking", "offer_available_slots", "send_whatsapp_follow_up"])
            row.forbidden_actions_json = _json_dumps(item.get("forbidden_actions") or ["clinical_advice", "payment_disputes", "medical_advice"])
            row.escalation_rules_json = _json_dumps(item.get("escalation_rules") or ["complaint", "payment", "medical_question", "uncertainty", "human_requested"])
            profile = WorkflowPromptProfileService.build_profile(
                org=org,
                category_slug=category_slug,
                software=service,
                identity=identity,
                compliance=compliance,
                services=services,
                workflow=row,
            )
            row.generated_profile_json = _json_dumps(profile)
            row.generated_prompt_preview = WorkflowPromptProfileService.render_prompt(profile)
            row.workflow_summary_preview = WorkflowPromptProfileService.render_summary(profile)
            row.updated_at = now
            db.add(row)
            workflow_rows.append(row)

        org.onboarding_state = "onboarding_completed" if complete else "wizard_in_progress"
        if complete:
            org.onboarding_completed_at = now
        org.onboarding_version = ONBOARDING_VERSION
        db.add(org)
        db.commit()
        return OrganisationOnboardingService.ai_config(db, org.id)

    @staticmethod
    def ai_config(db: Session, org_id: str) -> dict[str, Any]:
        org = db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one()
        category_slug = None
        if org.category_id:
            category_slug = db.execute(select(Category.slug).where(Category.id == org.category_id)).scalar_one_or_none()
        identity = db.execute(select(OrganisationAIIdentity).where(OrganisationAIIdentity.org_id == org_id)).scalar_one_or_none()
        compliance = db.execute(select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == org_id)).scalar_one_or_none()
        services = [
            row.name
            for row in db.execute(
                select(OrganisationServiceCatalogItem).where(
                    OrganisationServiceCatalogItem.org_id == org_id,
                    OrganisationServiceCatalogItem.is_active.is_(True),
                ).order_by(OrganisationServiceCatalogItem.name.asc())
            ).scalars()
        ]
        workflows = []
        for row in db.execute(
            select(OrganisationWorkflowConfig).where(OrganisationWorkflowConfig.org_id == org_id).order_by(OrganisationWorkflowConfig.workflow_key.asc())
        ).scalars():
            workflows.append(
                {
                    "workflow_key": row.workflow_key,
                    "enabled": row.enabled,
                    "channels": _json_loads(row.channels_json, []),
                    "generated_profile": _json_loads(row.generated_profile_json, {}),
                    "generated_prompt_preview": row.generated_prompt_preview or "",
                    "workflow_summary_preview": row.workflow_summary_preview or "",
                }
            )
        return {
            "status": OrganisationOnboardingService.status(db, org_id),
            "category_slug": category_slug,
            "ai_identity": None
            if identity is None
            else {
                "assistant_name": identity.assistant_name,
                "organisation_name": identity.organisation_name,
                "tone": identity.tone,
                "humor_level": identity.humor_level,
                "languages": _json_loads(identity.languages_json, ["en-GB"]),
                "terminology_label": identity.terminology_label,
                "disclose_ai": identity.disclose_ai,
            },
            "compliance": None
            if compliance is None
            else {
                "outbound_call_windows": _json_loads(compliance.outbound_call_windows_json, {}),
                "whatsapp_windows": _json_loads(compliance.whatsapp_windows_json, {}),
                "weekend_allowed": compliance.weekend_allowed,
                "ai_disclosure_wording": compliance.ai_disclosure_wording,
                "opt_out_wording": compliance.opt_out_wording,
                "escalation_destination": compliance.escalation_destination,
                "contact_preference_rules": _json_loads(compliance.contact_preference_rules_json, {}),
            },
            "services": services,
            "workflows": workflows,
        }

