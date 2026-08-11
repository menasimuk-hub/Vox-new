"""Provision the shared real-dashboard org used by AI Demo (Voxbulk Demo)."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.customer_feedback import FeedbackLocation
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.user import User
from app.services.demo_account_seed_service import DemoAccountSeedService
from app.services.ai_demo_dashboard_seed import ensure_expo_and_smart_card_demo_data
from app.services.org_enabled_services import (
    serialize_allowed_services,
    serialize_enabled_services,
)
from app.services.org_logo_storage_service import (
    normalize_logo_tone,
    save_logo_bytes,
    storage_key_for,
    validate_logo_upload,
)

logger = logging.getLogger(__name__)

DEMO_ORG_NAME = "Voxbulk Demo"
DEMO_OWNER_EMAIL = "voxbulk-demo@voxbulk.com"
# Live demo modules only — hide add-ons / unfinished products from Services + sidebar.
AI_DEMO_ACTIVE_MODULES: dict[str, bool] = {
    "interview": True,
    "survey": True,
    "customer_feedback": True,
    "feedback_campaigns": False,  # Add-on · Send campaign — not ready
    "expo": True,
    "smart_card": True,
    "appointments": False,
    "recovery": False,
    "follow_up": False,
    "campaigns": False,
}
DEMO_ORG_PROFILE = {
    "address_line1": "VoxBulk Ltd",
    "address_line2": "Registered in England and Wales",
    "city": "London",
    "county_state": "England",
    "postcode": "EC2A",
    "country": "United Kingdom",
    "country_code": "GB",
    "contact_name": "VoxBulk Demo",
    "contact_email": DEMO_OWNER_EMAIL,
    "contact_phone": "+442045770000",
    "website": "https://voxbulk.com",
    "profile_notes": "Shared AI Demo workspace — do not use for real customers.",
}

# Agent highlight_dashboard section / target → real dashboard path
DEMO_SECTION_ROUTES: dict[str, str] = {
    "services": "/settings/services",
    "enable_services": "/settings/services",
    "settings_services": "/settings/services",
    "settings": "/settings/services",
    "sidebar": "/settings/services",
    "menu": "/settings/services",
    "modules": "/settings/services",
    "pricing": "/account/packages",
    "packages": "/account/packages",
    "show_pricing": "/account/packages",
    "account_packages": "/account/packages",
    "feedback": "/feedback",
    "feedback_list": "/feedback",
    "customer_feedback": "/feedback",
    "feedback_new": "/feedback/new",
    "create_feedback": "/feedback/new",
    "feedback_results": "/feedback/results",
    "feedback_compare": "/feedback/compare",
    "results": "/feedback/results",
    "compare": "/feedback/compare",
    "surveys": "/surveys",
    "wa_survey": "/surveys",
    "whatsapp_surveys": "/surveys",
    "recruitment": "/interviews",
    "interviews": "/interviews",
    "ai_interview": "/interviews",
    "ai_interviews": "/interviews",
    "interview": "/interviews",
    "expo": "/expo",
    "voxbulk_expo": "/expo",
    "booth": "/expo",
    "smart_card": "/smart-card",
    "smartcard": "/smart-card",
    "smart_card_qr": "/smart-card",
    "platform_overview": "/settings/services",
    "dashboard": "/dashboard",
    "home": "/dashboard",
}


def pricing_tab_for_service(service: str | None) -> str:
    """Map product code → /account/packages ?tab= value."""
    s = str(service or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("feedback", "customer_feedback"):
        return "feedback"
    if s in ("expo", "voxbulk_expo", "booth"):
        return "expo"
    if s in ("smart_card", "smartcard", "smart_card_qr"):
        return "smartCard"
    if s in ("recruitment", "surveys", "interview", "interviews", "ai_interview", "core", "platform"):
        return "core"
    return "core"


def packages_route_for_service(service: str | None) -> str:
    return f"/account/packages?tab={pricing_tab_for_service(service)}"


def resolve_demo_route(*, section: str | None = None, target: str | None = None, service: str | None = None) -> str | None:
    for key in (section, target, service):
        raw = str(key or "").strip()
        if not raw:
            continue
        if raw.startswith("/"):
            # Keep query string for pricing tabs etc.
            return raw[:180]
        code = raw.lower().replace("-", "_").replace(" ", "_").replace("/", "_")
        if code in ("pricing", "packages", "show_pricing", "account_packages"):
            return packages_route_for_service(service)
        if code in DEMO_SECTION_ROUTES:
            return DEMO_SECTION_ROUTES[code]
        # Tolerate aliases like settings/services
        slash = raw.lower().strip("/")
        if slash in ("settings/services", "account/packages", "feedback", "surveys", "interviews", "expo", "smart-card"):
            if slash == "account/packages":
                return packages_route_for_service(service)
            return f"/{slash}"
    return None


SERVICE_START_PATHS: dict[str, str] = {
    "feedback": "/feedback",
    "surveys": "/surveys",
    "recruitment": "/interviews",
    "expo": "/expo",
    "smart_card": "/smart-card",
}


class AiDemoOrgService:
    @staticmethod
    def _logo_candidates() -> list[Path]:
        api_root = Path(__file__).resolve().parents[2]
        repo_root = api_root.parent
        return [
            repo_root / "dashboard.voxbulk.com" / "dashboard-web" / "public" / "brand" / "logo-black.png",
            repo_root / "voxbulk.com" / "frontend" / "public" / "brand" / "logo-black.png",
            repo_root / "admin.voxbulk.com" / "adim-web" / "public" / "brand" / "logo-black.png",
            api_root / "logos" / "logo-black.png",
        ]

    @staticmethod
    def find_demo_org(db: Session) -> Organisation | None:
        return db.execute(
            select(Organisation).where(Organisation.name == DEMO_ORG_NAME).order_by(Organisation.created_at.asc())
        ).scalars().first()

    @staticmethod
    def ensure_owner_user(db: Session, org: Organisation) -> User:
        user = db.execute(select(User).where(User.email == DEMO_OWNER_EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(
                email=DEMO_OWNER_EMAIL,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                is_active=True,
                is_superuser=False,
            )
            db.add(user)
            db.flush()
        membership = db.execute(
            select(OrganisationMembership).where(
                OrganisationMembership.org_id == org.id,
                OrganisationMembership.user_id == user.id,
            )
        ).scalar_one_or_none()
        if membership is None:
            db.add(
                OrganisationMembership(
                    org_id=org.id,
                    user_id=user.id,
                    role="owner",
                    dashboard_setup_completed_at=org.onboarding_completed_at or org.created_at,
                )
            )
        else:
            membership.role = "owner"
            if membership.dashboard_setup_completed_at is None:
                membership.dashboard_setup_completed_at = org.onboarding_completed_at or org.created_at
            db.add(membership)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def _apply_profile(org: Organisation) -> None:
        org.name = DEMO_ORG_NAME
        for key, value in DEMO_ORG_PROFILE.items():
            setattr(org, key, value)
        org.onboarding_state = "onboarding_completed"
        if org.onboarding_completed_at is None:
            from datetime import datetime

            org.onboarding_completed_at = datetime.utcnow()

    @staticmethod
    def _ensure_logo(org: Organisation) -> bool:
        if org.logo_storage_key:
            return False
        for path in AiDemoOrgService._logo_candidates():
            if not path.is_file():
                continue
            try:
                content = path.read_bytes()
                ext = validate_logo_upload(filename=path.name, content=content)
                key = storage_key_for(org_id=org.id, ext=ext)
                save_logo_bytes(storage_key=key, content=content)
                org.logo_storage_key = key
                org.logo_tone = normalize_logo_tone("light")
                return True
            except Exception:
                logger.exception("ai_demo_org_logo_failed path=%s", path)
        return False

    @staticmethod
    def apply_active_modules(db: Session, org: Organisation) -> None:
        """Keep Voxbulk Demo on live products only (no unfinished add-ons)."""
        org.allowed_services_json = serialize_allowed_services(dict(AI_DEMO_ACTIVE_MODULES))
        org.enabled_services_json = serialize_enabled_services(dict(AI_DEMO_ACTIVE_MODULES))
        org.onboarding_state = "onboarding_completed"
        db.add(org)
        db.commit()
        db.refresh(org)

    @staticmethod
    def ensure_demo_org(db: Session, *, reseeds: bool = False) -> dict[str, Any]:
        """Idempotent create/update Voxbulk Demo org, owner, logo, and sales demo seed."""
        created = False
        org = AiDemoOrgService.find_demo_org(db)
        if org is None:
            org = Organisation(name=DEMO_ORG_NAME)
            AiDemoOrgService._apply_profile(org)
            db.add(org)
            db.flush()
            created = True
        else:
            AiDemoOrgService._apply_profile(org)
            db.add(org)
            db.flush()

        logo_set = AiDemoOrgService._ensure_logo(org)
        db.add(org)
        db.commit()
        db.refresh(org)

        owner = AiDemoOrgService.ensure_owner_user(db, org)

        if reseeds:
            # Soft: seed_for_org skips if already seeded; caller can wipe separately.
            pass
        seed = DemoAccountSeedService.seed_for_org(db, org_id=org.id, user_id=owner.id)
        # Always re-apply live-module grants (seed may turn all modules on).
        AiDemoOrgService.apply_active_modules(db, org)
        expo_smart = ensure_expo_and_smart_card_demo_data(db, org_id=org.id, user_id=owner.id)
        try:
            from app.services.ai_demo_service import AiDemoService

            AiDemoService.upsert_knowledge_bases(db)
        except Exception:
            logger.exception("ai_demo_kb_upsert_failed")
        locations = AiDemoOrgService.feedback_prompt_numbers(db, org.id)

        return {
            "ok": True,
            "created": created,
            "org_id": org.id,
            "org_name": org.name,
            "owner_user_id": owner.id,
            "owner_email": owner.email,
            "logo_set": logo_set or bool(org.logo_storage_key),
            "seed": seed,
            "expo_smart_card": expo_smart,
            "feedback_locations": locations,
        }

    @staticmethod
    def feedback_prompt_numbers(db: Session, org_id: str) -> list[dict[str, Any]]:
        locs = db.execute(
            select(FeedbackLocation)
            .where(FeedbackLocation.org_id == org_id)
            .order_by(FeedbackLocation.created_at.asc())
        ).scalars().all()
        return [
            {
                "id": loc.id,
                "name": loc.name,
                "scan_count": int(loc.scan_count or 0),
                "status": loc.status,
            }
            for loc in locs
        ]

    @staticmethod
    def prompt_numbers_block(db: Session, org_id: str) -> str:
        locs = AiDemoOrgService.feedback_prompt_numbers(db, org_id)
        if not locs:
            return (
                "REAL DASHBOARD: You are guiding the visitor inside dashboard.voxbulk.com for org "
                f"'{DEMO_ORG_NAME}'. Cite only what is on screen — Feedback locations may still be seeding."
            )
        lines = [
            f"REAL DASHBOARD (dashboard.voxbulk.com — org '{DEMO_ORG_NAME}'):",
            "You MUST call highlight_dashboard before you say look here / open this / on this page.",
            "section values that work: services, packages, feedback, feedback_new, feedback_results, "
            "surveys, recruitment, interviews, expo, smart_card.",
            "Always pass session_id from DEMO_SESSION_ID on every tool call.",
            "Tour order: /settings/services → product page for the selected service → packages if pricing comes up.",
            "Only the live modules are enabled: AI Interviews, Surveys, Customer Feedback, Expo, Smart Card "
            "(no Send-campaign add-on, appointments, recovery, or broadcast campaigns).",
            "Customer Feedback locations on this org (cite these names/scans only):",
        ]
        for loc in locs:
            lines.append(f"- {loc['name']}: ~{loc['scan_count']} scans ({loc['status']})")
        return "\n".join(lines)

    @staticmethod
    def build_dashboard_handoff(
        db: Session,
        *,
        demo_session_id: str,
        start_path: str = "/settings/services",
        expires_minutes: int | None = None,
    ) -> dict[str, Any]:
        ensured = AiDemoOrgService.ensure_demo_org(db)
        org_id = str(ensured["org_id"])
        user_id = str(ensured["owner_user_id"])
        # Short-lived: demo soft-cap is ~7m — do not leave a 60m shared-org JWT lying around.
        ttl = int(expires_minutes) if expires_minutes is not None else 12
        ttl = max(8, min(ttl, 20))
        token = create_access_token(
            subject=user_id,
            org_id=org_id,
            expires_minutes=ttl,
            extra_claims={"demo_session_id": str(demo_session_id), "demo_access": True},
        )
        origin = (get_settings().dashboard_app_origin or "https://dashboard.voxbulk.com").rstrip("/")
        public = str(getattr(get_settings(), "public_site_base_url", None) or "https://voxbulk.com").rstrip("/")
        path = start_path if start_path.startswith("/") else f"/{start_path}"
        query = urlencode({"demo_session": demo_session_id})
        hash_params = urlencode(
            {
                "access_token": token,
                "org_id": org_id,
                "user_id": user_id,
            }
        )
        dashboard_url = f"{origin}{path}?{query}#{hash_params}"
        thanks_url = f"{public}/demo/thanks?session={demo_session_id}"
        return {
            "dashboard_url": dashboard_url,
            "thanks_url": thanks_url,
            "org_id": org_id,
            "user_id": user_id,
            "start_path": path,
            "token_expires_minutes": ttl,
            "feedback_locations": ensured.get("feedback_locations") or [],
        }
