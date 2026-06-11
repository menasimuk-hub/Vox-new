"""
Map GoCardless webhook JSON into BillingEventEmailService (payment failures + invoices).

GoCardless sends `{"events": [{ "id", "resource_type", "action", "metadata", "details", "links" }, ...]}`.

Tenant routing (required): set metadata when creating GC resources, e.g.
`metadata[org_id]` (or `organisation_id` / `retover_org_id`) and `metadata[client_email]`
(or `email`). Without these, events are skipped (logged) — no crash.
Subscription-linked payments can also resolve org/email from the local Subscription row.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.membership import OrganisationMembership
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_event_email_service import BillingEventEmailService
from app.services.invoice_service import InvoiceService

logger = logging.getLogger(__name__)

PROVIDER = "gocardless"

# Payment actions that should generate a payment_failed email (via record_payment_status).
MANDATE_CANCEL_ACTIONS = frozenset({"cancelled", "canceled", "failed", "expired", "blocked"})

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

# Successful subscription payments — invoice idempotently by payment id.
PAYMENT_SUCCESS_ACTIONS = frozenset(
    {
        "confirmed",
        "paid_out",
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

_INITIAL_DUPLICATE_WINDOW_SECONDS = 86400 * 3


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


def _resolve_org_email_from_subscription(
    db: Session,
    *,
    subscription_external_id: str,
    org_id: str,
    client_email: str,
) -> tuple[str, str, Subscription | None]:
    sub_ext = str(subscription_external_id or "").strip()
    if not sub_ext:
        return org_id, client_email, None

    sub = db.execute(
        select(Subscription).where(Subscription.external_subscription_id == sub_ext)
    ).scalar_one_or_none()
    if sub is None:
        return org_id, client_email, None

    resolved_org = org_id or str(sub.org_id)
    resolved_email = client_email
    if not resolved_email:
        org = db.get(Organisation, resolved_org)
        resolved_email = (org.contact_email if org else "") or ""
        if not resolved_email:
            membership = db.execute(
                select(OrganisationMembership)
                .where(OrganisationMembership.org_id == resolved_org)
                .limit(1)
            ).scalar_one_or_none()
            if membership is not None:
                user = db.get(User, membership.user_id)
                resolved_email = (user.email if user else "") or ""
    return resolved_org, resolved_email.strip().lower(), sub


def _org_contact_email(db: Session, org_id: str) -> str:
    org = db.get(Organisation, org_id)
    if org is not None and org.contact_email:
        return str(org.contact_email).strip().lower()
    membership = db.execute(
        select(OrganisationMembership).where(OrganisationMembership.org_id == org_id).limit(1)
    ).scalar_one_or_none()
    if membership is not None:
        user = db.get(User, membership.user_id)
        if user and user.email:
            return str(user.email).strip().lower()
    return ""


def _resolve_org_email_from_payment(
    db: Session,
    *,
    payment_id: str,
    org_id: str,
    client_email: str,
) -> tuple[str, str]:
    pid = str(payment_id or "").strip()
    if not pid:
        return org_id, client_email
    invoice = db.execute(
        select(BillingInvoice).where(BillingInvoice.dd_payment_id == pid).limit(1)
    ).scalar_one_or_none()
    if invoice is None:
        return org_id, client_email
    resolved_org = org_id or str(invoice.org_id)
    resolved_email = client_email or _org_contact_email(db, resolved_org)
    return resolved_org, resolved_email


def _payment_amount_pence(event: dict[str, Any], meta: dict[str, Any], sub: Subscription | None, db: Session) -> int:
    amount = _parse_int(_meta_get(meta, "amount_gbp_pence"))
    if amount > 0:
        return amount
    details = event.get("details")
    if isinstance(details, dict):
        amount = _parse_int(details.get("amount"))
        if amount > 0:
            return amount
    if sub is not None and sub.plan_id:
        plan = db.get(Plan, sub.plan_id)
        if plan is not None:
            return int(plan.price_gbp_pence or 0)
    return 0


def _is_duplicate_initial_payment_invoice(
    db: Session,
    *,
    org_id: str,
    subscription_external_id: str,
    amount_pence: int,
) -> bool:
    sub_ext = str(subscription_external_id or "").strip()
    if not sub_ext:
        return False
    activation_ext = f"sub:{sub_ext}:initial"
    activation = InvoiceService.get_by_external(db, provider=PROVIDER, external_invoice_id=activation_ext)
    if activation is None or activation.org_id != org_id:
        return False
    activation_subtotal = int(
        activation.subtotal_pence if activation.subtotal_pence is not None else activation.amount_gbp_pence or 0
    )
    if activation_subtotal != int(amount_pence or 0):
        return False
    created_at = activation.created_at or datetime.utcnow()
    age_seconds = (datetime.utcnow() - created_at).total_seconds()
    return age_seconds <= _INITIAL_DUPLICATE_WINDOW_SECONDS


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
        "payment_success_handled": 0,
        "invoice_handled": 0,
        "mandate_handled": 0,
        "errors": [],
    }

    for raw in events:
        if not isinstance(raw, dict):
            summary["skipped"] += 1
            continue
        resource_type = str(raw.get("resource_type") or "").strip().lower()
        action = str(raw.get("action") or "").strip().lower()
        event_id = str(raw.get("id") or "").strip()
        links = raw.get("links") if isinstance(raw.get("links"), dict) else {}
        payment_id = str(links.get("payment") or "").strip()
        subscription_id = str(links.get("subscription") or "").strip()

        logger.info(
            "gocardless_webhook_event_received",
            extra={
                "event_id": event_id,
                "resource_type": resource_type,
                "action": action,
                "payment_id": payment_id or None,
                "subscription_id": subscription_id or None,
            },
        )

        org_id, client_email = _extract_org_and_email(raw)
        sub: Subscription | None = None
        if resource_type == "payments" and (
            action in PAYMENT_SUCCESS_ACTIONS or action in PAYMENT_FAILURE_ACTIONS
        ):
            org_id, client_email, sub = _resolve_org_email_from_subscription(
                db,
                subscription_external_id=subscription_id,
                org_id=org_id,
                client_email=client_email,
            )
            if payment_id:
                org_id, client_email = _resolve_org_email_from_payment(
                    db,
                    payment_id=payment_id,
                    org_id=org_id,
                    client_email=client_email,
                )

        if not org_id or not client_email:
            logger.info(
                "gocardless_billing_webhook skip: missing org_id/client_email",
                extra={
                    "resource_type": resource_type,
                    "action": action,
                    "event_id": event_id,
                    "payment_id": payment_id or None,
                    "subscription_id": subscription_id or None,
                },
            )
            summary["skipped"] += 1
            continue

        ext_pay = _external_payment_event_id(raw)
        try:
            if resource_type == "payments" and action in PAYMENT_SUCCESS_ACTIONS and payment_id:
                meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
                amount_pence = _payment_amount_pence(raw, meta, sub, db)
                if amount_pence <= 0:
                    logger.warning(
                        "gocardless_payment_success skip: missing amount",
                        extra={
                            "event_id": event_id,
                            "payment_id": payment_id,
                            "org_id": org_id,
                        },
                    )
                    summary["skipped"] += 1
                    continue

                if _is_duplicate_initial_payment_invoice(
                    db,
                    org_id=org_id,
                    subscription_external_id=subscription_id,
                    amount_pence=amount_pence,
                ):
                    logger.info(
                        "gocardless_payment_success skip duplicate initial",
                        extra={
                            "event_id": event_id,
                            "payment_id": payment_id,
                            "subscription_id": subscription_id or None,
                            "org_id": org_id,
                        },
                    )
                    summary["skipped"] += 1
                    continue

                external_invoice_id = f"payment:{payment_id}"
                plan_name = ""
                plan = None
                if sub is not None and sub.plan_id:
                    plan = db.get(Plan, sub.plan_id)
                    plan_name = plan.name if plan else ""
                description = _meta_get(meta, "description") or (
                    f"{plan_name} — monthly subscription" if plan_name else "GoCardless subscription payment"
                )
                line_description = plan_name or description
                from app.services.billing_currency import resolve_org_currency

                org_row = db.get(Organisation, org_id)
                pay_currency = _meta_get(meta, "currency") or (
                    sub.billing_currency if sub else None
                ) or resolve_org_currency(db, org_row)

                try:
                    from app.services.billing_access_service import BillingAccessService
                    from app.services.billing_lifecycle_service import BillingLifecycleService
                    from app.services.payment_event_service import PaymentEventService

                    BillingAccessService.mark_first_payment_confirmed(db, org_id=org_id)
                    BillingLifecycleService.handle_dd_payment_success(db, payment_id=payment_id)
                    invoice, created, emailed = InvoiceService.issue_from_payment(
                        db,
                        org_id=org_id,
                        client_email=client_email,
                        subtotal_pence=amount_pence,
                        currency=pay_currency,
                        description=description,
                        provider=PROVIDER,
                        external_invoice_id=external_invoice_id,
                        payment_reference=payment_id,
                        payment_method="gocardless",
                        status="paid",
                        line_items=[
                            {
                                "description": line_description,
                                "quantity": 1,
                                "unit_pence": amount_pence,
                                "total_pence": amount_pence,
                            }
                        ],
                    )
                    if sub is not None and plan is not None and subscription_id:
                        BillingLifecycleService._advance_subscription_period(db, sub, plan)
                    PaymentEventService.record(
                        db,
                        org_id=org_id,
                        client_email=client_email,
                        status="succeeded",
                        provider=PROVIDER,
                        external_event_id=event_id or f"payment:{payment_id}",
                        event_kind="payment.succeeded",
                        source="webhook",
                        metadata={
                            "payment_id": payment_id,
                            "subscription_id": subscription_id or None,
                            "amount_pence": amount_pence,
                            "currency": pay_currency,
                        },
                    )
                    summary["payment_success_handled"] += 1
                    summary["processed"] += 1
                    from app.core.logging import safe_log_extra

                    logger.info(
                        "gocardless_payment_success_invoice",
                        extra=safe_log_extra(
                            event_id=event_id,
                            payment_id=payment_id,
                            subscription_id=subscription_id or None,
                            org_id=org_id,
                            client_email=client_email,
                            invoice_id=invoice.id,
                            external_invoice_id=external_invoice_id,
                            invoice_was_new=created,
                            emailed=emailed,
                        ),
                    )
                except Exception as exc:
                    logger.exception(
                        "gocardless_payment_success_invoice_failed",
                        extra={
                            "event_id": event_id,
                            "payment_id": payment_id,
                            "org_id": org_id,
                            "error": str(exc)[:500],
                        },
                    )
                    summary["errors"].append(str(exc)[:500])
                continue

            if resource_type == "mandates" and action in MANDATE_CANCEL_ACTIONS:
                mandate_id = str(links.get("mandate") or event_id or "").strip()
                try:
                    from app.services.billing_access_service import BillingAccessService

                    result = BillingAccessService.handle_mandate_cancelled(
                        db, org_id=org_id, mandate_id=mandate_id or None
                    )
                    summary["mandate_handled"] += 1
                    summary["processed"] += 1
                    logger.info(
                        "gocardless_mandate_cancelled",
                        extra={"org_id": org_id, "mandate_id": mandate_id, "result": result},
                    )
                except Exception as exc:
                    summary["errors"].append(str(exc)[:500])
                continue

            if resource_type == "payments" and action in PAYMENT_FAILURE_ACTIONS and ext_pay:
                st = _payment_status_for_action(action)
                dd_recovery: dict[str, Any] | None = None
                if payment_id:
                    try:
                        from app.services.billing_lifecycle_service import BillingLifecycleService

                        dd_recovery = BillingLifecycleService.handle_dd_payment_failure(
                            db,
                            payment_id=payment_id,
                            org_id=org_id,
                            client_email=client_email,
                            failure_reason=_failure_reason(raw),
                        )
                    except Exception:
                        logger.exception(
                            "dd_recovery_failure_handler_error",
                            extra={"payment_id": payment_id, "org_id": org_id},
                        )
                fail_vars: dict[str, Any] = {
                    "resource_type": resource_type,
                    "action": action,
                    "payment_id": payment_id,
                }
                if dd_recovery and dd_recovery.get("invoice_id"):
                    from app.services.billing_lifecycle_service import BillingLifecycleService

                    invoice = BillingLifecycleService.find_invoice_by_payment_id(db, payment_id)
                    if invoice is not None:
                        amount = int(
                            invoice.subtotal_pence
                            if invoice.subtotal_pence is not None
                            else invoice.amount_gbp_pence or 0
                        )
                        from app.services.billing_currency import money_display

                        fail_vars.update(
                            {
                                "invoice_number": invoice.invoice_number or invoice.external_invoice_id,
                                "amount": money_display(amount, invoice.currency or "GBP"),
                                "mandate_update_url": BillingLifecycleService._mandate_update_url(db, org_id),
                                "retry_count": str(dd_recovery.get("dd_retry_count") or ""),
                            }
                        )
                try:
                    from app.services.billing_access_service import BillingAccessService

                    BillingAccessService.handle_first_payment_failure(db, org_id=org_id)
                except Exception:
                    logger.exception("first_payment_failure_handler_error org_id=%s", org_id)
                row, _created, sent = BillingEventEmailService.record_payment_status(
                    db,
                    provider=PROVIDER,
                    external_event_id=ext_pay,
                    org_id=org_id,
                    client_email=client_email,
                    status=st,
                    failure_reason=_failure_reason(raw),
                    variables=fail_vars,
                    event_kind="payment.failed",
                    source="webhook",
                    metadata={"payment_id": payment_id, "action": action},
                )
                summary["payment_failed_handled"] += 1
                summary["processed"] += 1
                logger.info(
                    "gocardless payment billing event",
                    extra={"event_id": ext_pay, "sent": sent, "db_id": row.id, "status": st},
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
            logger.exception(
                "gocardless billing event handling error",
                extra={"event_id": event_id, "resource_type": resource_type, "action": action},
            )
            summary["errors"].append(str(e)[:500])

    return summary
