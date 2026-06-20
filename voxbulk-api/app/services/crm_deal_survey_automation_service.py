"""Poll CRM deals and trigger survey sends when deals enter configured stages."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.crm_survey_automation_event import CrmSurveyAutomationEvent
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.crm_connection_service import active_crm_provider
from app.services.messaging_log_service import normalize_e164
from app.services.pipedrive_connection_service import (
    PIPEDRIVE_API_BASE,
    _ensure_access_token,
    pipedrive_status,
)
from app.services.platform_catalog_service import ServiceOrderService
from app.services.survey_billing_context import org_survey_billing_context

logger = logging.getLogger(__name__)

POLL_INTERVAL_MINUTES = 15
DEFAULT_DELAY_HOURS = 24


def _delay_hours_from_block(block: dict[str, Any]) -> int:
    raw = block.get("delay_hours")
    if raw is None:
        return DEFAULT_DELAY_HOURS
    return max(0, min(int(raw), 168))


class CrmDealSurveyAutomationError(Exception):
    pass


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    return _loads(order.config_json)


def read_crm_automation_config(order: ServiceOrder) -> dict[str, Any]:
    cfg = _order_config(order)
    block = cfg.get("crm_automation")
    return block if isinstance(block, dict) else {}


def crm_automation_enabled(order: ServiceOrder) -> bool:
    block = read_crm_automation_config(order)
    return bool(block.get("enabled"))


def survey_crm_automation_blocks_auto_complete(order: ServiceOrder) -> bool:
    if order.service_code != "survey":
        return False
    if not crm_automation_enabled(order):
        return False
    return str(order.status or "").lower() == "running"


def _save_automation_config(db: Session, order: ServiceOrder, block: dict[str, Any]) -> dict[str, Any]:
    cfg = _order_config(order)
    cfg["crm_automation"] = block
    order.config_json = json.dumps(cfg, ensure_ascii=False)
    order.updated_at = datetime.utcnow()
    db.add(order)
    db.commit()
    db.refresh(order)
    return block


def _subscription_allows_automation(db: Session, org: Organisation) -> tuple[bool, str | None]:
    ctx = org_survey_billing_context(db, org)
    if ctx.get("has_dd_subscription") and not ctx.get("is_payg_plan"):
        return True, None
    return False, "CRM deal automation requires an active subscription (not pay-as-you-go or wallet-only)."


def _normalize_stage_ids(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        val = str(item or "").strip()
        if val and val not in out:
            out.append(val)
    return out


def update_crm_automation_settings(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    enabled: bool | None = None,
    stage_ids: list[str] | None = None,
    delay_hours: int | None = None,
    consent_acknowledged: bool | None = None,
) -> dict[str, Any]:
    if order.org_id != org_id or order.service_code != "survey":
        raise CrmDealSurveyAutomationError("CRM automation is only available for survey campaigns in your organisation")

    provider = active_crm_provider(db, org_id)
    if not provider:
        raise CrmDealSurveyAutomationError("Connect a CRM in Settings → Integrations before enabling automation")

    org = db.get(Organisation, org_id)
    if org is None:
        raise CrmDealSurveyAutomationError("Organisation not found")

    block = read_crm_automation_config(order)
    if enabled is not None:
        if enabled:
            ok, reason = _subscription_allows_automation(db, org)
            if not ok:
                raise CrmDealSurveyAutomationError(reason or "Subscription required")
            if consent_acknowledged is not True and block.get("consent_acknowledged") is not True:
                raise CrmDealSurveyAutomationError("Confirm consent before enabling CRM automation")
        block["enabled"] = bool(enabled)
    if stage_ids is not None:
        block["stage_ids"] = _normalize_stage_ids(stage_ids)
    if delay_hours is not None:
        block["delay_hours"] = max(0, min(int(delay_hours), 168))
    if consent_acknowledged is not None:
        block["consent_acknowledged"] = bool(consent_acknowledged)
    block["provider"] = provider
    block.setdefault("delay_hours", DEFAULT_DELAY_HOURS)
    if block.get("enabled") and not _normalize_stage_ids(block.get("stage_ids")):
        raise CrmDealSurveyAutomationError("Select at least one CRM deal stage")

    saved = _save_automation_config(db, order, block)
    if saved.get("enabled") and str(order.status or "").lower() in {"completed", "cancelled"}:
        order.status = "running"
        order.completed_at = None
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
    return automation_status(db, org_id, order)


def automation_status(db: Session, org_id: str, order: ServiceOrder) -> dict[str, Any]:
    block = read_crm_automation_config(order)
    provider = active_crm_provider(db, org_id)
    org = db.get(Organisation, org_id)
    sub_ok, sub_reason = _subscription_allows_automation(db, org) if org else (False, "Organisation not found")
    queued = int(
        db.execute(
            select(func.count())
            .select_from(CrmSurveyAutomationEvent)
            .where(CrmSurveyAutomationEvent.order_id == order.id, CrmSurveyAutomationEvent.status == "scheduled")
        ).scalar_one()
        or 0
    )
    sent = int(
        db.execute(
            select(func.count())
            .select_from(CrmSurveyAutomationEvent)
            .where(CrmSurveyAutomationEvent.order_id == order.id, CrmSurveyAutomationEvent.status == "sent")
        ).scalar_one()
        or 0
    )
    return {
        "enabled": bool(block.get("enabled")),
        "provider": block.get("provider") or provider,
        "stage_ids": _normalize_stage_ids(block.get("stage_ids")),
        "delay_hours": _delay_hours_from_block(block),
        "consent_acknowledged": block.get("consent_acknowledged") is True,
        "last_poll_at": block.get("last_poll_at"),
        "last_poll_summary": block.get("last_poll_summary"),
        "crm_connected": provider is not None,
        "subscription_eligible": sub_ok,
        "subscription_block_reason": sub_reason,
        "queued_count": queued,
        "sent_count": sent,
        "order_status": order.status,
    }


def list_pipedrive_deal_stages(db: Session, org_id: str) -> list[dict[str, Any]]:
    if not pipedrive_status(db, org_id).get("connected"):
        raise CrmDealSurveyAutomationError("Connect Pipedrive in Settings → Integrations")
    token = _ensure_access_token(db, org_id)
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=45.0) as client:
        res = client.get(f"{PIPEDRIVE_API_BASE}/stages", headers=headers)
    if res.status_code >= 400:
        raise CrmDealSurveyAutomationError(f"Pipedrive stages fetch failed: {res.text[:300]}")
    rows = (res.json() or {}).get("data") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "id": str(row.get("id") or ""),
                "name": str(row.get("name") or "").strip(),
                "pipeline_id": str(row.get("pipeline_id") or ""),
                "pipeline_name": str(row.get("pipeline_name") or "").strip(),
                "order_nr": row.get("order_nr"),
            }
        )
    out.sort(key=lambda r: (str(r.get("pipeline_name") or ""), int(r.get("order_nr") or 0)))
    return out


def list_crm_deal_stages(db: Session, org_id: str) -> list[dict[str, Any]]:
    provider = active_crm_provider(db, org_id)
    if provider == "pipedrive":
        return list_pipedrive_deal_stages(db, org_id)
    raise CrmDealSurveyAutomationError(f"Deal-stage automation is not yet supported for {provider or 'your CRM'}")


def _pipedrive_primary_phone(person: dict[str, Any]) -> str | None:
    phones = person.get("phone")
    if not isinstance(phones, list) or not phones:
        return None
    raw = ""
    for row in phones:
        if isinstance(row, dict) and row.get("primary"):
            raw = str(row.get("value") or "").strip()
            break
    if not raw and isinstance(phones[0], dict):
        raw = str(phones[0].get("value") or "").strip()
    if not raw:
        return None
    try:
        return normalize_e164(raw)
    except Exception:
        return raw or None


def _pipedrive_primary_email(person: dict[str, Any]) -> str | None:
    emails = person.get("email")
    if not isinstance(emails, list) or not emails:
        return None
    for row in emails:
        if isinstance(row, dict) and row.get("primary"):
            return str(row.get("value") or "").strip() or None
    first = emails[0]
    return str(first.get("value") or "").strip() or None if isinstance(first, dict) else None


def _fetch_pipedrive_person(token: str, person_id: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        res = client.get(f"{PIPEDRIVE_API_BASE}/persons/{person_id}", headers=headers)
    if res.status_code >= 400:
        return {}
    data = (res.json() or {}).get("data")
    return data if isinstance(data, dict) else {}


def _fetch_pipedrive_deals_for_stages(
    token: str,
    *,
    stage_ids: list[str],
    start: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    deals: list[dict[str, Any]] = []
    with httpx.Client(timeout=45.0) as client:
        for stage_id in stage_ids:
            res = client.get(
                f"{PIPEDRIVE_API_BASE}/deals",
                headers=headers,
                params={"stage_id": stage_id, "status": "all_not_deleted", "start": start, "limit": limit},
            )
            if res.status_code >= 400:
                logger.warning("pipedrive_deals_fetch_failed stage=%s body=%s", stage_id, res.text[:200])
                continue
            rows = (res.json() or {}).get("data") or []
            for row in rows:
                if isinstance(row, dict):
                    deals.append(row)
    return deals


def _stage_name_map(db: Session, org_id: str, provider: str) -> dict[str, str]:
    if provider != "pipedrive":
        return {}
    try:
        stages = list_pipedrive_deal_stages(db, org_id)
    except Exception:
        return {}
    return {str(s.get("id") or ""): str(s.get("name") or "") for s in stages}


def _evaluate_deal_candidate(
    db: Session,
    *,
    org_id: str,
    order: ServiceOrder,
    provider: str,
    deal: dict[str, Any],
    stage_names: dict[str, str],
    dry_run: bool,
) -> dict[str, Any]:
    deal_id = str(deal.get("id") or "").strip()
    stage_id = str(deal.get("stage_id") or "").strip()
    person_id = str(deal.get("person_id") or "").strip()
    title = str(deal.get("title") or "").strip()
    if not deal_id:
        return {"deal_id": "", "action": "skip", "reason": "missing_deal_id"}

    existing = db.execute(
        select(CrmSurveyAutomationEvent).where(
            CrmSurveyAutomationEvent.order_id == order.id,
            CrmSurveyAutomationEvent.provider == provider,
            CrmSurveyAutomationEvent.external_deal_id == deal_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "deal_id": deal_id,
            "deal_title": title,
            "action": "skip",
            "reason": f"already_{existing.status}",
        }

    if not person_id:
        return {"deal_id": deal_id, "deal_title": title, "action": "skip", "reason": "no_linked_person"}

    if provider == "pipedrive":
        token = _ensure_access_token(db, org_id)
        person = _fetch_pipedrive_person(token, person_id)
    else:
        person = {}

    name = str(person.get("name") or title or "Contact").strip()
    phone = _pipedrive_primary_phone(person) if provider == "pipedrive" else None
    email = _pipedrive_primary_email(person) if provider == "pipedrive" else None
    if not phone:
        return {
            "deal_id": deal_id,
            "deal_title": title,
            "contact_name": name,
            "action": "skip",
            "reason": "missing_phone",
        }

    block = read_crm_automation_config(order)
    delay_hours = _delay_hours_from_block(block)
    stage_change_raw = str(deal.get("stage_change_time") or deal.get("update_time") or "").strip()
    try:
        stage_change_at = datetime.fromisoformat(stage_change_raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        stage_change_at = datetime.utcnow()
    scheduled_send_at = stage_change_at + timedelta(hours=delay_hours)

    row = {
        "deal_id": deal_id,
        "deal_title": title,
        "contact_name": name,
        "contact_phone": phone,
        "contact_email": email,
        "stage_id": stage_id,
        "stage_name": stage_names.get(stage_id) or stage_id,
        "scheduled_send_at": scheduled_send_at.isoformat(),
        "action": "schedule" if scheduled_send_at <= datetime.utcnow() else "queue",
    }
    if dry_run:
        return row

    event = CrmSurveyAutomationEvent(
        id=str(uuid.uuid4()),
        org_id=org_id,
        order_id=order.id,
        provider=provider,
        external_deal_id=deal_id,
        external_person_id=person_id or None,
        deal_title=title or None,
        stage_id=stage_id or None,
        stage_name=row["stage_name"],
        contact_name=name,
        contact_phone=phone,
        contact_email=email,
        status="scheduled",
        scheduled_send_at=scheduled_send_at,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(event)
    return row


def dry_run_crm_automation(db: Session, org_id: str, order: ServiceOrder) -> dict[str, Any]:
    block = read_crm_automation_config(order)
    provider = str(block.get("provider") or active_crm_provider(db, org_id) or "").strip()
    stage_ids = _normalize_stage_ids(block.get("stage_ids"))
    if not stage_ids:
        raise CrmDealSurveyAutomationError("Select at least one deal stage first")
    if provider != "pipedrive":
        raise CrmDealSurveyAutomationError("Dry-run is only implemented for Pipedrive")

    token = _ensure_access_token(db, org_id)
    deals = _fetch_pipedrive_deals_for_stages(token, stage_ids=stage_ids, limit=50)
    stage_names = _stage_name_map(db, org_id, provider)
    rows = [
        _evaluate_deal_candidate(
            db,
            org_id=org_id,
            order=order,
            provider=provider,
            deal=deal,
            stage_names=stage_names,
            dry_run=True,
        )
        for deal in deals
    ]
    would_send = sum(1 for r in rows if r.get("action") in {"schedule", "queue"})
    would_skip = sum(1 for r in rows if r.get("action") == "skip")
    return {
        "ok": True,
        "provider": provider,
        "stage_ids": stage_ids,
        "delay_hours": _delay_hours_from_block(block),
        "examined": len(rows),
        "would_schedule": would_send,
        "would_skip": would_skip,
        "rows": rows[:100],
    }


def poll_crm_automation_for_order(db: Session, org_id: str, order: ServiceOrder) -> dict[str, Any]:
    block = read_crm_automation_config(order)
    if not block.get("enabled"):
        return {"skipped": True, "reason": "disabled"}
    provider = str(block.get("provider") or active_crm_provider(db, org_id) or "").strip()
    stage_ids = _normalize_stage_ids(block.get("stage_ids"))
    if not provider or not stage_ids:
        return {"skipped": True, "reason": "missing_provider_or_stages"}

    org = db.get(Organisation, org_id)
    if org is None:
        return {"skipped": True, "reason": "org_missing"}
    ok, reason = _subscription_allows_automation(db, org)
    if not ok:
        block["last_poll_at"] = datetime.utcnow().isoformat()
        block["last_poll_summary"] = reason
        _save_automation_config(db, order, block)
        return {"skipped": True, "reason": reason}

    if provider != "pipedrive" or not pipedrive_status(db, org_id).get("connected"):
        return {"skipped": True, "reason": "crm_not_connected"}

    token = _ensure_access_token(db, org_id)
    deals = _fetch_pipedrive_deals_for_stages(token, stage_ids=stage_ids, limit=100)
    stage_names = _stage_name_map(db, org_id, provider)
    scheduled = 0
    for deal in deals:
        result = _evaluate_deal_candidate(
            db,
            org_id=org_id,
            order=order,
            provider=provider,
            deal=deal,
            stage_names=stage_names,
            dry_run=False,
        )
        if result.get("action") in {"schedule", "queue"}:
            scheduled += 1
    db.commit()

    block["last_poll_at"] = datetime.utcnow().isoformat()
    block["last_poll_summary"] = f"examined={len(deals)} newly_scheduled={scheduled}"
    _save_automation_config(db, order, block)
    return {"ok": True, "examined": len(deals), "newly_scheduled": scheduled}


def _dispatch_automation_recipient(db: Session, *, order: ServiceOrder, event: CrmSurveyAutomationEvent) -> dict[str, Any]:
    from app.services.platform_catalog_service import PlatformCatalogService
    from app.services.survey_call_dispatch_service import SurveyCallDispatchService, is_ai_call_survey_order
    from app.services.survey_dispatch_service import SurveyDispatchService, _survey_intro_text
    from app.services.survey_wa_org_context_service import resolve_survey_organisation_name
    from app.services.telnyx_messaging_service import TelnyxMessagingService

    config = _order_config(order)
    channel = PlatformCatalogService.resolve_survey_channel(config)
    row_number = int(
        db.execute(
            select(func.max(ServiceOrderRecipient.row_number)).where(ServiceOrderRecipient.order_id == order.id)
        ).scalar_one()
        or 0
    ) + 1
    recipient = ServiceOrderRecipient(
        id=str(uuid.uuid4()),
        order_id=order.id,
        row_number=row_number,
        name=str(event.contact_name or "Contact"),
        phone=event.contact_phone,
        email=event.contact_email,
        status="pending",
        intake_source="crm_automation",
        created_at=datetime.utcnow(),
    )
    db.add(recipient)
    db.flush()

    if str(order.status or "").lower() not in {"running", "scheduled", "paid"}:
        order.status = "running"
        order.started_at = order.started_at or datetime.utcnow()
        db.add(order)

    if channel == "ai_call" or is_ai_call_survey_order(order):
        db.commit()
        db.refresh(recipient)
        SurveyCallDispatchService.tick_running_order(db, order)
        return {"recipient_id": recipient.id, "channel": "ai_call", "status": recipient.status}

    org_name = resolve_survey_organisation_name(db, org_id=str(order.org_id), config=config)
    organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
    intro_template = _survey_intro_text(config)
    result = SurveyDispatchService._dispatch_one(
        db,
        order=order,
        recipient=recipient,
        config=config,
        intro_template=intro_template,
        org_name=org_name,
        organiser=organiser,
        prefer_whatsapp=True,
        telnyx_ready=TelnyxMessagingService.is_configured(db),
    )
    db.commit()
    return {"recipient_id": recipient.id, "channel": "whatsapp", **result}


def process_due_crm_automation_sends(db: Session, *, limit: int = 50) -> dict[str, Any]:
    now = datetime.utcnow()
    due = list(
        db.execute(
            select(CrmSurveyAutomationEvent)
            .where(
                CrmSurveyAutomationEvent.status == "scheduled",
                CrmSurveyAutomationEvent.scheduled_send_at.is_not(None),
                CrmSurveyAutomationEvent.scheduled_send_at <= now,
            )
            .order_by(CrmSurveyAutomationEvent.scheduled_send_at.asc())
            .limit(limit)
        ).scalars()
    )
    sent = failed = skipped = 0
    for event in due:
        order = db.get(ServiceOrder, event.order_id)
        org = db.get(Organisation, event.org_id)
        if order is None or org is None:
            event.status = "skipped"
            event.skip_reason = "order_or_org_missing"
            skipped += 1
            continue
        if not crm_automation_enabled(order):
            event.status = "skipped"
            event.skip_reason = "automation_disabled"
            skipped += 1
            continue
        ok, reason = _subscription_allows_automation(db, org)
        if not ok:
            event.status = "skipped"
            event.skip_reason = reason
            skipped += 1
            continue
        if not event.contact_phone:
            event.status = "skipped"
            event.skip_reason = "missing_phone"
            skipped += 1
            continue
        try:
            result = _dispatch_automation_recipient(db, order=order, event=event)
            dispatch_status = str(result.get("status") or "").lower()
            event.recipient_id = str(result.get("recipient_id") or "") or None
            if dispatch_status in {"sent", "calling", "pending"}:
                event.status = "sent"
                event.sent_at = datetime.utcnow()
                sent += 1
            else:
                event.status = "failed"
                event.skip_reason = str(result.get("detail") or "dispatch_failed")[:512]
                failed += 1
        except Exception as exc:
            logger.exception("crm_automation_send_failed event=%s", event.id)
            event.status = "failed"
            event.skip_reason = str(exc)[:512]
            failed += 1
        event.updated_at = datetime.utcnow()
        db.add(event)
    db.commit()
    return {"due": len(due), "sent": sent, "failed": failed, "skipped": skipped}


def poll_all_crm_automation_orders(db: Session) -> dict[str, Any]:
    orders = list(
        db.execute(
            select(ServiceOrder).where(
                ServiceOrder.service_code == "survey",
                ServiceOrder.status.in_(["running", "scheduled", "paid", "completed"]),
            )
        ).scalars()
    )
    polled = enabled = 0
    for order in orders:
        if not crm_automation_enabled(order):
            continue
        enabled += 1
        poll_crm_automation_for_order(db, order.org_id, order)
        polled += 1
    sends = process_due_crm_automation_sends(db)
    return {"enabled_orders": enabled, "polled": polled, **sends}


def run_crm_automation_tick(db: Session) -> dict[str, Any]:
    return poll_all_crm_automation_orders(db)

