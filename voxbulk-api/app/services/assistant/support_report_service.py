"""Create diagnostic support tickets from assistant error report tokens."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.schemas.assistant import AssistantReportSupportOut
from app.services.assistant.rate_limit import check_assistant_rate_limit
from app.services.assistant.support_report import (
    get_consumed_ticket_ref,
    mark_report_token_consumed,
    verify_support_report_token,
)
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
    subject = f"Assistant error: {payload.get('intent') or 'unknown'}"
    diagnostic = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    message = (
        f"Automated assistant diagnostic report\n"
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        f"Org: {org_id}\n"
        f"User: {user_id}\n\n"
        f"{diagnostic}"
    )

    ticket = SupportTicketService.create_ticket(
        db,
        org_id=org_id,
        user_id=user_id,
        category="technical",
        subject=subject[:200],
        message=message[:8000],
    )
    ticket_ref = str(getattr(ticket, "public_ref", None) or ticket.id)
    if token_id:
        mark_report_token_consumed(token_id, ticket_ref=ticket_ref)

    return AssistantReportSupportOut(
        ok=True,
        message=f"Support ticket {ticket_ref} has been created. Our team will investigate.",
        ticket_ref=ticket_ref,
    )
