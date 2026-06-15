"""Create diagnostic support tickets from assistant error report tokens."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.schemas.assistant import AssistantReportSupportOut
from app.services.assistant.rate_limit import check_assistant_rate_limit
from app.services.assistant.support_report import (
    get_consumed_ticket_ref,
    mark_report_token_consumed,
    verify_support_report_token,
)
from app.services.assistant.ticket_diagnostic import format_assistant_diagnostic_plain_text
from app.services.support_ticket_service import SupportTicketService


def create_diagnostic_support_ticket(
    db: Session,
    *,
    org_id: str,
    user_id: str,
    support_report_token: str,
) -> AssistantReportSupportOut:
    rate = check_assistant_rate_limit(org_id=org_id, user_id=user_id, endpoint="report-support")
    if not rate.allowed:
        return AssistantReportSupportOut(
            ok=False,
            message="Please wait a moment before sending another report.",
        )

    token_id = support_report_token.split(":", 1)[0] if ":" in support_report_token else ""
    if token_id:
        existing = get_consumed_ticket_ref(token_id)
        if existing:
            return AssistantReportSupportOut(
                ok=True,
                message=f"We already received this report as ticket {existing}.",
                ticket_ref=existing,
                already_reported=True,
            )

    body = verify_support_report_token(support_report_token, org_id=org_id, user_id=user_id)
    if body is None:
        return AssistantReportSupportOut(ok=False, message="This report link has expired or is invalid.")

    payload = body.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}
    subject = f"Assistant error: {payload.get('intent') or 'unknown'}"
    diagnostic = {
        "user_message": payload.get("user_message"),
        "intent": payload.get("intent"),
        "endpoint_label": payload.get("endpoint_label"),
        "error_code": payload.get("error_code"),
        "error_detail": payload.get("error_detail"),
        "org_id": org_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "recent_history": payload.get("history") if isinstance(payload.get("history"), list) else [],
    }
    customer_message = (
        "I ran into a problem while using the dashboard assistant. "
        "Please investigate the issue and help me continue."
    )
    staff_note = format_assistant_diagnostic_plain_text(diagnostic)

    ticket = SupportTicketService.create_ticket(
        db,
        org_id=org_id,
        user_id=user_id,
        category="technical",
        subject=subject[:200],
        message=customer_message[:8000],
        staff_note=staff_note[:8000] if staff_note else None,
    )
    ticket_ref = str(getattr(ticket, "public_ref", None) or ticket.id)
    if token_id:
        mark_report_token_consumed(token_id, ticket_ref=ticket_ref)

    return AssistantReportSupportOut(
        ok=True,
        message=f"Support ticket {ticket_ref} has been created. Our team will investigate.",
        ticket_ref=ticket_ref,
    )
