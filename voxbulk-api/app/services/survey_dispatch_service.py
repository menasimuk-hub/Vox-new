from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import ServiceOrderService
from app.services.survey_builder_runtime_service import has_builder_runtime
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.services.whatsapp_provider_service import whatsapp_messaging_ready


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

        from app.services.survey_wa_org_context_service import resolve_survey_organisation_name

        org_name = resolve_survey_organisation_name(db, org_id=str(order.org_id), config=config)
        organiser = str(config.get("survey_organiser_name") or config.get("organiser_name") or org_name).strip()
        intro_template = _survey_intro_text(config)
        prefer_whatsapp = _uses_whatsapp(config)
        messaging_ready = whatsapp_messaging_ready(db)

        recipients = ServiceOrderService.get_recipients(db, order.id)
        sent = failed = skipped = 0
        rows: list[dict[str, Any]] = []
        settings = get_settings()
        chunk_size = max(1, int(getattr(settings, "wa_dispatch_chunk_size", 25) or 25))
        chunk_pause = max(0.0, float(getattr(settings, "wa_dispatch_chunk_pause_seconds", 1.0) or 1.0))

        for idx, recipient in enumerate(recipients):
            if prefer_whatsapp and idx > 0 and idx % chunk_size == 0 and chunk_pause > 0:
                time.sleep(chunk_pause)
            row_result = SurveyDispatchService._dispatch_one(
                db,
                order=order,
                recipient=recipient,
                config=config,
                intro_template=intro_template,
                org_name=org_name,
                organiser=organiser,
                prefer_whatsapp=prefer_whatsapp,
                messaging_ready=messaging_ready,
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
            "provider": messaging_ready.get("provider") or "none",
            "prefer_whatsapp": prefer_whatsapp,
            "messaging_ready": messaging_ready,
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
        config: dict[str, Any],
        intro_template: str,
        org_name: str,
        organiser: str,
        prefer_whatsapp: bool,
        messaging_ready: dict[str, Any],
    ) -> dict[str, Any]:
        first = _first_name(recipient.name)

        if not recipient.phone:
            recipient.status = "skipped"
            recipient.result_json = json.dumps({"error": "missing_phone"}, ensure_ascii=False)
            db.add(recipient)
            db.commit()
            return {"recipient_id": recipient.id, "name": recipient.name, "status": "skipped", "error": "missing_phone"}

        from app.services.uk_compliance_opt_out import should_block_outbound_phone
        from app.services.uk_compliance_audit_service import UkComplianceAuditService
        from app.services.uk_compliance_service import UkComplianceService

        compliance_errors = UkComplianceService.validate_order_for_send(db, order)
        if compliance_errors:
            recipient.status = "skipped"
            recipient.result_json = json.dumps(
                {"error": "compliance_blocked", "detail": compliance_errors},
                ensure_ascii=False,
            )
            db.add(recipient)
            db.commit()
            return {
                "recipient_id": recipient.id,
                "name": recipient.name,
                "status": "skipped",
                "error": "compliance_blocked",
            }

        skip_reason = should_block_outbound_phone(db, org_id=order.org_id, phone_e164=recipient.phone)
        if skip_reason:
            recipient.status = "skipped"
            recipient.result_json = json.dumps({"error": skip_reason}, ensure_ascii=False)
            db.add(recipient)
            db.commit()
            UkComplianceAuditService.record(
                db,
                event_type="send.blocked",
                org_id=order.org_id,
                order_id=order.id,
                detail={"reason": skip_reason, "recipient_id": recipient.id, "workflow": "survey"},
            )
            return {
                "recipient_id": recipient.id,
                "name": recipient.name,
                "status": "skipped",
                "error": skip_reason,
            }

        if not messaging_ready.get("enabled"):
            recipient.status = "pending_telnyx"
            recipient.result_json = json.dumps(
                {
                    "error": "whatsapp_not_configured",
                    "detail": "Configure Meta WhatsApp (or Telnyx for SMS) in admin Integrations.",
                },
                ensure_ascii=False,
            )
            db.add(recipient)
            db.commit()
            return {
                "recipient_id": recipient.id,
                "name": recipient.name,
                "status": "skipped",
                "error": "whatsapp_not_configured",
            }

        can_send = messaging_ready.get("whatsapp") if prefer_whatsapp else messaging_ready.get("sms")
        if not can_send:
            recipient.status = "pending_number"
            recipient.result_json = json.dumps(
                {
                    "error": "sender_not_approved",
                    "detail": "WhatsApp sender is not ready — check Meta WhatsApp credentials in admin Integrations.",
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

        if prefer_whatsapp and (
            has_builder_runtime(config)
            or config.get("wa_template_id")
            or config.get("welcome_template_id")
        ):
            from app.services.survey_session_service import SurveySessionService
            from app.utils.ofcom import platform_whatsapp_allowed

            active_session = SurveySessionService.get_active_by_recipient(db, recipient.id)
            if active_session is None:
                wa_ok, wa_reason = platform_whatsapp_allowed(db, str(recipient.phone or ""))
                if not wa_ok:
                    recipient.status = "pending"
                    recipient.result_json = json.dumps(
                        {
                            "error": "outside_wa_survey_hours",
                            "detail": wa_reason,
                            "deferred_at": datetime.utcnow().isoformat(),
                        },
                        ensure_ascii=False,
                    )
                    db.add(recipient)
                    db.commit()
                    UkComplianceAuditService.record(
                        db,
                        event_type="send.blocked",
                        org_id=order.org_id,
                        order_id=order.id,
                        detail={
                            "reason": wa_reason,
                            "recipient_id": recipient.id,
                            "workflow": "survey_wa_start",
                        },
                    )
                    return {
                        "recipient_id": recipient.id,
                        "name": recipient.name,
                        "status": "pending",
                        "error": "outside_wa_survey_hours",
                    }

            from app.services.survey_whatsapp_conversation_service import send_survey_opening

            sent = send_survey_opening(
                db,
                order=order,
                recipient=recipient,
                config=config,
            )
            db.refresh(recipient)
            if sent:
                return {
                    "recipient_id": recipient.id,
                    "name": recipient.name,
                    "phone": recipient.phone,
                    "status": "sent",
                    "channel": "whatsapp",
                    "detail": "builder_runtime_welcome",
                    "awaiting_start": True,
                }
            detail = ""
            try:
                fail_payload = json.loads(recipient.result_json or "{}")
                detail = str(fail_payload.get("error") or fail_payload.get("detail") or "")
            except Exception:
                pass
            return {
                "recipient_id": recipient.id,
                "name": recipient.name,
                "phone": recipient.phone,
                "status": "failed",
                "channel": "whatsapp",
                "detail": detail or "welcome_send_failed",
            }

        body = _personalize(intro_template, first_name=first, org_name=org_name, organiser=organiser)
        footer = UkComplianceService.privacy_footer_text(UkComplianceService.merged_compliance(db, order))
        if footer and footer not in body:
            body = f"{body}\n\n{footer}"

        wa_template_id = config.get("wa_template_id") if isinstance(config, dict) else None
        template_row = None
        template_components = None
        if prefer_whatsapp and wa_template_id:
            try:
                from app.services.survey_whatsapp_template_service import (
                    SurveyWhatsappTemplateService,
                    resolve_sendable_template_row,
                    template_row_is_sendable_on_meta,
                )
                from app.services.telnyx_whatsapp_template_sync_service import (
                    TelnyxWhatsappTemplateSyncService,
                )
                from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

                raw_row = SurveyWhatsappTemplateService.get_template(db, int(wa_template_id))
                template_row = resolve_sendable_template_row(db, raw_row) if raw_row is not None else None
                if template_row is not None and template_row_is_sendable_on_meta(template_row):
                    template_components = TelnyxWhatsappTemplateSyncService.build_components_for_row(
                        template_row,
                        variables={"first_name": first, "clinic_name": org_name, "organisation_name": org_name},
                        db=db,
                    )
                elif raw_row is not None:
                    from app.services.survey_whatsapp_template_service import template_row_needs_meta_approval

                    if template_row_needs_meta_approval(raw_row):
                        logger.warning(
                            "legacy_dispatch_skip_plaintext_wa_template_not_sendable",
                            extra={"order_id": str(order.id), "wa_template_id": wa_template_id},
                        )
                        return {"ok": False, "error": "WhatsApp template is not approved or is disabled."}
            except Exception:
                template_row = None
                template_components = None

        if (
            prefer_whatsapp
            and template_row is not None
            and template_components is not None
            and messaging_ready.get("whatsapp")
        ):
            from app.services.wa_template_profile_push_service import WaTemplateProfilePushService

            send_template_id = WaTemplateProfilePushService.send_template_id_for_active_profile(
                db,
                template_row,
                org_id=order.org_id,
                service_code="survey",
            )
            if not send_template_id:
                return {"ok": False, "error": "WhatsApp template is not available on the active connection profile."}

            result = TelnyxMessagingService.send_whatsapp(
                db,
                org_id=order.org_id,
                to_number=recipient.phone,
                body=body,
                template_id=send_template_id,
                template_name=template_row.name,
                template_language=template_row.language,
                template_components=template_components,
                meter_usage=False,
                service_code="survey",
            )
        elif prefer_whatsapp:
            result = TelnyxMessagingService.send_whatsapp(
                db,
                org_id=order.org_id,
                to_number=recipient.phone,
                body=body,
                meter_usage=False,
                service_code="survey",
            )
        else:
            result = TelnyxMessagingService.send_sms(
                db,
                to_number=recipient.phone,
                body=body,
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
            if template_row is not None:
                log_payload["wa_template_id"] = template_row.id
                log_payload["wa_template_name"] = template_row.name
            if prefer_whatsapp and template_row is not None:
                from app.services.survey_whatsapp_conversation_service import _whatsapp_flow

                wa_flow = _whatsapp_flow(config)
                wa_questions = wa_flow.get("questions") or []
                total = len(wa_questions) if isinstance(wa_questions, list) else 0
                log_payload["wa_conversation"] = {
                    "step": 0,
                    "total": total,
                    "answers": [],
                    "intro_sent_at": datetime.utcnow().isoformat(),
                }
            recipient.result_json = json.dumps(log_payload, ensure_ascii=False)
            db.add(recipient)
            db.commit()
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
