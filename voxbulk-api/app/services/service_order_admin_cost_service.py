"""Admin order view — retail vs Telnyx operator cost per call."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.service_order import ServiceOrder
from app.services.billing_currency import money_display, resolve_org_currency


def enrich_admin_order_costs(db: Session, order: ServiceOrder, payload: dict[str, Any]) -> dict[str, Any]:
    launch = payload.get("launch_billing") if isinstance(payload.get("launch_billing"), dict) else {}
    settlement = payload.get("billing_settlement") if isinstance(payload.get("billing_settlement"), dict) else {}
    currency = str(launch.get("currency") or settlement.get("currency") or resolve_org_currency(db, order.org_id))
    per_min = int(launch.get("unit_rate_minor") or 0)
    conn_fee = int(launch.get("connection_fee_minor") or 0)

    recipients = payload.get("recipients")
    if not isinstance(recipients, list):
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
        else:
            row["operator_cost"] = None
            row["operator_cost_currency"] = None
            row["operator_cost_display"] = "—"

        total_retail_minor += retail_minor

    payload["cost_summary"] = {
        "currency": currency,
        "total_retail_cost_minor": total_retail_minor,
        "total_retail_cost_display": money_display(total_retail_minor, currency),
        "total_operator_cost": round(total_operator, 4),
        "total_operator_cost_currency": operator_currency,
        "total_operator_cost_display": _operator_money(total_operator, operator_currency) if total_operator > 0 else "—",
    }
    return payload


def _operator_money(amount: float, currency: str) -> str:
    value = float(amount or 0)
    code = str(currency or "USD").upper()
    try:
        return f"{code} {value:.4f}" if code != "USD" else f"${value:.4f}"
    except Exception:
        return "—"
