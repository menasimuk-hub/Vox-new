"""Admin order view — retail vs Telnyx operator cost per call."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.models.wallet_transaction import WalletTransaction
from app.services.billing_currency import money_display, resolve_org_currency


def enrich_admin_order_costs(db: Session, order: ServiceOrder, payload: dict[str, Any]) -> dict[str, Any]:
    launch = payload.get("launch_billing") if isinstance(payload.get("launch_billing"), dict) else {}
    settlement = payload.get("billing_settlement") if isinstance(payload.get("billing_settlement"), dict) else {}
    org = db.get(Organisation, order.org_id)
    currency = str(launch.get("currency") or settlement.get("currency") or resolve_org_currency(db, org))
    per_min = int(launch.get("unit_rate_minor") or 0)
    conn_fee = int(launch.get("connection_fee_minor") or 0)

    recipients = payload.get("recipients")
    if not isinstance(recipients, list):
        payload["financial_summary"] = _build_financial_summary(db, order, payload, org, currency, launch, settlement, 0, 0.0, "USD")
        return payload

    from app.services.telnyx_call_cost_service import lookup_cost_by_refs

    total_retail_minor = 0
    total_operator = 0.0
    operator_currency = "USD"

    for row in recipients:
        if not isinstance(row, dict):
            continue
        bm = int(row.get("billable_minutes") or 0)
        retail_minor = bm * per_min + (conn_fee if bm > 0 else 0)
        row["retail_cost_minor"] = retail_minor
        row["retail_cost_display"] = money_display(retail_minor, currency) if retail_minor > 0 else "—"

        op = lookup_cost_by_refs(
            db,
            call_control_id=row.get("call_control_id"),
            conversation_id=row.get("telnyx_conversation_id") or row.get("conversation_id"),
            session_id=row.get("call_session_id") or row.get("telnyx_session_id"),
        )
        if op:
            op_cost = float(op.get("total_cost") or 0)
            op_cur = str(op.get("currency") or "USD")
            row["operator_cost"] = op_cost
            row["operator_cost_currency"] = op_cur
            row["operator_cost_display"] = _operator_money(op_cost, op_cur)
            total_operator += op_cost
            operator_currency = op_cur
            if retail_minor > 0 and op_cost > 0:
                row["margin_display"] = (
                    f"{money_display(retail_minor, currency)} − {_operator_money(op_cost, op_cur)} (not FX-adjusted)"
                )
            else:
                row["margin_display"] = "—"
        else:
            row["operator_cost"] = None
            row["operator_cost_currency"] = None
            row["operator_cost_display"] = "—"
            row["margin_display"] = "—"

        total_retail_minor += retail_minor

    payload["cost_summary"] = {
        "currency": currency,
        "total_retail_cost_minor": total_retail_minor,
        "total_retail_cost_display": money_display(total_retail_minor, currency),
        "total_operator_cost": round(total_operator, 4),
        "total_operator_cost_currency": operator_currency,
        "total_operator_cost_display": _operator_money(total_operator, operator_currency) if total_operator > 0 else "—",
        "margin_display": (
            f"{money_display(total_retail_minor, currency)} − {_operator_money(total_operator, operator_currency)} (not FX-adjusted)"
            if total_retail_minor > 0 and total_operator > 0
            else "—"
        ),
    }
    payload["financial_summary"] = _build_financial_summary(
        db,
        order,
        payload,
        org,
        currency,
        launch,
        settlement,
        total_retail_minor,
        total_operator,
        operator_currency,
    )
    return payload


def _build_financial_summary(
    db: Session,
    order: ServiceOrder,
    payload: dict[str, Any],
    org: Organisation | None,
    currency: str,
    launch: dict[str, Any],
    settlement: dict[str, Any],
    total_retail_minor: int,
    total_operator: float,
    operator_currency: str,
) -> dict[str, Any]:
    from app.services.plan_price_service import PlanPriceService

    live_rates = PlanPriceService.rates_for_org(db, org) if org else {}
    sales_rates = {
        "currency": currency,
        "plan_name": launch.get("plan_name") or live_rates.get("plan_name"),
        "interview_per_min_minor": int(launch.get("unit_rate_minor") or live_rates.get("interview_per_min_minor") or 0),
        "connection_fee_minor": int(launch.get("connection_fee_minor") or live_rates.get("connection_fee_minor") or 0),
        "cv_scan_fee_minor": int(live_rates.get("cv_scan_fee_minor") or 0),
        "interview_per_min_display": money_display(
            int(launch.get("unit_rate_minor") or live_rates.get("interview_per_min_minor") or 0),
            currency,
        ),
        "connection_fee_display": money_display(
            int(launch.get("connection_fee_minor") or live_rates.get("connection_fee_minor") or 0),
            currency,
        ),
        "cv_scan_fee_display": money_display(int(live_rates.get("cv_scan_fee_minor") or 0), currency),
        "live_rates_match_launch": bool(
            launch.get("unit_rate_minor") is not None or launch.get("connection_fee_minor") is not None
        ),
    }

    wallet_rows = db.execute(
        select(WalletTransaction)
        .where(WalletTransaction.order_id == order.id)
        .order_by(WalletTransaction.created_at.asc())
    ).scalars().all()
    wallet_transactions = [
        {
            "id": tx.id,
            "direction": tx.direction,
            "kind": tx.kind,
            "amount_minor": tx.amount_minor,
            "amount_display": money_display(tx.amount_minor, tx.currency or currency),
            "currency": tx.currency,
            "status": tx.status,
            "description": tx.description,
            "invoice_id": tx.invoice_id,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        }
        for tx in wallet_rows
    ]

    ats_wallet_pence = 0
    if order.service_code == "interview":
        try:
            from app.services.interview_ats_billing_service import ats_wallet_pence as _ats_wallet_pence

            ats_wallet_pence = _ats_wallet_pence(order)
        except Exception:
            ats_wallet_pence = 0

    quote_breakdown = payload.get("quote_breakdown") if isinstance(payload.get("quote_breakdown"), list) else []
    quote_total_minor = int(order.quote_total_pence or 0)

    return {
        "sales_rates": sales_rates,
        "quote_total_minor": quote_total_minor,
        "quote_total_display": money_display(quote_total_minor, currency),
        "quote_breakdown": quote_breakdown,
        "settlement": settlement or None,
        "wallet_transactions": wallet_transactions,
        "ats_wallet_pence": ats_wallet_pence,
        "ats_wallet_display": money_display(ats_wallet_pence, currency) if ats_wallet_pence > 0 else "—",
        "payment_invoice_id": order.payment_invoice_id,
        "launch_invoice_id": launch.get("invoice_id"),
        "total_retail_cost_minor": total_retail_minor,
        "total_retail_cost_display": money_display(total_retail_minor, currency) if total_retail_minor > 0 else "—",
        "total_operator_cost": round(total_operator, 4),
        "total_operator_cost_display": _operator_money(total_operator, operator_currency) if total_operator > 0 else "—",
        "margin_display": payload.get("cost_summary", {}).get("margin_display", "—"),
    }


def _operator_money(amount: float, currency: str) -> str:
    value = float(amount or 0)
    code = str(currency or "USD").upper()
    try:
        return f"{code} {value:.4f}" if code != "USD" else f"${value:.4f}"
    except Exception:
        return "—"
