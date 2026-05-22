from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lead_sales_task import LeadSalesTask
from app.models.sales_offer_template import SalesOfferTemplate
from app.services.lead_sales_service import get_lead_sales_settings
from app.services.promo_offer_service import PromoOfferService

VALID_CATEGORIES = {"subscription", "survey", "interview"}


def template_to_dict(row: SalesOfferTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "offer_type": row.offer_type,
        "plan_code": row.plan_code,
        "trial_days": int(row.trial_days or 0),
        "survey_contacts_included": int(row.survey_contacts_included or 0),
        "interview_contacts_included": int(row.interview_contacts_included or 0),
        "free_call_credits": int(row.free_call_credits or 0),
        "expires_in_days": int(row.expires_in_days or 30),
        "is_active": bool(row.is_active),
        "sort_order": int(row.sort_order or 100),
        "updated_at": row.updated_at,
    }


def list_templates(db: Session, *, active_only: bool = False) -> list[SalesOfferTemplate]:
    q = select(SalesOfferTemplate).order_by(SalesOfferTemplate.sort_order.asc(), SalesOfferTemplate.name.asc())
    if active_only:
        q = q.where(SalesOfferTemplate.is_active.is_(True))
    return list(db.execute(q).scalars().all())


def get_template(db: Session, template_id: str) -> SalesOfferTemplate | None:
    tid = str(template_id or "").strip()
    if not tid:
        return None
    return db.get(SalesOfferTemplate, tid)


def _normalize_offer_type(raw: str) -> str:
    return PromoOfferService.normalize_offer_type(raw)


def create_template(db: Session, payload: dict[str, Any]) -> SalesOfferTemplate:
    now = datetime.utcnow()
    offer_type = _normalize_offer_type(str(payload.get("offer_type") or "dental_trial"))
    row = SalesOfferTemplate(
        id=str(uuid.uuid4()),
        name=str(payload.get("name") or "Sales offer template").strip()[:128],
        offer_type=offer_type,
        plan_code=str(payload.get("plan_code") or "").strip().lower() or None,
        trial_days=max(0, int(payload.get("trial_days") or 15)),
        survey_contacts_included=max(0, int(payload.get("survey_contacts_included") or 0)),
        interview_contacts_included=max(0, int(payload.get("interview_contacts_included") or 0)),
        free_call_credits=max(0, int(payload.get("free_call_credits") or 0)),
        expires_in_days=max(1, int(payload.get("expires_in_days") or 30)),
        is_active=payload.get("is_active", True) is not False,
        sort_order=int(payload.get("sort_order") or 100),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_template(db: Session, template_id: str, payload: dict[str, Any]) -> SalesOfferTemplate:
    row = get_template(db, template_id)
    if row is None:
        raise ValueError("Template not found")
    if "name" in payload:
        row.name = str(payload.get("name") or row.name).strip()[:128]
    if "offer_type" in payload:
        row.offer_type = _normalize_offer_type(str(payload.get("offer_type") or row.offer_type))
    if "plan_code" in payload:
        row.plan_code = str(payload.get("plan_code") or "").strip().lower() or None
    if "trial_days" in payload:
        row.trial_days = max(0, int(payload.get("trial_days") or 0))
    if "survey_contacts_included" in payload:
        row.survey_contacts_included = max(0, int(payload.get("survey_contacts_included") or 0))
    if "interview_contacts_included" in payload:
        row.interview_contacts_included = max(0, int(payload.get("interview_contacts_included") or 0))
    if "free_call_credits" in payload:
        row.free_call_credits = max(0, int(payload.get("free_call_credits") or 0))
    if "expires_in_days" in payload:
        row.expires_in_days = max(1, int(payload.get("expires_in_days") or 30))
    if "is_active" in payload:
        row.is_active = bool(payload.get("is_active"))
    if "sort_order" in payload:
        row.sort_order = int(payload.get("sort_order") or row.sort_order)
    row.updated_at = datetime.utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def parse_task_outcome(task: LeadSalesTask) -> dict[str, Any]:
    raw = str(task.outcome_json or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def recommended_offer_category(task: LeadSalesTask, outcome: dict[str, Any] | None = None) -> str:
    data = outcome if outcome is not None else parse_task_outcome(task)
    raw = str(data.get("recommended_offer") or "").strip().lower()
    if raw in VALID_CATEGORIES:
        return raw
    interest = " ".join(
        [
            str(task.interest_summary or ""),
            str(task.sales_intent or ""),
            str(data.get("outcome_summary") or ""),
        ]
    ).lower()
    if any(k in interest for k in ("interview", "focus group", "qualitative")):
        return "interview"
    if any(k in interest for k in ("survey", "questionnaire", "nps", "feedback collection")):
        return "survey"
    return "subscription"


def resolve_template_for_task(
    db: Session,
    task: LeadSalesTask,
    *,
    category: str | None = None,
    template_id: str | None = None,
) -> SalesOfferTemplate | None:
    if template_id:
        row = get_template(db, template_id)
        if row and row.is_active:
            return row

    settings = get_lead_sales_settings(db)
    cat = str(category or recommended_offer_category(task)).strip().lower()
    if cat not in VALID_CATEGORIES:
        cat = "subscription"

    mapped_id = {
        "subscription": getattr(settings, "sales_template_subscription_id", None),
        "survey": getattr(settings, "sales_template_survey_id", None),
        "interview": getattr(settings, "sales_template_interview_id", None),
    }.get(cat)

    if mapped_id:
        row = get_template(db, mapped_id)
        if row and row.is_active:
            return row

    offer_type_by_cat = {
        "subscription": "dental_trial",
        "survey": "survey_credits",
        "interview": "interview_credits",
    }
    want_type = offer_type_by_cat.get(cat, "dental_trial")
    active = [row for row in list_templates(db, active_only=True) if _normalize_offer_type(row.offer_type) == want_type]
    return active[0] if active else None


def ensure_default_offer_templates(db: Session) -> bool:
    """Seed subscription/survey/interview templates when missing (e.g. migration 0062 not applied)."""
    if list_templates(db):
        return False

    settings = get_lead_sales_settings(db)
    now = datetime.utcnow()
    created = False
    mapping: dict[str, str] = {}
    rows = [
        ("subscription", "Subscription sale 1", "dental_trial", "dental_1", 15, 0, 0, 10),
        ("survey", "Survey sale 1", "survey_credits", None, 0, 3, 0, 20),
        ("interview", "Interview sale 1", "interview_credits", None, 0, 0, 3, 30),
    ]
    for key, name, offer_type, plan, trial, survey, interview, order in rows:
        tid = str(uuid.uuid4())
        db.add(
            SalesOfferTemplate(
                id=tid,
                name=name,
                offer_type=offer_type,
                plan_code=plan,
                trial_days=trial,
                survey_contacts_included=survey,
                interview_contacts_included=interview,
                free_call_credits=0,
                expires_in_days=30,
                is_active=True,
                sort_order=order,
                created_at=now,
                updated_at=now,
            )
        )
        mapping[key] = tid
        created = True

    if not created:
        return False

    if not getattr(settings, "sales_template_subscription_id", None):
        settings.sales_template_subscription_id = mapping["subscription"]
    if not getattr(settings, "sales_template_survey_id", None):
        settings.sales_template_survey_id = mapping["survey"]
    if not getattr(settings, "sales_template_interview_id", None):
        settings.sales_template_interview_id = mapping["interview"]
    settings.updated_at = now
    db.add(settings)
    db.commit()
    return True
