"""Organisation control center — enriched list rows and detail payloads for admin UI."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.org_usage_period import OrgUsagePeriod
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.service_order import ServiceOrder, ServiceOrderRecipient
from app.models.subscription import Subscription
from app.services.account_deletion_service import AccountDeletionService
from app.services.admin_org_service import AdminOrganisationService
from app.services.billing_access_service import BillingAccessService
from app.services.invoice_service import InvoiceService
from app.services.market_zone import country_column_matches_zone, country_to_zone, normalize_zone, zone_label
from app.services.org_audit_service import OrgAuditService
from app.services.country_vat_service import CountryVatService
from app.services.org_billing_profile_service import money_for_org, resolve_org_billing_profile, sync_org_country_code
from app.services.org_control_center_actions_service import OrgControlCenterActionsService
from app.services.platform_catalog_service import ServiceOrderService
from app.services.usage_wallet_service import UsageWalletService

_COMPLETED_RECIPIENT = frozenset({"completed", "done", "answered", "finished"})
_FAILED_RECIPIENT = frozenset({"failed", "error", "cancelled", "rejected", "no_answer", "busy"})
_OPEN_INVOICE_STATUSES = frozenset({"due", "open", "sent", "pending", "unpaid", "overdue", "collecting", "issued"})
_RUNNING_CAMPAIGN_STATUSES = ("running", "paused", "scheduled", "paid")


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


def _usage_metrics(db: Session, org: Organisation, usage_row, *, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = profile or resolve_org_billing_profile(db, org)
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


def _order_channel(order: ServiceOrder, recipients: list | None = None) -> str:
    config = _load_order_config(order)
    if order.service_code == "interview":
        if recipients:
            from app.services.interview_session_billing_service import summarize_interview_sessions

            stats = summarize_interview_sessions(recipients)
            if stats.get("interview_format") == "web":
                return "meeting"
            if stats.get("interview_format") == "mixed":
                return "mixed"
        mode = str(config.get("delivery_mode") or config.get("delivery") or config.get("channel") or "ai_call").lower()
        if mode in {"ai_meeting", "meeting"}:
            return "meeting"
        return "ai_call"
    ch = str(config.get("survey_channel") or config.get("channel") or "call").lower()
    if ch in {"whatsapp", "wa"}:
        return "whatsapp"
    if ch in {"sms"}:
        return "sms"
    return "call"


def _service_label(order: ServiceOrder, recipients: list | None = None) -> str:
    if order.service_code == "interview":
        ch = _order_channel(order, recipients)
        if ch == "meeting":
            return "Web interview"
        if ch == "mixed":
            return "Phone + web interview"
        return "AI Interview"
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
    from app.models.billing_invoice import BillingInvoice

    for row in db.execute(
        select(BillingInvoice.org_id).where(
            or_(
                BillingInvoice.invoice_number.ilike(like),
                BillingInvoice.external_invoice_id.ilike(like),
                BillingInvoice.id.ilike(like),
            )
        )
    ).all():
        org_ids.add(row[0])
    return org_ids


def _batch_usage_rows(db: Session, org_ids: list[str]) -> dict[str, OrgUsagePeriod]:
    if not org_ids:
        return {}
    now = datetime.utcnow()
    rows = list(
        db.execute(
            select(OrgUsagePeriod)
            .where(OrgUsagePeriod.org_id.in_(org_ids), OrgUsagePeriod.period_end >= now)
            .order_by(
                OrgUsagePeriod.org_id.asc(),
                OrgUsagePeriod.period_end.desc(),
                OrgUsagePeriod.updated_at.desc(),
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, OrgUsagePeriod] = {}
    for row in rows:
        if row.org_id not in out:
            out[row.org_id] = row
    return out


def _batch_invoices_by_org(db: Session, org_ids: list[str]) -> dict[str, list[BillingInvoice]]:
    if not org_ids:
        return {}
    rows = list(
        db.execute(
            select(BillingInvoice)
            .where(BillingInvoice.org_id.in_(org_ids))
            .order_by(BillingInvoice.created_at.desc())
        )
        .scalars()
        .all()
    )
    out: dict[str, list[BillingInvoice]] = {oid: [] for oid in org_ids}
    for inv in rows:
        bucket = out.get(inv.org_id)
        if bucket is not None:
            bucket.append(inv)
    return out


def _batch_running_campaign_counts(db: Session, org_ids: list[str]) -> dict[str, int]:
    if not org_ids:
        return {}
    rows = db.execute(
        select(ServiceOrder.org_id, func.count())
        .select_from(ServiceOrder)
        .where(
            ServiceOrder.org_id.in_(org_ids),
            ServiceOrder.status.in_(_RUNNING_CAMPAIGN_STATUSES),
        )
        .group_by(ServiceOrder.org_id)
    ).all()
    return {str(oid): int(count or 0) for oid, count in rows}


def _batch_orgs_with_campaign_status(db: Session, org_ids: list[str], campaign_status: str) -> set[str]:
    if not org_ids or not campaign_status:
        return set()
    rows = db.execute(
        select(ServiceOrder.org_id.distinct()).where(
            ServiceOrder.org_id.in_(org_ids),
            ServiceOrder.status == campaign_status,
        )
    ).all()
    return {str(row[0]) for row in rows}


def _batch_orgs_with_channel(db: Session, org_ids: list[str], channel: str, *, per_org_limit: int = 30) -> set[str]:
    if not org_ids or not channel:
        return set()
    orders = list(
        db.execute(
            select(ServiceOrder)
            .where(ServiceOrder.org_id.in_(org_ids))
            .order_by(ServiceOrder.org_id.asc(), ServiceOrder.created_at.desc())
        )
        .scalars()
        .all()
    )
    seen: dict[str, int] = {}
    matched: set[str] = set()
    for order in orders:
        oid = str(order.org_id)
        count = seen.get(oid, 0)
        if count >= per_org_limit:
            continue
        seen[oid] = count + 1
        if _order_channel(order) == channel:
            matched.add(oid)
    return matched


def _batch_plan_fields(
    db: Session,
    org_ids: list[str],
    subs_by_org: dict[str, dict[str, Subscription]],
) -> dict[str, dict[str, Any]]:
    plan_ids: set[str] = set()
    for bucket in subs_by_org.values():
        for sub in bucket.values():
            if sub and sub.plan_id:
                plan_ids.add(str(sub.plan_id))

    plans: dict[str, Plan] = {}
    if plan_ids:
        plans = {
            str(p.id): p
            for p in db.execute(select(Plan).where(Plan.id.in_(list(plan_ids)))).scalars().all()
        }

    out: dict[str, dict[str, Any]] = {}
    for org_id in org_ids:
        org_subs = subs_by_org.get(org_id, {})
        core_sub = org_subs.get("voxbulk")
        core_plan = plans.get(str(core_sub.plan_id)) if core_sub and core_sub.plan_id else None
        if core_sub is not None and core_plan is not None and not BillingAccessService.is_valid_core_plan(db, core_plan):
            core_sub = None
            core_plan = None

        feedback_sub = org_subs.get("customer_feedback")
        if feedback_sub is not None and str(feedback_sub.status or "").lower() in {"cancelled", "inactive"}:
            feedback_sub = None
        feedback_plan = plans.get(str(feedback_sub.plan_id)) if feedback_sub and feedback_sub.plan_id else None

        out[org_id] = {
            "subscription_status": core_sub.status if core_sub else None,
            "plan_code": core_plan.code if core_plan else None,
            "plan_name": core_plan.name if core_plan else None,
            "core_plan_code": core_plan.code if core_plan else None,
            "core_plan_name": core_plan.name if core_plan else None,
            "core_subscription_status": core_sub.status if core_sub else None,
            "feedback_plan_code": feedback_plan.code if feedback_plan else None,
            "feedback_plan_name": feedback_plan.name if feedback_plan else None,
            "feedback_subscription_status": feedback_sub.status if feedback_sub else None,
        }
    return out


def _light_billing_profile(db: Session, org: Organisation, core_sub: Subscription | None) -> dict[str, Any]:
    country_code = str(getattr(org, "country_code", None) or CountryVatService.resolve_org_country_code(db, org)).upper()[:2]
    market_zone = country_to_zone(org.country or country_code)
    from app.services.billing_currency import currency_symbol, resolve_org_currency

    currency = resolve_org_currency(db, org)
    sub_payment = None
    if core_sub is not None:
        sub_payment = getattr(core_sub, "payment_provider", None) or getattr(core_sub, "provider", None)
    return {
        "country": org.country,
        "country_code": country_code,
        "market_zone": market_zone,
        "market_label": zone_label(market_zone),
        "billing_currency": currency,
        "currency_symbol": currency_symbol(currency),
        "wallet_display": money_for_org(db, org, int(org.wallet_balance_pence or 0)),
        "billing_email": org.contact_email,
        "contact_email": org.contact_email,
        "allow_overage": bool(getattr(org, "allow_overage", True)),
        "payment_method": sub_payment,
    }


def _filter_invoice_dicts(invoices: list[dict[str, Any]], *, search: str | None = None) -> list[dict[str, Any]]:
    term = str(search or "").strip().lower()
    if not term:
        return invoices
    out: list[dict[str, Any]] = []
    for inv in invoices:
        if not isinstance(inv, dict):
            continue
        hay = " ".join(
            str(inv.get(k) or "")
            for k in ("invoice_number", "external_invoice_id", "id", "description")
        ).lower()
        if term in hay:
            out.append(inv)
    return out


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
        if not org_rows:
            return {"items": [], "count": 0}

        org_ids = [org.id for org in org_rows]
        subs_by_org = AdminOrganisationService._subs_by_org_service(db, org_ids)
        plan_fields_by_org = _batch_plan_fields(db, org_ids, subs_by_org)
        usage_by_org = _batch_usage_rows(db, org_ids)
        invoices_by_org = _batch_invoices_by_org(db, org_ids)
        running_campaigns_by_org = _batch_running_campaign_counts(db, org_ids)

        campaign_status_orgs: set[str] | None = None
        if campaign_status:
            campaign_status_orgs = _batch_orgs_with_campaign_status(db, org_ids, campaign_status)

        channel_orgs: set[str] | None = None
        if channel:
            channel_orgs = _batch_orgs_with_channel(db, org_ids, channel)

        items: list[dict[str, Any]] = []

        for org in org_rows:
            o = plan_fields_by_org.get(org.id, {})
            org_subs = subs_by_org.get(org.id, {})
            core_sub = org_subs.get("voxbulk")

            usage_row = usage_by_org.get(org.id)
            profile = _light_billing_profile(db, org, core_sub)
            usage = _usage_metrics(db, org, usage_row, profile=profile)
            invoices = invoices_by_org.get(org.id, [])
            open_invoices = [
                inv
                for inv in invoices
                if str(getattr(inv, "status", "") or "").lower() in _OPEN_INVOICE_STATUSES
            ]
            pay_status = _payment_status_from_invoices(invoices)
            running_campaigns = running_campaigns_by_org.get(org.id, 0)

            row_status = "frozen" if org.is_suspended else "active"
            wallet_pence = int(org.wallet_balance_pence or 0)

            item = {
                "id": org.id,
                "name": org.name,
                "company": org.name,
                "status": row_status,
                "plan": o.get("core_plan_name") or o.get("core_plan_code") or "—",
                "plan_code": o.get("core_plan_code"),
                "core_plan": o.get("core_plan_name") or o.get("core_plan_code") or "—",
                "core_plan_code": o.get("core_plan_code"),
                "core_plan_name": o.get("core_plan_name"),
                "core_subscription_status": o.get("core_subscription_status"),
                "feedback_plan": o.get("feedback_plan_name") or o.get("feedback_plan_code") or "—",
                "feedback_plan_code": o.get("feedback_plan_code"),
                "feedback_plan_name": o.get("feedback_plan_name"),
                "feedback_subscription_status": o.get("feedback_subscription_status"),
                "wallet_pence": wallet_pence,
                "wallet_display": profile.get("wallet_display") or money_for_org(db, org, wallet_pence),
                "survey_credits": int(org.survey_credits_balance or 0),
                "interview_credits": int(org.interview_credits_balance or 0),
                "payment_status": pay_status,
                "subscription_status": o.get("subscription_status"),
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
            if plan_code and str(o.get("plan_code") or "").lower() != plan_code.lower():
                continue
            if payment_status and item["payment_status"] != payment_status:
                continue
            if overage_only and not item["overage_risk"]:
                continue
            if invoices_due_only and item["invoices"] <= 0:
                continue
            if running_campaigns_only and item["campaigns"] <= 0:
                continue
            if campaign_status_orgs is not None and org.id not in campaign_status_orgs:
                continue
            if channel_orgs is not None and org.id not in channel_orgs:
                continue

            items.append(item)

        return {"items": items, "count": len(items)}

    @staticmethod
    def get_detail(db: Session, org_id: str, *, invoice_search: str | None = None) -> dict[str, Any] | None:
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
            core_sub = BillingAccessService.get_valid_core_subscription(db, org_id)
            if core_sub is not None:
                usage_row = UsageWalletService.bootstrap_from_plan(db, org_id=org_id, subscription=core_sub)

        usage = _usage_metrics(db, org, usage_row)
        usage_full = UsageWalletService.summary_dict(usage_row, db, org_id) if usage_row else None

        core_sub = BillingAccessService.get_valid_core_subscription(db, org_id)
        from app.services.subscription_summary_service import SubscriptionSummaryService

        sub_summary = SubscriptionSummaryService.build_org_summary(db, org_id)

        orders = ServiceOrderService.list_orders(db, org_id=org_id, limit=100)
        campaigns = []
        for order in orders:
            stats = _campaign_stats(db, order)
            recs = ServiceOrderService.get_recipients(db, order.id) if order.service_code == "interview" else None
            od = ServiceOrderService.order_to_admin_dict(
                db,
                order,
                include_recipients=order.service_code == "interview",
                recipients=recs,
            )
            od["quote_display"] = money_for_org(db, org, int(order.quote_total_pence or 0))
            campaigns.append(
                {
                    **od,
                    "service_label": _service_label(order, recs),
                    "channel": _order_channel(order, recs),
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

        subscription_finance = sub_summary.get("core")
        feedback_subscription_finance = sub_summary.get("feedback")

        return {
            "organisation": {
                "id": org.id,
                "name": org.name,
                "company": org.name,
                "status": "frozen" if org.is_suspended else "active",
                "is_suspended": org.is_suspended,
                "plan": o.core_plan_name or o.core_plan_code or "—",
                "plan_code": o.core_plan_code,
                "plan_name": o.core_plan_name,
                "core_plan": o.core_plan_name or o.core_plan_code or "—",
                "core_plan_code": o.core_plan_code,
                "core_plan_name": o.core_plan_name,
                "core_subscription_status": o.core_subscription_status,
                "feedback_plan": o.feedback_plan_name or o.feedback_plan_code or "—",
                "feedback_plan_code": o.feedback_plan_code,
                "feedback_plan_name": o.feedback_plan_name,
                "feedback_subscription_status": o.feedback_subscription_status,
                "subscription_status": o.core_subscription_status,
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
                "next_billing_date": subscription_finance.get("next_billing_date") if subscription_finance else None,
                "amount_next_payment_display": subscription_finance.get("amount_next_payment_display") if subscription_finance else None,
                "cancel_at_period_end": subscription_finance.get("cancel_at_period_end") if subscription_finance else False,
                "mandate_status": subscription_finance.get("mandate_status") if subscription_finance else None,
                "deletion_status": str(getattr(org, "deletion_status", "active") or "active"),
                "deletion_requested_at": getattr(org, "deletion_requested_at", None),
                **usage,
            },
            "deletion_request": AccountDeletionService._request_to_dict(db, pending_req)
            if (pending_req := AccountDeletionService._active_pending_request(db, org_id))
            else None,
            "subscription_finance": subscription_finance,
            "feedback_subscription_finance": feedback_subscription_finance,
            "billing_profile": profile,
            "usage": usage_full,
            "orders": campaigns,
            "campaigns": campaigns,
            "invoices": _filter_invoice_dicts(invoice_dicts, search=invoice_search),
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
            "subscription_cancellation": _subscription_cancellation_detail(db, org, core_sub),
            "refund_reviews": _list_org_refund_reviews(db, org_id),
        }


def _subscription_cancellation_detail(db: Session, org: Organisation, sub: Subscription | None) -> dict:
    from app.services.subscription_cancellation_service import SubscriptionCancellationService

    plan = SubscriptionCancellationService.get_plan(db, sub.plan_id) if sub else None
    refund_review = SubscriptionCancellationService.get_open_refund_review(db, org.id)
    return SubscriptionCancellationService.cancellation_dict(db, org, sub, plan, refund_review=refund_review)


def _list_org_refund_reviews(db: Session, org_id: str) -> list[dict]:
    from app.services.subscription_cancellation_service import SubscriptionCancellationService

    return SubscriptionCancellationService.list_refund_reviews(db, org_id=org_id, limit=20)
