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

from app.models.customer_feedback import FeedbackIndustry, FeedbackLocation, FeedbackSurveyType, FeedbackWaSender
from app.models.organisation import Organisation
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.survey_config_service import (
    build_survey_config,
    parse_selected_type_ids,
)
from app.services.market_zone import country_to_zone


TRIGGER_TEMPLATE = '✨ I want to start the survey for "{company}" — "{branch}" ✍️📋 [ref:{token}]'
REF_PATTERN = re.compile(r"\[ref:([A-Za-z0-9_-]+)\]", re.IGNORECASE)


def _build_qr_urls(*, phone: str, trigger_text: str) -> tuple[str, str]:
    wa_url = f"https://wa.me/{phone.lstrip('+')}?text={quote(trigger_text)}"
    qr_image_url = (
        "https://api.qrserver.com/v1/create-qr-code/?size=320x320&margin=8&data=" + quote(wa_url, safe="")
    )
    return wa_url, qr_image_url


def location_to_dict(db: Session, row: FeedbackLocation) -> dict[str, Any]:
    org = db.get(Organisation, row.org_id)
    industry = db.get(FeedbackIndustry, row.industry_id)
    survey_type = db.get(FeedbackSurveyType, row.survey_type_id)
    sender = db.execute(
        select(FeedbackWaSender).where(FeedbackWaSender.country_code == row.wa_sender_country)
    ).scalar_one_or_none()
    company = org.name if org else "Your business"
    branch_label = row.name or row.branch_code or row.id[:8]
    trigger_text = TRIGGER_TEMPLATE.format(company=company, branch=branch_label, token=row.qr_token)
    phone = sender.phone_e164 if sender else "+447700900000"
    wa_url, qr_image_url = _build_qr_urls(phone=phone, trigger_text=trigger_text)
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
        "marketing_opt_in_enabled": bool(row.marketing_opt_in_enabled),
        "qr_token": row.qr_token,
        "wa_sender_country": row.wa_sender_country,
        "status": row.status,
        "scan_count": row.scan_count,
        "trigger_text": trigger_text,
        "wa_url": wa_url,
        "qr_image_url": qr_image_url,
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
        sender = db.execute(
            select(FeedbackWaSender).where(FeedbackWaSender.country_code == zone)
        ).scalar_one_or_none()
        phone = sender.phone_e164 if sender else "+447700900000"
        branch = str(payload.get("name") or "Main branch").strip()
        token = secrets.token_urlsafe(12)
        trigger_text = TRIGGER_TEMPLATE.format(company=org.name, branch=branch, token=token)
        wa_url, qr_image_url = _build_qr_urls(phone=phone, trigger_text=trigger_text)
        return {
            "preview": True,
            "trigger_text": trigger_text,
            "wa_url": wa_url,
            "qr_image_url": qr_image_url,
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
        open_question = bool(payload.get("open_question_enabled", True))
        marketing_opt_in = bool(payload.get("marketing_opt_in_enabled", True))
        survey_config = build_survey_config(
            db,
            industry_id=industry_id,
            selected_type_ids=selected_ids,
            open_question_enabled=open_question,
            marketing_opt_in_enabled=marketing_opt_in,
        )
        now = datetime.utcnow()
        row = FeedbackLocation(
            id=str(uuid.uuid4()),
            org_id=org_id,
            industry_id=industry_id,
            survey_type_id=primary_type_id,
            name=str(payload.get("name") or "Location").strip(),
            branch_code=(str(payload.get("branch_code")).strip() if payload.get("branch_code") else None),
            qr_token=secrets.token_urlsafe(12),
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
    def parse_trigger_ref(body: str) -> str | None:
        match = REF_PATTERN.search(str(body or ""))
        return match.group(1) if match else None

    @staticmethod
    def record_scan(db: Session, location: FeedbackLocation) -> None:
        location.scan_count = int(location.scan_count or 0) + 1
        location.updated_at = datetime.utcnow()
        db.add(location)
        db.commit()
