"""Organisation control center — enriched list rows and detail payloads for admin UI."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.subscription import Subscription
from app.services.admin_org_service import AdminOrganisationService
from app.services.invoice_service import InvoiceService
from app.services.market_zone import country_column_matches_zone, country_to_zone, normalize_zone, zone_label
from app.services.org_audit_service import OrgAuditService
from app.services.org_billing_profile_service import money_for_org, resolve_org_billing_profile, sync_org_country_code
from app.services.org_control_center_actions_service import OrgControlCenterActionsService
from app.services.platform_catalog_service import ServiceOrderService
from app.services.usage_wallet_service import UsageWalletService

_COMPLETED_RECIPIENT = frozenset({"completed", "done", "answered", "finished"})
_FAILED_RECIPIENT = frozenset({"failed", "error", "cancelled", "rejected", "no_answer", "busy"})


def _payment_status_from_invoices(invoices: list) -> str:
    statuses = {str(getattr(inv, "status", "") or "").lower() for inv in invoices}
    if "overdue" in statuses:
        return "overdue"
    openish = statuses & {"due", "open", "sent", "pending", "unpaid", "collecting", "issued"}
    if openish:
        return "due"
    if statuses & {"paid"}:
        return "paid"
    return "paid"


def _usage_metrics(db: Session, org: Organisation, usage_row) -> dict[str, Any]:
    profile = resolve_org_billing_profile(db, org)
    from app.services.billing_monitor_service import BillingMonitorService

    if usage_row is None:
        monitor = BillingMonitorService.build_for_org(db, org, usage_row=None, pending_overage_pence=0)
        flat = BillingMonitorService.flatten_for_admin(monitor)
        return {
            **flat,
            "calls_included": 0,
            "calls_remaining": 0,
            "wa_included": 0,
            "wa_remaining": 0,
            "sms_included": 0,
            "sms_remaining": 0,
            "allow_overage": profile.get("allow_overage", True),
            "period_start": None,
            "period_end": None,
            "billing_currency": profile.get("billing_currency"),
            "currency_symbol": profile.get("currency_symbol"),
            "billing_monitor": monitor,
        }

    summary = UsageWalletService.summary_dict(usage_row, db, org.id if org else None)
    total_overage = UsageWalletService._calc_overage_pence(usage_row, db, org.id)
    pending_overage = max(0, total_overage - int(usage_row.overage_invoiced_pence or 0))
    monitor = BillingMonitorService.build_for_org(db, org, usage_row=usage_row, pending_overage_pence=pending_overage)
    flat = BillingMonitorService.flatten_for_admin(monitor)
    calls = summary.get("calls") or {}
    wa = summary.get("whatsapp") or {}
    sms = summary.get("sms") or {}
    allow_overage = bool(getattr(org, "allow_overage", True))
    return {
        **flat,
        "calls_included": int(calls.get("included") or 0),
        "calls_remaining": int(calls.get("remaining") or 0),
        "wa_included": int(wa.get("included") or 0),
        "wa_remaining": int(wa.get("remaining") or 0),
        "sms_included": int(sms.get("included") or 0),
        "sms_remaining": int(sms.get("remaining") or 0),
        "allow_overage": allow_overage,
        "period_start": summary.get("period_start"),
        "period_end": summary.get("period_end"),
        "billing_currency": profile.get("billing_currency"),
        "currency_symbol": profile.get("currency_symbol"),
        "billing_monitor": monitor,
        # Legacy aliases for shared pool list rows
        "package_remaining": int(flat.get("package_remaining_units") or 0),
        "package_included": int(flat.get("package_included_units") or 0),
        "package_used": int(flat.get("package_used_units") or 0),
    }


def _load_order_config(order: ServiceOrder) -> dict[str, Any]:
    try:
        config = json.loads(order.config_json or "{}")
    except Exception:
        config = {}
    return config if isinstance(config, dict) else {}


def _recipient_bucket(status: str | None) -> str:
    s = str(status or "").lower()
    if s in _COMPLETED_RECIPIENT:
        return "done"
    if s in _FAILED_RECIPIENT:
        return "failed"
    return "in_progress"


def _campaign_stats(db: Session, order: ServiceOrder) -> dict[str, int]:
    rows = list(
        db.execute(select(ServiceOrderRecipient.status).where(ServiceOrderRecipient.order_id == order.id)).all()
    )
    done = failed = inprog = 0
    for (status,) in rows:
        bucket = _recipient_bucket(status)
        if bucket == "done":
            done += 1
        elif bucket == "failed":
            failed += 1
        else:
            inprog += 1
    total = int(order.recipient_count or 0) or (done + failed + inprog)
    return {"total": total, "done": done, "failed": failed, "in_progress": inprog}


def _order_channel(order: ServiceOrder) -> str:
    config = _load_order_config(order)
    if order.service_code == "interview":
        mode = str(config.get("delivery_mode") or config.get("channel") or "ai_call").lower()
        if "zoom" in mode:
            return "zoom"
        return "ai_call"
    ch = str(config.get("survey_channel") or config.get("channel") or "call").lower()
    if ch in {"whatsapp", "wa"}:
        return "whatsapp"
    if ch in {"sms"}:
        return "sms"
    return "call"


def _service_label(order: ServiceOrder) -> str:
    if order.service_code == "interview":
        ch = _order_channel(order)
        return "Zoom Interview" if ch == "zoom" else "AI Interview"
    ch = _order_channel(order)
    if ch == "whatsapp":
        return "WhatsApp Survey"
    if ch == "sms":
        return "SMS Survey"
    return "Call Survey"


def _search_org_ids(db: Session, term: str) -> set[str] | None:
    q = term.strip()
    if not q:
        return None
    like = f"%{q}%"
    org_ids: set[str] = set()
    for row in db.execute(
        select(Organisation.id).where(
            or_(
                Organisation.name.ilike(like),
                Organisation.id.ilike(like),
                Organisation.contact_email.ilike(like),
                Organisation.contact_phone.ilike(like),
                Organisation.country.ilike(like),
            )
        )
    ).all():
        org_ids.add(row[0])
    for row in db.execute(select(ServiceOrder.org_id).where(ServiceOrder.id.ilike(like))).all():
        org_ids.add(row[0])
    return org_ids


class OrgControlCenterService:
    @staticmethod
    def list_rows(
        db: Session,
        *,
        limit: int = 200,
        offset: int = 0,
        search: str | None = None,
        country: str | None = None,
        status: str | None = None,
        plan_code: str | None = None,
        payment_status: str | None = None,
        campaign_status: str | None = None,
        channel: str | None = None,
        overage_only: bool = False,
        invoices_due_only: bool = False,
        running_campaigns_only: bool = False,
    ) -> dict[str, Any]:
        zone_key = normalize_zone(country)
        search_ids = _search_org_ids(db, search) if search else None

        org_query = select(Organisation).order_by(Organisation.created_at.desc())
        if zone_key:
            org_query = org_query.where(country_column_matches_zone(Organisation.country, zone_key))
        if search_ids is not None:
            if not search_ids:
                return {"items": [], "count": 0}
            org_query = org_query.where(Organisation.id.in_(list(search_ids)))

        org_rows = list(db.execute(org_query.limit(max(1, min(limit, 500))).offset(max(0, offset))).scalars().all())
        items: list[dict[str, Any]] = []

        for org in org_rows:
            sync_org_country_code(db, org, commit=False)
            o = AdminOrganisationService.get_org_summary(db, org_id=org.id)
            if o is None:
                continue

            usage_row = UsageWalletService.get_current(db, org.id)
            if usage_row is None:
                sub = db.execute(
                    select(Subscription)
                    .where(Subscription.org_id == org.id)
                    .order_by(Subscription.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if sub is not None:
                    usage_row = UsageWalletService.bootstrap_from_plan(db, org_id=org.id, subscription=sub)

            profile = resolve_org_billing_profile(db, org)
            usage = _usage_metrics(db, org, usage_row)
            invoices = InvoiceService.list_for_org(db, org_id=org.id, limit=50)
            open_invoices = [
                inv
                for inv in invoices
                if str(getattr(inv, "status", "") or "").lower()
                in {"due", "open", "sent", "pending", "unpaid", "overdue", "collecting", "issued"}
            ]
            pay_status = _payment_status_from_invoices(invoices)

            running_campaigns = int(
                db.execute(
                    select(func.count())
                    .select_from(ServiceOrder)
                    .where(
                        ServiceOrder.org_id == org.id,
                        ServiceOrder.status.in_(("running", "paused", "scheduled", "paid")),
                    )
                ).scalar_one()
                or 0
            )

            row_status = "frozen" if org.is_suspended else "active"
            wallet_pence = int(org.wallet_balance_pence or 0)

            item = {
                "id": org.id,
                "name": org.name,
                "company": org.name,
                "status": row_status,
                "plan": o.plan_name or o.plan_code or "—",
                "plan_code": o.plan_code,
                "wallet_pence": wallet_pence,
                "wallet_display": profile.get("wallet_display") or money_for_org(db, org, wallet_pence),
                "survey_credits": int(org.survey_credits_balance or 0),
                "interview_credits": int(org.interview_credits_balance or 0),
                "payment_status": pay_status,
                "subscription_status": o.subscription_status,
                "campaigns": running_campaigns,
                "invoices": len(open_invoices),
                "contact_email": org.contact_email,
                "contact_phone": org.contact_phone,
                "country": org.country,
                "country_code": profile.get("country_code"),
                "market_zone": profile.get("market_zone"),
                "market_label": profile.get("market_label"),
                "billing_currency": profile.get("billing_currency"),
                "currency_symbol": profile.get("currency_symbol"),
                "allow_overage": profile.get("allow_overage", True),
                **usage,
            }

            if status and item["status"] != status:
                continue
            if plan_code and str(o.plan_code or "").lower() != plan_code.lower():
                continue
            if payment_status and item["payment_status"] != payment_status:
                continue
            if overage_only and not item["overage_risk"]:
                continue
            if invoices_due_only and item["invoices"] <= 0:
                continue
            if running_campaigns_only and item["campaigns"] <= 0:
                continue
            if campaign_status:
                has_status = bool(
                    db.execute(
                        select(func.count())
                        .select_from(ServiceOrder)
                        .where(ServiceOrder.org_id == org.id, ServiceOrder.status == campaign_status)
                    ).scalar_one()
                )
                if not has_status:
                    continue
            if channel:
                orders = ServiceOrderService.list_orders(db, org_id=org.id, limit=30)
                if not any(_order_channel(o_) == channel for o_ in orders):
                    continue

            items.append(item)

        db.commit()
        return {"items": items, "count": len(items)}

    @staticmethod
    def get_detail(db: Session, org_id: str) -> dict[str, Any] | None:
        o = AdminOrganisationService.get_org_summary(db, org_id=org_id)
        if o is None:
            return None

        org = db.get(Organisation, org_id)
        if org is None:
            return None

        sync_org_country_code(db, org)
        profile = resolve_org_billing_profile(db, org)

        usage_row = UsageWalletService.get_current(db, org_id)
        if usage_row is None:
            sub = db.execute(
                select(Subscription)
                .where(Subscription.org_id == org_id)
                .order_by(Subscription.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if sub is not None:
                usage_row = UsageWalletService.bootstrap_from_plan(db, org_id=org_id, subscription=sub)

        usage = _usage_metrics(db, org, usage_row)
        usage_full = UsageWalletService.summary_dict(usage_row, db, org_id) if usage_row else None

        sub = db.execute(
            select(Subscription)
            .where(Subscription.org_id == org_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        orders = ServiceOrderService.list_orders(db, org_id=org_id, limit=100)
        campaigns = []
        for order in orders:
            stats = _campaign_stats(db, order)
            od = ServiceOrderService.order_to_admin_dict(db, order)
            od["quote_display"] = money_for_org(db, org, int(order.quote_total_pence or 0))
            campaigns.append(
                {
                    **od,
                    "service_label": _service_label(order),
                    "channel": _order_channel(order),
                    "progress": stats,
                }
            )

        invoices = InvoiceService.list_for_org(db, org_id=org_id, limit=100)
        invoice_dicts = [InvoiceService.invoice_to_dict(db, inv) for inv in invoices]
        open_invoices = [
            inv
            for inv in invoices
            if str(getattr(inv, "status", "") or "").lower()
            in {"due", "open", "sent", "pending", "unpaid", "overdue", "collecting", "issued"}
        ]

        currency = profile.get("billing_currency") or "GBP"
        paid_total = sum(int(getattr(inv, "amount_gbp_pence", 0) or 0) for inv in invoices if str(inv.status).lower() == "paid")
        outstanding = sum(
            int(getattr(inv, "amount_gbp_pence", 0) or 0)
            for inv in invoices
            if str(inv.status).lower() in {"due", "open", "sent", "pending", "unpaid", "collecting", "issued"}
        )
        overdue_total = sum(
            int(getattr(inv, "amount_gbp_pence", 0) or 0) for inv in invoices if str(inv.status).lower() == "overdue"
        )

        activity = OrgAuditService.list_events(db, org_id, limit=200)
        wallet_pence = int(org.wallet_balance_pence or 0)
        wallet_history = OrgControlCenterActionsService.wallet_history(db, org_id, limit=100)

        last_paid = next(
            (
                inv
                for inv in sorted(invoices, key=lambda x: x.created_at or datetime.min, reverse=True)
                if str(inv.status).lower() == "paid"
            ),
            None,
        )
        last_invoice = invoices[0] if invoices else None

        return {
            "organisation": {
                "id": org.id,
                "name": org.name,
                "company": org.name,
                "status": "frozen" if org.is_suspended else "active",
                "is_suspended": org.is_suspended,
                "plan": o.plan_name or o.plan_code or "—",
                "plan_code": o.plan_code,
                "plan_name": o.plan_name,
                "subscription_status": o.subscription_status,
                "payment_method": profile.get("payment_method") or "—",
                "payment_status": _payment_status_from_invoices(invoices),
                "wallet_pence": wallet_pence,
                "wallet_display": profile.get("wallet_display") or money_for_org(db, org, wallet_pence),
                "survey_credits": int(org.survey_credits_balance or 0),
                "interview_credits": int(org.interview_credits_balance or 0),
                "profile_notes": org.profile_notes,
                "contact_name": org.contact_name,
                "contact_email": org.contact_email,
                "contact_phone": org.contact_phone,
                "billing_email": profile.get("billing_email"),
                "country": org.country,
                "country_code": profile.get("country_code"),
                "market_zone": profile.get("market_zone"),
                "market_label": profile.get("market_label"),
                "billing_currency": currency,
                "currency_symbol": profile.get("currency_symbol"),
                "allow_overage": profile.get("allow_overage", True),
                "billing_start": usage.get("period_start"),
                "billing_end": usage.get("period_end"),
                "last_payment": (
                    f"{money_for_org(db, org, int(last_paid.amount_gbp_pence or 0))} on "
                    f"{(last_paid.created_at.date().isoformat() if last_paid.created_at else '—')}"
                    if last_paid
                    else "—"
                ),
                "last_invoice": getattr(last_invoice, "invoice_number", None) or (last_invoice.id if last_invoice else None),
                "open_invoices": len(open_invoices),
                "running_campaigns": sum(
                    1 for c in campaigns if str(c.get("status") or "") in {"running", "paused", "scheduled", "paid"}
                ),
                **usage,
            },
            "billing_profile": profile,
            "usage": usage_full,
            "orders": campaigns,
            "campaigns": campaigns,
            "invoices": invoice_dicts,
            "wallet_history": wallet_history,
            "invoice_summary": {
                "total_pence": sum(int(getattr(inv, "amount_gbp_pence", 0) or 0) for inv in invoices),
                "total_display": money_for_org(db, org, sum(int(getattr(inv, "amount_gbp_pence", 0) or 0) for inv in invoices)),
                "paid_pence": paid_total,
                "paid_display": money_for_org(db, org, paid_total),
                "outstanding_pence": outstanding,
                "outstanding_display": money_for_org(db, org, outstanding),
                "overdue_pence": overdue_total,
                "overdue_display": money_for_org(db, org, overdue_total),
                "currency": currency,
            },
            "activity": activity,
        }
