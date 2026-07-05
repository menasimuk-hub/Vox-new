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


TRIGGER_TEMPLATE = "Hi! I'd like to share feedback for {company} at {branch}. {token}"
TOKEN_PATTERN = re.compile(r"\b([a-z0-9]{2,24}-[a-z0-9]{2,24}-[a-z0-9]{6})\b", re.IGNORECASE)
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


def _random_suffix(length: int = 6) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_location_qr_token(*, company: str, branch: str) -> str:
    """company-branch-xxxxxx (6-char suffix), stored in DB and shown in the WhatsApp message."""
    return f"{_slug_part(company)}-{_slug_part(branch)}-{_random_suffix(6)}"


def build_trigger_text(*, company: str, branch: str, token: str) -> str:
    clean_token = str(token or "").strip().lower()
    return TRIGGER_TEMPLATE.format(
        company=str(company or "Your business").strip(),
        branch=str(branch or "Main branch").strip(),
        token=clean_token,
    )


def _qr_image_for(target_url: str) -> str:
    return (
        "https://api.qrserver.com/v1/create-qr-code/?size=320x320&margin=8&charset-source=UTF-8&charset-target=UTF-8&data="
        + quote(str(target_url or ""), safe="", encoding="utf-8")
    )


def _build_qr_urls(*, phone: str, trigger_text: str, qr_target_url: str | None = None) -> tuple[str, str]:
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
    # Default to the WhatsApp deep link only when no web landing URL is supplied (back-compat).
    qr_image_url = _qr_image_for(qr_target_url or wa_url)
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
    wa_url, qr_image_url = _build_qr_urls(phone=phone, trigger_text=trigger_text, qr_target_url=web_survey_url)
    selected_ids: list[str] = []
    if row.selected_survey_type_ids_json:
        try:
            parsed = json.loads(row.selected_survey_type_ids_json)
            if isinstance(parsed, list):
                selected_ids = [str(x) for x in parsed]
        except json.JSONDecodeError:
            selected_ids = []
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
        "wa_sender_country": row.wa_sender_country,
        "status": row.status,
        "scan_count": row.scan_count,
        "trigger_text": trigger_text,
        "wa_sender_phone": phone,
        "wa_url": wa_url,
        "qr_image_url": qr_image_url,
        "web_survey_url": web_survey_url,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class FeedbackLocationService:
    @staticmethod
    def list_locations(db: Session, org_id: str) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(FeedbackLocation)
                .where(FeedbackLocation.org_id == org_id)
                .order_by(FeedbackLocation.created_at.desc())
            )
            .scalars()
            .all()
        )
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
    def create_location(db: Session, org_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if FeedbackBillingService.get_active_subscription(db, org_id) is None:
            raise ValueError("Subscribe to a Customer feedback package before adding locations.")
        max_loc = FeedbackBillingService.max_locations(db, org_id)
        if max_loc <= 0:
            raise ValueError("Subscribe to a Customer feedback package before adding locations.")
        current = FeedbackLocationService.count_locations(db, org_id)
        if current >= max_loc:
            raise ValueError(
                f"Location limit reached ({max_loc}). Upgrade your Customer feedback package or contact support."
            )
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
        location_name = str(payload.get("name") or "Location").strip()
        company_name = org.name if org else "Your business"
        qr_token = build_location_qr_token(company=company_name, branch=location_name)
        while db.execute(select(FeedbackLocation.qr_token).where(FeedbackLocation.qr_token == qr_token)).scalar_one_or_none():
            qr_token = build_location_qr_token(company=company_name, branch=location_name)
        now = datetime.utcnow()
        row = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry_id,
            survey_type_id=primary_type_id,
            name=location_name,
            branch_code=(str(payload.get("branch_code")).strip() if payload.get("branch_code") else None),
            qr_token=qr_token,
            wa_sender_country=zone,
            status=str(payload.get("status") or "active"),
            selected_survey_type_ids_json=json.dumps(selected_ids),
            open_question_enabled=open_question,
            marketing_opt_in_enabled=marketing_opt_in,
            survey_config_json=json.dumps(survey_config),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return location_to_dict(db, row)

    @staticmethod
    def update_location(db: Session, org_id: str, location_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = db.get(FeedbackLocation, location_id)
        if row is None or row.org_id != org_id:
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

        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        db.refresh(row)
        return location_to_dict(db, row)

    @staticmethod
    def delete_location(db: Session, org_id: str, location_id: str) -> None:
        row = db.get(FeedbackLocation, location_id)
        if row is None or row.org_id != org_id:
            raise ValueError("Location not found")
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
        token_match = TOKEN_PATTERN.search(text)
        if token_match:
            return str(token_match.group(1)).strip().lower()
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
