"""Customer Feedback locations and QR codes."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType
from app.models.organisation import Organisation
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.feedback_wa_phone import resolve_feedback_wa_phone_for_qr
from app.services.customer_feedback.survey_config_service import (
    build_survey_config,
    parse_selected_type_ids,
    parse_selected_type_ids_from_location,
    rebuild_survey_config_for_location,
    validate_feedback_survey_templates_ready,
)
from app.services.customer_feedback.feedback_marketing_policy import effective_marketing_opt_in_enabled
from app.services.market_zone import country_to_zone
from app.services.customer_feedback.web_theme_service import (
    load_web_theme_from_location,
    merge_web_theme_into_config,
    parse_web_theme_config,
    resolve_theme_id,
)
from app.services.customer_feedback.feedback_ai_followup_service import (
    enrich_ai_follow_up_with_call_kb,
    load_ai_follow_up_from_location,
)


TRIGGER_TEMPLATE = "Hi! I'd like to share feedback for {company} at {branch}. {token}"
# company/branch slugs may contain hyphens (e.g. rottnest-island-wadj-rottnest-<suffix>).
# Require ≥2 slug segments + a 6–32 char suffix; prefer the longest match when parsing.
TOKEN_PATTERN = re.compile(r"\b((?:[a-z0-9]{2,24}-){2,}[a-z0-9]{6,32})\b", re.IGNORECASE)
REF_PATTERN = re.compile(r"\bref:\s*([A-Za-z0-9-]+)", re.IGNORECASE)
LEGACY_REF_PATTERN = re.compile(r"\[ref:([A-Za-z0-9_-]+)\]", re.IGNORECASE)
LANGUAGE_HINT_PATTERN = re.compile(
    r"(?:\(\s*(ar|en|en_gb|en_us|en_au|arabic|english)\s*\)|\s+(ar|en))\s*$",
    re.IGNORECASE,
)
_FEEDBACK_INTENT_PATTERNS = (
    re.compile(r"(?i)\bshare feedback\b"),
    re.compile(r"(?i)\bi['']?d like to share feedback\b"),
    re.compile(r"(?i)\bleave feedback\b"),
)
SCAN_QR_HINT = "Please scan the QR code at the location to start your feedback survey."


def _slug_part(text: str, *, max_len: int = 20) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return (base or "location")[:max_len]


def _random_suffix(length: int = 16) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_location_qr_token(*, company: str, branch: str) -> str:
    """company-branch-<suffix>. New locations use 16-char suffix; legacy 6-char tokens still work."""
    return f"{_slug_part(company)}-{_slug_part(branch)}-{_random_suffix(16)}"


def build_trigger_text(*, company: str, branch: str, token: str) -> str:
    clean_token = str(token or "").strip().lower()
    return TRIGGER_TEMPLATE.format(
        company=str(company or "Your business").strip(),
        branch=str(branch or "Main branch").strip(),
        token=clean_token,
    )


def _qr_image_for(row: FeedbackLocation) -> str:
    from app.services.brand_assets import api_public_origin
    from app.services.qr_style_render import build_qr_png_url

    token = str(row.qr_token or "").strip()
    return build_qr_png_url(
        api_origin=api_public_origin() or "https://api.voxbulk.com",
        path=f"/public/feedback/{token}/qr.png",
        fg=str(getattr(row, "qr_fg_color", None) or "000000"),
        bg=str(getattr(row, "qr_bg_color", None) or "ffffff"),
        transparent=bool(getattr(row, "qr_transparent", False)),
        module_style=str(getattr(row, "qr_module_style", None) or "square"),
        corner_style=str(getattr(row, "qr_corner_style", None) or "square"),
        show_arrow=bool(getattr(row, "qr_show_arrow", False)),
        frame_round=str(getattr(row, "qr_frame_round", None) or "none"),
        size=512,
    )


def _build_qr_urls(
    *,
    phone: str,
    trigger_text: str,
    qr_target_url: str | None = None,
    location: FeedbackLocation | None = None,
) -> tuple[str, str]:
    """Return (wa_url, qr_image_url).

    The scannable QR now points at the web survey landing page (Task 6 — feedback-flow),
    where the visitor chooses WhatsApp or web. The wa.me deep link is still returned so the
    landing page (and dashboard) can offer the WhatsApp option.
    """
    digits = str(phone or "").strip().lstrip("+").replace(" ", "")
    if not digits:
        raise ValueError("WhatsApp business number is not configured for Customer Feedback.")
    encoded_text = quote(trigger_text, safe="", encoding="utf-8")
    wa_url = f"https://wa.me/{digits}?text={encoded_text}"
    if location is not None:
        qr_image_url = _qr_image_for(location)
    else:
        # Preview without a row — plain styled URL is not available; fall back to external.
        from urllib.parse import quote as q

        target = qr_target_url or wa_url
        qr_image_url = (
            "https://api.qrserver.com/v1/create-qr-code/?size=320x320&margin=8&data="
            + q(str(target or ""), safe="", encoding="utf-8")
        )
    return wa_url, qr_image_url


def location_to_dict(db: Session, row: FeedbackLocation) -> dict[str, Any]:
    org = db.get(Organisation, row.org_id)
    industry = db.get(FeedbackIndustry, row.industry_id)
    survey_type = db.get(FeedbackSurveyType, row.survey_type_id)
    company = org.name if org else "Your business"
    branch_label = row.name or row.branch_code or row.id[:8]
    trigger_text = build_trigger_text(company=company, branch=branch_label, token=row.qr_token)
    phone = resolve_feedback_wa_phone_for_qr(db, row.wa_sender_country)
    web_base = get_settings().public_site_base_url.rstrip("/")
    web_survey_url = f"{web_base}/survey/{row.qr_token}"
    wa_url, qr_image_url = _build_qr_urls(
        phone=phone, trigger_text=trigger_text, qr_target_url=web_survey_url, location=row
    )
    selected_ids: list[str] = []
    if row.selected_survey_type_ids_json:
        try:
            parsed = json.loads(row.selected_survey_type_ids_json)
            if isinstance(parsed, list):
                selected_ids = [str(x) for x in parsed]
        except json.JSONDecodeError:
            selected_ids = []
    from app.services.qr_style_fields import qr_style_dict

    return {
        "id": row.id,
        "org_id": row.org_id,
        "name": row.name,
        "branch_code": row.branch_code,
        "industry_id": row.industry_id,
        "industry_name": industry.name if industry else None,
        "survey_type_id": row.survey_type_id,
        "survey_type_name": survey_type.name if survey_type else None,
        "selected_survey_type_ids": selected_ids,
        "open_question_enabled": bool(row.open_question_enabled),
        "marketing_opt_in_enabled": effective_marketing_opt_in_enabled(row.marketing_opt_in_enabled),
        "qr_token": row.qr_token,
        **qr_style_dict(row, include_transparent=True),
        "wa_sender_country": row.wa_sender_country,
        "status": row.status,
        "scan_count": row.scan_count,
        "trigger_text": trigger_text,
        "wa_sender_phone": phone,
        "wa_url": wa_url,
        "qr_image_url": qr_image_url,
        "web_survey_url": web_survey_url,
        "web_theme": load_web_theme_from_location(row),
        "ai_follow_up": load_ai_follow_up_from_location(row),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class FeedbackLocationService:
    @staticmethod
    def list_locations(
        db: Session, org_id: str, *, created_by_user_id: str | None = None
    ) -> list[dict[str, Any]]:
        stmt = (
            select(FeedbackLocation)
            .where(FeedbackLocation.org_id == org_id)
            .order_by(FeedbackLocation.created_at.desc())
        )
        if created_by_user_id:
            stmt = stmt.where(FeedbackLocation.created_by_user_id == created_by_user_id)
        rows = list(db.execute(stmt).scalars().all())
        return [location_to_dict(db, r) for r in rows]

    @staticmethod
    def count_locations(db: Session, org_id: str) -> int:
        return int(
            db.execute(
                select(func.count()).select_from(FeedbackLocation).where(FeedbackLocation.org_id == org_id)
            ).scalar_one()
            or 0
        )

    @staticmethod
    def count_active_locations(db: Session, org_id: str) -> int:
        return int(
            db.execute(
                select(func.count())
                .select_from(FeedbackLocation)
                .where(
                    FeedbackLocation.org_id == org_id,
                    FeedbackLocation.status == "active",
                )
            ).scalar_one()
            or 0
        )

    @staticmethod
    def activate_preview_locations(db: Session, org_id: str) -> dict[str, Any]:
        """After pay: flip preview drafts to active up to package max_locations."""
        max_loc = FeedbackBillingService.max_locations(db, org_id)
        if max_loc <= 0:
            return {"activated": 0, "left_preview": 0}
        active_n = FeedbackLocationService.count_active_locations(db, org_id)
        slots = max(0, max_loc - active_n)
        preview_rows = list(
            db.execute(
                select(FeedbackLocation)
                .where(
                    FeedbackLocation.org_id == org_id,
                    FeedbackLocation.status.in_(("preview", "preview_exhausted")),
                )
                .order_by(FeedbackLocation.created_at.asc())
            )
            .scalars()
            .all()
        )
        activated = 0
        for row in preview_rows:
            if activated >= slots:
                break
            row.status = "active"
            row.updated_at = datetime.utcnow()
            db.add(row)
            activated += 1
        db.commit()
        return {"activated": activated, "left_preview": max(0, len(preview_rows) - activated)}

    @staticmethod
    def gate_session_start(db: Session, location: FeedbackLocation) -> tuple[str | None, str | None]:
        """
        Returns (billing_mode, error_message).
        billing_mode is 'live' | 'preview' when allowed; None when blocked.
        """
        from app.models.customer_feedback import FEEDBACK_PREVIEW_TESTS_LIMIT

        status = str(location.status or "").strip().lower()
        if status == "paused":
            return None, "This Customer Feedback QR is paused."
        if status == "archived":
            return None, "This Customer Feedback QR is no longer available."
        renew = "https://dashboard.voxbulk.com/account/feedback/packages"
        if status in {"preview", "preview_exhausted"}:
            # After pay, flip preview drafts to active when slots allow.
            FeedbackLocationService.activate_preview_locations(db, location.org_id)
            db.refresh(location)
            status = str(location.status or "").strip().lower()
        if status == "active":
            mode = FeedbackBillingService.access_mode(db, location.org_id)
            if mode == "live":
                return "live", None
            if mode == "expired":
                return (
                    None,
                    f"Your Customer feedback package has expired. Renew to continue: {renew}",
                )
            return (
                None,
                f"Subscribe to a Customer feedback package to collect responses: {renew}",
            )
        if status == "preview":
            used = FeedbackBillingService.preview_tests_used(db, location.org_id)
            if used >= FEEDBACK_PREVIEW_TESTS_LIMIT:
                location.status = "preview_exhausted"
                location.updated_at = datetime.utcnow()
                db.add(location)
                db.commit()
                return (
                    None,
                    f"Demo testing limit reached ({FEEDBACK_PREVIEW_TESTS_LIMIT} scans). "
                    f"Pay to activate this QR survey: {renew}",
                )
            return "preview", None
        if status == "preview_exhausted":
            return (
                None,
                f"Demo testing limit reached ({FEEDBACK_PREVIEW_TESTS_LIMIT} scans). "
                f"Pay to activate this QR survey: {renew}",
            )
        return None, "This Customer Feedback QR is unavailable."

    @staticmethod
    def preview_location(db: Session, org_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        org = db.get(Organisation, org_id)
        if org is None:
            raise ValueError("Organisation not found")
        industry_id = str(payload.get("industry_id") or "").strip()
        if not industry_id:
            raise ValueError("industry_id required")
        selected_ids = parse_selected_type_ids(payload)
        if not selected_ids:
            raise ValueError("At least one survey topic is required")
        zone = country_to_zone(getattr(org, "country", None))
        phone = resolve_feedback_wa_phone_for_qr(db, zone)
        branch = str(payload.get("name") or "Main branch").strip()
        token = build_location_qr_token(company=org.name, branch=branch)
        trigger_text = build_trigger_text(company=org.name, branch=branch, token=token)
        web_base = get_settings().public_site_base_url.rstrip("/")
        web_survey_url = f"{web_base}/survey/{token}"
        wa_url, qr_image_url = _build_qr_urls(
            phone=phone, trigger_text=trigger_text, qr_target_url=web_survey_url
        )
        return {
            "preview": True,
            "trigger_text": trigger_text,
            "wa_sender_phone": phone,
            "wa_url": wa_url,
            "qr_image_url": qr_image_url,
            "web_survey_url": web_survey_url,
            "selected_survey_type_ids": selected_ids,
            "open_question_enabled": bool(payload.get("open_question_enabled", True)),
            "marketing_opt_in_enabled": bool(payload.get("marketing_opt_in_enabled", True)),
        }

    @staticmethod
    def create_location(
        db: Session, org_id: str, payload: dict[str, Any], *, created_by_user_id: str | None = None
    ) -> dict[str, Any]:
        live_sub = FeedbackBillingService.get_usage_eligible_subscription(db, org_id)
        if live_sub is not None:
            max_loc = FeedbackBillingService.max_locations(db, org_id)
            if max_loc <= 0:
                raise ValueError("Subscribe to a Customer feedback package before adding locations.")
            current = FeedbackLocationService.count_active_locations(db, org_id)
            if current >= max_loc:
                raise ValueError(
                    f"Location limit reached ({max_loc}). Upgrade your Customer feedback package or contact support."
                )
            default_status = "active"
        else:
            # Unpaid: save as demo preview (org-wide 20-scan testing pool).
            default_status = "preview"
        org = db.get(Organisation, org_id)
        zone = country_to_zone(getattr(org, "country", None) if org else None)
        industry_id = str(payload.get("industry_id") or "").strip()
        selected_ids = parse_selected_type_ids(payload)
        primary_type_id = selected_ids[0] if selected_ids else str(payload.get("survey_type_id") or "").strip()
        if not industry_id or not primary_type_id:
            raise ValueError("industry_id and at least one survey topic are required")
        from app.models.customer_feedback import FeedbackIndustry
        from app.services.customer_feedback.catalog_service import FeedbackCatalogService

        industry = db.get(FeedbackIndustry, industry_id)
        if industry is None or not FeedbackCatalogService._industry_visible_to_org(db, industry, org_id):
            raise ValueError("Industry is not available for this organisation.")
        open_question = bool(payload.get("open_question_enabled", True))
        marketing_opt_in = effective_marketing_opt_in_enabled(payload.get("marketing_opt_in_enabled", False))
        template_errors = validate_feedback_survey_templates_ready(
            db,
            industry_id=industry_id,
            selected_type_ids=selected_ids,
            open_question_enabled=open_question,
            marketing_opt_in_enabled=marketing_opt_in,
        )
        if template_errors:
            raise ValueError(template_errors[0])
        survey_config = build_survey_config(
            db,
            industry_id=industry_id,
            selected_type_ids=selected_ids,
            open_question_enabled=open_question,
            marketing_opt_in_enabled=marketing_opt_in,
        )
        web_theme = payload.get("web_theme")
        ai_follow_up = payload.get("ai_follow_up")
        location_name = str(payload.get("name") or "Location").strip()
        company_name = org.name if org else "Your business"
        if isinstance(web_theme, dict) or isinstance(ai_follow_up, dict):
            extras: dict[str, Any] = {}
            if isinstance(web_theme, dict):
                extras["web_theme"] = web_theme
            if isinstance(ai_follow_up, dict):
                extras["ai_follow_up"] = enrich_ai_follow_up_with_call_kb(
                    db,
                    ai_follow_up,
                    org=org,
                    location_name=location_name,
                    industry_name=getattr(industry, "name", None),
                    selected_type_ids=selected_ids,
                )
            survey_config = merge_web_theme_into_config(survey_config, extras.get("web_theme"))
            if extras.get("ai_follow_up"):
                survey_config["ai_follow_up"] = extras["ai_follow_up"]
        qr_token = build_location_qr_token(company=company_name, branch=location_name)
        while db.execute(select(FeedbackLocation.qr_token).where(FeedbackLocation.qr_token == qr_token)).scalar_one_or_none():
            qr_token = build_location_qr_token(company=company_name, branch=location_name)
        now = datetime.utcnow()
        # Only paid creates may be active; unpaid always saves as preview demo.
        status = default_status
        requested = str(payload.get("status") or "").strip().lower()
        if live_sub is not None and requested in {"active", "paused"}:
            status = requested
        row = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry_id,
            survey_type_id=primary_type_id,
            name=location_name,
            branch_code=(str(payload.get("branch_code")).strip() if payload.get("branch_code") else None),
            qr_token=qr_token,
            wa_sender_country=zone,
            status=status,
            selected_survey_type_ids_json=json.dumps(selected_ids),
            open_question_enabled=open_question,
            marketing_opt_in_enabled=marketing_opt_in,
            survey_config_json=json.dumps(survey_config),
            created_by_user_id=(str(created_by_user_id).strip() or None) if created_by_user_id else None,
            created_at=now,
            updated_at=now,
        )
        from app.services.qr_style_fields import init_qr_style_on_create

        init_qr_style_on_create(row, payload, allow_transparent=True)
        db.add(row)
        db.commit()
        db.refresh(row)
        return location_to_dict(db, row)

    @staticmethod
    def get_location_row(
        db: Session,
        org_id: str,
        location_id: str,
        *,
        created_by_user_id: str | None = None,
    ) -> FeedbackLocation | None:
        row = db.get(FeedbackLocation, location_id)
        if row is None or row.org_id != org_id:
            return None
        if created_by_user_id and str(row.created_by_user_id or "") != str(created_by_user_id):
            return None
        return row

    @staticmethod
    def update_location(
        db: Session,
        org_id: str,
        location_id: str,
        payload: dict[str, Any],
        *,
        created_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        row = FeedbackLocationService.get_location_row(
            db, org_id, location_id, created_by_user_id=created_by_user_id
        )
        if row is None:
            raise ValueError("Location not found")
        if payload.get("name"):
            row.name = str(payload["name"]).strip()
        if "branch_code" in payload:
            row.branch_code = str(payload["branch_code"]).strip() if payload["branch_code"] else None
        if payload.get("status"):
            row.status = str(payload["status"]).strip()

        survey_fields_changed = False
        if "selected_survey_type_ids" in payload or "survey_type_id" in payload:
            selected_ids = parse_selected_type_ids(payload)
            if not selected_ids:
                selected_ids = parse_selected_type_ids_from_location(row)
            if not selected_ids:
                raise ValueError("At least one survey topic is required")
            row.selected_survey_type_ids_json = json.dumps(selected_ids)
            row.survey_type_id = selected_ids[0]
            survey_fields_changed = True
        if "open_question_enabled" in payload:
            row.open_question_enabled = bool(payload.get("open_question_enabled"))
            survey_fields_changed = True
        if "marketing_opt_in_enabled" in payload:
            row.marketing_opt_in_enabled = effective_marketing_opt_in_enabled(payload.get("marketing_opt_in_enabled"))
            survey_fields_changed = True

        if survey_fields_changed:
            row.survey_config_json = json.dumps(rebuild_survey_config_for_location(db, row))

        if "web_theme" in payload or "ai_follow_up" in payload or survey_fields_changed:
            cfg = parse_web_theme_config(row.survey_config_json)
            if "web_theme" in payload and isinstance(payload.get("web_theme"), dict):
                cfg["web_theme"] = payload["web_theme"]
            industry = db.get(FeedbackIndustry, row.industry_id)
            org = db.get(Organisation, org_id)
            ai_cfg = (
                payload["ai_follow_up"]
                if "ai_follow_up" in payload and isinstance(payload.get("ai_follow_up"), dict)
                else (cfg.get("ai_follow_up") if isinstance(cfg.get("ai_follow_up"), dict) else None)
            )
            if isinstance(ai_cfg, dict):
                cfg["ai_follow_up"] = enrich_ai_follow_up_with_call_kb(
                    db,
                    ai_cfg,
                    org=org,
                    location_name=str(row.name or ""),
                    industry_name=getattr(industry, "name", None) if industry else None,
                    selected_type_ids=parse_selected_type_ids_from_location(row),
                )
            row.survey_config_json = json.dumps(cfg)

        from app.services.qr_style_fields import apply_qr_style_payload

        apply_qr_style_payload(row, payload, allow_transparent=True)

        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return location_to_dict(db, row)

    @staticmethod
    def delete_location(
        db: Session, org_id: str, location_id: str, *, created_by_user_id: str | None = None
    ) -> None:
        from pathlib import Path

        from sqlalchemy import delete, update

        from app.models.customer_feedback import (
            FeedbackAiFollowUpJob,
            FeedbackMarketingSubscriber,
            FeedbackResponse,
            FeedbackSession,
            FeedbackVoiceNoteJob,
        )

        row = FeedbackLocationService.get_location_row(
            db, org_id, location_id, created_by_user_id=created_by_user_id
        )
        if row is None:
            raise ValueError("Location not found")
        loc_id = str(row.id)
        session_ids = [
            str(sid)
            for sid in db.execute(
                select(FeedbackSession.id).where(FeedbackSession.location_id == loc_id)
            ).scalars().all()
        ]
        if session_ids:
            voice_jobs = list(
                db.execute(
                    select(FeedbackVoiceNoteJob).where(FeedbackVoiceNoteJob.session_id.in_(session_ids))
                )
                .scalars()
                .all()
            )
            for job in voice_jobs:
                raw = str(getattr(job, "audio_file_path", None) or "").strip()
                if not raw:
                    continue
                try:
                    path = Path(raw)
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass
            db.execute(
                delete(FeedbackAiFollowUpJob).where(FeedbackAiFollowUpJob.session_id.in_(session_ids))
            )
            db.execute(
                delete(FeedbackVoiceNoteJob).where(FeedbackVoiceNoteJob.session_id.in_(session_ids))
            )
            db.execute(delete(FeedbackResponse).where(FeedbackResponse.session_id.in_(session_ids)))
        db.execute(delete(FeedbackResponse).where(FeedbackResponse.location_id == loc_id))
        db.execute(delete(FeedbackSession).where(FeedbackSession.location_id == loc_id))
        db.execute(
            update(FeedbackMarketingSubscriber)
            .where(FeedbackMarketingSubscriber.location_id == loc_id)
            .values(location_id=None, session_id=None)
        )
        db.delete(row)
        db.commit()

    @staticmethod
    def resolve_by_token(db: Session, token: str) -> FeedbackLocation | None:
        tok = str(token or "").strip()
        if not tok:
            return None
        return db.execute(select(FeedbackLocation).where(FeedbackLocation.qr_token == tok)).scalar_one_or_none()

    @staticmethod
    def parse_trigger_language_hint(body: str) -> str | None:
        match = LANGUAGE_HINT_PATTERN.search(str(body or ""))
        if not match:
            return None
        raw = str(match.group(1) or match.group(2) or "").strip().lower()
        return raw or None

    @staticmethod
    def is_feedback_intent_message(body: str) -> bool:
        text = str(body or "").strip()
        if not text or FeedbackLocationService.parse_trigger_ref(text):
            return False
        return any(pattern.search(text) for pattern in _FEEDBACK_INTENT_PATTERNS)

    @staticmethod
    def parse_trigger_ref(body: str) -> str | None:
        text = str(body or "")
        token_matches = TOKEN_PATTERN.findall(text)
        if token_matches:
            # Longest wins so multi-hyphen tokens are not truncated to a mid-string triple.
            return max((str(m).strip().lower() for m in token_matches), key=len)
        match = REF_PATTERN.search(text) or LEGACY_REF_PATTERN.search(text)
        if not match:
            return None
        return str(match.group(1)).strip().lower()

    @staticmethod
    def record_scan(db: Session, location: FeedbackLocation) -> None:
        location.scan_count = int(location.scan_count or 0) + 1
        location.updated_at = datetime.utcnow()
        db.add(location)
        db.commit()
