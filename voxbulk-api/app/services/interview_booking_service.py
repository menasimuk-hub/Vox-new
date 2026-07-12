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
    INTERVIEW_CANCEL_TEMPLATE_NAME,
    INTERVIEW_JOB_CLOSED_TEMPLATE_NAME,
    INTERVIEW_BOOKING_CANCEL_BODY,
    INTERVIEW_JOB_CLOSED_BODY,
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

SLOT_MINUTES = 4


def interview_slot_minutes() -> int:
    """Interview booking slot length (minutes). Override with INTERVIEW_SLOT_MINUTES env (1–60)."""
    try:
        from app.core.config import get_settings

        raw = int(get_settings().interview_slot_minutes)
        return max(1, min(60, raw))
    except (TypeError, ValueError, AttributeError):
        return SLOT_MINUTES


def interview_relax_restrictions() -> bool:
    """Temporary: skip Ofcom/org booking-hour filters and interview dial-hour checks."""
    try:
        from app.core.config import get_settings

        return bool(get_settings().interview_relax_hours)
    except Exception:
        return False


FULL_DAY_BOOKING_HOURS = 24


def booking_window_bounds(
    order: ServiceOrder,
    *,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """UTC window used to generate bookable slots (may extend to 24h when relax mode is on)."""
    start = order.scheduled_start_at
    end = order.scheduled_end_at
    if start is None or end is None:
        raise ValueError("Interview schedule is not configured")
    if not interview_relax_restrictions():
        return start, end
    min_end = start + timedelta(hours=FULL_DAY_BOOKING_HOURS)
    if end < min_end:
        end = min_end
    return start, end


def ensure_full_day_booking_window(db: Session, order: ServiceOrder) -> ServiceOrder:
    """When relax mode is on, persist at least a 24-hour booking window on the order."""
    if not interview_relax_restrictions():
        return order
    start = order.scheduled_start_at
    end = order.scheduled_end_at
    if start is None or end is None:
        return order
    min_end = start + timedelta(hours=FULL_DAY_BOOKING_HOURS)
    if end >= min_end:
        return order
    order.scheduled_end_at = min_end
    order.updated_at = _now()
    config = _order_config(order)
    config["calling_window_end_at"] = _iso_utc(min_end) or min_end.isoformat()
    config["booking_full_day_hours"] = FULL_DAY_BOOKING_HOURS
    order.config_json = json.dumps(config, ensure_ascii=False)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


BOOKING_HOURS_START = (9, 0)
BOOKING_HOURS_END = (17, 30)
VOICE_TERMINAL = frozenset(
    {"completed", "no_answer", "failed", "busy", "skipped", "cancelled", "opted_out", "done"}
)
BOOKING_LOCKED_MESSAGE = "Your interview is already complete — booking is no longer available."
BOOKING_OPTED_OUT_MESSAGE = "This interview was closed — booking is no longer available."


def interview_booking_locked(recipient: ServiceOrderRecipient) -> str | None:
    """Return a user-facing reason when this candidate must not book/reschedule/cancel."""
    status = str(recipient.status or "").lower()
    parsed = _recipient_result(recipient)
    if status in {"opted_out"} or parsed.get("opted_out"):
        return BOOKING_OPTED_OUT_MESSAGE
    if parsed.get("awaiting_candidate_action") and status not in {"completed", "done", "opted_out"}:
        # Early exit (not free / short drop / wrong person) — allow rebook.
        return None
    if status in {"completed", "done"}:
        # Layer 2 still reviewing transcript — do not lock booking yet.
        if parsed.get("session_outcome_provisional") and not parsed.get("session_outcome_reviewed_at"):
            return None
        return BOOKING_LOCKED_MESSAGE
    if parsed.get("analysis_saved_at"):
        return BOOKING_LOCKED_MESSAGE
    if parsed.get("ended_at") and status in VOICE_TERMINAL:
        return BOOKING_LOCKED_MESSAGE
    return None


def admin_unlock_interview_booking(
    db: Session,
    *,
    order: ServiceOrder,
    recipient: ServiceOrderRecipient,
    reason: str = "admin_unlock",
    clear_slot: bool = True,
    send_reschedule_email: bool = True,
) -> dict[str, Any]:
    """Ops unlock for stuck completed bookings so the candidate can rebook.

    Does not reopen recording_declined / opted_out rows.
    """
    from app.models.interview_booking_token import InterviewBookingToken
    from app.services.interview_early_exit_service import _strip_completed_interview_artifacts

    parsed = _recipient_result(recipient)
    if str(recipient.status or "").lower() in {"opted_out"} or parsed.get("opted_out"):
        raise ValueError("Candidate opted out — unlock is not allowed.")
    if parsed.get("session_outcome") == "recording_declined":
        raise ValueError("Recording was declined — unlock is not allowed.")

    now = datetime.utcnow()
    now_iso = now.isoformat()
    token = db.execute(
        select(InterviewBookingToken).where(
            InterviewBookingToken.order_id == order.id,
            InterviewBookingToken.recipient_id == recipient.id,
        )
    ).scalar_one_or_none()

    cleared_slot: str | None = None
    if clear_slot and token is not None and token.booked_start_at is not None:
        cleared_slot = token.booked_start_at.isoformat()
        token.booked_start_at = None
        token.updated_at = now
        db.add(token)

    merged = dict(parsed)
    for key in (
        "ended_at",
        "call_completed_at",
        "meeting_ended_at",
        "analysis_saved_at",
        "analysis",
        "score",
        "thank_you_email_sent_at",
    ):
        merged.pop(key, None)
    _strip_completed_interview_artifacts(merged)
    merged.update(
        {
            "awaiting_candidate_action": True,
            "session_outcome": "reschedule",
            "session_outcome_provisional": False,
            "admin_unlocked_at": now_iso,
            "admin_unlock_reason": str(reason or "admin_unlock")[:240],
            "early_exit_reason": "admin_unlock",
        }
    )
    if cleared_slot:
        merged["cleared_booked_start_at"] = cleared_slot
        merged["booking_cancelled_at"] = now_iso
        merged["booking_cancelled_via"] = "admin_unlock"

    recipient.status = "pending"
    recipient.updated_at = now
    recipient.result_json = json.dumps(merged, ensure_ascii=False)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)

    email_sent = False
    if send_reschedule_email:
        try:
            from app.services.interview_session_outcome_email_service import (
                dispatch_interview_session_outcome_email,
            )

            mail = dispatch_interview_session_outcome_email(
                db, order=order, recipient=recipient, outcome="reschedule"
            )
            email_sent = bool(mail.get("ok") or (mail.get("skipped") and mail.get("reason") == "already_sent"))
        except Exception:
            logger.exception("admin_unlock_reschedule_email_failed")

    return {
        "ok": True,
        "status": recipient.status,
        "locked": interview_booking_locked(recipient),
        "cleared_slot": cleared_slot,
        "reschedule_email_sent": email_sent,
    }


def _booking_withdrawn(recipient: ServiceOrderRecipient) -> bool:
    """True when the candidate permanently opted out (not a mere slot cancel)."""
    merged = _recipient_result(recipient)
    return bool(merged.get("booking_withdrawn"))


def _assert_booking_allowed(recipient: ServiceOrderRecipient) -> None:
    reason = interview_booking_locked(recipient)
    if reason:
        raise ValueError(reason)
    if _booking_withdrawn(recipient):
        raise ValueError("This interview was cancelled — you are no longer scheduled for an AI call.")


def _order_booking_closed_message(order: ServiceOrder, db: Session) -> str | None:
    config = _order_config(order)
    role = str(config.get("role") or config.get("position") or order.title or "Interview").strip()
    company = InterviewBookingService._org_name(db, order)
    now = _now()
    if config.get("booking_closed_at") or str(order.status or "") == "cancelled":
        reason = str(config.get("booking_closed_reason") or "").strip()
        if reason:
            return f"The {role} role at {company} is no longer available — {reason}"
        return f"The {role} role at {company} is no longer accepting bookings — this campaign has ended."
    if str(order.status or "") == "completed":
        return f"The {role} role at {company} has expired — interviews for this position are closed."
    if order.scheduled_end_at and now >= order.scheduled_end_at:
        return f"The {role} role at {company} has closed — the interview booking window has ended."
    if config.get("calling_window_ended_at"):
        return f"The {role} role at {company} has closed — the interview calling window has ended."
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


def _email_from_cv_text(recipient: ServiceOrderRecipient) -> str | None:
    """Last resort: scan raw CV text when column/json have no email."""
    from app.services.interview_cv_parse_service import EMAIL_RE

    text = str(recipient.cv_text or "").strip()
    if not text:
        return None
    match = EMAIL_RE.search(text)
    if not match:
        return None
    addr = match.group(0).strip().lower()
    return addr if "@" in addr else None


def _recipient_outreach_email(recipient: ServiceOrderRecipient) -> str | None:
    """Best email for booking/cancel outreach (column, then CV parse, then result_json, then CV text)."""
    direct = str(recipient.email or "").strip().lower()
    if direct and "@" in direct:
        return direct
    try:
        cv = json.loads(recipient.cv_parsed_json or "{}")
        if isinstance(cv, dict):
            for key in ("email", "email_address", "contact_email"):
                val = str(cv.get(key) or "").strip().lower()
                if val and "@" in val:
                    return val
    except Exception:
        pass
    merged = _recipient_result(recipient)
    for key in ("invite_sent_to", "outreach_email", "email", "candidate_email", "contact_email"):
        val = str(merged.get(key) or "").strip().lower()
        if val and "@" in val:
            return val
    return _email_from_cv_text(recipient)


def _persist_recipient_outreach_email(db: Session, recipient: ServiceOrderRecipient) -> str | None:
    """Resolve outreach email and persist on the recipient row before SMTP send."""
    outreach = _recipient_outreach_email(recipient)
    if not outreach:
        return None
    if outreach != str(recipient.email or "").strip().lower():
        recipient.email = outreach
        db.add(recipient)
    try:
        cv = json.loads(recipient.cv_parsed_json or "{}")
        if not isinstance(cv, dict):
            cv = {}
    except Exception:
        cv = {}
    if not str(cv.get("email") or "").strip():
        cv["email"] = outreach
        recipient.cv_parsed_json = json.dumps(cv, ensure_ascii=False)
        db.add(recipient)
    db.flush()
    return outreach


def campaign_invites_were_sent(order: ServiceOrder) -> bool:
    """True once booking invites were dispatched at launch (not for saved drafts)."""
    cfg = _order_config(order)
    dispatch = cfg.get("last_invite_dispatch")
    if isinstance(dispatch, dict):
        if dispatch.get("ok") is False:
            return False
        if int(dispatch.get("email_sent") or 0) > 0 or int(dispatch.get("whatsapp_sent") or 0) > 0:
            return True
    if cfg.get("booking_invites_sent_at"):
        return True
    return False


def order_has_booking_outreach_candidates(db: Session, order: ServiceOrder) -> bool:
    """True when at least one candidate should receive closure email (invite/booking proof on file)."""
    for recipient in ServiceOrderService.get_recipients(db, order.id):
        if interview_booking_locked(recipient):
            continue
        if _booking_withdrawn(recipient):
            continue
        token_row = db.execute(
            select(InterviewBookingToken)
            .where(
                InterviewBookingToken.order_id == order.id,
                InterviewBookingToken.recipient_id == recipient.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        if recipient_received_booking_outreach(recipient, token_row):
            return True
    return False


def recipient_received_booking_outreach(
    recipient: ServiceOrderRecipient,
    token_row: InterviewBookingToken | None,
) -> bool:
    """True when the candidate received an invite or booked a slot — safe to notify on closure."""
    if token_row is not None and token_row.booked_start_at is not None:
        return True
    if token_row is not None and token_row.wa_sent_at is not None:
        return True
    merged = _recipient_result(recipient)
    if merged.get("invite_email_sent_at") or merged.get("invite_wa_sent_at"):
        return True
    if merged.get("booking_invite_sent_at") or merged.get("scheduling_sent_at"):
        return True
    if merged.get("booking_token") or merged.get("booking_url"):
        return True
    if str(recipient.status or "").lower() in {"sent", "scheduled"}:
        return True
    return False


def _first_name(name: str | None) -> str:
    raw = str(name or "").strip()
    if not raw:
        return "there"
    return raw.split()[0]


def booking_public_origin() -> str:
    settings = get_settings()
    booking = str(settings.booking_app_origin or "").strip().rstrip("/")
    if booking:
        return booking
    origin = str(settings.dashboard_app_origin or settings.public_app_origin or "http://localhost:5175").rstrip("/")
    return origin


def booking_url_for_token(token: str) -> str:
    return f"{booking_public_origin()}/book/{quote(str(token).strip(), safe='')}"


def meeting_url_for_token(token: str) -> str:
    return f"{booking_public_origin()}/meet/{quote(str(token).strip(), safe='')}"


PHONE_CHANNEL = "phone"
MEETING_CHANNEL = "meeting"


def resolve_booking_channel_options(
    db: Session, phone: str, *, order: ServiceOrder | None = None
) -> dict[str, Any]:
    from app.services.telnyx_phone_allowlist_service import TelnyxPhoneAllowlistService

    # Candidate-choice booking: the allowlist always decides. If the candidate's
    # mobile is eligible for AI calling they may pick phone OR online meeting;
    # otherwise only the browser meeting room is offered. The order-level
    # ``delivery`` no longer forces web-only — the per-slot ``channel`` the
    # candidate selects is the source of truth.
    check = TelnyxPhoneAllowlistService.validate_phone_db(db, phone)
    phone_available = bool(check.get("allowed"))
    return {
        "phone_available": phone_available,
        "meeting_available": True,
        "default_channel": PHONE_CHANNEL if phone_available else MEETING_CHANNEL,
    }


def resolve_booking_url(
    recipient: ServiceOrderRecipient | None,
    token: str,
) -> str:
    """Prefer the booking link stored on the invite email (result_json.booking_url)."""
    tok = str(token or "").strip()
    if recipient is not None and tok:
        merged = _recipient_result(recipient)
        stored_url = str(merged.get("booking_url") or "").strip()
        stored_token = str(merged.get("booking_token") or "").strip()
        if stored_url and (not stored_token or stored_token == tok):
            return stored_url
    return booking_url_for_token(tok)


def booking_reschedule_url_for_token(token: str, *, recipient: ServiceOrderRecipient | None = None) -> str:
    base = resolve_booking_url(recipient, token)
    if "reschedule=" in base:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}reschedule=1"


def _ceil_to_slot_grid(dt: datetime) -> datetime:
    """Next slot boundary on the clock (grid from INTERVIEW_SLOT_MINUTES)."""
    sm = interview_slot_minutes()
    dt = dt.replace(second=0, microsecond=0)
    total = dt.hour * 60 + dt.minute
    if total % sm == 0:
        return dt
    ceiled = ((total // sm) + 1) * sm
    return dt.replace(hour=ceiled // 60, minute=ceiled % 60)


def _slot_starts(window_start: datetime, window_end: datetime, *, now: datetime | None = None) -> list[datetime]:
    if window_end <= window_start:
        return []
    cursor = _ceil_to_slot_grid(window_start.replace(second=0, microsecond=0))
    if now:
        min_start = _ceil_to_slot_grid(now.replace(second=0, microsecond=0))
        if cursor < min_start:
            cursor = min_start
    slots: list[datetime] = []
    while cursor + timedelta(minutes=interview_slot_minutes()) <= window_end:
        if cursor >= window_start.replace(second=0, microsecond=0):
            slots.append(cursor)
        cursor += timedelta(minutes=interview_slot_minutes())
    return slots


def _filter_slots_to_calling_hours(
    db: Session,
    order: ServiceOrder,
    slots: list[datetime],
) -> list[datetime]:
    """Only expose booking slots between 09:00 and 17:30 (org timezone, UK default)."""
    if interview_relax_restrictions():
        return list(slots)
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
        slot_end_local = local + timedelta(minutes=interview_slot_minutes())
        if day_start <= local.time() and slot_end_local.time() <= day_end:
            out.append(slot)
    return out


def _assert_slot_within_booking_hours(db: Session, order: ServiceOrder, slot_start: datetime) -> None:
    """Reject any slot outside 09:00–17:30 UK (Ofcom calling window)."""
    if interview_relax_restrictions():
        return
    allowed = _filter_slots_to_calling_hours(db, order, [slot_start])
    if not allowed:
        raise ValueError("Selected time is outside calling hours (09:00–17:30 UK time)")


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


def _booking_display_meta() -> dict[str, str]:
    if interview_relax_restrictions():
        return {
            "display_timezone": "Europe/London",
            "display_timezone_label": "UK time (GMT/BST)",
            "calling_hours_label": "Any time UK (testing mode — no hour restrictions)",
        }
    start = f"{BOOKING_HOURS_START[0]:02d}:{BOOKING_HOURS_START[1]:02d}"
    end = f"{BOOKING_HOURS_END[0]:02d}:{BOOKING_HOURS_END[1]:02d}"
    return {
        "display_timezone": "Europe/London",
        "display_timezone_label": "UK time (GMT/BST)",
        "calling_hours_label": f"{start}–{end} UK time (9:00 am – 5:30 pm)",
    }


def _interview_language_for_order(db: Session, order: ServiceOrder) -> str:
    """Return 'ar' or 'en' for public meeting/booking UI localization."""
    try:
        from app.services.voice_agent_runtime import resolve_interview_language

        config = _order_config(order)
        lang = resolve_interview_language(config)
        return "ar" if lang == "ar" else "en"
    except Exception:
        return "en"


def interview_order_read_only(order: ServiceOrder) -> bool:
    """True when the employer must not change or resend invites (stopped/finished)."""
    return str(order.status or "").lower() in {"cancelled", "completed", "archived"}


def _assert_order_accepts_invite_changes(order: ServiceOrder) -> None:
    if interview_order_read_only(order):
        status = str(order.status or "").lower()
        if status == "cancelled":
            raise ValueError("This campaign was stopped — booking invites cannot be sent or resent.")
        if status == "completed":
            raise ValueError("This campaign is finished — booking invites cannot be sent or resent.")
        raise ValueError("This campaign is read-only — booking invites cannot be sent or resent.")


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
        for name in (INTERVIEW_CONFIRMATION_TEMPLATE_NAME, "interview_confirm_book_v4", "interview_confirm_book_v3"):
            row = TelnyxWhatsappTemplateSyncService.resolve_for_send(
                db,
                template_name=name,
                sales_template_key="interview_booking_confirm",
            )
            if row is not None:
                return row
        return None

    @staticmethod
    def resolve_cancel_template(db: Session, order: ServiceOrder) -> TelnyxWhatsappTemplate | None:
        config = _order_config(order)
        template_id = str(config.get("wa_cancel_template_id") or "").strip()
        template_name = str(config.get("wa_cancel_template_name") or "").strip()
        row = TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_id=template_id or None,
            template_name=template_name or INTERVIEW_CANCEL_TEMPLATE_NAME,
            sales_template_key="interview_booking_cancel",
        )
        if row is not None:
            return row
        return TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_name=INTERVIEW_CANCEL_TEMPLATE_NAME,
            sales_template_key="interview_booking_cancel",
        )

    @staticmethod
    def resolve_job_closed_template(db: Session, order: ServiceOrder) -> TelnyxWhatsappTemplate | None:
        config = _order_config(order)
        template_id = str(config.get("wa_job_closed_template_id") or "").strip()
        template_name = str(config.get("wa_job_closed_template_name") or "").strip()
        row = TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_id=template_id or None,
            template_name=template_name or INTERVIEW_JOB_CLOSED_TEMPLATE_NAME,
            sales_template_key="interview_job_closed",
        )
        if row is not None:
            return row
        return TelnyxWhatsappTemplateSyncService.resolve_for_send(
            db,
            template_name=INTERVIEW_JOB_CLOSED_TEMPLATE_NAME,
            sales_template_key="interview_job_closed",
        )

    @staticmethod
    def build_cancel_components(
        row: TelnyxWhatsappTemplate,
        *,
        candidate_name: str,
        role: str,
        company_name: str,
        slot_start: datetime,
    ) -> list[dict[str, Any]] | None:
        built = build_telnyx_components(
            "interview_booking_cancel",
            {
                "first_name": _first_name(candidate_name),
                "role": str(role or "Interview").strip(),
                "company_name": str(company_name or "VOXBULK").strip(),
                "interview_date": _format_slot_date(slot_start),
                "interview_time": _format_slot_time(slot_start),
            },
            include_url_button=False,
        )
        if built:
            return built
        return TelnyxWhatsappTemplateSyncService.build_components_for_row(
            row,
            variables={
                "first_name": _first_name(candidate_name),
                "role": role,
                "company_name": company_name,
                "interview_date": _format_slot_date(slot_start),
                "interview_time": _format_slot_time(slot_start),
            },
        )

    @staticmethod
    def build_job_closed_components(
        row: TelnyxWhatsappTemplate,
        *,
        candidate_name: str,
        role: str,
        company_name: str,
    ) -> list[dict[str, Any]] | None:
        built = build_telnyx_components(
            "interview_job_closed",
            {
                "first_name": _first_name(candidate_name),
                "role": str(role or "Interview").strip(),
                "company_name": str(company_name or "VOXBULK").strip(),
            },
            include_url_button=False,
        )
        if built:
            return built
        return TelnyxWhatsappTemplateSyncService.build_components_for_row(
            row,
            variables={
                "first_name": _first_name(candidate_name),
                "role": role,
                "company_name": company_name,
            },
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
        careers_email: str | None = None,
        channel_line: str | None = None,
    ) -> str:
        text = str(body or "").strip() or INTERVIEW_BOOKING_BODY
        variables: dict[int, str] = {
            1: _first_name(candidate_name),
            2: str(role or "interview").strip(),
        }
        # Confirmation templates: {{3}} date, {{4}} time, {{5}} channel line.
        # Email-sent: {{3}} company, {{4}} careers inbox.
        if interview_date is not None:
            variables[3] = str(interview_date).strip()
            if interview_time is not None:
                variables[4] = str(interview_time).strip()
            if channel_line is not None:
                variables[5] = str(channel_line).strip()
        elif careers_email is not None:
            variables[3] = str(company_name or "VOXBULK").strip() or "VOXBULK"
            variables[4] = str(careers_email or "careers@voxbulk.com").strip() or "careers@voxbulk.com"
        elif company_name is not None:
            variables[3] = str(company_name or "VOXBULK").strip() or "VOXBULK"
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
        careers_email: str = "careers@voxbulk.com",
    ) -> list[dict[str, Any]] | None:
        first = _first_name(candidate_name)
        role_line = str(role or "Interview").strip() or "Interview"
        company_line = str(company_name or "VOXBULK").strip() or "VOXBULK"
        email_line = str(careers_email or "careers@voxbulk.com").strip() or "careers@voxbulk.com"
        built = build_telnyx_components(
            "interview_email_sent",
            {
                "first_name": first,
                "role": role_line,
                "company_name": company_line,
                "careers_email": email_line,
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
                    {"type": "text", "text": email_line[:1024]},
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
        meeting_url: str | None = None,
        channel: str | None = None,
    ) -> list[dict[str, Any]] | None:
        first = _first_name(candidate_name)
        role_line = str(role or "your interview").strip() or "your interview"
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)
        channel_key = str(channel or "").strip().lower()
        meet = str(meeting_url or "").strip()
        if channel_key == MEETING_CHANNEL and meet:
            channel_line = f"Join your online meeting: {meet}"
        else:
            channel_line = "We will call you on the number you provided."

        body_values = [first, role_line, date_line, time_line, channel_line]
        # Older approved templates (v4) only accept 4 body variables.
        var_count = InterviewBookingService._template_body_var_count(row)
        if var_count and var_count < 5:
            body_values = body_values[: max(1, var_count)]

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
                    "meeting_url": meet,
                    "channel_line": channel_line,
                },
            )
            if built:
                # Trim to match older 4-var templates still live on Meta.
                if var_count and var_count < 5:
                    for part in built:
                        if str(part.get("type") or "").lower() == "body":
                            params = part.get("parameters")
                            if isinstance(params, list) and len(params) > var_count:
                                part["parameters"] = params[:var_count]
                return built
        return [body_params]

    @staticmethod
    def _template_body_var_count(row: TelnyxWhatsappTemplate) -> int | None:
        """Return max {{n}} in template body, or None if unknown."""
        import re

        texts: list[str] = []
        for raw in (row.draft_components_json, row.components_json, row.body_preview):
            if not raw:
                continue
            try:
                parsed = json.loads(raw) if str(raw).strip().startswith(("[", "{")) else None
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, list):
                for comp in parsed:
                    if isinstance(comp, dict) and str(comp.get("type") or "").upper() == "BODY":
                        texts.append(str(comp.get("text") or ""))
            else:
                texts.append(str(raw))
        found = 0
        for text in texts:
            for match in re.findall(r"\{\{(\d+)\}\}", text):
                found = max(found, int(match))
        return found or None

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
                careers_email="careers@voxbulk.com",
            ),
            "buttons": [],
            "confirmation_template_name": INTERVIEW_CONFIRMATION_TEMPLATE_NAME,
            "confirmation_body": InterviewBookingService._render_body_preview(
                INTERVIEW_BOOKING_CONFIRMATION_BODY,
                candidate_name="Alex",
                role=role,
                interview_date="Sat 14 Jun 2026",
                interview_time="10:00 AM",
                channel_line="Join your online meeting: https://dashboard.voxbulk.com/meet/sample-token",
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
            careers_email="careers@voxbulk.com",
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
            channel_line="Join your online meeting: https://dashboard.voxbulk.com/meet/sample-token",
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

        interview_language = _interview_language_for_order(db, order)
        merged = _recipient_result(recipient)
        if _booking_withdrawn(recipient):
            cancelled_at = merged.get("booking_cancelled_at")
            return {
                "token": row.token,
                "candidate_name": recipient.name or "Candidate",
                "role": role,
                "organisation_name": org_name,
                "interview_language": interview_language,
                "booking_closed": True,
                "closed_message": (
                    "Your interview was cancelled. You will not receive an AI call or any further messages about this job."
                ),
                "slot_minutes": interview_slot_minutes(),
                "available_slots": [],
                "booked_start_at": None,
                "booked_end_at": None,
                "window_start": _iso_utc(order.scheduled_start_at),
                "window_end": _iso_utc(order.scheduled_end_at),
                "already_booked": False,
                "cancelled_at": str(cancelled_at) if cancelled_at else None,
                "can_reschedule": False,
                "can_cancel": False,
                **_booking_display_meta(),
            }

        closed_message = _order_booking_closed_message(order, db)
        if closed_message:
            has_booking = row.booked_start_at is not None
            return {
                "token": row.token,
                "candidate_name": recipient.name or "Candidate",
                "role": role,
                "organisation_name": org_name,
                "interview_language": interview_language,
                "booking_closed": True,
                "closed_message": closed_message,
                "slot_minutes": interview_slot_minutes(),
                "available_slots": [],
                "booked_start_at": _iso_utc(row.booked_start_at),
                "booked_end_at": _iso_utc(row.booked_end_at),
                "window_start": _iso_utc(order.scheduled_start_at),
                "window_end": _iso_utc(order.scheduled_end_at),
                "already_booked": has_booking,
                "cancelled_at": None,
                "can_reschedule": has_booking,
                "can_cancel": has_booking,
                "booking_url": booking_url_for_token(row.token),
                "meeting_url": meeting_url_for_token(row.token) if row.channel == MEETING_CHANNEL else None,
                **_booking_display_meta(),
            }

        _assert_booking_allowed(recipient)

        cancelled_at = merged.get("booking_cancelled_at")

        booked = _booked_starts(db, order.id, exclude_token_id=row.id)
        win_start, win_end = booking_window_bounds(order, now=now)
        raw_slots = _slot_starts(win_start, win_end, now=now)
        filtered = _filter_slots_to_calling_hours(db, order, raw_slots)
        available = [
            start
            for start in filtered
            if start not in booked or (row.booked_start_at and start == row.booked_start_at)
        ]

        channel_options = resolve_booking_channel_options(db, str(recipient.phone or ""), order=order)

        payload: dict[str, Any] = {
            "token": row.token,
            "candidate_name": recipient.name or "Candidate",
            "role": role,
            "organisation_name": org_name,
            "interview_language": interview_language,
            "booking_closed": False,
            "closed_message": None,
            "slot_minutes": interview_slot_minutes(),
            "available_slots": [_iso_utc(s) for s in available],
            "booked_start_at": _iso_utc(row.booked_start_at),
            "booked_end_at": _iso_utc(row.booked_end_at),
            "window_start": _iso_utc(win_start),
            "window_end": _iso_utc(win_end),
            "already_booked": row.booked_start_at is not None,
            "cancelled_at": str(cancelled_at) if cancelled_at else None,
            "can_reschedule": row.booked_start_at is not None,
            "can_cancel": row.booked_start_at is not None,
            "channel": row.channel,
            "channel_options": channel_options,
            "booking_url": booking_url_for_token(row.token),
            "meeting_url": meeting_url_for_token(row.token) if row.channel == MEETING_CHANNEL else None,
            **_booking_display_meta(),
        }
        if row.booked_start_at is not None:
            from app.services.interview_calendar_service import build_interview_calendar_variables

            cal = build_interview_calendar_variables(
                token=row.token,
                slot_start=row.booked_start_at,
                slot_end=row.booked_end_at,
                role=role,
                company_name=org_name,
            )
            payload["calendar_google_url"] = cal.get("calendar_google_url")
            payload["calendar_outlook_url"] = cal.get("calendar_outlook_url")
            payload["calendar_ics_url"] = cal.get("calendar_ics_url")
        return payload

    @staticmethod
    def confirm_booking(db: Session, token: str, slot_start_iso: str, channel: str | None = None) -> dict[str, Any]:
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

        slot_end = slot_start + timedelta(minutes=interview_slot_minutes())
        now = _now()
        win_start, win_end = booking_window_bounds(order, now=now)
        if slot_start < win_start or slot_end > win_end:
            raise ValueError("Selected time is outside the interview window")

        if slot_start < now:
            raise ValueError("Selected time is in the past")

        allowed_slots = set(
            _filter_slots_to_calling_hours(
                db,
                order,
                _slot_starts(win_start, win_end, now=now),
            )
        )
        if slot_start not in allowed_slots:
            in_window = (
                slot_start >= win_start
                and slot_start + timedelta(minutes=interview_slot_minutes()) <= win_end
            )
            if in_window:
                raise ValueError(
                    f"Selected time is not a valid {interview_slot_minutes()}-minute slot — pick a time from the available list"
                )
            raise ValueError("Selected time is outside calling hours (09:00–17:30 UK time)")

        _assert_slot_within_booking_hours(db, order, slot_start)

        booked = _booked_starts(db, order.id)
        if slot_start in booked:
            raise ValueError("That slot was just taken — pick another time")

        channel_options = resolve_booking_channel_options(db, str(recipient.phone or ""), order=order)
        chosen = str(channel or channel_options.get("default_channel") or PHONE_CHANNEL).strip().lower()
        if chosen == PHONE_CHANNEL and not channel_options.get("phone_available"):
            chosen = MEETING_CHANNEL
        if chosen not in {PHONE_CHANNEL, MEETING_CHANNEL}:
            raise ValueError("Invalid interview channel")
        if chosen == PHONE_CHANNEL and not channel_options.get("phone_available"):
            raise ValueError("Phone interviews are not available for your number — choose online meeting")
        if chosen == MEETING_CHANNEL and not channel_options.get("meeting_available"):
            raise ValueError("Online meetings are not available for this interview — choose phone")

        row.booked_start_at = slot_start
        row.booked_end_at = slot_end
        row.channel = chosen
        row.updated_at = now
        db.add(row)

        merged = _recipient_result(recipient)
        merged.pop("booking_cancelled_at", None)
        merged.pop("booking_withdrawn", None)
        merged.pop("awaiting_candidate_action", None)
        merged.pop("early_exit_at", None)
        merged.pop("early_exit_reason", None)
        merged.update(
            {
                "booking_token": row.token,
                "booking_url": booking_url_for_token(row.token),
                "meeting_url": meeting_url_for_token(row.token) if chosen == MEETING_CHANNEL else None,
                "channel": chosen,
                "booked_start_at": _iso_utc(slot_start),
                "booked_end_at": _iso_utc(slot_end),
                "booking_confirmed_at": _iso_utc(now),
            }
        )
        if str(recipient.status or "").lower() not in {"completed", "done", "calling", "in_progress"}:
            recipient.status = "scheduled"
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        notify: dict[str, Any] = {}
        try:
            notify = InterviewBookingService._send_booking_confirmations(db, order, recipient, slot_start)
        except Exception:
            logger.exception(
                "booking_confirm_notify_failed order_id=%s recipient_id=%s",
                order.id,
                recipient.id,
            )

        email_ok = bool(notify.get("confirmation_email_sent"))
        email_err = notify.get("confirmation_email_error")
        sent_to = str(notify.get("confirmation_sent_to") or "").strip()
        message = (
            f"Your interview slot is confirmed. A confirmation email was sent to {sent_to} — check inbox and spam."
            if email_ok and sent_to
            else (
                "Your interview slot is confirmed. A confirmation email was sent — check inbox and spam."
                if email_ok
                else (
                    f"Your slot is confirmed but we could not send the confirmation email"
                    f"{f': {email_err}' if email_err else ''}. "
                    "Save this page or note your booked time."
                )
            )
        )
        return {
            "ok": True,
            "booked_start_at": _iso_utc(slot_start),
            "booked_end_at": _iso_utc(slot_end),
            "channel": chosen,
            "meeting_url": meeting_url_for_token(row.token) if chosen == MEETING_CHANNEL else None,
            "candidate_name": recipient.name,
            "confirmation_email_sent": email_ok,
            "confirmation_email_error": email_err,
            "confirmation_sent_to": sent_to or None,
            "confirmation_wa_sent": bool(notify.get("confirmation_wa_sent")),
            "message": message,
        }

    @staticmethod
    def _booking_token_for_recipient(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> str | None:
        merged = _recipient_result(recipient)
        tok = str(merged.get("booking_token") or "").strip()
        if tok:
            return tok
        row = db.execute(
            select(InterviewBookingToken)
            .where(
                InterviewBookingToken.order_id == order.id,
                InterviewBookingToken.recipient_id == recipient.id,
            )
            .limit(1)
        ).scalar_one_or_none()
        return str(row.token).strip() if row is not None else None

    @staticmethod
    def calendar_ics_payload(db: Session, token: str) -> tuple[str, str]:
        row = db.execute(
            select(InterviewBookingToken).where(InterviewBookingToken.token == str(token).strip()).limit(1)
        ).scalar_one_or_none()
        if row is None or row.booked_start_at is None:
            raise ValueError("No booked interview found for this calendar link")

        order = db.get(ServiceOrder, row.order_id)
        recipient = db.get(ServiceOrderRecipient, row.recipient_id)
        if order is None or recipient is None:
            raise ValueError("Booking link is no longer valid")
        if _booking_withdrawn(recipient):
            raise ValueError("This interview was cancelled")

        closed_message = _order_booking_closed_message(order, db)
        if closed_message:
            raise ValueError(closed_message)

        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        slot_start = row.booked_start_at
        slot_end = row.booked_end_at or (slot_start + timedelta(minutes=interview_slot_minutes()))
        title = f"{role} interview — {company_name}"
        description = (
            f"AI phone interview for the {role} role at {company_name}. "
            "We will call you at the booked time."
        )

        from app.services.interview_calendar_service import build_interview_ics

        ics = build_interview_ics(
            slot_start=slot_start,
            slot_end=slot_end,
            title=title,
            description=description,
            uid=f"interview-{row.token}@voxbulk.com",
        )
        filename = f"interview-{role[:40].replace(' ', '-').lower()}.ics"
        return ics, filename

    @staticmethod
    def _send_booking_confirmations(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        slot_start: datetime,
    ) -> dict[str, Any]:
        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)
        first = _first_name(recipient.name)
        token = InterviewBookingService._booking_token_for_recipient(db, order, recipient)
        channel = ""
        if token:
            token_row = db.execute(
                select(InterviewBookingToken).where(InterviewBookingToken.token == token).limit(1)
            ).scalar_one_or_none()
            channel = str(getattr(token_row, "channel", "") or "").strip().lower()
        meeting_url = ""
        if token and channel == "meeting":
            meeting_url = meeting_url_for_token(token)
        calendar_vars: dict[str, str] = {"calendar_links_html": ""}
        if token:
            try:
                from app.services.interview_calendar_service import build_interview_calendar_variables

                calendar_vars = build_interview_calendar_variables(
                    token=token,
                    slot_start=slot_start,
                    slot_end=slot_start + timedelta(minutes=interview_slot_minutes()),
                    role=role,
                    company_name=company_name,
                )
            except Exception as exc:
                logger.warning(
                    "booking_confirm_calendar_vars_failed",
                    extra={"order_id": order.id, "recipient_id": recipient.id, "error": str(exc)},
                )

        if channel == "meeting":
            channel_note = "Join the online meeting room at your booked time using the link below."
            meeting_link_html = (
                f'<p style="margin:16px 0;"><a href="{meeting_url}" style="display:inline-block;padding:12px 18px;background:#1a2d5c;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;">Join online meeting</a></p>'
                f'<p style="word-break:break-all;font-size:13px;color:#6b6560;"><a href="{meeting_url}" style="color:#1a2d5c;">{meeting_url}</a></p>'
                if meeting_url
                else ""
            )
        else:
            channel_note = "We will call you on the number you provided."
            meeting_link_html = ""

        base_variables = {
            "candidate_name": recipient.name or "there",
            "role": role,
            "company_name": company_name,
            "interview_date": date_line,
            "interview_time": time_line,
            "interview_channel_note": channel_note,
            "meeting_link_html": meeting_link_html,
            "meeting_url": meeting_url,
            **calendar_vars,
        }

        outreach_email = _persist_recipient_outreach_email(db, recipient)
        email_sent = False
        email_error: str | None = None
        confirm_channel = "none"
        if outreach_email:
            db.commit()
            db.refresh(recipient)
            try:
                sent_ok, err, confirm_channel = CareerEmailService.send_booking_confirm_email(
                    db,
                    to_email=outreach_email,
                    variables=base_variables,
                )
                email_sent = sent_ok
                if not sent_ok:
                    email_error = err or "send_failed"
                    logger.warning(
                        "booking_confirm_email_failed",
                        extra={
                            "order_id": order.id,
                            "recipient_id": recipient.id,
                            "to": outreach_email,
                            "error": err,
                            "channel": confirm_channel,
                        },
                    )
                elif confirm_channel == "plain_fallback":
                    logger.warning(
                        "booking_confirm_plain_fallback_used",
                        extra={
                            "order_id": order.id,
                            "recipient_id": recipient.id,
                            "to": outreach_email,
                        },
                    )
                else:
                    logger.info(
                        "booking_confirm_template_sent",
                        extra={
                            "order_id": order.id,
                            "recipient_id": recipient.id,
                            "to": outreach_email,
                            "template_key": "interview_booking_confirm",
                        },
                    )
            except Exception as exc:
                email_error = str(exc)
                logger.exception(
                    "booking_confirm_email_error",
                    extra={"order_id": order.id, "recipient_id": recipient.id},
                )
            if email_sent:
                merged = _recipient_result(recipient)
                merged["confirmation_email_sent_at"] = _now().isoformat()
                merged["confirmation_sent_to"] = outreach_email
                if confirm_channel == "plain_fallback":
                    merged["confirmation_plain_fallback"] = True
                    merged.pop("confirmation_email_template", None)
                else:
                    merged["confirmation_email_template"] = "interview_booking_confirm"
                    merged.pop("confirmation_plain_fallback", None)
                merged.pop("confirmation_email_failed", None)
                recipient.result_json = json.dumps(merged, ensure_ascii=False)
                db.add(recipient)
                db.commit()
            elif email_error:
                merged = _recipient_result(recipient)
                merged["confirmation_email_failed"] = email_error
                merged.pop("confirmation_email_template", None)
                recipient.result_json = json.dumps(merged, ensure_ascii=False)
                db.add(recipient)
                db.commit()
        else:
            email_error = "no_recipient_email"
            logger.warning(
                "booking_confirm_no_email",
                extra={"order_id": order.id, "recipient_id": recipient.id},
            )

        wa_sent = False
        if not recipient.phone:
            return {
                "confirmation_email_sent": email_sent,
                "confirmation_email_error": email_error,
                "confirmation_sent_to": outreach_email,
                "confirmation_wa_sent": wa_sent,
            }
        confirm_row = InterviewBookingService.resolve_confirmation_template(db, order)
        if confirm_row is None:
            return {
                "confirmation_email_sent": email_sent,
                "confirmation_email_error": email_error,
                "confirmation_sent_to": outreach_email,
                "confirmation_wa_sent": wa_sent,
            }
        components = InterviewBookingService.build_confirmation_components(
            confirm_row,
            candidate_name=recipient.name or "Candidate",
            role=role,
            slot_start=slot_start,
            meeting_url=meeting_url or None,
            channel=channel or None,
        )
        if meeting_url:
            fallback_body = (
                f"Hi {first}, your {role} interview is confirmed for {date_line} at {time_line}. "
                f"Join your online meeting: {meeting_url}"
            )
        else:
            fallback_body = (
                f"Hi {first}, your {role} interview is confirmed for {date_line} at {time_line}. "
                "We will call you on this number."
            )
        from app.services.interview_whatsapp_send_service import InterviewWhatsappSendService

        result = InterviewWhatsappSendService.send_template_or_plain(
            db,
            to_number=str(recipient.phone),
            body=fallback_body,
            org_id=order.org_id,
            template_row=confirm_row,
            template_components=components,
            template_language=confirm_row.language or "en_US",
        )
        if result.ok:
            wa_sent = True
            TelnyxMessagingService.log_outbound(
                db,
                org_id=order.org_id,
                to_number=str(recipient.phone),
                from_number=None,
                body=f"[template:{confirm_row.name}] {fallback_body}",
                result=result,
            )
            # Older 4-var confirmation templates cannot carry the meeting URL — send a follow-up.
            var_count = InterviewBookingService._template_body_var_count(confirm_row)
            if meeting_url and (not var_count or var_count < 5):
                link_body = (
                    f"Hi {first}, here is your online interview room link for {date_line} at {time_line}:\n"
                    f"{meeting_url}\n\n"
                    "The room opens 1 minute before your booked time."
                )
                link_result = TelnyxMessagingService.send_whatsapp(
                    db,
                    to_number=str(recipient.phone),
                    body=link_body,
                    org_id=order.org_id,
                    meter_usage=False,
                    service_code="ai_interview",
                )
                if link_result.ok:
                    TelnyxMessagingService.log_outbound(
                        db,
                        org_id=order.org_id,
                        to_number=str(recipient.phone),
                        from_number=None,
                        body=link_body,
                        result=link_result,
                    )
                else:
                    logger.warning(
                        "booking_confirm_wa_meeting_link_failed",
                        extra={
                            "recipient_id": recipient.id,
                            "detail": link_result.detail or link_result.status,
                        },
                    )
            merged = _recipient_result(recipient)
            merged["confirmation_wa_sent_at"] = _now().isoformat()
            if meeting_url:
                merged["confirmation_wa_meeting_url"] = meeting_url
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)
            db.commit()
        else:
            logger.warning(
                "booking_confirm_wa_failed",
                extra={"recipient_id": recipient.id, "detail": result.detail or result.status},
            )

        return {
            "confirmation_email_sent": email_sent,
            "confirmation_email_error": email_error,
            "confirmation_sent_to": outreach_email,
            "confirmation_wa_sent": wa_sent,
        }

    @staticmethod
    def _send_booking_cancellation(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        slot_start: datetime,
    ) -> bool:
        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)

        outreach_email = _persist_recipient_outreach_email(db, recipient)
        if not outreach_email:
            return False
        variables = {
            "candidate_name": recipient.name or "there",
            "role": role,
            "company_name": company_name,
            "interview_date": date_line,
            "interview_time": time_line,
        }
        try:
            sent_ok, err = CareerEmailService.send_templated_critical(
                db,
                template_key="interview_booking_cancel",
                to_email=outreach_email,
                variables=variables,
            )
            if sent_ok:
                return True
            if err:
                logger.warning(
                    "booking_cancel_email_failed",
                    extra={"recipient_id": recipient.id, "error": err},
                )
            return False
        except Exception:
            logger.exception(
                "booking_cancel_email_error",
                extra={"recipient_id": recipient.id},
            )
            return False

    @staticmethod
    def _send_booking_cancellation_whatsapp(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        *,
        slot_start: datetime,
    ) -> bool:
        if not recipient.phone:
            return False
        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        first = _first_name(recipient.name)
        date_line = _format_slot_date(slot_start)
        time_line = _format_slot_time(slot_start)
        cancel_row = InterviewBookingService.resolve_cancel_template(db, order)
        fallback_body = (
            f"Hi {first}, your {role} interview at {company_name} on {date_line} at {time_line} "
            f"has been cancelled. You will not receive any further messages about this job."
        )
        from app.services.interview_whatsapp_send_service import InterviewWhatsappSendService

        try:
            if cancel_row is not None:
                components = InterviewBookingService.build_cancel_components(
                    cancel_row,
                    candidate_name=recipient.name or "Candidate",
                    role=role,
                    company_name=company_name,
                    slot_start=slot_start,
                )
                result = InterviewWhatsappSendService.send_template_or_plain(
                    db,
                    to_number=str(recipient.phone),
                    body=fallback_body,
                    org_id=order.org_id,
                    template_row=cancel_row,
                    template_components=components,
                    template_language=cancel_row.language or "en_US",
                )
            else:
                result = InterviewWhatsappSendService.send_template_or_plain(
                    db,
                    to_number=str(recipient.phone),
                    body=fallback_body,
                    org_id=order.org_id,
                )
            if result.ok:
                TelnyxMessagingService.log_outbound(
                    db,
                    org_id=order.org_id,
                    to_number=str(recipient.phone),
                    from_number=None,
                    body=f"[template:{cancel_row.name if cancel_row else 'text'}] {fallback_body}",
                    result=result,
                )
                return True
        except Exception:
            logger.exception(
                "booking_cancel_wa_error",
                extra={"recipient_id": recipient.id},
            )
        return False

    @staticmethod
    def _hangup_active_call_if_any(db: Session, order: ServiceOrder, recipient: ServiceOrderRecipient) -> None:
        merged = _recipient_result(recipient)
        call_id = str(merged.get("call_control_id") or "").strip()
        if not call_id:
            return
        try:
            from app.services.telnyx_voice_service import TelnyxVoiceAdapter, _telnyx_config

            config = _telnyx_config(db, org_id=order.org_id)
            TelnyxVoiceAdapter.hangup_call(call_control_id=call_id, config=config)
        except Exception:
            logger.exception(
                "booking_cancel_hangup_failed",
                extra={"order_id": order.id, "recipient_id": recipient.id, "call_control_id": call_id},
            )

    @staticmethod
    def notify_campaign_closed(
        db: Session,
        order: ServiceOrder,
        *,
        reason: str | None = None,
        include_uninvited: bool = False,
        notify_all_with_email: bool = False,
    ) -> dict[str, Any]:
        """Email (and optional WhatsApp) candidates when the employer closes a campaign."""
        if order.service_code != "interview":
            return {"ok": True, "skipped": True, "reason": "not_interview"}

        had_prior_outreach = campaign_invites_were_sent(order) or order_has_booking_outreach_candidates(db, order)
        if not had_prior_outreach and not include_uninvited:
            return {"ok": True, "skipped": True, "reason": "invites_never_sent"}

        config = _order_config(order)

        role = str(config.get("role") or config.get("position") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        closure_reason = (reason or config.get("booking_closed_reason") or "This interview campaign has been closed.").strip()
        recipients = ServiceOrderService.get_recipients(db, order.id)

        email_sent = 0
        wa_sent = 0
        skipped = 0
        errors: list[str] = []
        job_closed_row = InterviewBookingService.resolve_job_closed_template(db, order)

        for recipient in recipients:
            if interview_booking_locked(recipient):
                skipped += 1
                continue
            if _booking_withdrawn(recipient):
                skipped += 1
                continue
            merged = _recipient_result(recipient)
            if merged.get("campaign_cancel_email_sent_at"):
                skipped += 1
                continue

            token_row = db.execute(
                select(InterviewBookingToken)
                .where(
                    InterviewBookingToken.order_id == order.id,
                    InterviewBookingToken.recipient_id == recipient.id,
                )
                .limit(1)
            ).scalar_one_or_none()
            if (
                not notify_all_with_email
                and not include_uninvited
                and not recipient_received_booking_outreach(recipient, token_row)
            ):
                skipped += 1
                continue

            outreach_email = _persist_recipient_outreach_email(db, recipient)
            if not outreach_email:
                if notify_all_with_email or include_uninvited:
                    errors.append(f"{recipient.name or recipient.id}: no email for cancellation notice")
                skipped += 1
                continue

            had_booked_slot = token_row is not None and token_row.booked_start_at is not None
            booked_slot_start = token_row.booked_start_at if had_booked_slot and token_row else None

            InterviewBookingService._hangup_active_call_if_any(db, order, recipient)
            if had_booked_slot and token_row is not None:
                token_row.booked_start_at = None
                token_row.booked_end_at = None
                token_row.updated_at = _now()
                db.add(token_row)

            recipient_email_sent = False
            recipient_wa_sent = False
            if outreach_email:
                try:
                    if booked_slot_start is not None:
                        recipient_email_sent = InterviewBookingService._send_booking_cancellation(
                            db,
                            order,
                            recipient,
                            slot_start=booked_slot_start,
                        )
                    else:
                        sent_ok, err = CareerEmailService.send_templated_critical(
                            db,
                            template_key="interview_campaign_cancelled",
                            to_email=outreach_email,
                            variables={
                                "candidate_name": recipient.name or "there",
                                "role": role,
                                "company_name": company_name,
                                "closure_reason": closure_reason,
                            },
                        )
                        if sent_ok:
                            recipient_email_sent = True
                        elif err:
                            errors.append(f"{outreach_email}: {err}")
                            logger.warning(
                                "campaign_cancel_email_failed",
                                extra={
                                    "recipient_id": recipient.id,
                                    "order_id": order.id,
                                    "error": err,
                                },
                            )
                except Exception as exc:
                    errors.append(f"{outreach_email}: {exc}")
                    logger.exception(
                        "campaign_cancel_email_error",
                        extra={"recipient_id": recipient.id, "order_id": order.id},
                    )

            # WhatsApp costs per message — only notify candidates who had a booked slot.
            if recipient.phone and had_booked_slot:
                first = _first_name(recipient.name)
                fallback_body = (
                    f"Hi {first}, the {role} role at {company_name} is no longer available. "
                    f"You will not receive any further messages about this job."
                )
                try:
                    from app.services.interview_whatsapp_send_service import InterviewWhatsappSendService

                    if job_closed_row is not None:
                        components = InterviewBookingService.build_job_closed_components(
                            job_closed_row,
                            candidate_name=recipient.name or "Candidate",
                            role=role,
                            company_name=company_name,
                        )
                        result = InterviewWhatsappSendService.send_template_or_plain(
                            db,
                            to_number=str(recipient.phone),
                            body=fallback_body,
                            org_id=order.org_id,
                            template_row=job_closed_row,
                            template_components=components,
                            template_language=job_closed_row.language or "en_US",
                        )
                    else:
                        result = InterviewWhatsappSendService.send_template_or_plain(
                            db,
                            to_number=str(recipient.phone),
                            body=fallback_body,
                            org_id=order.org_id,
                        )
                    if result.ok:
                        recipient_wa_sent = True
                        TelnyxMessagingService.log_outbound(
                            db,
                            org_id=order.org_id,
                            to_number=str(recipient.phone),
                            from_number=None,
                            body=f"[template:{job_closed_row.name if job_closed_row else 'text'}] {fallback_body}",
                            result=result,
                        )
                except Exception:
                    logger.exception(
                        "campaign_cancel_wa_error",
                        extra={"recipient_id": recipient.id, "order_id": order.id},
                    )

            if recipient_email_sent:
                email_sent += 1
            if recipient_wa_sent:
                wa_sent += 1
            merged = _recipient_result(recipient)
            if recipient_email_sent:
                merged["campaign_cancel_email_sent_at"] = _now().isoformat()
            if recipient_wa_sent:
                merged["campaign_cancel_wa_sent_at"] = _now().isoformat()
            merged["booking_withdrawn"] = True
            merged["campaign_closed_at"] = _now().isoformat()
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            if str(recipient.status or "").lower() in {"pending", "calling", "queued"}:
                recipient.status = "cancelled"
            db.add(recipient)

        config = _order_config(order)
        config["campaign_cancel_notified_at"] = _now().isoformat()
        if reason:
            config["booking_closed_reason"] = reason
        order.config_json = json.dumps(config, ensure_ascii=False)
        db.add(order)
        db.commit()

        from app.services.career_email_service import interview_email_delivery_status

        return {
            "ok": email_sent > 0 or wa_sent > 0 or (skipped > 0 and not errors),
            "email_sent": email_sent,
            "whatsapp_sent": wa_sent,
            "skipped": skipped,
            "errors": errors[:50],
            "recipient_count": len(recipients),
            "email_delivery": interview_email_delivery_status(db),
        }

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
        InterviewBookingService._hangup_active_call_if_any(db, order, recipient)
        if str(recipient.status or "").lower() not in {"completed", "done"}:
            recipient.status = "pending"
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        db.add(recipient)
        db.commit()

        email_sent = InterviewBookingService._send_booking_cancellation(
            db, order, recipient, slot_start=previous_start
        )
        wa_sent = InterviewBookingService._send_booking_cancellation_whatsapp(
            db, order, recipient, slot_start=previous_start
        )
        if email_sent or wa_sent:
            merged = _recipient_result(recipient)
            if email_sent:
                merged["cancellation_email_sent_at"] = _now().isoformat()
            if wa_sent:
                merged["cancellation_wa_sent_at"] = _now().isoformat()
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)
            db.commit()
        elif not str(recipient.email or "").strip() and not str(recipient.phone or "").strip():
            logger.warning(
                "booking_cancel_no_contact",
                extra={"order_id": order.id, "recipient_id": recipient.id, "source": source},
            )
        elif not email_sent and str(recipient.email or "").strip():
            logger.warning(
                "booking_cancel_email_failed",
                extra={"order_id": order.id, "recipient_id": recipient.id, "source": source, "email": recipient.email},
            )

        return {
            "ok": True,
            "cancelled": True,
            "candidate_name": recipient.name,
            "source": source,
            "cancellation_email_sent": email_sent,
            "cancellation_wa_sent": wa_sent,
        }

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

        _assert_order_accepts_booking(db, order)
        _assert_booking_allowed(recipient)

        if row.booked_start_at is None:
            raise ValueError("Book a time first before rescheduling")

        if not order.scheduled_start_at or not order.scheduled_end_at:
            raise ValueError("Interview schedule is not configured")

        try:
            slot_start = datetime.fromisoformat(str(slot_start_iso).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ValueError("Invalid slot time") from exc

        slot_end = slot_start + timedelta(minutes=interview_slot_minutes())
        now = _now()
        win_start, win_end = booking_window_bounds(order, now=now)
        if slot_start < win_start or slot_end > win_end:
            raise ValueError("Selected time is outside the interview window")

        if slot_start < now:
            raise ValueError("Selected time is in the past")

        allowed_slots = set(
            _filter_slots_to_calling_hours(
                db,
                order,
                _slot_starts(win_start, win_end, now=now),
            )
        )
        if slot_start not in allowed_slots:
            in_window = (
                slot_start >= win_start
                and slot_start + timedelta(minutes=interview_slot_minutes()) <= win_end
            )
            if in_window:
                raise ValueError(
                    f"Selected time is not a valid {interview_slot_minutes()}-minute slot — pick a time from the available list"
                )
            raise ValueError("Selected time is outside calling hours (09:00–17:30 UK time)")

        _assert_slot_within_booking_hours(db, order, slot_start)

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
        merged.pop("booking_withdrawn", None)
        merged.pop("awaiting_candidate_action", None)
        merged.pop("early_exit_at", None)
        merged.pop("early_exit_reason", None)
        merged.update(
            {
                "booking_token": row.token,
                "booking_url": resolve_booking_url(recipient, row.token),
                "booked_start_at": _iso_utc(slot_start),
                "booked_end_at": _iso_utc(slot_end),
                "booking_rescheduled_at": _iso_utc(now),
                "previous_booked_start_at": _iso_utc(previous_start) if previous_start else None,
            }
        )
        recipient.result_json = json.dumps(merged, ensure_ascii=False)
        if str(recipient.status or "").lower() not in {"completed", "done", "calling", "in_progress"}:
            recipient.status = "scheduled"
        db.add(recipient)
        db.commit()

        notify = InterviewBookingService._send_booking_confirmations(db, order, recipient, slot_start)

        return {
            "ok": True,
            "rescheduled": True,
            "confirmation_email_sent": bool(notify.get("confirmation_email_sent")),
            "confirmation_email_error": notify.get("confirmation_email_error"),
            "confirmation_wa_sent": bool(notify.get("confirmation_wa_sent")),
            "booked_start_at": _iso_utc(slot_start),
            "booked_end_at": _iso_utc(slot_end),
            "candidate_name": recipient.name,
        }

    @staticmethod
    def recipients_pending_invite_email(db: Session, order: ServiceOrder) -> bool:
        """True when any candidate has email but no recorded invite email yet."""
        for recipient in ServiceOrderService.get_recipients(db, order.id):
            if not str(recipient.email or "").strip():
                continue
            if not _recipient_result(recipient).get("invite_email_sent_at"):
                return True
        return False

    @staticmethod
    def send_interview_invitation_email(
        db: Session,
        *,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        outreach_email: str,
        role: str,
        company_name: str,
        booking_url: str,
        force_resend: bool = False,
        force_email: bool = False,
        smtp_ready: bool = True,
    ) -> tuple[bool, dict[str, Any], str | None]:
        """
        Send one interview booking invite email — shared by launch and resend paths.

        Returns (count_as_sent, merged_result_json, error_message).
        count_as_sent is True only when SMTP succeeded or idempotent skip (already sent).
        """
        merged_check = _recipient_result(recipient)
        if force_resend or force_email:
            merged_check.pop("invite_email_sent_at", None)
            merged_check.pop("invite_email_failed", None)
            merged_check.pop("invite_email_ok", None)

        prior_to = str(merged_check.get("invite_sent_to") or "").strip().lower()
        already_sent = (
            bool(merged_check.get("invite_email_sent_at"))
            and bool(merged_check.get("invite_email_ok"))
            and prior_to == outreach_email.strip().lower()
            and not force_resend
            and not force_email
        )
        if already_sent:
            return True, merged_check, None

        if not smtp_ready:
            err = "SMTP not configured or disabled"
            merged_check["invite_email_failed"] = err
            merged_check.pop("invite_email_ok", None)
            merged_check.pop("invite_email_sent_at", None)
            return False, merged_check, err

        attempted_at = _now().isoformat()
        merged_check["invitation_email_attempted_at"] = attempted_at
        try:
            sent_ok, err = CareerEmailService.send_templated_critical(
                db,
                template_key="interview_booking_invite",
                to_email=outreach_email,
                variables={
                    "candidate_name": recipient.name or "there",
                    "role": role,
                    "company_name": company_name,
                    "booking_url": booking_url,
                },
            )
            if sent_ok:
                merged_check.pop("invite_email_failed", None)
                merged_check["invite_email_ok"] = True
                merged_check["invite_email_sent_at"] = _now().isoformat()
                merged_check["invite_sent_to"] = outreach_email.strip().lower()
                logger.info(
                    "interview_invite_email_sent",
                    extra={
                        "order_id": order.id,
                        "recipient_id": recipient.id,
                        "to": outreach_email,
                    },
                )
                return True, merged_check, None

            merged_check["invite_email_failed"] = err or "send_failed"
            merged_check.pop("invite_email_ok", None)
            merged_check.pop("invite_email_sent_at", None)
            logger.error(
                "interview_invite_email_failed",
                extra={
                    "order_id": order.id,
                    "recipient_id": recipient.id,
                    "to": outreach_email,
                    "error": err,
                },
            )
            return False, merged_check, err or "send_failed"
        except Exception as exc:
            merged_check["invite_email_failed"] = str(exc)
            merged_check.pop("invite_email_ok", None)
            merged_check.pop("invite_email_sent_at", None)
            logger.exception(
                "interview_invite_email_exception",
                extra={"order_id": order.id, "recipient_id": recipient.id, "to": outreach_email},
            )
            return False, merged_check, str(exc)

    @staticmethod
    def send_invites(
        db: Session,
        order: ServiceOrder,
        *,
        recipient_ids: list[str] | None = None,
        channels: list[str] | None = None,
        force_resend: bool = False,
        force_email: bool = False,
    ) -> dict[str, Any]:
        if order.service_code != "interview":
            raise ValueError("Booking invites are only for interview orders")
        _assert_order_accepts_invite_changes(order)
        if not order.scheduled_start_at or not order.scheduled_end_at:
            raise ValueError("Set the calling window (start and end) before sending booking links")

        from app.services.uk_compliance_service import UkComplianceService

        UkComplianceService.assert_order_launch_allowed(db, order)

        config = _order_config(order)
        role = str(config.get("role") or order.title or "Interview").strip()
        company_name = InterviewBookingService._org_name(db, order)
        template_row = InterviewBookingService.resolve_invite_wa_template(db, order)

        use_channels = [str(c).strip().lower() for c in (channels or ["email", "whatsapp"]) if str(c).strip()]
        if not use_channels:
            use_channels = ["email", "whatsapp"]

        from app.services.career_email_service import interview_email_delivery_status

        email_delivery = interview_email_delivery_status(db)
        smtp_ready = bool(email_delivery.get("can_send_email"))
        careers_from = str(email_delivery.get("interview_from_email") or "careers@voxbulk.com")

        recipients = ServiceOrderService.get_recipients(db, order.id)
        id_filter = {str(x).strip() for x in (recipient_ids or []) if str(x).strip()}
        if id_filter:
            recipients = [r for r in recipients if r.id in id_filter]

        logger.info(
            "interview_send_invites_start",
            extra={
                "order_id": order.id,
                "recipient_count": len(recipients),
                "channels": use_channels,
                "force_resend": force_resend,
                "force_email": force_email,
                "smtp_ready": smtp_ready,
            },
        )

        wa_sent = 0
        email_sent = 0
        skipped_locked = 0
        errors: list[str] = []

        if "email" in use_channels and not smtp_ready:
            missing = email_delivery.get("smtp_missing_fields") or []
            smtp_hint = "Enable SMTP in Admin → Email"
            if missing:
                smtp_hint += f" (missing: {', '.join(str(m) for m in missing)})"
            smtp_hint += f" — interview From is {careers_from}"
            errors.append(smtp_hint)

        from app.services.interview_cv_exclusion_service import is_auto_excluded_recipient

        for recipient in recipients:
            if is_auto_excluded_recipient(recipient):
                skipped_locked += 1
                continue
            if interview_booking_locked(recipient):
                skipped_locked += 1
                errors.append(f"{recipient.name or recipient.id}: interview already complete — invite skipped")
                continue
            outreach_email = _persist_recipient_outreach_email(db, recipient)
            if not outreach_email and "email" in use_channels:
                if recipient.phone and "whatsapp" in use_channels:
                    pass
                else:
                    errors.append(
                        f"{recipient.name or recipient.id}: no email address"
                        + (" (add email on candidate or re-upload CV with contact details)" if recipient.phone else "")
                    )
                    if "whatsapp" not in use_channels or not recipient.phone:
                        continue

            token_row = InterviewBookingService.ensure_token(db, order, recipient)
            url = booking_url_for_token(token_row.token)
            first = _first_name(recipient.name)
            recipient_email_sent = False
            recipient_wa_sent = False
            merged_pre = _recipient_result(recipient)
            merged_pre.update(
                {
                    "booking_token": token_row.token,
                    "booking_url": url,
                    "booking_invite_prepared_at": _now().isoformat(),
                }
            )
            recipient.result_json = json.dumps(merged_pre, ensure_ascii=False)
            db.add(recipient)

            if "email" in use_channels and outreach_email:
                if not smtp_ready:
                    errors.append(
                        f"{recipient.name or recipient.id}: invite email skipped — SMTP not configured or disabled"
                    )
                else:
                    counted, merged_check, email_err = InterviewBookingService.send_interview_invitation_email(
                        db,
                        order=order,
                        recipient=recipient,
                        outreach_email=outreach_email,
                        role=role,
                        company_name=company_name,
                        booking_url=url,
                        force_resend=force_resend,
                        force_email=force_email,
                        smtp_ready=smtp_ready,
                    )
                    if counted:
                        recipient_email_sent = True
                        email_sent += 1
                    elif email_err:
                        label = recipient.name or recipient.id
                        errors.append(f"{label}: Email {outreach_email}: {email_err}")
                    recipient.result_json = json.dumps(merged_check, ensure_ascii=False)
                    db.add(recipient)

            if "whatsapp" in use_channels and recipient.phone:
                from app.services.uk_compliance_opt_out import should_block_outbound_phone

                skip_reason = should_block_outbound_phone(db, org_id=order.org_id, phone_e164=recipient.phone)
                if skip_reason:
                    errors.append(f"{recipient.name} WA: blocked ({skip_reason})")
                    continue
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
                            careers_email=careers_from,
                        )
                        fallback_body = (
                            f"Dear {first}, we sent you an email from careers@voxbulk.com "
                            f"about your {role} interview at {company_name}. Please check your inbox and spam folder."
                        )
                        from app.services.interview_whatsapp_send_service import InterviewWhatsappSendService

                        log_body = f"[template:{template_row.name}] {fallback_body}"
                        result = InterviewWhatsappSendService.send_template_or_plain(
                            db,
                            to_number=str(recipient.phone),
                            body=fallback_body,
                            org_id=order.org_id,
                            template_row=template_row,
                            template_components=components,
                            template_language=template_row.language or "en_US",
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

            if recipient_email_sent or recipient_wa_sent:
                if str(recipient.status or "").lower() in {"", "pending"}:
                    recipient.status = "sent"

            merged = _recipient_result(recipient)
            now_iso = _now().isoformat()
            merged.update({"booking_token": token_row.token, "booking_url": url, "booking_invite_sent_at": now_iso})
            if recipient_email_sent:
                merged["invite_email_sent_at"] = merged.get("invite_email_sent_at") or now_iso
                merged["invite_email_ok"] = True
                merged.pop("invite_email_failed", None)
            if recipient_wa_sent:
                merged["invite_wa_sent_at"] = (token_row.wa_sent_at or _now()).isoformat()
            recipient.result_json = json.dumps(merged, ensure_ascii=False)
            db.add(recipient)

        dispatch_ok = email_sent > 0 or wa_sent > 0
        if "email" in use_channels and email_sent == 0:
            dispatch_ok = False
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

        logger.info(
            "interview_send_invites_complete",
            extra={
                "order_id": order.id,
                "email_sent": email_sent,
                "whatsapp_sent": wa_sent,
                "skipped_locked": skipped_locked,
                "error_count": len(errors),
                "ok": dispatch_ok,
            },
        )

        from app.services.career_email_service import interview_email_delivery_status

        return {
            "ok": dispatch_ok,
            "whatsapp_sent": wa_sent,
            "email_sent": email_sent,
            "skipped_locked": skipped_locked,
            "errors": errors,
            "email_delivery": interview_email_delivery_status(db),
        }
