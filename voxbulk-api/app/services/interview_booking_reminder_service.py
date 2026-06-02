"""Send interview reminders ~30 minutes before booked AI call slots."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.services.career_email_service import CareerEmailService
from app.services.interview_booking_service import (
    InterviewBookingService,
    _first_name,
    _format_slot_date,
    _format_slot_time,
    _recipient_outreach_email,
    _recipient_result,
    interview_slot_minutes,
)
from app.services.telnyx_messaging_service import TelnyxMessagingService

logger = logging.getLogger(__name__)

REMINDER_MINUTES = 30
REMINDER_WINDOW_MINUTES = 2


def _order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        data = json.loads(order.config_json or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class InterviewBookingReminderService:
    @staticmethod
    def process_due_reminders(db: Session, *, limit: int = 50) -> dict[str, int]:
        """
        Runs on the interview call scheduler (~every 30s). Sends email + optional WhatsApp
        when booked_start_at is about 30 minutes from now (±2 min).
        """
        now = datetime.utcnow()
        window_start = now + timedelta(minutes=REMINDER_MINUTES - REMINDER_WINDOW_MINUTES)
        window_end = now + timedelta(minutes=REMINDER_MINUTES + REMINDER_WINDOW_MINUTES)

        rows = list(
            db.execute(
                select(InterviewBookingToken, ServiceOrderRecipient, ServiceOrder)
                .join(ServiceOrderRecipient, ServiceOrderRecipient.id == InterviewBookingToken.recipient_id)
                .join(ServiceOrder, ServiceOrder.id == InterviewBookingToken.order_id)
                .where(
                    ServiceOrder.service_code == "interview",
                    ServiceOrder.payment_status == "approved",
                    ServiceOrder.status.in_(("scheduled", "paid", "running")),
                    InterviewBookingToken.booked_start_at.is_not(None),
                    InterviewBookingToken.booked_start_at >= window_start,
                    InterviewBookingToken.booked_start_at <= window_end,
                )
                .order_by(InterviewBookingToken.booked_start_at.asc())
                .limit(max(1, min(limit, 200)))
            ).all()
        )

        sent_email = 0
        sent_wa = 0
        skipped = 0
        errors = 0

        for token_row, recipient, order in rows:
            parsed = _recipient_result(recipient)
            if parsed.get("reminder_sent_at"):
                skipped += 1
                continue
            status = str(recipient.status or "pending").lower()
            if status in {"completed", "done", "calling", "in_progress", "ringing"}:
                skipped += 1
                continue
            try:
                ok = InterviewBookingReminderService._send_reminder(db, order, recipient, token_row)
                if ok.get("email"):
                    sent_email += 1
                if ok.get("whatsapp"):
                    sent_wa += 1
                if not ok.get("email") and not ok.get("whatsapp"):
                    errors += 1
            except Exception:
                errors += 1
                logger.exception(
                    "interview_reminder_failed",
                    extra={"order_id": order.id, "recipient_id": recipient.id},
                )

        return {
            "candidates_checked": len(rows),
            "email_sent": sent_email,
            "whatsapp_sent": sent_wa,
            "skipped": skipped,
            "errors": errors,
        }

    @staticmethod
    def _send_reminder(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        token_row: InterviewBookingToken,
    ) -> dict[str, bool]:
        slot_start = token_row.booked_start_at
        if slot_start is None:
            return {"email": False, "whatsapp": False}

        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        first = _first_name(recipient.name)
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)

        calendar_vars: dict[str, str] = {"calendar_links_html": ""}
        token = str(token_row.token or "").strip()
        if token:
            try:
                from app.services.interview_calendar_service import build_interview_calendar_variables

                calendar_vars = build_interview_calendar_variables(
                    token=token,
                    slot_start=slot_start,
                    slot_end=token_row.booked_end_at or (slot_start + timedelta(minutes=interview_slot_minutes())),
                    role=role,
                    company_name=company_name,
                )
            except Exception as exc:
                logger.warning(
                    "reminder_calendar_vars_failed",
                    extra={"order_id": order.id, "recipient_id": recipient.id, "error": str(exc)},
                )

        variables = {
            "candidate_name": recipient.name or "there",
            "role": role,
            "company_name": company_name,
            "interview_date": date_line,
            "interview_time": time_line,
            **calendar_vars,
        }

        email_ok = False
        wa_ok = False
        err_notes: list[str] = []

        outreach_email = _recipient_outreach_email(recipient)
        if outreach_email:
            if outreach_email != str(recipient.email or "").strip().lower():
                recipient.email = outreach_email
                db.add(recipient)
                db.commit()
                db.refresh(recipient)
            try:
                email_ok, err, ch = CareerEmailService.send_booking_reminder_email(
                    db,
                    to_email=outreach_email,
                    variables=variables,
                )
                if not email_ok and err:
                    err_notes.append(f"email:{err}")
                elif ch == "plain_fallback":
                    err_notes.append("email:plain_fallback_used")
            except Exception as exc:
                err_notes.append(f"email:{exc}")
        else:
            err_notes.append("email:no_recipient_email")

        if recipient.phone:
            body = (
                f"Hi {first}, reminder: your {role} interview with {company_name} "
                f"is in about 30 minutes ({date_line} at {time_line}). We will call you on this number."
            )
            try:
                from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

                phone_check = TelnyxPhoneAllowlistService.validate_phone_db(db, str(recipient.phone))
                if not phone_check.get("allowed"):
                    err_notes.append(f"wa:{phone_check.get('reason') or 'phone_not_allowed'}")
                else:
                    result = TelnyxMessagingService.send_whatsapp(
                        db,
                        to_number=str(recipient.phone),
                        body=body,
                        org_id=order.org_id,
                    )
                    if result.ok:
                        wa_ok = True
                        TelnyxMessagingService.log_outbound(
                            db,
                            org_id=order.org_id,
                            to_number=str(recipient.phone),
                            from_number=None,
                            body=body,
                            result=result,
                        )
                    else:
                        err_notes.append(f"wa:{result.detail or result.status}")
            except Exception as exc:
                err_notes.append(f"wa:{exc}")

        merged = _recipient_result(recipient)
        merged["reminder_sent_at"] = datetime.utcnow().isoformat()
        if err_notes:
            merged["reminder_errors"] = err_notes
        if email_ok:
            merged["reminder_email_sent_at"] = merged["reminder_sent_at"]
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        return {"email": email_ok, "whatsapp": wa_ok}
