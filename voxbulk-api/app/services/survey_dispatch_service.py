from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import ServiceOrderService
from app.services.telnyx_messaging_service import TelnyxMessagingService


def _first_name(full_name: str) -> str:
    parts = str(full_name or "").strip().split()
    return parts[0] if parts else "there"


def _personalize(text: str, *, first_name: str, org_name: str, organiser: str) -> str:
    out = str(text or "")
    mapping = {
        "first_name": first_name,
        "clinic_name": org_name,
        "organisation_name": org_name,
        "business_name": org_name,
        "assistant_name": organiser,
        "organiser_name": organiser,
        "survey_organiser": organiser,
    }
    for key, value in mapping.items():
        out = out.replace(f"{{{key}}}", value)
    out = re.sub(r"\[Your Name\]", organiser, out, flags=re.I)
    out = re.sub(r"\[Clinic/Business Name\]", org_name, out, flags=re.I)
    out = re.sub(r"\bVOXBULK\b", org_name, out, flags=re.I)
    return out.strip()


def _survey_intro_text(config: dict[str, Any]) -> str:
    wa = config.get("whatsapp_flow") if isinstance(config.get("whatsapp_flow"), dict) else {}
    intro = str(wa.get("intro") or "").strip()
    if intro:
        return intro
    script = str(config.get("approved_script") or "")
    m = re.search(r"INTRO\s*\r?\n([\s\S]*?)(?=\r?\n\s*QUESTIONS|\r?\n\s*CLOSING|$)", script, re.I)
    if m:
        return m.group(1).strip()
    return "Hi {first_name}, please reply to our short survey from {clinic_name}."


def _uses_whatsapp(config: dict[str, Any]) -> bool:
    channels = config.get("channels") or []
    if isinstance(channels, list) and any(str(c).lower() == "whatsapp" for c in channels):
        return True
    method = str(config.get("contact_method") or "").lower()
    return "whatsapp" in method


class SurveyDispatchService:
    @staticmethod
    def dispatch_survey_order(db: Session, order: ServiceOrder) -> dict[str, Any]:
        if order.service_code != "survey":
            return {"skipped": True, "reason": "not_a_survey"}
        if order.status not in {"running", "scheduled"}:
            return {"skipped": True, "reason": f"status_{order.status}"}

        try:
            config = json.loads(order.config_json or "{}")
        except Exception:
            config = {}

        org_name = str(config.get("organisation_name") or config.get("clinic_name") or "Your business").strip()
        organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
        intro_template = _survey_intro_text(config)
        prefer_whatsapp = _uses_whatsapp(config)
        telnyx_ready = TelnyxMessagingService.is_configured(db)

        recipients = ServiceOrderService.get_recipients(db, order.id)
        sent = failed = skipped = 0
        rows: list[dict[str, Any]] = []

        for recipient in recipients:
            row_result = SurveyDispatchService._dispatch_one(
                db,
                order=order,
                recipient=recipient,
                intro_template=intro_template,
                org_name=org_name,
                organiser=organiser,
                prefer_whatsapp=prefer_whatsapp,
                telnyx_ready=telnyx_ready,
            )
            rows.append(row_result)
            if row_result["status"] == "sent":
                sent += 1
            elif row_result["status"] == "skipped":
                skipped += 1
            else:
                failed += 1

        report = {
            "dispatch_at": datetime.utcnow().isoformat(),
            "provider": "telnyx",
            "prefer_whatsapp": prefer_whatsapp,
            "telnyx": telnyx_ready,
            "intro_preview": _personalize(intro_template, first_name="Alex", org_name=org_name, organiser=organiser)[:280],
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
            "total": len(recipients),
            "recipients": rows,
            "note": (
                "WhatsApp attempted first; SMS used as fallback when WhatsApp is not approved yet."
                if prefer_whatsapp
                else "SMS dispatch (WhatsApp not selected for this order)."
            ),
        }
        order.report_json = json.dumps(report, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return report

    @staticmethod
    def _dispatch_one(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        intro_template: str,
        org_name: str,
        organiser: str,
        prefer_whatsapp: bool,
        telnyx_ready: dict[str, bool],
    ) -> dict[str, Any]:
        first = _first_name(recipient.name)
        body = _personalize(intro_template, first_name=first, org_name=org_name, organiser=organiser)
        if not recipient.phone:
            recipient.status = "skipped"
            recipient.result_json = json.dumps({"error": "missing_phone"}, ensure_ascii=False)
            db.add(recipient)
            db.commit()
            return {"recipient_id": recipient.id, "name": recipient.name, "status": "skipped", "error": "missing_phone"}

        if not telnyx_ready.get("enabled"):
            recipient.status = "pending_telnyx"
            recipient.result_json = json.dumps(
                {"error": "telnyx_not_configured", "detail": "Configure Telnyx in admin Integrations."},
                ensure_ascii=False,
            )
            db.add(recipient)
            db.commit()
            return {
                "recipient_id": recipient.id,
                "name": recipient.name,
                "status": "skipped",
                "error": "telnyx_not_configured",
            }

        can_send = telnyx_ready.get("whatsapp") if prefer_whatsapp else telnyx_ready.get("sms")
        if not can_send:
            recipient.status = "pending_number"
            recipient.result_json = json.dumps(
                {
                    "error": "sender_not_approved",
                    "detail": "Waiting for Telnyx mobile/WhatsApp number approval.",
                },
                ensure_ascii=False,
            )
            db.add(recipient)
            db.commit()
            return {
                "recipient_id": recipient.id,
                "name": recipient.name,
                "status": "skipped",
                "error": "sender_not_approved",
            }

        result = TelnyxMessagingService.send_survey_message(
            db,
            org_id=order.org_id,
            to_number=recipient.phone,
            body=body,
            prefer_whatsapp=prefer_whatsapp,
        )

        log_payload = {
            "channel": result.channel,
            "external_id": result.external_id,
            "detail": result.detail,
            "body_preview": body[:200],
        }
        try:
            TelnyxMessagingService.log_outbound(
                db,
                org_id=order.org_id,
                to_number=recipient.phone,
                from_number=None,
                body=body,
                result=result,
            )
        except Exception:
            pass

        if result.ok:
            recipient.status = "sent"
            log_payload["status"] = result.status
        else:
            recipient.status = "failed"
            log_payload["status"] = "failed"
        recipient.result_json = json.dumps(log_payload, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        return {
            "recipient_id": recipient.id,
            "name": recipient.name,
            "phone": recipient.phone,
            "status": "sent" if result.ok else "failed",
            "channel": result.channel,
            "detail": result.detail,
        }
