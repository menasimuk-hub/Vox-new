"""Interview operations dashboard aggregation for the admin console."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.user import User
from app.services.interview_activity_service import InterviewActivityService
from app.services.interview_booking_service import campaign_invites_were_sent
from app.services.platform_catalog_service import ServiceOrderService


def _loads(raw: str | None) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _parse_dt(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None) if raw.tzinfo else raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _max_dt(*values: datetime | None) -> datetime | None:
    valid = [v for v in values if v is not None]
    return max(valid) if valid else None


def _channel_label(sent: int, failed: int, pending: int, total: int) -> str:
    if total <= 0:
        return "—"
    if failed and not sent:
        return f"{failed} failed"
    if failed:
        return f"{sent}/{total} sent · {failed} failed"
    if sent >= total:
        return f"{sent}/{total} sent"
    if sent:
        return f"{sent}/{total} sent · {pending} pending"
    if pending:
        return f"{pending} pending"
    return "Not started"


def _channel_state(sent: int, failed: int, pending: int, total: int, *, launched: bool) -> str:
    if total <= 0:
        return "none"
    if failed:
        return "failed"
    if sent >= total:
        return "complete"
    if sent or pending:
        return "partial" if launched else "pending"
    return "pending" if launched else "idle"


def _aggregate_recipients(
    order: ServiceOrder,
    recipients: list[ServiceOrderRecipient],
) -> dict[str, Any]:
    email_sent = email_failed = email_pending = 0
    wa_sent = wa_failed = wa_pending = 0
    call_active = call_done = call_failed = call_pending = 0
    attention_reasons: list[str] = []
    last_error: str | None = None
    last_event_at: datetime | None = None

    for recipient in recipients:
        parsed = _loads(recipient.result_json)
        activity = InterviewActivityService.activity_status(recipient, parsed=parsed, order=order)
        recipient_last = _max_dt(
            _parse_dt(getattr(recipient, "updated_at", None)),
            _parse_dt(recipient.created_at),
            _parse_dt(parsed.get("invite_email_sent_at")),
            _parse_dt(parsed.get("invite_wa_sent_at")),
            _parse_dt(parsed.get("call_started_at")),
            _parse_dt(parsed.get("call_completed_at")),
        )
        last_event_at = _max_dt(last_event_at, recipient_last)

        if parsed.get("invite_email_failed"):
            email_failed += 1
            last_error = str(parsed.get("invite_email_failed"))
            attention_reasons.append(f"Email failed for {recipient.name or recipient.email or recipient.id}")
        elif parsed.get("invite_email_ok") or parsed.get("invite_email_sent_at"):
            email_sent += 1
        elif str(recipient.email or "").strip():
            email_pending += 1

        if parsed.get("invite_wa_sent_at"):
            wa_sent += 1
        elif str(recipient.phone or "").strip():
            wa_pending += 1

        if activity == "calling":
            call_active += 1
        elif activity in {"interview_completed", "report_ready", "scheduling_sent"}:
            call_done += 1
        elif activity == "call_failed":
            call_failed += 1
            attention_reasons.append(f"Call failed for {recipient.name or recipient.phone or recipient.id}")
        else:
            call_pending += 1

        if activity == "pending" and not str(recipient.name or "").strip():
            attention_reasons.append(f"Recipient #{recipient.row_number} missing name")
        if not str(recipient.phone or "").strip():
            attention_reasons.append(f"Recipient #{recipient.row_number} missing phone")

        try:
            from app.services.interview_intake_service import compute_intake_errors

            intake_errors = compute_intake_errors(recipient)
            if intake_errors:
                attention_reasons.append(
                    f"Recipient #{recipient.row_number}: {', '.join(intake_errors[:2])}"
                )
        except Exception:
            pass

    total = len(recipients)
    return {
        "recipient_total": total,
        "email_sent": email_sent,
        "email_failed": email_failed,
        "email_pending": email_pending,
        "email_label": _channel_label(email_sent, email_failed, email_pending, total),
        "email_state": _channel_state(
            email_sent, email_failed, email_pending, total, launched=campaign_invites_were_sent(order)
        ),
        "whatsapp_sent": wa_sent,
        "whatsapp_failed": wa_failed,
        "whatsapp_pending": wa_pending,
        "whatsapp_label": _channel_label(wa_sent, wa_failed, wa_pending, total),
        "whatsapp_state": _channel_state(
            wa_sent, wa_failed, wa_pending, total, launched=campaign_invites_were_sent(order)
        ),
        "call_active": call_active,
        "call_done": call_done,
        "call_failed": call_failed,
        "call_pending": call_pending,
        "call_label": (
            f"{call_done}/{total} done"
            if call_done
            else (f"{call_active} active" if call_active else (f"{call_failed} failed" if call_failed else f"{call_pending} pending"))
        ),
        "call_state": (
            "failed"
            if call_failed and not call_done
            else ("active" if call_active else ("complete" if call_done and call_done >= total else "partial" if call_done else "pending"))
        ),
        "attention_reasons": attention_reasons,
        "last_error": last_error,
        "last_event_at": last_event_at.isoformat() if last_event_at else None,
    }


def _launch_status(order: ServiceOrder, config: dict[str, Any]) -> tuple[str, str]:
    dispatch = config.get("last_invite_dispatch")
    launched = campaign_invites_were_sent(order)
    if order.status in {"running", "paused"} and order.started_at:
        if isinstance(dispatch, dict) and dispatch.get("ok") is False:
            return "launch_failed", "Launch incomplete"
        if launched:
            return "launched", "Launched"
        return "running_no_invites", "Running · invites pending"
    if config.get("launch_requested_at") and not launched:
        if isinstance(dispatch, dict) and dispatch.get("ok") is False:
            return "launch_failed", "Launch failed"
        return "launch_pending", "Launch requested"
    if order.payment_status == "approved" and order.status in {"draft", "quoted", "scheduled"}:
        return "waiting", "Waiting to launch"
    if launched:
        return "invites_sent", "Invites sent"
    if order.status == "completed":
        return "completed", "Completed"
    if order.status == "cancelled":
        return "cancelled", "Cancelled"
    return "not_launched", "Not launched"


def _delivery_health(
    agg: dict[str, Any],
    *,
    needs_attention: bool,
    launch_code: str,
) -> str:
    if launch_code == "launch_failed" or agg.get("email_state") == "failed":
        return "failed"
    if needs_attention or launch_code in {"running_no_invites", "launch_pending"}:
        return "stuck"
    if agg.get("email_state") == "partial" or agg.get("call_state") == "partial":
        return "partial"
    if agg.get("email_state") == "complete" or agg.get("call_state") == "complete":
        return "healthy"
    return "partial" if launch_code == "launched" else "healthy"


def _needs_attention(
    order: ServiceOrder,
    agg: dict[str, Any],
    launch_code: str,
    config: dict[str, Any],
) -> tuple[bool, list[str]]:
    reasons = list(agg.get("attention_reasons") or [])
    dispatch = config.get("last_invite_dispatch")
    if launch_code == "launch_failed":
        errors = dispatch.get("errors") if isinstance(dispatch, dict) else None
        if isinstance(errors, list) and errors:
            reasons.append(str(errors[0]))
        else:
            reasons.append("Launch dispatch failed")
    if order.payment_status == "approved" and launch_code == "waiting" and order.status == "scheduled":
        reasons.append("Payment approved but not launched")
    if launch_code == "running_no_invites":
        reasons.append("Interview running but invites not confirmed")
    if agg.get("email_failed"):
        reasons.append(f"{agg['email_failed']} email delivery failure(s)")
    if agg.get("call_failed"):
        reasons.append(f"{agg['call_failed']} call failure(s)")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in reasons:
        key = str(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return bool(deduped), deduped[:8]


def order_operations_row(
    db: Session,
    order: ServiceOrder,
    recipients: list[ServiceOrderRecipient],
    *,
    org_name: str | None = None,
    owner_email: str | None = None,
) -> dict[str, Any]:
    config = _loads(order.config_json)
    agg = _aggregate_recipients(order, recipients)
    launch_code, launch_label = _launch_status(order, config)
    needs_flag, attention_reasons = _needs_attention(order, agg, launch_code, config)
    health = _delivery_health(agg, needs_attention=needs_flag, launch_code=launch_code)

    dispatch = config.get("last_invite_dispatch")
    if isinstance(dispatch, dict) and dispatch.get("errors") and not agg.get("last_error"):
        errors = dispatch.get("errors")
        if isinstance(errors, list) and errors:
            agg["last_error"] = str(errors[0])

    last_activity = _max_dt(
        _parse_dt(order.updated_at),
        _parse_dt(order.started_at),
        _parse_dt(agg.get("last_event_at")),
        _parse_dt(config.get("launch_requested_at")),
        _parse_dt(config.get("booking_invites_sent_at")),
    )

    search_bits = [
        order.id,
        order.title,
        order.reference_id,
        order.campaign_id,
        org_name or "",
        owner_email or "",
        config.get("role") or "",
    ]
    for recipient in recipients:
        search_bits.extend([recipient.name or "", recipient.phone or "", recipient.email or "", recipient.id])

    base = ServiceOrderService.order_to_dict(order, recipients=recipients)
    return {
        **{k: base[k] for k in (
            "id",
            "org_id",
            "title",
            "reference_id",
            "campaign_id",
            "status",
            "status_label",
            "payment_status",
            "payment_method",
            "recipient_count",
            "quote_total_gbp",
            "run_mode",
            "scheduled_start_at",
            "scheduled_end_at",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
            "is_live",
            "is_finished",
            "report",
        ) if k in base},
        "org_name": org_name,
        "owner_email": owner_email,
        "role_title": config.get("role") or order.title,
        "launch_status": launch_code,
        "launch_label": launch_label,
        "launch_requested_at": config.get("launch_requested_at"),
        "booking_invites_sent_at": config.get("booking_invites_sent_at"),
        "last_invite_dispatch": dispatch if isinstance(dispatch, dict) else None,
        "email_status": agg["email_state"],
        "email_label": agg["email_label"],
        "whatsapp_status": agg["whatsapp_state"],
        "whatsapp_label": agg["whatsapp_label"],
        "call_status": agg["call_state"],
        "call_label": agg["call_label"],
        "delivery_health": health,
        "needs_attention": needs_flag,
        "attention_reasons": attention_reasons,
        "last_error": agg.get("last_error"),
        "last_activity_at": last_activity.isoformat() if last_activity else None,
        "delivery": agg,
        "search_text": " ".join(x for x in search_bits if x).lower(),
    }


class InterviewOperationsService:
    @staticmethod
    def operations_payload(db: Session) -> dict[str, Any]:
        orders = list(
            db.execute(
                select(ServiceOrder)
                .where(ServiceOrder.service_code == "interview")
                .order_by(ServiceOrder.updated_at.desc())
            ).scalars()
        )
        if not orders:
            return {"overview": InterviewOperationsService._empty_overview(), "orders": []}

        order_ids = [o.id for o in orders]
        recipients = list(
            db.execute(
                select(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id.in_(order_ids))
            ).scalars()
        )
        by_order: dict[str, list[ServiceOrderRecipient]] = {}
        for recipient in recipients:
            by_order.setdefault(recipient.order_id, []).append(recipient)
        for recs in by_order.values():
            recs.sort(key=lambda r: r.row_number or 0)

        org_ids = {o.org_id for o in orders if o.org_id}
        user_ids = {o.user_id for o in orders if o.user_id}
        org_map = {
            row.id: row.name
            for row in db.execute(select(Organisation).where(Organisation.id.in_(org_ids))).scalars()
        } if org_ids else {}
        user_map = {
            row.id: row.email
            for row in db.execute(select(User).where(User.id.in_(user_ids))).scalars()
        } if user_ids else {}

        rows: list[dict[str, Any]] = []
        today = datetime.utcnow().date()
        overview = {
            "total": len(orders),
            "live": 0,
            "running": 0,
            "paused": 0,
            "scheduled": 0,
            "completed": 0,
            "drafts": 0,
            "pending_payment_approval": 0,
            "failed_payments": 0,
            "active_interviews": 0,
            "waiting_to_launch": 0,
            "in_progress": 0,
            "needs_attention": 0,
            "completed_today": 0,
            "failed_deliveries": 0,
        }

        for order in orders:
            recs = by_order.get(order.id, [])
            row = order_operations_row(
                db,
                order,
                recs,
                org_name=org_map.get(order.org_id),
                owner_email=user_map.get(order.user_id),
            )
            rows.append(row)

            if ServiceOrderService.is_live_interview(order, recipients=recs):
                overview["live"] += 1
            if order.status == "running":
                overview["running"] += 1
            elif order.status == "paused":
                overview["paused"] += 1
            elif order.status == "scheduled":
                overview["scheduled"] += 1
            elif order.status == "completed":
                overview["completed"] += 1
            elif order.status == "draft":
                overview["drafts"] += 1
            if order.payment_status == "pending_approval":
                overview["pending_payment_approval"] += 1
            if order.payment_status == "rejected":
                overview["failed_payments"] += 1

            if row["is_live"]:
                overview["active_interviews"] += 1
            if row["launch_status"] in {"waiting", "launch_pending"}:
                overview["waiting_to_launch"] += 1
            if order.status in {"running", "paused"}:
                overview["in_progress"] += 1
            if row["needs_attention"]:
                overview["needs_attention"] += 1
            if row["email_status"] == "failed" or row["launch_status"] == "launch_failed":
                overview["failed_deliveries"] += 1

            completed_at = _parse_dt(order.completed_at)
            if completed_at and completed_at.date() == today:
                overview["completed_today"] += 1
            elif order.status == "completed" and _parse_dt(order.updated_at) and _parse_dt(order.updated_at).date() == today:
                overview["completed_today"] += 1

        return {"overview": overview, "orders": rows}

    @staticmethod
    def _empty_overview() -> dict[str, int]:
        return {
            "total": 0,
            "live": 0,
            "running": 0,
            "paused": 0,
            "scheduled": 0,
            "completed": 0,
            "drafts": 0,
            "pending_payment_approval": 0,
            "failed_payments": 0,
            "active_interviews": 0,
            "waiting_to_launch": 0,
            "in_progress": 0,
            "needs_attention": 0,
            "completed_today": 0,
            "failed_deliveries": 0,
        }

    @staticmethod
    def enhanced_overview(db: Session) -> dict[str, Any]:
        payload = InterviewOperationsService.operations_payload(db)
        return payload["overview"]
