"""
Map GoCardless webhook JSON into BillingEventEmailService (payment failures + invoices).

GoCardless sends `{"events": [{ "id", "resource_type", "action", "metadata", "details", "links" }, ...]}`.

Tenant routing (required): set metadata when creating GC resources, e.g.
`metadata[org_id]` (or `organisation_id` / `retover_org_id`) and `metadata[client_email]`
(or `email`). Without these, events are skipped (logged) — no crash.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.billing_event_email_service import BillingEventEmailService

logger = logging.getLogger(__name__)

PROVIDER = "gocardless"

# Payment actions that should generate a payment_failed email (via record_payment_status).
PAYMENT_FAILURE_ACTIONS = frozenset(
    {
        "failed",
        "charged_back",
        "cancelled",
        "canceled",
        "customer_approval_denied",
        "late_failure_settled",
    }
)

# Invoice-style resources (GoCardless Invoicing / compatible shapes).
INVOICE_RESOURCE_TYPES = frozenset({"invoices", "invoice"})
INVOICE_CREATE_ACTIONS = frozenset(
    {
        "invoice_created",
        "created",
        "issued",
        "scheduled",
    }
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.I,
)


def _meta_get(meta: Any, *keys: str) -> str:
    if not isinstance(meta, dict):
        return ""
    for k in keys:
        v = meta.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _parse_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _extract_org_and_email(event: dict[str, Any]) -> tuple[str, str]:
    meta = event.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    details = event.get("details")
    detail_meta: dict[str, Any] = {}
    if isinstance(details, dict):
        dm = details.get("metadata")
        if isinstance(dm, dict):
            detail_meta = dm

    def from_maps(*ks: str) -> tuple[str, str]:
        o = _meta_get(meta, *ks) or _meta_get(detail_meta, *ks)
        e = _meta_get(meta, "client_email", "email", "customer_email") or _meta_get(
            detail_meta, "client_email", "email", "customer_email"
        )
        return o, e

    org_id, email = from_maps("org_id", "organisation_id", "retover_org_id", "organisationId")
    if org_id and not _UUID_RE.match(org_id):
        logger.warning("gocardless_billing_webhook ignored: org_id not a UUID", extra={"org_id": org_id[:64]})
        return "", ""
    return org_id.strip(), email.strip().lower()


def _payment_status_for_action(action: str) -> str:
    a = (action or "").strip().lower()
    if a == "customer_approval_denied":
        return "declined"
    if a in {"charged_back", "late_failure_settled"}:
        return "failed"
    if a in {"cancelled", "canceled"}:
        return "canceled"
    return a or "unknown"


def _failure_reason(event: dict[str, Any]) -> str | None:
    details = event.get("details")
    if not isinstance(details, dict):
        return None
    parts = [
        details.get("description"),
        details.get("cause"),
        details.get("reason_code"),
    ]
    out = " — ".join(str(p).strip() for p in parts if p is not None and str(p).strip())
    return out or None


def _external_payment_event_id(event: dict[str, Any]) -> str:
    eid = str(event.get("id") or "").strip()
    if eid:
        return eid
    links = event.get("links") if isinstance(event, dict) else None
    if isinstance(links, dict):
        pay = links.get("payment") or links.get("payments")
        act = event.get("action") if isinstance(event, dict) else None
        if pay and act:
            return f"{pay}:{act}"
    return ""


def _external_invoice_id(event: dict[str, Any]) -> str:
    links = event.get("links") if isinstance(event, dict) else None
    if isinstance(links, dict):
        for k in ("invoice", "invoices"):
            if links.get(k):
                return str(links[k]).strip()
    meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    ext = _meta_get(meta, "external_invoice_id", "invoice_id")
    if ext:
        return ext
    eid = event.get("id") if isinstance(event, dict) else None
    return str(eid or "").strip()


def apply_gocardless_billing_events(db: Session, events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Apply supported billing-related GoCardless events. Idempotent via BillingEventEmailService.
    """
    summary: dict[str, Any] = {
        "processed": 0,
        "skipped": 0,
        "payment_failed_handled": 0,
        "invoice_handled": 0,
        "errors": [],
    }

    for raw in events:
        if not isinstance(raw, dict):
            summary["skipped"] += 1
            continue
        resource_type = str(raw.get("resource_type") or "").strip().lower()
        action = str(raw.get("action") or "").strip().lower()

        org_id, client_email = _extract_org_and_email(raw)
        if not org_id or not client_email:
            logger.info(
                "gocardless_billing_webhook skip: missing org_id/client_email in metadata",
                extra={"resource_type": resource_type, "action": action, "event_id": raw.get("id")},
            )
            summary["skipped"] += 1
            continue

        ext_pay = _external_payment_event_id(raw)
        try:
            if resource_type == "payments" and action in PAYMENT_FAILURE_ACTIONS and ext_pay:
                st = _payment_status_for_action(action)
                row, _created, sent = BillingEventEmailService.record_payment_status(
                    db,
                    provider=PROVIDER,
                    external_event_id=ext_pay,
                    org_id=org_id,
                    client_email=client_email,
                    status=st,
                    failure_reason=_failure_reason(raw),
                    variables={
                        "resource_type": resource_type,
                        "action": action,
                        "payment_id": str((raw.get("links") or {}).get("payment") or ""),
                    },
                )
                summary["payment_failed_handled"] += 1
                summary["processed"] += 1
                logger.info(
                    "gocardless payment billing event",
                    extra={"event_id": ext_pay, "sent": sent, "db_id": row.id},
                )
                continue

            if resource_type in INVOICE_RESOURCE_TYPES and action in INVOICE_CREATE_ACTIONS:
                inv_id = _external_invoice_id(raw)
                if not inv_id:
                    summary["skipped"] += 1
                    continue
                meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
                amount = _parse_int(meta.get("amount_gbp_pence"))
                currency = _meta_get(meta, "currency") or "GBP"
                status_str = _meta_get(meta, "invoice_status") or "issued"

                row, _created, sent = BillingEventEmailService.create_invoice(
                    db,
                    provider=PROVIDER,
                    external_invoice_id=inv_id,
                    org_id=org_id,
                    client_email=client_email,
                    amount_gbp_pence=amount or 0,
                    currency=currency or "GBP",
                    status=status_str or "issued",
                    variables={
                        "resource_type": resource_type,
                        "action": action,
                    },
                )
                summary["invoice_handled"] += 1
                summary["processed"] += 1
                logger.info(
                    "gocardless invoice billing event",
                    extra={"invoice_id": inv_id, "sent": sent, "db_row": row.id},
                )
                continue

            summary["skipped"] += 1

        except Exception as e:
            logger.exception("gocardless billing event handling error")
            summary["errors"].append(str(e)[:500])

    return summary
