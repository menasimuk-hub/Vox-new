"""Safe assistant tool execution — never leak raw Python errors to users."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.dependencies import CurrentPrincipal
from app.models.membership import OrganisationMembership
from app.models.user import User

logger = logging.getLogger(__name__)

T = TypeVar("T")

INVOICE_READ_ERROR = "I'm having trouble reading the invoice details right now."
INVOICE_FALLBACK_HINT = "I can still show your recent usage and wallet transactions."

_GREETING = re.compile(
    r"^\s*(hi|hello|hey|howdy|good\s+(morning|afternoon|evening)|greetings)\b",
    re.I,
)

_INTERNAL_ERROR_MARKERS = (
    "traceback",
    "typeerror",
    "valueerror",
    "attributeerror",
    "keyerror",
    "nameerror",
    "missing ",
    "required positional argument",
    "not defined",
    "exception",
    "invoice_to_dict",
)


def is_greeting(message: str) -> bool:
    return bool(_GREETING.search((message or "").strip()))


def looks_like_internal_error(text: str) -> bool:
    t = (text or "").lower()
    return any(marker in t for marker in _INTERNAL_ERROR_MARKERS)


def sanitize_user_text(text: str, *, default: str = "Something went wrong. Please try again.") -> str:
    if not text or looks_like_internal_error(text):
        return default
    return text


def user_display_name(db: Session, principal: CurrentPrincipal) -> str:
    user = db.get(User, principal.user_id)
    if user and user.email:
        local = user.email.split("@", 1)[0]
        chunk = re.split(r"[.+_-]", local, maxsplit=1)[0]
        if chunk:
            return chunk[:1].upper() + chunk[1:]

    membership = db.execute(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == principal.user_id,
            OrganisationMembership.org_id == principal.org_id,
        )
    ).scalar_one_or_none()
    if membership and membership.dashboard_setup_profile_json:
        try:
            profile = json.loads(membership.dashboard_setup_profile_json)
            if isinstance(profile, dict):
                for key in ("name", "full_name", "first_name", "display_name"):
                    val = profile.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip().split()[0]
        except (json.JSONDecodeError, TypeError):
            pass

    return "there"


def run_tool(tool: str, fn: Callable[[], T], *, default: T | None = None) -> tuple[T | None, bool]:
    """Run a tool; return (result, failed). Logs failures; never raises."""
    try:
        return fn(), False
    except Exception:
        logger.exception("assistant tool failed: %s", tool)
        return default, True


def usage_summary_fragment(usage_payload: dict[str, Any] | None) -> str:
    if not usage_payload:
        return ""
    calls = usage_payload.get("calls") or {}
    wa = usage_payload.get("whatsapp") or {}
    parts: list[str] = []
    if calls:
        parts.append(f"AI calls: {calls.get('used', 0)}/{calls.get('included', 0)} min used")
    if wa:
        parts.append(f"WA surveys: {wa.get('used', 0)}/{wa.get('included', 0)} recipients used")
    return ". ".join(parts)
