"""Send real Calendly scheduling links to shortlisted interview candidates."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.platform_catalog_service import ServiceOrderService
from app.services.scheduling_connection_service import create_scheduling_link, scheduling_status
from app.services.smtp_mailer_service import SmtpMailerService
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
        return {"ok": True, "recipient_ids": ids, "count": len(ids)}

    @staticmethod
    def send_scheduling_links(
        db: Session,
        order: ServiceOrder,
        *,
        recipient_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Scheduling send is only for interview orders")

        status = scheduling_status(db, order.org_id)
        if not status.get("connected"):
            raise ValueError("Connect Calendly or Cronofy in System settings before sending scheduling links")

        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        ids = recipient_ids or list(config.get("top_10_recipient_ids") or [])
        ids = [str(x).strip() for x in ids if str(x).strip()][:10]
        if not ids:
            raise ValueError("Select at least one candidate")

        sent = 0
        errors: list[str] = []
        for rid in ids:
            recipient = db.get(ServiceOrderRecipient, rid)
            if recipient is None or recipient.order_id != order.id:
                continue
            try:
                url = create_scheduling_link(
                    db,
                    order.org_id,
                    candidate_name=str(recipient.name or "Candidate"),
                    candidate_email=str(recipient.email or ""),
                )
            except Exception as exc:
                errors.append(f"{recipient.name}: {exc}")
                continue

            merged = _recipient_result(recipient)
            merged.update(
                {
                    "scheduling_url": url,
                    "scheduling_url_sent_at": datetime.utcnow().isoformat(),
                    "scheduling_provider": status.get("provider"),
                }
            )
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)

            if recipient.email:
                body = (
                    f"Hi {recipient.name or 'there'},\n\n"
                    f"Thank you for completing your screening call for {role}.\n\n"
                    f"Please book your next interview here:\n{url}\n\n"
                    "Best regards"
                )
                try:
                    sent_ok, err = TransactionalEmailService.send_templated_optional(
                        db,
                        template_key="interview_scheduling_invite",
                        to_addr=str(recipient.email).strip(),
                        variables={
                            "candidate_name": recipient.name or "there",
                            "role": role,
                            "scheduling_url": url,
                        },
                    )
                    if not sent_ok:
                        SmtpMailerService.send_plain(
                            db,
                            to_addrs=[str(recipient.email).strip()],
                            subject=f"Next step — {role}",
                            body_text=body,
                        )
                except Exception as exc:
                    errors.append(f"Email {recipient.email}: {exc}")
                    continue
            sent += 1

        config["scheduling_sent_at"] = datetime.utcnow().isoformat()
        order.config_json = json.dumps(config, ensure_ascii=False)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()

        return {"ok": True, "sent": sent, "errors": errors}
