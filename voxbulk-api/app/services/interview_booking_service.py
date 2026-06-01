"""Public candidate booking links and WhatsApp invites for interview orders."""

from __future__ import annotations

import logging
import json
import secrets
from datetime import datetime, timedelta, timezone, time
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
UK_TZ = ZoneInfo("Europe/London")

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.interview_booking_token import InterviewBookingToken
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.telnyx_whatsapp_template import TelnyxWhatsappTemplate
from app.services.platform_catalog_service import ServiceOrderService
from app.services.sales_whatsapp_telnyx_service import (
    build_telnyx_components,
    url_button_has_dynamic_suffix,
    url_button_index_from_components,
)
from app.services.telnyx_messaging_service import TelnyxMessagingService
from app.data.interview_booking_whatsapp_defaults import (
    INTERVIEW_BOOKING_BODY,
    INTERVIEW_BOOKING_CONFIRMATION_BODY,
    INTERVIEW_BOOKING_CONFIRMATION_BUTTONS,
    INTERVIEW_BOOKING_INVITE_BUTTONS,
    INTERVIEW_BOOKING_PREVIEW_BUTTONS,
    INTERVIEW_BOOKING_TEMPLATE_NAME,
    INTERVIEW_CONFIRMATION_TEMPLATE_NAME,
    INTERVIEW_EMAIL_SENT_BODY,
    INTERVIEW_EMAIL_SENT_TEMPLATE_NAME,
)
from app.services.career_email_service import CareerEmailService
from app.services.telnyx_whatsapp_template_sync_service import (
    TelnyxWhatsappTemplateSyncService,
    full_body_preview,
    send_template_id_for_row,
    template_to_dict,
)

SLOT_MINUTES = 30
BOOKING_HOURS_START = (9, 0)
BOOKING_HOURS_END = (17, 30)
VOICE_TERMINAL = frozenset(
    {"completed", "no_answer", "failed", "busy", "skipped", "cancelled", "opted_out", "done"}
)
BOOKING_LOCKED_MESSAGE = "Your AI interview is already complete — booking is no longer available."


def interview_booking_locked(recipient: ServiceOrderRecipient) -> str | None:
    """Return a user-facing reason when this candidate must not book/reschedule/cancel."""
    status = str(recipient.status or "").lower()
    parsed = _recipient_result(recipient)
    if status in {"completed", "done"}:
        return BOOKING_LOCKED_MESSAGE
    if parsed.get("analysis_saved_at"):
        return BOOKING_LOCKED_MESSAGE
    if parsed.get("ended_at") and status in VOICE_TERMINAL:
        return BOOKING_LOCKED_MESSAGE
    return None


def _assert_booking_allowed(recipient: ServiceOrderRecipient) -> None:
    reason = interview_booking_locked(recipient)
    if reason:
        raise ValueError(reason)


def _order_booking_closed_message(order: ServiceOrder, db: Session) -> str | None:
    config = _order_config(order)
    if config.get("booking_closed_at") or str(order.status or "") == "cancelled":
        role = str(config.get("role") or config.get("position") or order.title or "Interview").strip()
        company = InterviewBookingService._org_name(db, order)
        return (
            f"The {role} role at {company} is no longer accepting bookings — this campaign has ended."
        )
    if str(order.status or "") == "completed":
        role = str(config.get("role") or config.get("position") or order.title or "Interview").strip()
        company = InterviewBookingService._org_name(db, order)
        return f"The {role} role at {company} has expired — interviews for this position are closed."
    return None


def _assert_order_accepts_booking(db: Session, order: ServiceOrder) -> None:
    message = _order_booking_closed_message(order, db)
    if message:
        raise ValueError(message)


def _now() -> datetime:
    return datetime.utcnow()


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


def booking_public_origin() -> str:
    settings = get_settings()
    origin = str(settings.dashboard_app_origin or settings.public_app_origin or "http://localhost:5175").rstrip("/")
    return origin


def booking_url_for_token(token: str) -> str:
    return f"{booking_public_origin()}/book/{quote(str(token).strip(), safe='')}"


def booking_reschedule_url_for_token(token: str) -> str:
    return f"{booking_url_for_token(token)}?reschedule=1"


def _slot_starts(window_start: datetime, window_end: datetime, *, now: datetime | None = None) -> list[datetime]:
    if window_end <= window_start:
        return []
    cursor = window_start
    if now and cursor < now:
        # Align to next slot boundary after now
        delta = int((now - window_start).total_seconds() // 60)
        skip = (delta // SLOT_MINUTES) + (1 if delta % SLOT_MINUTES else 0)
        cursor = window_start + timedelta(minutes=skip * SLOT_MINUTES)
    slots: list[datetime] = []
    while cursor + timedelta(minutes=SLOT_MINUTES) <= window_end:
        slots.append(cursor)
        cursor += timedelta(minutes=SLOT_MINUTES)
    return slots


def _filter_slots_to_calling_hours(
    db: Session,
    order: ServiceOrder,
    slots: list[datetime],
) -> list[datetime]:
    """Only expose booking slots between 09:00 and 17:30 (org timezone, UK default)."""
    from app.utils.ofcom import is_weekend_uk, resolve_org_call_window

    out: list[datetime] = []
    for slot in slots:
        local = slot.replace(tzinfo=timezone.utc).astimezone(UK_TZ)
        if is_weekend_uk(local):
            from app.models.organisation_ai_config import OrganisationComplianceConfig

            row = db.execute(
                select(OrganisationComplianceConfig).where(OrganisationComplianceConfig.org_id == order.org_id)
            ).scalar_one_or_none()
            if row is not None and not row.weekend_allowed:
                continue
        window = resolve_org_call_window(db, order.org_id, now=local)
        day_start = max(window.start, time(9, 0))
        day_end = min(window.end, time(17, 30))
        slot_end_local = local + timedelta(minutes=SLOT_MINUTES)
        if day_start <= local.time() and slot_end_local.time() <= day_end:
            out.append(slot)
    return out


def _booked_starts(db: Session, order_id: str, *, exclude_token_id: str | None = None) -> set[datetime]:
    q = select(InterviewBookingToken.booked_start_at, InterviewBookingToken.id).where(
        InterviewBookingToken.order_id == order_id,
        InterviewBookingToken.booked_start_at.is_not(None),
    )
    rows = list(db.execute(q).all())
    out: set[datetime] = set()
    for start, token_id in rows:
        if start is None:
            continue
        if exclude_token_id and str(token_id) == str(exclude_token_id):
            continue
        out.add(start)
    return out


def _buttons_from_components(components: list[Any] | None) -> list[dict[str, str]]:
    if not isinstance(components, list):
        return []
    out: list[dict[str, str]] = []
    for comp in components:
        if str(comp.get("type") or "").upper() != "BUTTONS":
            continue
        for btn in comp.get("buttons") or []:
            if not isinstance(btn, dict):
                continue
            label = str(
                btn.get("text") or btn.get("title") or btn.get("label") or btn.get("button_text") or ""
            ).strip()
            if not label:
                continue
            btn_type = str(btn.get("type") or "QUICK_REPLY").strip().lower()
            out.append({"label": label, "type": btn_type})
    return out


def _render_template_body(body: str | None, variables: dict[int, str]) -> str:
    import re

    text = str(body or "").strip()
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        try:
            idx = int(match.group(1))
        except ValueError:
            return match.group(0)
        return str(variables.get(idx, match.group(0)))

    return re.sub(r"\{\{(\d+)\}\}", _replace, text)


def _format_slot_date(dt: datetime) -> str:
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    local = aware.astimezone(UK_TZ)
    return local.strftime("%a %d %b %Y").replace(" 0", " ")


def _format_slot_time(dt: datetime) -> str:
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    local = aware.astimezone(UK_TZ)
    return local.strftime("%I:%M %p").lstrip("0")


def _iso_utc(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=None).isoformat() + "Z"


def _booking_invite_buttons(components: list[Any] | None) -> list[dict[str, str]]:
    """Booking invite: Book My Interview + Reschedule + Cancel."""
    buttons = _buttons_from_components(components)
    if buttons:
        return buttons
    return [dict(b) for b in INTERVIEW_BOOKING_INVITE_BUTTONS]


def _confirmation_buttons(components: list[Any] | None) -> list[dict[str, str]]:
    """Confirmation: Reschedule + Cancel only."""
    buttons = _buttons_from_components(components)
    if buttons:
        return buttons
    return [dict(b) for b in INTERVIEW_BOOKING_CONFIRMATION_BUTTONS]


def _interview_booking_buttons(components: list[Any] | None) -> list[dict[str, str]]:
    return _booking_invite_buttons(components)


def _template_components(row: TelnyxWhatsappTemplate) -> list[Any]:
    try:
        parsed = json.loads(row.components_json or "null")
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


class InterviewBookingService:
    @staticmethod
    def _org_name(db: Session, order: ServiceOrder) -> str:
        try:
            from app.services.recovery_service import OrganisationService

            org = OrganisationService.get_org(db, order.org_id)
            name = str(org.name if org else "").strip()
            return name or "VOXBULK"
        except Exception:
            return "VOXBULK"

    @staticmethod
    def ensure_token(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> InterviewBookingToken:
        existing = db.execute(
            select(InterviewBookingToken)
            .where(
                InterviewBookingToken.order_id == order.id,
                InterviewBookingToken.recipient_id == recipient.id,
            )
            .order_by(InterviewBookingToken.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        token = secrets.token_urlsafe(24)
        row = InterviewBookingToken(
            order_id=order.id,
            recipient_id=recipient.id,
            org_id=order.org_id,
            token=token,
            expires_at=order.scheduled_end_at,
            created_at=_now(),
            updated_at=_now(),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def resolve_invite_wa_template(db: Session, order: ServiceOrder) -> TelnyxWhatsappTemplate | None:
        config = _order_config(order)
        template_id = str(config.get("wa_email_sent_template_id") or "").strip()
        template_name = str(config.get("wa_email_sent_template_name") or "").strip()
        row = TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_id=template_id or None,
            template_name=template_name or INTERVIEW_EMAIL_SENT_TEMPLATE_NAME,
            sales_template_key="interview_email_sent",
        )
        if row is not None:
            return row
        return TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_name=INTERVIEW_EMAIL_SENT_TEMPLATE_NAME,
            sales_template_key="interview_email_sent",
        )

    @staticmethod
    def resolve_template(db: Session, order: ServiceOrder) -> TelnyxWhatsappTemplate | None:
        """Legacy URL-button booking template (deprecated at launch)."""
        config = _order_config(order)
        template_id = str(config.get("wa_booking_template_id") or "").strip()
        template_name = str(config.get("wa_booking_template_name") or "").strip()
        row = TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_id=template_id or None,
            template_name=template_name or INTERVIEW_BOOKING_TEMPLATE_NAME,
            sales_template_key="interview_booking_invite",
        )
        if row is not None:
            return row
        from app.services.platform_whatsapp_template_service import PlatformWhatsappTemplateService

        grouped = PlatformWhatsappTemplateService.list_for_dashboard(db, approved_only=True)
        booking = (grouped.get("grouped") or {}).get("booking") or []
        for item in booking:
            name = str(item.get("name") or "").strip().lower()
            if name == INTERVIEW_BOOKING_TEMPLATE_NAME.lower():
                tid = str(item.get("template_id") or "").strip()
                if tid:
                    return TelnyxWhatsappTemplateSyncService.resolve_for_send(db, template_id=tid)
        if booking:
            first_id = str(booking[0].get("template_id") or "").strip()
            if first_id:
                return TelnyxWhatsappTemplateSyncService.resolve_for_send(db, template_id=first_id)
        return None

    @staticmethod
    def resolve_confirmation_template(db: Session, order: ServiceOrder) -> TelnyxWhatsappTemplate | None:
        config = _order_config(order)
        template_id = str(config.get("wa_confirmation_template_id") or "").strip()
        template_name = str(config.get("wa_confirmation_template_name") or "").strip()
        row = TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_id=template_id or None,
            template_name=template_name or INTERVIEW_CONFIRMATION_TEMPLATE_NAME,
            sales_template_key="interview_booking_confirm",
        )
        if row is not None:
            return row
        return TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_name=INTERVIEW_CONFIRMATION_TEMPLATE_NAME,
            sales_template_key="interview_booking_confirm",
        )

    @staticmethod
    def _render_body_preview(
        body: str | None,
        *,
        candidate_name: str,
        role: str,
        company_name: str | None = None,
        interview_date: str | None = None,
        interview_time: str | None = None,
    ) -> str:
        text = str(body or "").strip() or INTERVIEW_BOOKING_BODY
        variables: dict[int, str] = {
            1: _first_name(candidate_name),
            2: str(role or "interview").strip(),
        }
        # {{3}} = company_name
        if company_name is not None:
            variables[3] = str(company_name or "VOXBULK").strip() or "VOXBULK"
        # {{4}} = interview_date (only if not using company_name in that slot)
        if interview_date is not None:
            variables[4] = str(interview_date).strip()
        # {{5}} = interview_time (if needed)
        if interview_time is not None:
            variables[5] = str(interview_time).strip()
        return _render_template_body(text, variables)

    @staticmethod
    def build_booking_components(
        row: TelnyxWhatsappTemplate,
        *,
        candidate_name: str,
        role: str,
        company_name: str,
        booking_token: str,
    ) -> list[dict[str, Any]] | None:
        stored_components: list[Any] | None = None
        try:
            parsed = json.loads(row.components_json or "null")
            if isinstance(parsed, list):
                stored_components = parsed
        except json.JSONDecodeError:
            stored_components = None

        first = _first_name(candidate_name)
        role_line = str(role or "your interview").strip() or "your interview"
        company_line = str(company_name or "VOXBULK").strip() or "VOXBULK"
        body_values = [first, role_line, company_line]

        body_params = {
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)[:1024]} for v in body_values],
        }
        components: list[dict[str, Any]] = [body_params]

        url_idx = url_button_index_from_components(stored_components)
        if url_idx is not None:
            include_url = url_button_has_dynamic_suffix(stored_components) if stored_components else True
            if include_url:
                components.append(
                    {
                        "type": "button",
                        "sub_type": "url",
                        "index": int(url_idx),
                        "parameters": [{"type": "text", "text": booking_token[:1024]}],
                    }
                )
        elif row.sales_template_key:
            built = TelnyxWhatsappTemplateSyncService.build_components_for_row(
                row,
                variables={
                    "first_name": first,
                    "role": role_line,
                    "company_name": company_line,
                    "booking_token": booking_token,
                    "offer_line": role_line,
                    "offer_summary": company_line,
                },
            )
            if built:
                return built

        generic = TelnyxWhatsappTemplateSyncService.build_components_for_row(
            row,
            variables={
                "first_name": first,
                "role": role_line,
                "company_name": company_line,
                "booking_token": booking_token,
                "offer_line": role_line,
                "offer_summary": company_line,
            },
        )
        return generic or components

    @staticmethod
    def build_email_sent_components(
        row: TelnyxWhatsappTemplate,
        *,
        candidate_name: str,
        role: str,
        company_name: str,
    ) -> list[dict[str, Any]] | None:
        first = _first_name(candidate_name)
        role_line = str(role or "Interview").strip() or "Interview"
        company_line = str(company_name or "VOXBULK").strip() or "VOXBULK"
        built = build_telnyx_components(
            "interview_email_sent",
            {
                "first_name": first,
                "role": role_line,
                "company_name": company_line,
            },
            include_url_button=False,
        )
        if built:
            return built
        return [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": first[:1024]},
                    {"type": "text", "text": role_line[:1024]},
                    {"type": "text", "text": company_line[:1024]},
                ],
            }
        ]

    @staticmethod
    def build_confirmation_components(
        row: TelnyxWhatsappTemplate,
        *,
        candidate_name: str,
        role: str,
        slot_start: datetime,
    ) -> list[dict[str, Any]] | None:
        first = _first_name(candidate_name)
        role_line = str(role or "your interview").strip() or "your interview"
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)
        body_values = [first, role_line, date_line, time_line]
        body_params = {
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)[:1024]} for v in body_values],
        }
        if row.sales_template_key:
            built = TelnyxWhatsappTemplateSyncService.build_components_for_row(
                row,
                variables={
                    "first_name": first,
                    "role": role_line,
                    "interview_date": date_line,
                    "interview_time": time_line,
                    "offer_line": role_line,
                },
            )
            if built:
                return built
        return [body_params]

    @staticmethod
    def _fallback_preview(
        *,
        role: str,
        company_name: str,
        sync_result: dict[str, Any] | None,
        sync_error: str | None,
    ) -> dict[str, Any]:
        return {
            "name": INTERVIEW_EMAIL_SENT_TEMPLATE_NAME,
            "template_id": None,
            "status": "FALLBACK",
            "is_fallback": True,
            "invite_mode": "email_first",
            "sync": sync_result,
            "sync_error": sync_error,
            "sample_booking_url": booking_url_for_token("sample-booking-token"),
            "rendered_body": InterviewBookingService._render_body_preview(
                INTERVIEW_EMAIL_SENT_BODY,
                candidate_name="Alex",
                role=role,
                company_name=company_name,
            ),
            "buttons": [],
            "confirmation_template_name": INTERVIEW_CONFIRMATION_TEMPLATE_NAME,
            "confirmation_body": InterviewBookingService._render_body_preview(
                INTERVIEW_BOOKING_CONFIRMATION_BODY,
                candidate_name="Alex",
                role=role,
                interview_date="Sat 14 Jun 2026",
                interview_time="10:00 AM",
            ),
            "confirmation_buttons": [dict(b) for b in INTERVIEW_BOOKING_CONFIRMATION_BUTTONS],
        }

    @staticmethod
    def preview_template(db: Session, order: ServiceOrder, *, sync_first: bool = True) -> dict[str, Any]:
        sync_result: dict[str, Any] | None = None
        sync_error: str | None = None
        if sync_first:
            try:
                sync_result = TelnyxWhatsappTemplateSyncService.sync(db)
            except Exception as exc:
                sync_error = str(exc)

        role = str(_order_config(order).get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        row = InterviewBookingService.resolve_invite_wa_template(db, order)
        confirm_row = InterviewBookingService.resolve_confirmation_template(db, order)
        if row is None:
            return InterviewBookingService._fallback_preview(
                role=role,
                company_name=company_name,
                sync_result=sync_result,
                sync_error=sync_error,
            )

        sample_token = "sample-booking-token"
        components = _template_components(row)
        body_source = full_body_preview(components) or row.body_preview or INTERVIEW_EMAIL_SENT_BODY
        confirm_components = _template_components(confirm_row) if confirm_row else []
        confirm_body_source = (
            full_body_preview(confirm_components) or (confirm_row.body_preview if confirm_row else None)
        ) or INTERVIEW_BOOKING_CONFIRMATION_BODY

        enriched = template_to_dict(row)
        enriched["is_fallback"] = False
        enriched["invite_mode"] = "email_first"
        enriched["sync"] = sync_result
        enriched["sync_error"] = sync_error
        enriched["sample_booking_url"] = booking_url_for_token(sample_token)
        enriched["sample_components"] = InterviewBookingService.build_email_sent_components(
            row,
            candidate_name="Alex",
            role=role,
            company_name=company_name,
        )
        enriched["rendered_body"] = InterviewBookingService._render_body_preview(
            body_source,
            candidate_name="Alex",
            role=role,
            company_name=company_name,
        )
        enriched["buttons"] = []
        enriched["confirmation_template_name"] = (
            confirm_row.name if confirm_row else INTERVIEW_CONFIRMATION_TEMPLATE_NAME
        )
        enriched["confirmation_body"] = InterviewBookingService._render_body_preview(
            confirm_body_source,
            candidate_name="Alex",
            role=role,
            interview_date="Sat 14 Jun 2026",
            interview_time="10:00 AM",
        )
        enriched["confirmation_buttons"] = _confirmation_buttons(confirm_components)
        return enriched

    @staticmethod
    def public_page(db: Session, token: str) -> dict[str, Any]:
        row = db.execute(
            select(InterviewBookingToken).where(InterviewBookingToken.token == str(token).strip()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Booking link not found or expired")

        order = db.get(ServiceOrder, row.order_id)
        recipient = db.get(ServiceOrderRecipient, row.recipient_id)
        if order is None or recipient is None:
            raise ValueError("Booking link is no longer valid")

        now = _now()
        if row.expires_at and now > row.expires_at:
            raise ValueError("This booking link has expired")

        if not order.scheduled_start_at or not order.scheduled_end_at:
            raise ValueError("Interview schedule is not configured yet")

        config = _order_config(order)
        role = str(config.get("role") or config.get("position") or order.title or "Interview").strip()
        org_name = ""
        try:
            from app.services.recovery_service import OrganisationService

            org = OrganisationService.get_org(db, order.org_id)
            org_name = str(org.name if org else "").strip()
        except Exception:
            org_name = ""

        closed_message = _order_booking_closed_message(order, db)
        if closed_message:
            return {
                "token": row.token,
                "candidate_name": recipient.name or "Candidate",
                "role": role,
                "organisation_name": org_name,
                "booking_closed": True,
                "closed_message": closed_message,
                "slot_minutes": SLOT_MINUTES,
                "available_slots": [],
                "booked_start_at": _iso_utc(row.booked_start_at),
                "booked_end_at": _iso_utc(row.booked_end_at),
                "window_start": _iso_utc(order.scheduled_start_at),
                "window_end": _iso_utc(order.scheduled_end_at),
                "already_booked": row.booked_start_at is not None,
                "cancelled_at": None,
                "can_reschedule": False,
                "can_cancel": False,
            }

        _assert_booking_allowed(recipient)

        merged = _recipient_result(recipient)
        cancelled_at = merged.get("booking_cancelled_at")

        booked = _booked_starts(db, order.id, exclude_token_id=row.id)
        raw_slots = _slot_starts(order.scheduled_start_at, order.scheduled_end_at, now=now)
        filtered = _filter_slots_to_calling_hours(db, order, raw_slots)
        available = [
            start
            for start in filtered
            if start not in booked or (row.booked_start_at and start == row.booked_start_at)
        ]

        return {
            "token": row.token,
            "candidate_name": recipient.name or "Candidate",
            "role": role,
            "organisation_name": org_name,
            "booking_closed": False,
            "closed_message": None,
            "slot_minutes": SLOT_MINUTES,
            "available_slots": [_iso_utc(s) for s in available],
            "booked_start_at": _iso_utc(row.booked_start_at),
            "booked_end_at": _iso_utc(row.booked_end_at),
            "window_start": _iso_utc(order.scheduled_start_at),
            "window_end": _iso_utc(order.scheduled_end_at),
            "already_booked": row.booked_start_at is not None,
            "cancelled_at": str(cancelled_at) if cancelled_at else None,
            "can_reschedule": row.booked_start_at is not None,
            "can_cancel": row.booked_start_at is not None,
        }

    @staticmethod
    def confirm_booking(db: Session, token: str, slot_start_iso: str) -> dict[str, Any]:
        row = db.execute(
            select(InterviewBookingToken).where(InterviewBookingToken.token == str(token).strip()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Booking link not found")

        order = db.get(ServiceOrder, row.order_id)
        recipient = db.get(ServiceOrderRecipient, row.recipient_id)
        if order is None or recipient is None:
            raise ValueError("Booking link is no longer valid")

        _assert_order_accepts_booking(db, order)
        _assert_booking_allowed(recipient)

        if row.booked_start_at is not None:
            raise ValueError("You have already booked a time slot")

        if not order.scheduled_start_at or not order.scheduled_end_at:
            raise ValueError("Interview schedule is not configured")

        try:
            slot_start = datetime.fromisoformat(str(slot_start_iso).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ValueError("Invalid slot time") from exc

        slot_end = slot_start + timedelta(minutes=SLOT_MINUTES)
        if slot_start < order.scheduled_start_at or slot_end > order.scheduled_end_at:
            raise ValueError("Selected time is outside the interview window")

        now = _now()
        if slot_start < now:
            raise ValueError("Selected time is in the past")

        allowed_slots = set(
            _filter_slots_to_calling_hours(
                db,
                order,
                _slot_starts(order.scheduled_start_at, order.scheduled_end_at, now=now),
            )
        )
        if slot_start not in allowed_slots:
            raise ValueError("Selected time is outside calling hours (09:00–17:30)")

        booked = _booked_starts(db, order.id)
        if slot_start in booked:
            raise ValueError("That slot was just taken — pick another time")

        row.booked_start_at = slot_start
        row.booked_end_at = slot_end
        row.updated_at = now
        db.add(row)

        merged = _recipient_result(recipient)
        merged.pop("booking_cancelled_at", None)
        merged.update(
            {
                "booking_token": row.token,
                "booking_url": booking_url_for_token(row.token),
                "booked_start_at": slot_start.isoformat(),
                "booked_end_at": slot_end.isoformat(),
                "booking_confirmed_at": now.isoformat(),
            }
        )
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        order_id = order.id
        recipient_id = recipient.id
        slot_copy = slot_start

        def _notify() -> None:
            try:
                from app.core.database import get_sessionmaker

                with get_sessionmaker()() as bg_db:
                    bg_order = bg_db.get(ServiceOrder, order_id)
                    bg_recipient = bg_db.get(ServiceOrderRecipient, recipient_id)
                    if bg_order is None or bg_recipient is None:
                        return
                    InterviewBookingService._send_booking_confirmations(bg_db, bg_order, bg_recipient, slot_copy)
            except Exception:
                logger.exception("booking_confirm_notify_failed order_id=%s recipient_id=%s", order_id, recipient_id)

        import threading

        threading.Thread(target=_notify, daemon=True).start()

        return {
            "ok": True,
            "booked_start_at": slot_start.isoformat(),
            "booked_end_at": slot_end.isoformat(),
            "candidate_name": recipient.name,
        }

    @staticmethod
    def _send_booking_confirmations(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        slot_start: datetime,
    ) -> None:
        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)
        first = _first_name(recipient.name)

        if recipient.email:
            sent_ok = False
            try:
                sent_ok, err = CareerEmailService.send_templated_optional(
                    db,
                    template_key="interview_booking_confirm",
                    to_email=str(recipient.email).strip(),
                    variables={
                        "candidate_name": recipient.name or "there",
                        "role": role,
                        "company_name": company_name,
                        "interview_date": date_line,
                        "interview_time": time_line,
                    },
                )
                if not sent_ok:
                    logger.warning(
                        "booking_confirm_email_failed",
                        extra={"recipient_id": recipient.id, "error": err},
                    )
            except Exception as exc:
                logger.exception(
                    "booking_confirm_email_error",
                    extra={"recipient_id": recipient.id, "error": str(exc)},
                )
            if sent_ok:
                merged = _recipient_result(recipient)
                merged["confirmation_email_sent_at"] = _now().isoformat()
                recipient.result_json = json.dumps(merged, ensure_ascii=False)
                db.add(recipient)
                db.commit()

        if not recipient.phone:
            return
        confirm_row = InterviewBookingService.resolve_confirmation_template(db, order)
        if confirm_row is None:
            return
        components = InterviewBookingService.build_confirmation_components(
            confirm_row,
            candidate_name=recipient.name or "Candidate",
            role=role,
            slot_start=slot_start,
        )
        fallback_body = (
            f"Hi {first}, your {role} interview is confirmed for {date_line} at {time_line}."
        )
        try:
            result = TelnyxMessagingService.send_whatsapp(
                db,
                to_number=str(recipient.phone),
                body=fallback_body,
                template_name=confirm_row.name,
                template_id=send_template_id_for_row(confirm_row),
                template_language=confirm_row.language or "en_US",
                template_components=components,
                org_id=order.org_id,
            )
            if result.ok:
                TelnyxMessagingService.log_outbound(
                    db,
                    org_id=order.org_id,
                    to_number=str(recipient.phone),
                    from_number=None,
                    body=f"[template:{confirm_row.name}] {fallback_body}",
                    result=result,
                )
        except Exception:
            pass

    @staticmethod
    def _send_booking_cancellation(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        slot_start: datetime,
        token: str,
    ) -> bool:
        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)
        book_url = booking_url_for_token(token)

        if not recipient.email:
            return False
        try:
            sent_ok, _err = CareerEmailService.send_templated_optional(
                db,
                template_key="interview_booking_cancel",
                to_email=str(recipient.email).strip(),
                variables={
                    "candidate_name": recipient.name or "there",
                    "role": role,
                    "company_name": company_name,
                    "interview_date": date_line,
                    "interview_time": time_line,
                    "booking_url": book_url,
                },
            )
            return bool(sent_ok)
        except Exception:
            return False

    @staticmethod
    def cancel_booking(db: Session, token: str, *, source: str = "web") -> dict[str, Any]:
        row = db.execute(
            select(InterviewBookingToken).where(InterviewBookingToken.token == str(token).strip()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Booking link not found")

        order = db.get(ServiceOrder, row.order_id)
        recipient = db.get(ServiceOrderRecipient, row.recipient_id)
        if order is None or recipient is None:
            raise ValueError("Booking link is no longer valid")

        _assert_order_accepts_booking(db, order)
        _assert_booking_allowed(recipient)

        if row.booked_start_at is None:
            raise ValueError("You do not have a booked interview to cancel")

        now = _now()
        previous_start = row.booked_start_at
        row.booked_start_at = None
        row.booked_end_at = None
        row.updated_at = now
        db.add(row)

        merged = _recipient_result(recipient)
        merged.update(
            {
                "booking_cancelled_at": now.isoformat(),
                "cancelled_booked_start_at": previous_start.isoformat() if previous_start else None,
                "booking_cancelled_via": str(source or "web").strip().lower() or "web",
            }
        )
        merged.pop("booked_start_at", None)
        merged.pop("booked_end_at", None)
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        email_sent = InterviewBookingService._send_booking_cancellation(
            db, order, recipient, slot_start=previous_start, token=row.token
        )
        if email_sent:
            merged = _recipient_result(recipient)
            merged["cancellation_email_sent_at"] = _now().isoformat()
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)
            db.commit()

        return {"ok": True, "cancelled": True, "candidate_name": recipient.name, "source": source}

    @staticmethod
    def reschedule_booking(db: Session, token: str, slot_start_iso: str) -> dict[str, Any]:
        row = db.execute(
            select(InterviewBookingToken).where(InterviewBookingToken.token == str(token).strip()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Booking link not found")

        order = db.get(ServiceOrder, row.order_id)
        recipient = db.get(ServiceOrderRecipient, row.recipient_id)
        if order is None or recipient is None:
            raise ValueError("Booking link is no longer valid")

        _assert_booking_allowed(recipient)

        if row.booked_start_at is None:
            raise ValueError("Book a time first before rescheduling")

        if not order.scheduled_start_at or not order.scheduled_end_at:
            raise ValueError("Interview schedule is not configured")

        try:
            slot_start = datetime.fromisoformat(str(slot_start_iso).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ValueError("Invalid slot time") from exc

        slot_end = slot_start + timedelta(minutes=SLOT_MINUTES)
        if slot_start < order.scheduled_start_at or slot_end > order.scheduled_end_at:
            raise ValueError("Selected time is outside the interview window")

        now = _now()
        if slot_start < now:
            raise ValueError("Selected time is in the past")

        allowed_slots = set(
            _filter_slots_to_calling_hours(
                db,
                order,
                _slot_starts(order.scheduled_start_at, order.scheduled_end_at, now=now),
            )
        )
        if slot_start not in allowed_slots:
            raise ValueError("Selected time is outside calling hours (09:00–17:30)")

        if row.booked_start_at == slot_start:
            raise ValueError("You are already booked for that time")

        booked = _booked_starts(db, order.id, exclude_token_id=row.id)
        if slot_start in booked:
            raise ValueError("That slot was just taken — pick another time")

        previous_start = row.booked_start_at
        row.booked_start_at = slot_start
        row.booked_end_at = slot_end
        row.updated_at = now
        db.add(row)

        merged = _recipient_result(recipient)
        merged.pop("booking_cancelled_at", None)
        merged.update(
            {
                "booking_token": row.token,
                "booking_url": booking_url_for_token(row.token),
                "booked_start_at": slot_start.isoformat(),
                "booked_end_at": slot_end.isoformat(),
                "booking_rescheduled_at": now.isoformat(),
                "previous_booked_start_at": previous_start.isoformat() if previous_start else None,
            }
        )
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        InterviewBookingService._send_booking_confirmations(db, order, recipient, slot_start)

        return {
            "ok": True,
            "rescheduled": True,
            "booked_start_at": slot_start.isoformat(),
            "booked_end_at": slot_end.isoformat(),
            "candidate_name": recipient.name,
        }

    @staticmethod
    def send_invites(
        db: Session,
        order: ServiceOrder,
        *,
        recipient_ids: list[str] | None = None,
        channels: list[str] | None = None,
        force_resend: bool = False,
    ) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Booking invites are only for interview orders")
        if not order.scheduled_start_at or not order.scheduled_end_at:
            raise ValueError("Set the calling window (start and end) before sending booking links")

        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        template_row = InterviewBookingService.resolve_invite_wa_template(db, order)

        use_channels = [str(c).strip().lower() for c in (channels or ["email", "whatsapp"]) if str(c).strip()]
        if not use_channels:
            use_channels = ["email", "whatsapp"]

        recipients = ServiceOrderService.get_recipients(db, order.id)
        id_filter = {str(x).strip() for x in (recipient_ids or []) if str(x).strip()}
        if id_filter:
            recipients = [r for r in recipients if r.id in id_filter]

        wa_sent = 0
        email_sent = 0
        skipped_locked = 0
        errors: list[str] = []

        for recipient in recipients:
            if interview_booking_locked(recipient):
                skipped_locked += 1
                errors.append(f"{recipient.name or recipient.id}: interview already complete — invite skipped")
                continue
            if not recipient.email and "email" in use_channels:
                if recipient.phone and "whatsapp" in use_channels:
                    pass
                elif not recipient.phone:
                    errors.append(f"{recipient.name or recipient.id}: no phone or email")
                    continue

            token_row = InterviewBookingService.ensure_token(db, order, recipient)
            url = booking_url_for_token(token_row.token)
            first = _first_name(recipient.name)
            recipient_email_sent = False
            recipient_wa_sent = False

            if "email" in use_channels and recipient.email:
                merged_check = _recipient_result(recipient)
                if merged_check.get("invite_email_sent_at") and not force_resend:
                    recipient_email_sent = True
                else:
                    try:
                        sent_ok, err = CareerEmailService.send_templated_optional(
                            db,
                            template_key="interview_booking_invite",
                            to_email=str(recipient.email).strip(),
                            variables={
                                "candidate_name": recipient.name or "there",
                                "role": role,
                                "company_name": company_name,
                                "booking_url": url,
                            },
                        )
                        if sent_ok:
                            email_sent += 1
                            recipient_email_sent = True
                        elif err:
                            errors.append(f"Email {recipient.email}: {err}")
                    except Exception as exc:
                        errors.append(f"Email {recipient.email}: {exc}")

            if "whatsapp" in use_channels and recipient.phone:
                if token_row.wa_sent_at and not force_resend:
                    recipient_wa_sent = True
                elif template_row is None:
                    errors.append(f"{recipient.name}: no WhatsApp interview_email_sent template")
                else:
                    from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

                    phone_check = TelnyxPhoneAllowlistService.validate_phone_db(db, str(recipient.phone))
                    if not phone_check.get("allowed"):
                        errors.append(
                            f"{recipient.name} WA: {phone_check.get('reason') or 'phone not on allow list'}"
                        )
                    else:
                        components = InterviewBookingService.build_email_sent_components(
                            template_row,
                            candidate_name=recipient.name or "Candidate",
                            role=role,
                            company_name=company_name,
                        )
                        fallback_body = (
                            f"Dear {first}, we sent you an email from careers@voxbulk.com "
                            f"about your {role} interview at {company_name}. Please check your inbox and spam folder."
                        )
                        log_body = f"[template:{template_row.name}] {fallback_body}"
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
                            token_row.wa_sent_at = _now()
                            token_row.wa_message_id = result.external_id
                            token_row.updated_at = _now()
                            db.add(token_row)
                            wa_sent += 1
                            recipient_wa_sent = True
                            TelnyxMessagingService.log_outbound(
                                db,
                                org_id=order.org_id,
                                to_number=str(recipient.phone),
                                from_number=None,
                                body=log_body,
                                result=result,
                            )
                        else:
                            errors.append(f"{recipient.name} WA: {result.detail or result.status}")

            merged = _recipient_result(recipient)
            now_iso = _now().isoformat()
            merged.update({"booking_token": token_row.token, "booking_url": url, "booking_invite_sent_at": now_iso})
            if recipient_email_sent:
                merged["invite_email_sent_at"] = merged.get("invite_email_sent_at") or now_iso
            if recipient_wa_sent:
                merged["invite_wa_sent_at"] = (token_row.wa_sent_at or _now()).isoformat()
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)

        dispatch_ok = email_sent > 0 or wa_sent > 0
        config["last_invite_dispatch"] = {
            "at": _now().isoformat(),
            "whatsapp_sent": wa_sent,
            "email_sent": email_sent,
            "skipped_locked": skipped_locked,
            "errors": errors[:50],
            "ok": dispatch_ok,
        }
        if dispatch_ok:
            config["booking_invites_sent_at"] = _now().isoformat()
        if template_row is not None:
            config["wa_email_sent_template_id"] = send_template_id_for_row(template_row)
            config["wa_email_sent_template_name"] = template_row.name
        order.config_json = json.dumps(config, ensure_ascii=False)
        order.updated_at = _now()
        db.add(order)
        db.commit()

        return {
            "ok": dispatch_ok,
            "whatsapp_sent": wa_sent,
            "email_sent": email_sent,
            "skipped_locked": skipped_locked,
            "errors": errors,
        }
