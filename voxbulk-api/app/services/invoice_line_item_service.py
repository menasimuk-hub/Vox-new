"""Build structured invoice line items from orders, quotes, and launch billing."""

from __future__ import annotations

import json
from typing import Any

from app.models.service_order import ServiceOrder


class InvoiceLineItemService:
    @staticmethod
    def _line(
        *,
        description: str,
        quantity: int,
        unit_pence: int,
        total_pence: int | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        qty = max(1, int(quantity or 1))
        unit = max(0, int(unit_pence or 0))
        total = max(0, int(total_pence if total_pence is not None else qty * unit))
        row: dict[str, Any] = {
            "description": description.strip(),
            "quantity": qty,
            "unit_pence": unit,
            "total_pence": total,
        }
        if kind:
            row["kind"] = kind
        return row

    @staticmethod
    def from_quote_payload(quote: dict[str, Any]) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        count = max(0, int(quote.get("recipient_count") or 0))
        for raw in quote.get("lines") or []:
            if not isinstance(raw, dict):
                continue
            kind = str(raw.get("kind") or "").strip().lower()
            channel = str(raw.get("channel") or "").strip().lower()
            amount = max(0, int(raw.get("amount_pence") or 0))
            if kind == "connection_fee":
                unit = amount // max(count, 1) if count else amount
                lines.append(
                    InvoiceLineItemService._line(
                        description="AI call — connection fee",
                        quantity=max(count, 1),
                        unit_pence=unit,
                        total_pence=amount,
                        kind="connection_fee",
                    )
                )
            elif kind == "per_minute":
                duration = max(1, int(raw.get("duration_minutes") or 1))
                per_min = max(0, int(raw.get("per_min_pence") or 0))
                qty = max(count, 1) * duration
                label = "AI call minutes" if channel in {"ai_call", "phone", ""} else "Call minutes"
                lines.append(
                    InvoiceLineItemService._line(
                        description=label,
                        quantity=qty,
                        unit_pence=per_min,
                        total_pence=amount,
                        kind="call_minutes",
                    )
                )
            elif kind == "per_recipient":
                unit = max(0, int(raw.get("unit_price_pence") or 0))
                if unit <= 0 and count:
                    unit = amount // count
                lines.append(
                    InvoiceLineItemService._line(
                        description="WA survey recipients",
                        quantity=max(count, 1),
                        unit_pence=unit,
                        total_pence=amount,
                        kind="wa_survey",
                    )
                )
            elif kind == "per_person":
                unit = max(0, int(raw.get("unit_price_pence") or 0))
                if unit <= 0 and count:
                    unit = amount // max(count, 1)
                lines.append(
                    InvoiceLineItemService._line(
                        description=str(raw.get("label") or "Service units"),
                        quantity=max(count, 1),
                        unit_pence=unit,
                        total_pence=amount,
                        kind=kind,
                    )
                )
            elif amount > 0:
                lines.append(
                    InvoiceLineItemService._line(
                        description=str(raw.get("label") or raw.get("detail") or "Service charge"),
                        quantity=1,
                        unit_pence=amount,
                        total_pence=amount,
                        kind=kind or "other",
                    )
                )
        if not lines:
            total = max(0, int(quote.get("total_pence") or 0))
            if total > 0:
                lines.append(
                    InvoiceLineItemService._line(
                        description="Campaign charge",
                        quantity=1,
                        unit_pence=total,
                        total_pence=total,
                    )
                )
        return lines

    @staticmethod
    def amount_due_pence(line_items: list[dict[str, Any]] | None) -> int:
        return sum(max(0, int(row.get("total_pence") or 0)) for row in (line_items or []) if not row.get("included_in_plan"))

    @staticmethod
    def catalog_value_pence(line_items: list[dict[str, Any]] | None) -> int:
        return sum(max(0, int(row.get("catalog_pence") or row.get("total_pence") or 0)) for row in (line_items or []))

    @staticmethod
    def _voice_product_label(*, service_code: str, channel: str) -> str:
        sc = str(service_code or "").strip().lower()
        ch = str(channel or "").strip().lower()
        if sc == "interview":
            if ch in {"ai_meeting", "meeting", "web"}:
                return "AI interview (web)"
            return "AI interview (phone)"
        return "AI call survey"

    @staticmethod
    def from_campaign_settlement(
        costs: dict[str, Any],
        *,
        order_title: str = "",
        channel: str = "ai_call",
        service_code: str = "",
    ) -> list[dict[str, Any]]:
        title = (order_title or "Campaign").strip()
        ch = str(channel or costs.get("channel") or "").strip().lower()
        lines: list[dict[str, Any]] = []

        if ch == "whatsapp":
            units = max(0, int(costs.get("actual_units") or 0))
            included = max(0, int(costs.get("included_units") or 0))
            extra = max(0, int(costs.get("extra_units") or 0))
            pkg_rate = max(0, int(costs.get("wa_package_fee_minor") or costs.get("catalog_per_min_minor") or 0))
            extra_rate = max(0, int(costs.get("wa_extra_minor") or costs.get("per_min_rate_minor") or 0))
            if units > 0 and pkg_rate > 0:
                catalog_total = units * pkg_rate
                lines.append(
                    InvoiceLineItemService._line(
                        description=f"WA survey — {title}",
                        quantity=units,
                        unit_pence=pkg_rate,
                        total_pence=extra * extra_rate if extra > 0 else 0,
                        kind="wa_survey",
                    )
                )
                lines[-1]["catalog_pence"] = catalog_total
                if included > 0 and extra <= 0:
                    lines.append(
                        InvoiceLineItemService._line(
                            description="Included in plan allowance",
                            quantity=1,
                            unit_pence=0,
                            total_pence=0,
                            kind="allowance_credit",
                        )
                    )
                    lines[-1]["included_in_plan"] = True
                    lines[-1]["catalog_pence"] = catalog_total
            return lines

        product = InvoiceLineItemService._voice_product_label(service_code=service_code, channel=ch)
        connected = max(0, int(costs.get("connected_calls") or 0))
        conn_unit = max(0, int(costs.get("connection_fee_unit_minor") or 0))
        total_mins = max(0, int(costs.get("total_billable_minutes") or 0))
        included_mins = max(0, int(costs.get("included_minutes") or 0))
        extra_mins = max(0, int(costs.get("extra_minutes") or 0))
        catalog_rate = max(0, int(costs.get("catalog_per_min_minor") or costs.get("per_min_rate_minor") or 0))
        extra_rate = max(0, int(costs.get("extra_per_min_minor") or costs.get("per_min_rate_minor") or 0))
        is_sub = bool(costs.get("is_subscription"))

        if connected > 0 and conn_unit > 0:
            conn_catalog = connected * conn_unit
            conn_due = conn_catalog if (not is_sub or extra_mins > 0) else 0
            lines.append(
                InvoiceLineItemService._line(
                    description=f"{product} — connection fee — {title}",
                    quantity=connected,
                    unit_pence=conn_unit,
                    total_pence=conn_due,
                    kind="connection_fee",
                )
            )
            lines[-1]["catalog_pence"] = conn_catalog

        if total_mins > 0 and catalog_rate > 0:
            mins_catalog = total_mins * catalog_rate
            mins_due = extra_mins * extra_rate if is_sub else total_mins * catalog_rate
            lines.append(
                InvoiceLineItemService._line(
                    description=f"{product} — call minutes — {title}",
                    quantity=total_mins,
                    unit_pence=catalog_rate,
                    total_pence=mins_due,
                    kind="call_minutes",
                )
            )
            lines[-1]["catalog_pence"] = mins_catalog

        if is_sub and included_mins > 0 and extra_mins <= 0 and lines:
            lines.append(
                InvoiceLineItemService._line(
                    description="Included in plan allowance",
                    quantity=1,
                    unit_pence=0,
                    total_pence=0,
                    kind="allowance_credit",
                )
            )
            lines[-1]["included_in_plan"] = True
        return lines

    @staticmethod
    def from_actual_call_usage(
        costs: dict[str, Any],
        *,
        order_title: str = "",
        channel: str = "ai_call",
    ) -> list[dict[str, Any]]:
        return InvoiceLineItemService.from_campaign_settlement(
            costs,
            order_title=order_title,
            channel=channel,
            service_code=str(costs.get("service_code") or ""),
        )

    @staticmethod
    def from_launch_breakdown(breakdown: dict[str, Any], *, order_title: str = "") -> list[dict[str, Any]]:
        channel = str(breakdown.get("channel") or "").strip().lower()
        title = (order_title or "Campaign").strip()
        lines: list[dict[str, Any]] = []
        if channel == "whatsapp":
            units = max(0, int(breakdown.get("units_billable") or 0))
            unit = max(0, int(breakdown.get("unit_rate_minor") or 0))
            if units > 0:
                lines.append(
                    InvoiceLineItemService._line(
                        description=f"WA survey — {title}",
                        quantity=units,
                        unit_pence=unit,
                        total_pence=units * unit,
                        kind="wa_survey",
                    )
                )
        elif channel == "ai_call":
            duration = max(1, int(breakdown.get("duration_minutes") or 1))
            conn_unit = max(0, int(breakdown.get("connection_fee_minor") or 0))
            conn_total = max(0, int(breakdown.get("connection_fee_total_minor") or 0))
            billable_mins = max(0, int(breakdown.get("units_billable") or 0))
            per_min = max(0, int(breakdown.get("unit_rate_minor") or 0))
            if conn_total > 0:
                recipients = conn_total // conn_unit if conn_unit else max(1, billable_mins // duration)
                lines.append(
                    InvoiceLineItemService._line(
                        description=f"AI call — connection fee — {title}",
                        quantity=max(recipients, 1),
                        unit_pence=conn_unit,
                        total_pence=conn_total,
                        kind="connection_fee",
                    )
                )
            if billable_mins > 0:
                lines.append(
                    InvoiceLineItemService._line(
                        description=f"AI call minutes — {title}",
                        quantity=billable_mins,
                        unit_pence=per_min,
                        total_pence=billable_mins * per_min,
                        kind="call_minutes",
                    )
                )
        if not lines:
            amount = max(
                0,
                int(breakdown.get("dd_charge_minor") or 0) + int(breakdown.get("wallet_charge_minor") or 0),
            )
            if amount > 0:
                lines.append(
                    InvoiceLineItemService._line(
                        description=f"Campaign launch — {title}",
                        quantity=1,
                        unit_pence=amount,
                        total_pence=amount,
                    )
                )
        return lines

    @staticmethod
    def _ats_lines_from_order(order: ServiceOrder) -> list[dict[str, Any]]:
        try:
            cfg = json.loads(order.config_json or "{}")
        except json.JSONDecodeError:
            return []
        if not isinstance(cfg, dict):
            return []
        charges = cfg.get("ats_charges")
        if not isinstance(charges, list) or not charges:
            legacy_count = int(cfg.get("ats_last_charge_count") or 0)
            legacy_unit = int(cfg.get("ats_last_unit_pence") or 0)
            if legacy_count > 0 and legacy_unit > 0:
                return [
                    InvoiceLineItemService._line(
                        description="ATS CV screening",
                        quantity=legacy_count,
                        unit_pence=legacy_unit,
                        total_pence=legacy_count * legacy_unit,
                        kind="ats_cv_scan",
                    )
                ]
            return []
        unit = 0
        for row in charges:
            if not isinstance(row, dict):
                continue
            unit = max(unit, int(row.get("catalog_unit_pence") or row.get("amount_pence") or 0))
        if unit <= 0:
            return []
        count = len([r for r in charges if isinstance(r, dict)])
        if count <= 0:
            return []
        return [
            InvoiceLineItemService._line(
                description="ATS CV screening",
                quantity=count,
                unit_pence=unit,
                total_pence=count * unit,
                kind="ats_cv_scan",
            )
        ]

    @staticmethod
    def from_order(order: ServiceOrder) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for raw in (order.quote_breakdown_json, order.launch_billing_json):
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            if parsed.get("lines"):
                lines = InvoiceLineItemService.from_quote_payload(parsed)
                break
            if parsed.get("channel"):
                lines = InvoiceLineItemService.from_launch_breakdown(
                    parsed,
                    order_title=str(order.title or order.survey_name or ""),
                )
                break
        if not lines:
            total = max(0, int(order.quote_total_pence or 0))
            if total > 0:
                lines = [
                    InvoiceLineItemService._line(
                        description=str(order.title or order.service_code or "Service order"),
                        quantity=max(1, int(order.recipient_count or 1)),
                        unit_pence=total,
                        total_pence=total,
                    )
                ]
        ats_lines = InvoiceLineItemService._ats_lines_from_order(order)
        if ats_lines:
            lines = [*lines, *ats_lines]
        return lines

    @staticmethod
    def gross_total_pence(line_items: list[dict[str, Any]] | None) -> int:
        return sum(max(0, int(row.get("total_pence") or 0)) for row in (line_items or []))
