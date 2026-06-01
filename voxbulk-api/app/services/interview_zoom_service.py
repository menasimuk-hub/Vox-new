"""Zoom meeting creation for interview orders with delivery=zoom via Telnyx."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import ServiceOrderService
from app.services.transactional_email_service import TransactionalEmailService
from app.services.telnyx_voice_service import TelnyxCallerIdService


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


class InterviewZoomService:
    @staticmethod
    def create_zoom_meeting_via_telnyx(db: Session, topic: str) -> dict[str, Any]:
        """Create Zoom meeting through Telnyx integration."""
        try:
            # Get Telnyx zoom connection from provider settings
            from app.services.provider_settings import ProviderSettingsService
            
            config, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="zoom")
            if not enabled or not config:
                raise ValueError("Zoom is not configured in Telnyx")
            
            # Use Telnyx API to create meeting
            import httpx
            from app.core.config import get_settings
            
            settings = get_settings()
            telnyx_api_key = config.get("telnyx_api_key") or settings.telnyx_api_key
            
            if not telnyx_api_key:
                raise ValueError("Telnyx API key not found")
            
            # Call Telnyx to create Zoom meeting
            headers = {"Authorization": f"Bearer {telnyx_api_key}"}
            payload = {"topic": topic}
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    "https://api.telnyx.com/v2/zoom/meetings",
                    json=payload,
                    headers=headers
                )
                
                if response.status_code != 201:
                    raise ValueError(f"Telnyx Zoom meeting creation failed: {response.text[:300]}")
                
                data = response.json().get("data", {})
                return {
                    "id": data.get("id"),
                    "join_url": data.get("join_url"),
                    "topic": data.get("topic"),
                }
        except Exception as exc:
            raise ValueError(f"Failed to create Zoom meeting via Telnyx: {str(exc)}")

    @staticmethod
    def start_campaign(db: Session, order: ServiceOrder) -> None:
        if order.service_code != "interview":
            raise ValueError("Not an interview order")
        config = _order_config(order)
        if str(config.get("delivery") or "").strip().lower() != "zoom":
            raise ValueError("Interview order is not configured for Zoom")

        role = str(config.get("role") or order.title or "Interview").strip()
        recipients = ServiceOrderService.get_recipients(db, order.id)
        now = datetime.utcnow()
        order.status = "running"
        order.started_at = order.started_at or now
        order.updated_at = now
        db.add(order)
        db.commit()

        for recipient in recipients:
            topic = f"{role} — {recipient.name or 'Candidate'}"
            try:
                meeting = InterviewZoomService.create_zoom_meeting_via_telnyx(db, topic=topic)
            except Exception as exc:
                recipient.status = "failed"
                merged = _recipient_result(recipient)
                merged.update({"channel": "zoom", "error": str(exc)[:500]})
                recipient.result_json = json.dumps(merged, ensure_ascii=False)
                db.add(recipient)
                continue

            join_url = str(meeting.get("join_url") or "").strip()
            recipient.status = "completed" if join_url else "failed"
            merged = _recipient_result(recipient)
            merged.update(
                {
                    "channel": "zoom",
                    "zoom_meeting_id": meeting.get("id"),
                    "join_url": join_url,
                    "scheduling_url": join_url,
                    "delivered_at": now.isoformat(),
                }
            )
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)

            if join_url and recipient.email:
                try:
                    TransactionalEmailService.send_templated_optional(
                        db,
                        template_key="interview_zoom_invite",
                        to_addr=str(recipient.email).strip(),
                        variables={
                            "candidate_name": recipient.name or "there",
                            "role": role,
                            "join_url": join_url,
                        },
                    )
                except Exception:
                    pass

        order.status = "completed"
        order.completed_at = datetime.utcnow()
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
