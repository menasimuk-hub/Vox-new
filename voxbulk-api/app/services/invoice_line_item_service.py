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
