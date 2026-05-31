"""Send human-interview booking links (Calendly/Cronofy) to shortlisted candidates."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.platform_catalog_service import ServiceOrderService
from app.services.scheduling_connection_service import create_scheduling_link, scheduling_status
from app.services.smtp_mailer_service import SmtpMailerService
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    send_template_id_for_row,
)
from app.services.transactional_email_service import TransactionalEmailService


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _recipient_result(recipient: ServiceOrderRecipient) -> dict[str, Any]:
    try:
        data = json.loads(recipient.result_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _first_name(name: str | None) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "there"
    return raw.split()[0]


def _now() -> datetime:
    return datetime.utcnow()


def _org_name(db: Session, order: ServiceOrder) -> str:
    try:
        from app.services.recovery_service import OrganisationService

        org = OrganisationService.get_org(db, order.org_id)
        name = str(org.name if org else "").strip()
        return name or "VOXBULK"
    except Exception:
        return "VOXBULK"


def _resolve_scheduling_wa_template(db: Session, order: ServiceOrder) -> TelnyxWhatsappTemplate | None:
    config = _order_config(order)
    template_id = str(config.get("wa_scheduling_template_id") or "").strip()
    template_name = str(config.get("wa_scheduling_template_name") or "").strip()
    row = TelnyxWhatsappTemplateSyncService.resolve_for_send(
        db,
        template_id=template_id or None,
        template_name=template_name or None,
        sales_template_key="interview_scheduling_invite",
    )
    if row is not None:
        return row

    from app.services.platform_whatsapp_template_service import PlatformWhatsappTemplateService

    grouped = PlatformWhatsappTemplateService.list_for_dashboard(db, approved_only=True)
    booking = (grouped.get("grouped") or {}).get("booking") or []
    for item in booking:
        name = str(item.get("name") or "").strip().lower()
        if any(x in name for x in ("schedul", "calendly", "cronofy", "follow", "next")):
            tid = str(item.get("template_id") or "").strip()
            if tid:
                resolved = TelnyxWhatsappTemplateSyncService.resolve_for_send(db, template_id=tid)
                if resolved is not None:
                    return resolved
    if booking:
        first_id = str(booking[0].get("template_id") or "").strip()
        if first_id:
            return TelnyxWhatsappTemplateSyncService.resolve_for_send(db, template_id=first_id)
    return None


def _build_scheduling_wa_components(
    row: TelnyxWhatsappTemplate,
    *,
    candidate_name: str,
    role: str,
    scheduling_url: str,
) -> list[dict[str, Any]]:
    built: list[dict[str, Any]] | None = None
    try:
        built = TelnyxWhatsappTemplateSyncService.build_components_for_row(
            row,
            variables={
                "first_name": _first_name(candidate_name),
                "candidate_name": candidate_name or "Candidate",
                "role": role,
                "scheduling_url": scheduling_url,
                "offer_line": role,
                "offer_summary": scheduling_url,
            },
        )
    except Exception:
        built = None
    if built:
        return [c for c in built if str(c.get("type") or "").lower() != "button"]
    return [
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": _first_name(candidate_name)[:1024]},
                {"type": "text", "text": str(role or "interview")[:1024]},
                {"type": "text", "text": str(scheduling_url)[:1024]},
            ],
        }
    ]


class InterviewSchedulingService:
    @staticmethod
    def save_shortlist(db: Session, order: ServiceOrder, recipient_ids: list[str]) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Shortlist is only for interview orders")
        ids = [str(x).strip() for x in recipient_ids if str(x).strip()][:10]
        recipients = ServiceOrderService.get_recipients(db, order.id)
        valid = {r.id for r in recipients}
        ids = [rid for rid in ids if rid in valid]
        config = _order_config(order)
        config["top_10_recipient_ids"] = ids
        config["shortlist_saved_at"] = datetime.utcnow().isoformat()
        order.config_json = json.dumps(config, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        from app.services.hubspot_connection_service import sync_shortlist_to_hubspot

        hubspot_result = sync_shortlist_to_hubspot(db, order.org_id, order=order, recipient_ids=ids)
        return {"ok": True, "recipient_ids": ids, "count": len(ids), "hubspot": hubspot_result}

    @staticmethod
    def send_scheduling_links(
        db: Session,
        order: ServiceOrder,
        *,
        recipient_ids: list[str] | None = None,
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Scheduling send is only for interview orders")

        org_status = scheduling_status(db, order.org_id)
        if not org_status.get("connected"):
            raise ValueError(
                "Connect Calendly or Cronofy in Settings → System before sending human interview links"
            )

        config = _order_config(order)
        ids = recipient_ids or list(config.get("top_10_recipient_ids") or [])
        ids = [str(x).strip() for x in ids if str(x).strip()][:10]
        if not ids:
            raise ValueError("Select at least one candidate")

        channel_list = [str(c).strip().lower() for c in (channels or config.get("scheduling_channels") or ["email"]) if str(c).strip()]
        if not channel_list:
            channel_list = ["email"]

        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = _org_name(db, order)
        template_row = _resolve_scheduling_wa_template(db, order)

        from app.services.hubspot_connection_service import hubspot_status, sync_recipient_to_hubspot

        hubspot = hubspot_status(db, order.org_id)
        hubspot_sync_enabled = bool(hubspot.get("connected") and hubspot.get("auto_sync_scheduling_send"))

        recipients = ServiceOrderService.get_recipients(db, order.id)
        id_filter = {str(x).strip() for x in ids if str(x).strip()}
        recipients = [r for r in recipients if r.id in id_filter]

        wa_sent = 0
        email_sent = 0
        hubspot_synced = 0
        errors: list[str] = []

        for recipient in recipients:
            if not recipient.phone and "whatsapp" in channel_list:
                if recipient.email and "email" in channel_list:
                    pass
                elif not recipient.email:
                    errors.append(f"{recipient.name or recipient.id}: no phone or email")
                    continue

            try:
                sched_url = create_scheduling_link(
                    db,
                    order.org_id,
                    candidate_name=recipient.name or "Candidate",
                    candidate_email=str(recipient.email or "").strip(),
                )
            except ValueError as exc:
                errors.append(f"{recipient.name or recipient.id}: {exc}")
                continue

            first = _first_name(recipient.name)

            if "whatsapp" in channel_list and recipient.phone:
                fallback_body = (
                    f"Hi {first}, thank you for completing your screening call for {role} at {company_name}. "
                    f"Please book your next interview here: {sched_url}"
                )
                if template_row is None:
                    errors.append(f"{recipient.name}: no WhatsApp scheduling template available")
                else:
                    components = _build_scheduling_wa_components(
                        template_row,
                        candidate_name=recipient.name or "Candidate",
                        role=role,
                        scheduling_url=sched_url,
                    )
                    result = TelnyxMessagingService.send_whatsapp(
                        db,
                        to_number=str(recipient.phone),
                        body=fallback_body,
                        template_name=template_row.name,
                        template_id=send_template_id_for_row(template_row),
                        template_language=template_row.language or "en_US",
                        template_components=components,
                        org_id=order.org_id,
                    )
                    if result.ok:
                        wa_sent += 1
                        TelnyxMessagingService.log_outbound(
                            db,
                            org_id=order.org_id,
                            to_number=str(recipient.phone),
                            from_number=None,
                            body=fallback_body,
                            result=result,
                        )
                    else:
                        errors.append(f"{recipient.name} WA: {result.detail or result.status}")

            if "email" in channel_list and recipient.email:
                body = (
                    f"Hi {recipient.name or 'there'},\n\n"
                    f"Thank you for completing your screening call for {role}.\n\n"
                    f"Please book your next interview here:\n{sched_url}\n\n"
                    "Best regards"
                )
                try:
                    from app.services.career_email_service import CareerEmailService

                    sent_ok, err = CareerEmailService.send_templated_optional(
                        db,
                        template_key="interview_scheduling_invite",
                        to_email=str(recipient.email).strip(),
                        variables={
                            "candidate_name": recipient.name or "there",
                            "role": role,
                            "scheduling_url": sched_url,
                        },
                    )
                    if sent_ok:
                        email_sent += 1
                    elif err:
                        errors.append(f"Email {recipient.email}: {err}")
                except Exception as exc:
                    errors.append(f"Email {recipient.email}: {exc}")

            merged = _recipient_result(recipient)
            merged.update(
                {
                    "scheduling_url": sched_url,
                    "scheduling_url_sent_at": _now().isoformat(),
                    "scheduling_sent_at": _now().isoformat(),
                    "human_scheduling_provider": org_status.get("provider"),
                }
            )
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)

            if hubspot_sync_enabled:
                try:
                    sync_recipient_to_hubspot(
                        db,
                        order.org_id,
                        order=order,
                        recipient=recipient,
                        scheduling_url=sched_url,
                    )
                    hubspot_synced += 1
                except ValueError as exc:
                    errors.append(f"HubSpot {recipient.name or recipient.id}: {exc}")

        config = _order_config(order)
        config["scheduling_sent_at"] = _now().isoformat()
        config["scheduling_channels"] = channel_list
        if template_row is not None:
            config["wa_scheduling_template_id"] = send_template_id_for_row(template_row)
            config["wa_scheduling_template_name"] = template_row.name
        order.config_json = json.dumps(config, ensure_ascii=False)
        order.updated_at = _now()
        db.add(order)
        db.commit()

        return {
            "ok": True,
            "sent": wa_sent + email_sent,
            "whatsapp_sent": wa_sent,
            "email_sent": email_sent,
            "hubspot_synced": hubspot_synced,
            "errors": errors,
            "provider": org_status.get("provider"),
        }
