"""Live and final campaign cost — catalog value vs amount due (settlement + usage UI)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.organisation import Organisation
from app.models.service_order import ServiceOrder
from app.services.billing_currency import money_display, resolve_org_currency

_VOICE_CHANNELS = frozenset({"ai_call", "ai_meeting", "phone", "call", "meeting"})


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class CampaignRunningCostService:
    @staticmethod
    def rates_from_snapshot(snapshot: dict[str, Any], db: Session, org: Organisation) -> dict[str, int]:
        """Resolve frozen launch rates with live fallback when snapshot is incomplete."""
        unit = int(snapshot.get("unit_rate_minor") or snapshot.get("list_per_min_minor") or 0)
        merged = {
            "per_min_minor": int(snapshot.get("per_min_minor") or unit or 0),
            "extra_per_min_minor": int(snapshot.get("extra_per_min_minor") or unit or 0),
            "list_per_min_minor": int(snapshot.get("list_per_min_minor") or unit or 0),
            "connection_fee_minor": int(snapshot.get("connection_fee_minor") or 0),
            "wa_package_fee_minor": int(snapshot.get("wa_package_fee_minor") or 0),
            "wa_extra_minor": int(snapshot.get("wa_extra_minor") or unit or 0),
        }
        if merged["per_min_minor"] > 0 and merged["list_per_min_minor"] > 0:
            return merged
        try:
            from app.services.gocardless_service import BillingService
            from app.services.plan_price_service import PlanPriceService

            plan = BillingService.resolve_active_plan(db, org.id)
            live = PlanPriceService.rates_for_org(db, org, plan=plan)
            for key in merged:
                if merged[key] <= 0:
                    merged[key] = int(live.get(key if key != "list_per_min_minor" else "interview_per_min_minor") or live.get("per_min_minor") or 0)
        except Exception:
            pass
        return merged

    @staticmethod
    def _is_subscription(snapshot: dict[str, Any], order: ServiceOrder) -> bool:
        method = str(snapshot.get("payment_method") or order.payment_method or "").lower()
        return method in {"allowance", "direct_debit", "gocardless_dd", "subscription_allowance"}

    @staticmethod
    def _voice_included_extra(
        db: Session,
        org_id: str,
        *,
        total_billable: int,
        unmetered_billable: int = 0,
        snapshot: dict[str, Any],
    ) -> tuple[int, int]:
        from app.services.usage_wallet_service import UsageWalletService

        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return 0, total_billable

        calls_included = int(row.calls_included or 0)
        calls_used = int(row.calls_used or 0)
        used_excluding_unmetered = max(0, calls_used - max(0, unmetered_billable))
        remaining = max(0, calls_included - used_excluding_unmetered)

        launch_remaining = snapshot.get("calls_remaining_at_launch")
        if launch_remaining is not None:
            try:
                remaining = min(remaining, max(0, int(launch_remaining)))
            except (TypeError, ValueError):
                pass

        included = min(total_billable, remaining)
        return included, max(0, total_billable - included)

    @staticmethod
    def _wa_included_extra(
        db: Session,
        org_id: str,
        *,
        actual_units: int,
        snapshot: dict[str, Any],
    ) -> tuple[int, int]:
        from app.services.package_entitlement_service import PackageEntitlementService
        from app.services.usage_wallet_service import UsageWalletService

        row = UsageWalletService.get_current(db, org_id)
        if row is None:
            return 0, actual_units

        launch_remaining = snapshot.get("wa_remaining_at_launch")
        if launch_remaining is not None:
            try:
                remaining = max(0, int(launch_remaining))
            except (TypeError, ValueError):
                remaining = 0
        elif PackageEntitlementService.shared_pool_active(row, row.plan_code):
            ent = PackageEntitlementService.for_usage_row(row, plan_code=row.plan_code)
            remaining = max(0, int(ent.get("whatsapp_remaining") or 0))
        else:
            remaining = max(0, int(row.whatsapp_included or 0) - int(row.whatsapp_used or 0))

        included = min(actual_units, remaining)
        return included, max(0, actual_units - included)

    @staticmethod
    def compute_voice(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        snapshot: dict[str, Any],
        usage: dict[str, Any],
        *,
        unmetered_billable: int = 0,
        service_code: str = "",
    ) -> dict[str, Any]:
        rates = CampaignRunningCostService.rates_from_snapshot(snapshot, db, org)
        is_sub = CampaignRunningCostService._is_subscription(snapshot, order)
        total_billable = max(0, int(usage.get("total_billable_minutes") or 0))
        connected = max(0, int(usage.get("connected_calls") or 0))
        conn_unit = rates["connection_fee_minor"]

        if is_sub:
            included_minutes, extra_minutes = CampaignRunningCostService._voice_included_extra(
                db,
                order.org_id,
                total_billable=total_billable,
                unmetered_billable=unmetered_billable,
                snapshot=snapshot,
            )
            catalog_minutes_value = total_billable * rates["per_min_minor"]
            catalog_conn = connected * conn_unit
            catalog_cost = catalog_minutes_value + catalog_conn
            conn_due = conn_unit * connected if extra_minutes > 0 else 0
            minute_due = extra_minutes * rates["extra_per_min_minor"]
            amount_due = conn_due + minute_due
            included_value = included_minutes * rates["per_min_minor"] + (
                connected * conn_unit if extra_minutes <= 0 else 0
            )
        else:
            included_minutes = 0
            extra_minutes = total_billable
            list_rate = rates["list_per_min_minor"]
            conn_due = connected * conn_unit
            minute_due = total_billable * list_rate
            catalog_cost = conn_due + minute_due
            amount_due = catalog_cost
            included_value = 0

        currency = str(snapshot.get("currency") or resolve_org_currency(db, org))
        return {
            "channel": str(snapshot.get("channel") or "ai_call").lower(),
            "is_subscription": is_sub,
            "total_billable_minutes": total_billable,
            "included_minutes": included_minutes,
            "extra_minutes": extra_minutes,
            "connected_calls": connected,
            "catalog_cost_minor": catalog_cost,
            "included_value_minor": min(catalog_cost, included_value if is_sub else 0),
            "amount_due_minor": amount_due,
            "final_charge_minor": amount_due,
            "connection_fee_minor": conn_due if not is_sub else (conn_unit * connected if extra_minutes > 0 else 0),
            "connection_fee_unit_minor": conn_unit,
            "per_min_rate_minor": rates["extra_per_min_minor"] if is_sub and extra_minutes > 0 else (
                rates["list_per_min_minor"] if not is_sub else rates["per_min_minor"]
            ),
            "catalog_per_min_minor": rates["per_min_minor"] if is_sub else rates["list_per_min_minor"],
            "extra_per_min_minor": rates["extra_per_min_minor"],
            "currency": currency,
            "service_code": service_code or order.service_code,
        }

    @staticmethod
    def compute_whatsapp(
        db: Session,
        order: ServiceOrder,
        org: Organisation,
        snapshot: dict[str, Any],
        *,
        actual_units: int,
    ) -> dict[str, Any]:
        rates = CampaignRunningCostService.rates_from_snapshot(snapshot, db, org)
        is_sub = CampaignRunningCostService._is_subscription(snapshot, order)
        units = max(0, int(actual_units or 0))

        if is_sub:
            included_units, extra_units = CampaignRunningCostService._wa_included_extra(
                db, order.org_id, actual_units=units, snapshot=snapshot
            )
            catalog_cost = units * rates["wa_package_fee_minor"]
            amount_due = extra_units * rates["wa_extra_minor"]
            included_value = included_units * rates["wa_package_fee_minor"]
        else:
            included_units = 0
            extra_units = units
            catalog_cost = units * rates["wa_extra_minor"]
            amount_due = catalog_cost
            included_value = 0

        currency = str(snapshot.get("currency") or resolve_org_currency(db, org))
        return {
            "channel": "whatsapp",
            "is_subscription": is_sub,
            "actual_units": units,
            "included_units": included_units,
            "extra_units": extra_units,
            "catalog_cost_minor": catalog_cost,
            "included_value_minor": included_value,
            "amount_due_minor": amount_due,
            "final_charge_minor": amount_due,
            "connection_fee_minor": 0,
            "wa_package_fee_minor": rates["wa_package_fee_minor"],
            "wa_extra_minor": rates["wa_extra_minor"],
            "per_min_rate_minor": rates["wa_extra_minor"],
            "currency": currency,
            "service_code": order.service_code,
        }

    @staticmethod
    def compute_for_order(
        db: Session,
        order: ServiceOrder,
        *,
        trigger: str = "live",
    ) -> dict[str, Any]:
        from app.services.campaign_billing_settlement_service import CampaignBillingSettlementService

        org = db.get(Organisation, order.org_id)
        if org is None:
            return {"catalog_cost_minor": 0, "amount_due_minor": 0, "cost_kind": "none"}

        snapshot = _parse_json(order.launch_billing_json)
        settlement = snapshot.get("settlement") if isinstance(snapshot.get("settlement"), dict) else None
        if settlement:
            final = int(settlement.get("final_charge_minor") or 0)
            catalog = int(settlement.get("catalog_cost_minor") or final)
            currency = str(snapshot.get("currency") or resolve_org_currency(db, org))
            return {
                "catalog_cost_minor": catalog,
                "catalog_cost_display": money_display(catalog, currency),
                "amount_due_minor": final,
                "amount_due_display": money_display(final, currency),
                "cost_kind": "final",
                "currency": currency,
                "breakdown": settlement,
            }

        channel = str(snapshot.get("channel") or "").lower()
        is_voice = channel in _VOICE_CHANNELS or order.service_code == "interview"

        if is_voice:
            usage = CampaignBillingSettlementService.aggregate_phone_calls(db, order, trigger=trigger)
            unmetered = 0
            if order.service_code == "interview":
                from app.services.interview_session_billing_service import unmetered_billable_minutes
                from app.services.platform_catalog_service import ServiceOrderService

                recipients = ServiceOrderService.get_recipients(db, order.id)
                unmetered = unmetered_billable_minutes(recipients)
            costs = CampaignRunningCostService.compute_voice(
                db,
                order,
                org,
                snapshot,
                usage,
                unmetered_billable=unmetered,
                service_code=order.service_code or "",
            )
        elif channel == "whatsapp":
            from app.services.billing_reconciliation_service import BillingReconciliationService

            units = BillingReconciliationService._actual_whatsapp_units(db, order, trigger=trigger)
            costs = CampaignRunningCostService.compute_whatsapp(db, order, org, snapshot, actual_units=units)
        else:
            return {"catalog_cost_minor": 0, "amount_due_minor": 0, "cost_kind": "none"}

        currency = costs.get("currency") or resolve_org_currency(db, org)
        status = str(order.status or "").lower()
        cost_kind = "final" if status in {"completed", "cancelled"} else "running"
        if not snapshot and int(order.quote_total_pence or 0) > 0:
            cost_kind = "estimated"

        catalog = int(costs.get("catalog_cost_minor") or 0)
        due = int(costs.get("amount_due_minor") or 0)
        return {
            **costs,
            "catalog_cost_minor": catalog,
            "catalog_cost_display": money_display(catalog, currency),
            "amount_due_minor": due,
            "amount_due_display": money_display(due, currency),
            "cost_kind": cost_kind,
        }
