"""Customer-facing campaign usage breakdown for Account → Usage."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.wallet_transaction import WalletTransaction
from app.services.billing_currency import money_display, resolve_org_currency
from app.services.usage_wallet_service import UsageWalletService


BILLING_SOURCE_LABELS = {
    "included_in_package": "Included in package",
    "wallet": "Wallet",
    "quote": "Quote / service order",
    "overage": "Overage",
    "promo_credits": "Promo credits",
    "no_charge": "No charge",
}


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _survey_channel(config: dict[str, Any], launch: dict[str, Any]) -> str:
    ch = str(
        launch.get("channel")
        or config.get("survey_channel")
        or config.get("channel")
        or "ai_call"
    ).strip().lower()
    if ch in {"whatsapp", "wa"}:
        return "whatsapp"
    if ch in {"call", "phone", "ai_call"}:
        return "ai_call"
    return ch or "ai_call"


def _type_labels(service_code: str, channel: str) -> tuple[str, str]:
    sc = str(service_code or "").strip().lower()
    if sc == "interview":
        return "Interview", "ai_call"
    if sc == "survey":
        if channel == "whatsapp":
            return "WhatsApp Survey", "whatsapp"
        return "AI Call Survey", "ai_call"
    return sc.title() or "Campaign", channel or "—"


def _map_billing_source(
    *,
    launch: dict[str, Any],
    payment_method: str | None,
    payment_status: str,
    cost_minor: int,
) -> tuple[str, str]:
    method = str(launch.get("payment_method") or payment_method or "").strip().lower()
    if payment_status not in {"approved", "paid"} and cost_minor <= 0:
        return "no_charge", BILLING_SOURCE_LABELS["no_charge"]
    if method in {"allowance", "subscription_allowance", "package"}:
        return "included_in_package", BILLING_SOURCE_LABELS["included_in_package"]
    if method in {"wallet"} or str(payment_method or "").lower() == "wallet":
        return "wallet", BILLING_SOURCE_LABELS["wallet"]
    if method in {"direct_debit", "gocardless_dd", "gocardless"} or str(payment_method or "").lower() in {
        "gocardless",
        "gocardless_dd",
    }:
        return "quote", BILLING_SOURCE_LABELS["quote"]
    if method in {"promo", "promo_credits", "credits"}:
        return "promo_credits", BILLING_SOURCE_LABELS["promo_credits"]
    if cost_minor <= 0 and payment_status == "approved":
        return "included_in_package", BILLING_SOURCE_LABELS["included_in_package"]
    if cost_minor > 0:
        return "wallet", BILLING_SOURCE_LABELS["wallet"]
    return "no_charge", BILLING_SOURCE_LABELS["no_charge"]


def _usage_from_launch(launch: dict[str, Any], order: ServiceOrder) -> tuple[int | None, str, str]:
    unit = str(launch.get("unit") or "").strip().lower()
    qty = launch.get("units_billable")
    if qty is None:
        qty = launch.get("units_total")
    if qty is None and unit == "recipients":
        qty = order.recipient_count
    if qty is None:
        qty = order.recipient_count or None
    try:
        quantity = int(qty) if qty is not None else None
    except (TypeError, ValueError):
        quantity = None

    if unit == "minutes":
        label = f"{quantity} minutes" if quantity is not None else "—"
        unit_name = "minutes"
    elif unit == "recipients" or str(launch.get("channel") or "") == "whatsapp":
        label = f"{quantity} messages" if quantity is not None else "—"
        unit_name = "messages"
    elif quantity is not None:
        label = f"{quantity} recipients"
        unit_name = "recipients"
    else:
        label = "—"
        unit_name = "units"
    return quantity, unit_name, label


def _cost_from_order(db: Session, order: ServiceOrder, org: Organisation, launch: dict[str, Any], wallet_tx: WalletTransaction | None) -> tuple[int, int, str]:
    """Return (catalog_cost_minor, amount_due_minor, cost_kind)."""
    from app.services.campaign_running_cost_service import CampaignRunningCostService

    if launch.get("billing_phase") in {"held", "pending_settlement", "billing_failed"} or launch.get("settlement"):
        payload = CampaignRunningCostService.compute_for_order(db, order)
        catalog = int(payload.get("catalog_cost_minor") or 0)
        due = int(payload.get("amount_due_minor") or 0)
        kind = str(payload.get("cost_kind") or "running")
        return catalog, due, kind

    wallet_charge = int(launch.get("wallet_charge_minor") or launch.get("wallet_charged_minor") or 0)
    dd_charge = int(launch.get("dd_charge_minor") or launch.get("dd_charged_minor") or 0)
    catalog = int(launch.get("catalog_cost_minor") or 0)
    due = int(launch.get("amount_due_minor") or wallet_charge + dd_charge)
    if catalog <= 0:
        catalog = due
    kind = "actual"
    if due <= 0 and wallet_tx is not None:
        due = int(wallet_tx.amount_minor or 0)
        if catalog <= 0:
            catalog = due
        kind = "actual"
    elif due <= 0 and int(order.quote_total_pence or 0) > 0 and str(order.payment_status or "").lower() == "approved":
        due = int(order.quote_total_pence or 0)
        if catalog <= 0:
            catalog = due
        kind = "estimated"
    elif due <= 0 and catalog <= 0:
        kind = "none"
    return max(0, catalog), max(0, due), kind


class BillingUsageBreakdownService:
    @staticmethod
    def _period_bounds(db: Session, org_id: str, period_start: datetime | None, period_end: datetime | None) -> tuple[datetime | None, datetime | None]:
        if period_start and period_end:
            return period_start, period_end
        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return None, None
        return row.period_start, row.period_end

    @staticmethod
    def build(
        db: Session,
        org: Organisation,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        service_code: str | None = None,
        status: str | None = None,
        billing_source: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        currency = resolve_org_currency(db, org)
        p_start, p_end = BillingUsageBreakdownService._period_bounds(db, org.id, period_start, period_end)

        filters = [ServiceOrder.org_id == org.id]
        if p_start:
            filters.append(ServiceOrder.created_at >= p_start)
        if p_end:
            filters.append(ServiceOrder.created_at <= p_end)
        if service_code:
            filters.append(ServiceOrder.service_code == service_code.strip().lower())
        if status:
            filters.append(ServiceOrder.status == status.strip().lower())
        if search and search.strip():
            q = f"%{search.strip()}%"
            filters.append(
                or_(
                    ServiceOrder.title.ilike(q),
                    ServiceOrder.id.ilike(q),
                    ServiceOrder.campaign_id.ilike(q),
                    ServiceOrder.reference_id.ilike(q),
                )
            )

        total_count = int(db.scalar(select(func.count()).select_from(ServiceOrder).where(*filters)) or 0)
        orders = list(
            db.execute(
                select(ServiceOrder).where(*filters).order_by(ServiceOrder.created_at.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 200))
            )
            .scalars()
            .all()
        )

        order_ids = [o.id for o in orders]
        wallet_by_order: dict[str, WalletTransaction] = {}
        if order_ids:
            txs = list(
                db.execute(
                    select(WalletTransaction)
                    .where(
                        WalletTransaction.org_id == org.id,
                        WalletTransaction.order_id.in_(order_ids),
                        WalletTransaction.direction == "debit",
                    )
                    .order_by(WalletTransaction.created_at.desc())
                )
                .scalars()
                .all()
            )
            for tx in txs:
                if tx.order_id and tx.order_id not in wallet_by_order:
                    wallet_by_order[tx.order_id] = tx

        rows: list[dict[str, Any]] = []
        for order in orders:
            config = _parse_json(order.config_json)
            launch = _parse_json(order.launch_billing_json)
            channel = _survey_channel(config, launch)
            type_label, channel_label = _type_labels(order.service_code, channel)
            wallet_tx = wallet_by_order.get(order.id)
            catalog_minor, amount_due_minor, cost_kind = _cost_from_order(db, order, org, launch, wallet_tx)
            source_key, source_label = _map_billing_source(
                launch=launch,
                payment_method=order.payment_method,
                payment_status=str(order.payment_status or ""),
                cost_minor=amount_due_minor,
            )
            if billing_source and source_key != billing_source.strip().lower():
                continue
            qty, unit_name, usage_display = _usage_from_launch(launch, order)
            rows.append(
                {
                    "order_id": order.id,
                    "campaign_id": order.campaign_id or order.reference_id,
                    "name": order.title,
                    "service_code": order.service_code,
                    "type_label": type_label,
                    "channel": channel_label,
                    "status": order.status,
                    "usage_quantity": qty,
                    "usage_unit": unit_name,
                    "usage_display": usage_display,
                    "cost_minor": catalog_minor,
                    "cost_display": money_display(catalog_minor, currency),
                    "amount_due_minor": amount_due_minor,
                    "amount_due_display": money_display(amount_due_minor, currency),
                    "cost_kind": cost_kind,
                    "billing_source": source_key,
                    "billing_source_label": source_label,
                    "created_at": order.created_at.isoformat() if order.created_at else None,
                    "payment_status": order.payment_status,
                }
            )

        usage_row = UsageWalletService.get_current(db, org.id)
        calls_inc = int(getattr(usage_row, "calls_included", 0) or 0) if usage_row else 0
        calls_used = int(getattr(usage_row, "calls_used", 0) or 0) if usage_row else 0
        wa_inc = int(getattr(usage_row, "whatsapp_included", 0) or 0) if usage_row else 0
        wa_used = int(getattr(usage_row, "whatsapp_used", 0) or 0) if usage_row else 0
        cv_inc = int(getattr(usage_row, "cv_scans_included", 0) or 0) if usage_row else 0
        cv_used_row = int(getattr(usage_row, "cv_scans_used", 0) or 0) if usage_row else 0
        summary = {
            "calls_used": calls_used,
            "calls_included": calls_inc,
            "calls_remaining": max(0, calls_inc - calls_used) if calls_inc > 0 else 0,
            "whatsapp_used": wa_used,
            "whatsapp_included": wa_inc,
            "whatsapp_remaining": max(0, wa_inc - wa_used) if wa_inc > 0 else 0,
            "cv_scans_used": cv_used_row,
            "cv_scans_included": cv_inc,
            "cv_scans_remaining": max(0, cv_inc - cv_used_row) if cv_inc > 0 else 0,
            "overage_pending_pence": 0,
            "overage_pending_display": money_display(0, currency),
            "wallet_paid_minor": sum(r["amount_due_minor"] for r in rows if r["billing_source"] == "wallet"),
            "wallet_paid_display": money_display(
                sum(r["amount_due_minor"] for r in rows if r["billing_source"] == "wallet"),
                currency,
            ),
            "extra_due_at_completion_minor": sum(
                r["amount_due_minor"] for r in rows if str(r.get("status") or "").lower() in {"running", "paid", "approved"}
            ),
            "extra_due_at_completion_display": money_display(
                sum(
                    r["amount_due_minor"]
                    for r in rows
                    if str(r.get("status") or "").lower() in {"running", "paid", "approved"}
                ),
                currency,
            ),
        }
        if usage_row is not None:
            total_overage = UsageWalletService._calc_overage_pence(usage_row, db, org.id)
            pending = max(0, total_overage - int(usage_row.overage_invoiced_pence or 0))
            summary["overage_pending_pence"] = pending
            summary["overage_pending_display"] = money_display(pending, currency)

        return {
            "ok": True,
            "period_start": p_start.isoformat() if p_start else None,
            "period_end": p_end.isoformat() if p_end else None,
            "currency": currency,
            "summary": summary,
            "rows": rows,
            "total": total_count if not billing_source else len(rows),
            "limit": limit,
            "offset": offset,
            "gaps": [
                "Cost shows campaign catalog value; Amount due is extra charges only (invoiced when the campaign completes).",
                "Running campaigns update as sessions complete — refresh the page or wait for auto-refresh.",
            ],
        }

    @staticmethod
    def get_row(db: Session, org_id: str, order_id: str) -> dict[str, Any] | None:
        order = db.get(ServiceOrder, order_id)
        if order is None or order.org_id != org_id:
            return None
        org = db.get(Organisation, org_id)
        if org is None:
            return None
        payload = BillingUsageBreakdownService.build(db, org, limit=1, offset=0, search=order_id)
        for row in payload.get("rows") or []:
            if row.get("order_id") == order_id:
                return row
        return None
