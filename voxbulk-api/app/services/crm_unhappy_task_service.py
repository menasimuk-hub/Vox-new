"""Optional CRM follow-up task when a survey respondent is flagged unhappy."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.crm_connection_service import active_crm_provider
from app.services.survey_results_service import _is_unhappy_respondent

logger = logging.getLogger(__name__)

HUBSPOT_TASKS_URL = "https://api.hubapi.com/crm/v3/objects/tasks"
TASK_TO_CONTACT_ASSOCIATION_TYPE_ID = 204


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _crm_create_task_enabled(cfg: dict[str, Any]) -> bool:
    return cfg.get("create_task_on_unhappy_score") is True


def _task_already_created(recipient: ServiceOrderRecipient) -> bool:
    result = _loads(recipient.result_json)
    return bool(str(result.get("crm_unhappy_task_created_at") or "").strip())


def _mark_task_created(db: Session, recipient: ServiceOrderRecipient, *, provider: str, task_id: str) -> None:
    result = _loads(recipient.result_json)
    result.update(
        {
            "crm_unhappy_task_created_at": datetime.utcnow().isoformat(),
            "crm_unhappy_task_provider": provider,
            "crm_unhappy_task_id": task_id,
        }
    )
    recipient.result_json = json.dumps(result, ensure_ascii=False)
    db.add(recipient)


def _survey_title(order: ServiceOrder) -> str:
    return str(order.title or order.survey_name or "Survey").strip() or "Survey"


def _task_copy(order: ServiceOrder, recipient: ServiceOrderRecipient) -> tuple[str, str]:
    title = _survey_title(order)
    name = str(recipient.name or "Respondent").strip()
    phone = str(recipient.phone or "").strip()
    subject = f"VoxBulk: follow up unhappy survey — {title}"[:255]
    body_lines = [
        f"Unhappy or low score on survey: {title}",
        f"Contact: {name}",
    ]
    if phone:
        body_lines.append(f"Phone: {phone}")
    email = str(recipient.email or "").strip()
    if email:
        body_lines.append(f"Email: {email}")
    body_lines.append("Recommended: call within 24 hours.")
    return subject, "\n".join(body_lines)


def _create_hubspot_task(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> dict[str, Any]:
    from app.services.hubspot_connection_service import (
        _ensure_access_token,
        get_hubspot_config,
        hubspot_status,
    )
    from app.services.hubspot_contact_sync_service import _resolve_hubspot_contact_id

    status = hubspot_status(db, org_id)
    if not status.get("connected"):
        return {"ok": True, "skipped": True, "reason": "not_connected"}

    cfg = get_hubspot_config(db, org_id)
    if not _crm_create_task_enabled(cfg):
        return {"ok": True, "skipped": True, "reason": "disabled"}

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        return {"ok": True, "skipped": True, "reason": "no_email_or_phone"}

    token = _ensure_access_token(db, org_id)
    contact_id = _resolve_hubspot_contact_id(db, org_id, token, email=email, phone=phone)
    if not contact_id:
        return {"ok": True, "skipped": True, "reason": "contact_not_found"}

    subject, body = _task_copy(order, recipient)
    due_ms = int((datetime.utcnow() + timedelta(hours=24)).timestamp() * 1000)
    payload = {
        "properties": {
            "hs_task_subject": subject,
            "hs_task_body": body,
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": "HIGH",
            "hs_timestamp": str(due_ms),
        }
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0) as client:
        res = client.post(HUBSPOT_TASKS_URL, headers=headers, json=payload)
        if res.status_code >= 400:
            raise ValueError(f"HubSpot task create failed: {res.text[:300]}")
        task_id = str((res.json() or {}).get("id") or "").strip()
        if not task_id:
            raise ValueError("HubSpot did not return a task ID")
        assoc_url = f"{HUBSPOT_TASKS_URL}/{task_id}/associations/contacts/{contact_id}/{TASK_TO_CONTACT_ASSOCIATION_TYPE_ID}"
        assoc_res = client.put(assoc_url, headers=headers)
        if assoc_res.status_code >= 400:
            logger.warning("hubspot_task_association_failed task=%s contact=%s", task_id, contact_id)

    _mark_task_created(db, recipient, provider="hubspot", task_id=task_id)
    return {"ok": True, "provider": "hubspot", "task_id": task_id, "contact_id": contact_id}


def _create_pipedrive_task(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> dict[str, Any]:
    from app.services.pipedrive_connection_service import (
        PIPEDRIVE_API_BASE,
        _ensure_access_token,
        _search_person_by_email,
        get_pipedrive_config,
        pipedrive_status,
    )

    status = pipedrive_status(db, org_id)
    if not status.get("connected"):
        return {"ok": True, "skipped": True, "reason": "not_connected"}

    cfg = get_pipedrive_config(db, org_id)
    if not _crm_create_task_enabled(cfg):
        return {"ok": True, "skipped": True, "reason": "disabled"}

    email = str(recipient.email or "").strip()
    phone = str(recipient.phone or "").strip()
    if not email and not phone:
        return {"ok": True, "skipped": True, "reason": "no_email_or_phone"}

    token = _ensure_access_token(db, org_id)
    person_id = _search_person_by_email(token, email) if email else None
    if not person_id:
        result = _loads(recipient.result_json)
        person_id = str(result.get("pipedrive_person_id") or "").strip() or None
    if not person_id:
        return {"ok": True, "skipped": True, "reason": "person_not_found"}

    subject, body = _task_copy(order, recipient)
    due_date = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d")
    activity_payload = {
        "subject": subject[:255],
        "type": "task",
        "person_id": int(person_id),
        "due_date": due_date,
        "note": body,
        "done": 0,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with httpx.Client(timeout=30.0) as client:
        res = client.post(f"{PIPEDRIVE_API_BASE}/activities", headers=headers, json=activity_payload)
    if res.status_code >= 400:
        raise ValueError(f"Pipedrive task create failed: {res.text[:300]}")
    activity_id = str(((res.json() or {}).get("data") or {}).get("id") or "").strip()
    if not activity_id:
        raise ValueError("Pipedrive did not return an activity ID")

    _mark_task_created(db, recipient, provider="pipedrive", task_id=activity_id)
    return {"ok": True, "provider": "pipedrive", "task_id": activity_id, "person_id": person_id}


def _zoho_api_base(api_domain: str) -> str:
    domain = str(api_domain or "").strip().rstrip("/")
    if not domain:
        return "https://www.zohoapis.com"
    if domain.startswith("http"):
        return domain
    return f"https://{domain}"


def _create_zoho_task(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> dict[str, Any]:
    from app.services.zoho_crm_connection_service import (
        _ensure_access_token,
        get_zoho_crm_config,
        zoho_crm_status,
    )

    status = zoho_crm_status(db, org_id)
    if not status.get("connected"):
        return {"ok": True, "skipped": True, "reason": "not_connected"}

    cfg = get_zoho_crm_config(db, org_id)
    if not _crm_create_task_enabled(cfg):
        return {"ok": True, "skipped": True, "reason": "disabled"}

    email = str(recipient.email or "").strip()
    if not email:
        return {"ok": True, "skipped": True, "reason": "no_email"}

    token, api_domain = _ensure_access_token(db, org_id)
    api_base = _zoho_api_base(api_domain)
    headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}

    with httpx.Client(timeout=30.0) as client:
        search_res = client.get(
            f"{api_base}/crm/v2/Contacts/search",
            headers=headers,
            params={"email": email},
        )
        contact_id = ""
        if search_res.status_code < 400:
            rows = (search_res.json() or {}).get("data") or []
            if rows and isinstance(rows[0], dict):
                contact_id = str(rows[0].get("id") or "").strip()

    if not contact_id:
        return {"ok": True, "skipped": True, "reason": "contact_not_found"}

    subject, body = _task_copy(order, recipient)
    due_date = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d")
    task_payload = {
        "data": [
            {
                "Subject": subject[:255],
                "Description": body,
                "Due_Date": due_date,
                "Priority": "High",
                "Status": "Not Started",
                "Who_Id": contact_id,
            }
        ]
    }
    with httpx.Client(timeout=30.0) as client:
        res = client.post(f"{api_base}/crm/v2/Tasks", headers=headers, json=task_payload)
    if res.status_code >= 400:
        raise ValueError(f"Zoho task create failed: {res.text[:300]}")
    rows = (res.json() or {}).get("data") or []
    task_id = ""
    if rows and isinstance(rows[0], dict):
        task_id = str(rows[0].get("details", {}).get("id") or rows[0].get("id") or "").strip()

    _mark_task_created(db, recipient, provider="zoho_crm", task_id=task_id or "created")
    return {"ok": True, "provider": "zoho_crm", "task_id": task_id, "contact_id": contact_id}


def maybe_create_unhappy_crm_task(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> None:
    if order.service_code != "survey":
        return
    if str(recipient.status or "").lower() != "completed":
        return
    if not _is_unhappy_respondent(recipient):
        return
    if _task_already_created(recipient):
        return

    provider = active_crm_provider(db, order.org_id)
    if not provider:
        return

    try:
        if provider == "hubspot":
            result = _create_hubspot_task(db, order.org_id, order=order, recipient=recipient)
        elif provider == "pipedrive":
            result = _create_pipedrive_task(db, order.org_id, order=order, recipient=recipient)
        elif provider == "zoho_crm":
            result = _create_zoho_task(db, order.org_id, order=order, recipient=recipient)
        else:
            return
        if result.get("ok") and not result.get("skipped"):
            db.commit()
            logger.info(
                "crm_unhappy_task_created org=%s order=%s recipient=%s provider=%s task=%s",
                order.org_id,
                order.id,
                recipient.id,
                result.get("provider"),
                result.get("task_id"),
            )
    except Exception as exc:
        logger.warning(
            "crm_unhappy_task_failed org=%s order=%s recipient=%s err=%s",
            order.org_id,
            order.id,
            recipient.id,
            str(exc)[:200],
        )


def maybe_post_survey_crm_actions(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> None:
    """Write-back survey results and optional unhappy follow-up task."""
    from app.services.hubspot_contact_sync_service import maybe_sync_survey_result_to_hubspot

    maybe_sync_survey_result_to_hubspot(db, order, recipient)
    maybe_create_unhappy_crm_task(db, order, recipient)
