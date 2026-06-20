"""Unified survey result write-back to the active CRM."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.crm_connection_service import active_crm_provider

logger = logging.getLogger(__name__)


def maybe_sync_survey_result_to_active_crm(
    db: Session,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
) -> None:
    if order.service_code != "survey":
        return
    if str(recipient.status or "").lower() != "completed":
        return

    provider = active_crm_provider(db, order.org_id)
    if not provider:
        return

    try:
        if provider == "hubspot":
            from app.services.hubspot_contact_sync_service import maybe_sync_survey_result_to_hubspot

            maybe_sync_survey_result_to_hubspot(db, order, recipient)
        elif provider == "pipedrive":
            from app.services.pipedrive_contact_sync_service import sync_survey_result_to_pipedrive

            result = sync_survey_result_to_pipedrive(db, order.org_id, order=order, recipient=recipient)
            if result.get("ok") and not result.get("skipped"):
                db.commit()
        elif provider == "zoho_crm":
            from app.services.zoho_crm_contact_sync_service import sync_survey_result_to_zoho_crm

            result = sync_survey_result_to_zoho_crm(db, order.org_id, order=order, recipient=recipient)
            if result.get("ok") and not result.get("skipped"):
                db.commit()
    except Exception as exc:
        logger.warning(
            "crm_survey_writeback_failed org=%s order=%s recipient=%s provider=%s err=%s",
            order.org_id,
            order.id,
            recipient.id,
            provider,
            str(exc)[:200],
        )


def sync_survey_result_to_active_crm(
    db: Session,
    org_id: str,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    force: bool = True,
) -> dict:
    provider = active_crm_provider(db, org_id)
    if not provider:
        raise ValueError("No CRM connected")

    if provider == "hubspot":
        from app.services.hubspot_contact_sync_service import HubspotContactSyncError, sync_survey_result_to_hubspot

        try:
            return sync_survey_result_to_hubspot(db, org_id, order=order, recipient=recipient, force=force)
        except HubspotContactSyncError as exc:
            raise ValueError(str(exc)) from exc

    if provider == "pipedrive":
        from app.services.pipedrive_contact_sync_service import PipedriveContactSyncError, sync_survey_result_to_pipedrive

        try:
            return sync_survey_result_to_pipedrive(db, org_id, order=order, recipient=recipient, force=force)
        except PipedriveContactSyncError as exc:
            raise ValueError(str(exc)) from exc

    if provider == "zoho_crm":
        from app.services.zoho_crm_contact_sync_service import ZohoCrmContactSyncError, sync_survey_result_to_zoho_crm

        try:
            return sync_survey_result_to_zoho_crm(db, org_id, order=order, recipient=recipient, force=force)
        except ZohoCrmContactSyncError as exc:
            raise ValueError(str(exc)) from exc

    raise ValueError(f"Result sync is not supported for {provider}")
