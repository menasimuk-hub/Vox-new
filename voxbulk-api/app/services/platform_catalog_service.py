from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.platform_service import PlatformService, ServicePricingRule
from app.models.service_order import ServiceOrder, ServiceOrderRecipient

logger = logging.getLogger(__name__)

SURVEY_CHANNEL_ALIASES = {"call": "ai_call"}
SURVEY_DELIVERY_CHANNELS = frozenset({"ai_call", "whatsapp"})


class PlatformCatalogService:
    DEFAULT_SERVICES = [
        {
            "code": "survey",
            "name": "Survey",
            "description": "AI phone and WhatsApp survey campaigns with smart reporting.",
            "service_kind": "order",
            "sort_order": 10,
            "rules": [
                {
                    "channel": "base",
                    "rule_type": "flat_per_order",
                    "label": "Survey setup fee",
                    "base_fee_pence": 500,
                    "sort_order": 5,
                },
                {
                    "channel": "whatsapp",
                    "rule_type": "bundle",
                    "label": "WhatsApp — 50 contacts",
                    "bundle_size": 50,
                    "bundle_price_pence": 1000,
                    "overage_unit_price_pence": 20,
                    "sort_order": 10,
                },
                {
                    "channel": "whatsapp",
                    "rule_type": "bundle",
                    "label": "WhatsApp — 100 contacts",
                    "bundle_size": 100,
                    "bundle_price_pence": 1500,
                    "overage_unit_price_pence": 15,
                    "sort_order": 11,
                },
                {
                    "channel": "whatsapp",
                    "rule_type": "bundle",
                    "label": "WhatsApp — 250 contacts",
                    "bundle_size": 250,
                    "bundle_price_pence": 3200,
                    "overage_unit_price_pence": 12,
                    "sort_order": 12,
                },
                {
                    "channel": "ai_call",
                    "rule_type": "bundle",
                    "label": "AI call — 50 contacts",
                    "bundle_size": 50,
                    "bundle_price_pence": 2900,
                    "overage_unit_price_pence": 58,
                    "sort_order": 20,
                },
                {
                    "channel": "ai_call",
                    "rule_type": "bundle",
                    "label": "AI call — 100 contacts",
                    "bundle_size": 100,
                    "bundle_price_pence": 4900,
                    "overage_unit_price_pence": 49,
                    "sort_order": 21,
                },
                {
                    "channel": "ai_call",
                    "rule_type": "bundle",
                    "label": "AI call — 250 contacts",
                    "bundle_size": 250,
                    "bundle_price_pence": 9900,
                    "overage_unit_price_pence": 40,
                    "sort_order": 22,
                },
            ],
        },
        {
            "code": "interview",
            "name": "Interview",
            "description": "AI phone or Zoom interview screening campaigns.",
            "service_kind": "order",
            "sort_order": 20,
            "rules": [
                {"channel": "ai_call", "rule_type": "per_minute", "label": "Interview AI call — per minute", "unit_price_pence": 35},
                {"channel": "zoom", "rule_type": "per_person", "label": "Interview Zoom — per person", "unit_price_pence": 500},
            ],
        },
        {
            "code": "interview_ats",
            "name": "Interview ATS",
            "description": "AI CV screening score per candidate (DeepSeek ATS).",
            "service_kind": "addon",
            "sort_order": 25,
            "rules": [
                {
                    "channel": "base",
                    "rule_type": "per_person",
                    "label": "ATS scan per CV",
                    "unit_price_pence": 75,
                    "sort_order": 10,
                },
            ],
        },
    ]

    @staticmethod
    def normalize_survey_channel(raw: str | None) -> str:
        channel = str(raw or "").strip().lower()
        return SURVEY_CHANNEL_ALIASES.get(channel, channel)

    @staticmethod
    def resolve_survey_channel(options: dict[str, Any] | None) -> str:
        options = options or {}

        explicit = options.get("survey_channel") or options.get("delivery")
        if explicit:
            channel = PlatformCatalogService.normalize_survey_channel(str(explicit))
            if channel not in SURVEY_DELIVERY_CHANNELS:
                raise ValueError("Survey channel must be ai_call or whatsapp")
            return channel

        channels = options.get("channels")
        if isinstance(channels, list) and channels:
            normalized = [PlatformCatalogService.normalize_survey_channel(str(c)) for c in channels if c]
            normalized = [c for c in normalized if c in SURVEY_DELIVERY_CHANNELS]
            if len(normalized) > 1:
                raise ValueError("Mixed survey channels are not supported — choose ai_call or whatsapp")
            if len(normalized) == 1:
                return normalized[0]

        contact_method = str(options.get("contact_method") or "").strip().lower()
        if "both" in contact_method:
            raise ValueError("Mixed survey channels are not supported — choose ai_call or whatsapp")
        if "whatsapp" in contact_method:
            return "whatsapp"
        if "ai" in contact_method or "phone" in contact_method or "call" in contact_method:
            return "ai_call"

        return "ai_call"

    @staticmethod
    def rule_to_dict(rule: ServicePricingRule, *, include_internal: bool = False) -> dict[str, Any]:
        channel = PlatformCatalogService.normalize_survey_channel(rule.channel)
        out: dict[str, Any] = {
            "id": rule.id,
            "service_id": rule.service_id,
            "channel": channel,
            "rule_type": rule.rule_type,
            "label": rule.label,
            "bundle_size": rule.bundle_size,
            "bundle_price_pence": rule.bundle_price_pence,
            "bundle_price_gbp": f"£{(int(rule.bundle_price_pence or 0)) / 100:.2f}" if rule.bundle_price_pence is not None else None,
            "overage_unit_price_pence": rule.overage_unit_price_pence,
            "overage_unit_price_gbp": (
                f"£{(int(rule.overage_unit_price_pence or 0)) / 100:.2f}"
                if rule.overage_unit_price_pence is not None
                else None
            ),
            "base_fee_pence": rule.base_fee_pence,
            "unit_price_pence": rule.unit_price_pence,
            "included_units": rule.included_units,
            "sort_order": rule.sort_order,
            "notes": rule.notes,
        }
        if include_internal:
            out["is_active"] = bool(rule.is_active)
        return out

    @staticmethod
    def survey_packages_for_service(
        db: Session,
        service: PlatformService,
        *,
        active_only: bool = True,
        include_internal: bool = False,
    ) -> dict[str, Any]:
        rules = PlatformCatalogService.list_rules_for_service(db, service.id, active_only=active_only)
        base_rule = next((r for r in rules if r.channel == "base"), None)
        packages: dict[str, list[dict[str, Any]]] = {"ai_call": [], "whatsapp": []}

        for rule in rules:
            channel = PlatformCatalogService.normalize_survey_channel(rule.channel)
            if channel not in packages:
                continue
            if str(rule.rule_type) != "bundle":
                continue
            packages[channel].append(PlatformCatalogService.rule_to_dict(rule, include_internal=include_internal))

        for channel in packages:
            packages[channel].sort(
                key=lambda row: (
                    int(row.get("sort_order") or 100),
                    int(row.get("bundle_size") or 0),
                )
            )

        return {
            "service_code": service.code,
            "service_name": service.name,
            "setup_fee_pence": int(base_rule.base_fee_pence or 0) if base_rule else 0,
            "setup_fee_gbp": f"£{(int(base_rule.base_fee_pence or 0) if base_rule else 0) / 100:.2f}",
            "packages": packages,
        }

    @staticmethod
    def ensure_defaults(db: Session) -> None:
        for svc in PlatformCatalogService.DEFAULT_SERVICES:
            row = db.execute(select(PlatformService).where(PlatformService.code == svc["code"])).scalar_one_or_none()
            if row is None:
                row = PlatformService(
                    code=svc["code"],
                    name=svc["name"],
                    description=svc["description"],
                    service_kind=svc["service_kind"],
                    sort_order=int(svc["sort_order"]),
                    is_active=True,
                )
                db.add(row)
                db.flush()

            for rule in svc.get("rules") or []:
                channel = str(rule["channel"])
                rule_type = str(rule["rule_type"])
                label = str(rule["label"])
                bundle_size = rule.get("bundle_size")

                stmt = select(ServicePricingRule.id).where(
                    ServicePricingRule.service_id == row.id,
                    ServicePricingRule.channel == channel,
                    ServicePricingRule.rule_type == rule_type,
                )
                if rule_type == "bundle" and bundle_size is not None:
                    stmt = stmt.where(ServicePricingRule.bundle_size == int(bundle_size))
                else:
                    stmt = stmt.where(ServicePricingRule.label == label)

                existing = db.execute(stmt).scalar_one_or_none()
                if existing is not None:
                    continue

                db.add(
                    ServicePricingRule(
                        service_id=row.id,
                        channel=channel,
                        rule_type=rule_type,
                        label=label,
                        base_fee_pence=int(rule.get("base_fee_pence") or 0),
                        unit_price_pence=int(rule.get("unit_price_pence") or 0),
                        bundle_size=int(bundle_size) if bundle_size is not None else None,
                        bundle_price_pence=int(rule["bundle_price_pence"]) if rule.get("bundle_price_pence") is not None else None,
                        overage_unit_price_pence=int(rule["overage_unit_price_pence"])
                        if rule.get("overage_unit_price_pence") is not None
                        else None,
                        sort_order=int(rule.get("sort_order") or 100),
                        is_active=True,
                    )
                )

        PlatformCatalogService._migrate_legacy_call_channel(db)
        db.commit()

    @staticmethod
    def _migrate_legacy_call_channel(db: Session) -> None:
        legacy = list(
            db.execute(
                select(ServicePricingRule).where(ServicePricingRule.channel == "call")
            ).scalars()
        )
        for rule in legacy:
            rule.channel = "ai_call"
            db.add(rule)

    @staticmethod
    def list_services(db: Session, *, active_only: bool = True) -> list[PlatformService]:
        PlatformCatalogService.ensure_defaults(db)
        stmt = select(PlatformService).order_by(PlatformService.sort_order.asc(), PlatformService.name.asc())
        if active_only:
            stmt = stmt.where(PlatformService.is_active.is_(True))
        return list(db.execute(stmt).scalars())

    @staticmethod
    def get_service_by_code(db: Session, code: str) -> PlatformService | None:
        PlatformCatalogService.ensure_defaults(db)
        return db.execute(select(PlatformService).where(PlatformService.code == code)).scalar_one_or_none()

    @staticmethod
    def list_rules_for_service(db: Session, service_id: str, *, active_only: bool = True) -> list[ServicePricingRule]:
        stmt = (
            select(ServicePricingRule)
            .where(ServicePricingRule.service_id == service_id)
            .order_by(ServicePricingRule.sort_order.asc(), ServicePricingRule.bundle_size.asc())
        )
        if active_only:
            stmt = stmt.where(ServicePricingRule.is_active.is_(True))
        return list(db.execute(stmt).scalars())

    @staticmethod
    def _money(pence: int) -> str:
        return f"£{int(pence or 0) / 100:.2f}"

    @staticmethod
    def _bundle_rules_for_channel(rules: list[ServicePricingRule], channel: str) -> list[ServicePricingRule]:
        normalized = PlatformCatalogService.normalize_survey_channel(channel)
        out = [
            r
            for r in rules
            if PlatformCatalogService.normalize_survey_channel(r.channel) == normalized and str(r.rule_type) == "bundle"
        ]
        return sorted(out, key=lambda r: (int(r.sort_order or 100), int(r.bundle_size or 0)))

    @staticmethod
    def _pick_survey_bundle_rule(
        rules: list[ServicePricingRule],
        *,
        channel: str,
        recipient_count: int,
        selected_rule_id: str | None = None,
    ) -> ServicePricingRule:
        bundle_rules = PlatformCatalogService._bundle_rules_for_channel(rules, channel)
        if not bundle_rules:
            raise ValueError(f"No active survey packages configured for channel: {channel}")

        if selected_rule_id:
            picked = next((r for r in bundle_rules if str(r.id) == str(selected_rule_id)), None)
            if picked is None:
                raise ValueError("Selected survey package is not available for this channel")
            return picked

        count = max(int(recipient_count or 0), 0)
        fitting = [r for r in bundle_rules if int(r.bundle_size or 0) >= count]
        if fitting:
            return min(fitting, key=lambda r: int(r.bundle_size or 0))

        return max(bundle_rules, key=lambda r: int(r.bundle_size or 0))

    @staticmethod
    def _quote_survey_bundle(rule: ServicePricingRule, recipient_count: int) -> tuple[int, list[dict[str, Any]]]:
        count = max(int(recipient_count or 0), 0)
        bundle_size = max(int(rule.bundle_size or 0), 1)
        bundle_price = int(rule.bundle_price_pence or 0)
        overage_rate = int(rule.overage_unit_price_pence or 0)

        lines: list[dict[str, Any]] = []
        total = bundle_price

        lines.append(
            {
                "kind": "bundle",
                "channel": PlatformCatalogService.normalize_survey_channel(rule.channel),
                "rule_id": rule.id,
                "label": rule.label,
                "amount_pence": bundle_price,
                "detail": f"{rule.label}: {bundle_size} contacts @ {PlatformCatalogService._money(bundle_price)}",
                "bundle_size": bundle_size,
                "contacts_included": bundle_size,
            }
        )

        if count > bundle_size and overage_rate > 0:
            extra_contacts = count - bundle_size
            overage_amount = extra_contacts * overage_rate
            total += overage_amount
            lines.append(
                {
                    "kind": "overage",
                    "channel": PlatformCatalogService.normalize_survey_channel(rule.channel),
                    "rule_id": rule.id,
                    "label": f"{rule.label} — extra contacts",
                    "amount_pence": overage_amount,
                    "detail": (
                        f"Overage: {extra_contacts} × {PlatformCatalogService._money(overage_rate)} "
                        f"= {PlatformCatalogService._money(overage_amount)}"
                    ),
                    "extra_contacts": extra_contacts,
                    "overage_unit_price_pence": overage_rate,
                }
            )
            logger.info(
                "survey_quote_overage rule_id=%s channel=%s contacts=%s bundle_size=%s extra=%s amount_pence=%s",
                rule.id,
                rule.channel,
                count,
                bundle_size,
                extra_contacts,
                overage_amount,
            )
        elif count > bundle_size and overage_rate <= 0:
            logger.warning(
                "survey_quote_no_overage_rate rule_id=%s channel=%s contacts=%s bundle_size=%s",
                rule.id,
                rule.channel,
                count,
                bundle_size,
            )

        return total, lines

    @staticmethod
    def _line_amount(rule: ServicePricingRule, count: int, *, duration_minutes: int = 0) -> tuple[int, str]:
        count = max(int(count or 0), 0)
        rt = str(rule.rule_type)
        if rt == "flat_per_order":
            amt = int(rule.base_fee_pence or 0)
            return amt, f"{rule.label}: {PlatformCatalogService._money(amt)}"
        if rt == "per_person":
            amt = count * int(rule.unit_price_pence or 0)
            unit = int(rule.unit_price_pence or 0)
            return amt, f"{rule.label}: {count} × {PlatformCatalogService._money(unit)} = {PlatformCatalogService._money(amt)}"
        if rt == "per_minute":
            duration = max(int(duration_minutes or 0), 0)
            unit = int(rule.unit_price_pence or 0)
            amt = count * duration * unit
            return amt, f"{rule.label}: {count} × {duration} min × {PlatformCatalogService._money(unit)}/min = {PlatformCatalogService._money(amt)}"
        if rt == "bundle":
            amt, lines = PlatformCatalogService._quote_survey_bundle(rule, count)
            detail = " · ".join(line["detail"] for line in lines)
            return amt, detail
        if rt == "flat_plus_per_person":
            amt = int(rule.base_fee_pence or 0) + count * int(rule.unit_price_pence or 0)
            return amt, f"{rule.label}: {PlatformCatalogService._money(amt)}"
        return 0, rule.label

    @staticmethod
    def calculate_quote(
        db: Session,
        *,
        service_code: str,
        recipient_count: int,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        svc = PlatformCatalogService.get_service_by_code(db, service_code)
        if svc is None:
            raise ValueError(f"Unknown service: {service_code}")
        rules = PlatformCatalogService.list_rules_for_service(db, svc.id)
        if not rules:
            raise ValueError("No pricing rules configured for this service")

        count = max(int(recipient_count or 0), 0)
        lines: list[dict[str, Any]] = []
        total = 0

        if service_code == "survey":
            channel = PlatformCatalogService.resolve_survey_channel(options)
            selected_rule_id = options.get("package_id") or options.get("rule_id") or options.get("selected_rule_id")

            base_rule = next((r for r in rules if r.channel == "base"), None)
            if base_rule is not None:
                base_amt = int(base_rule.base_fee_pence or 0)
                if base_amt > 0:
                    total += base_amt
                    lines.append(
                        {
                            "kind": "setup",
                            "channel": "base",
                            "rule_id": base_rule.id,
                            "label": base_rule.label,
                            "amount_pence": base_amt,
                            "detail": f"{base_rule.label}: {PlatformCatalogService._money(base_amt)}",
                        }
                    )

            bundle_rule = PlatformCatalogService._pick_survey_bundle_rule(
                rules,
                channel=channel,
                recipient_count=count,
                selected_rule_id=str(selected_rule_id) if selected_rule_id else None,
            )
            bundle_total, bundle_lines = PlatformCatalogService._quote_survey_bundle(bundle_rule, count)
            total += bundle_total
            lines.extend(bundle_lines)

            logger.info(
                "survey_quote channel=%s contacts=%s rule_id=%s total_pence=%s",
                channel,
                count,
                bundle_rule.id,
                total,
            )

            return {
                "service_code": service_code,
                "survey_channel": channel,
                "recipient_count": count,
                "selected_package_id": bundle_rule.id,
                "total_pence": total,
                "total_gbp": PlatformCatalogService._money(total),
                "lines": lines,
                "currency": "GBP",
            }

        if service_code == "interview":
            delivery = PlatformCatalogService.normalize_survey_channel(str(options.get("delivery") or "ai_call"))
            if delivery not in {"ai_call", "zoom"}:
                raise ValueError("Interview delivery must be ai_call or zoom")
            rule = next((r for r in rules if PlatformCatalogService.normalize_survey_channel(r.channel) == delivery), None)
            if rule is None:
                raise ValueError(f"No pricing rule for interview channel: {delivery}")

            from app.services.voxbulk_pricing_service import VoxbulkPricingService

            settings = VoxbulkPricingService.get_settings(db)
            org_id = str(options.get("org_id") or "").strip() or None
            plan_id = str(options.get("plan_id") or "").strip() or None
            plan = None
            if plan_id:
                from app.models.plan import Plan

                plan = db.get(Plan, plan_id)
            rates = VoxbulkPricingService.resolve_rates_for_org(db, org_id, plan=plan)
            duration = max(
                int(options.get("duration_minutes") or settings.estimator_default_duration_min or 12),
                1,
            )
            per_min = int(rates["interview_per_min_pence"])
            conn = int(rates["connection_fee_pence"]) if delivery == "ai_call" else 0

            if str(rule.rule_type) == "per_minute" or delivery == "ai_call":
                per_call = VoxbulkPricingService.interview_call_cost_pence(
                    per_min_pence=per_min,
                    duration_min=duration,
                    connection_fee_pence=conn,
                )
                amt = per_call * count
                detail = (
                    f"AI interview: {count} × ({PlatformCatalogService._money(conn)} connection + "
                    f"{duration} min × {PlatformCatalogService._money(per_min)}/min) = "
                    f"{PlatformCatalogService._money(amt)}"
                )
                if conn > 0:
                    lines.append(
                        {
                            "kind": "connection_fee",
                            "channel": delivery,
                            "label": settings.connection_fee_label,
                            "amount_pence": conn * count,
                            "detail": f"{settings.connection_fee_label}: {count} × {PlatformCatalogService._money(conn)}",
                        }
                    )
                minute_amt = per_min * duration * count
                lines.append(
                    {
                        "kind": "per_minute",
                        "channel": delivery,
                        "label": rule.label,
                        "amount_pence": minute_amt,
                        "detail": f"Call minutes: {count} × {duration} min × {PlatformCatalogService._money(per_min)}/min",
                        "duration_minutes": duration,
                        "per_min_pence": per_min,
                    }
                )
                total += amt
            else:
                amt, detail = PlatformCatalogService._line_amount(rule, count)
                total += amt
                lines.append({"channel": delivery, "label": rule.label, "amount_pence": amt, "detail": detail})
        else:
            for rule in rules:
                amt, detail = PlatformCatalogService._line_amount(rule, count)
                total += amt
                lines.append({"channel": rule.channel, "label": rule.label, "amount_pence": amt, "detail": detail})

        return {
            "service_code": service_code,
            "recipient_count": count,
            "total_pence": total,
            "total_gbp": PlatformCatalogService._money(total),
            "lines": lines,
            "currency": "GBP",
        }


class ServiceOrderService:
    RECIPIENT_TEMPLATE_HEADERS = ["name", "phone", "email"]

    @staticmethod
    def recipient_template_csv() -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(ServiceOrderService.RECIPIENT_TEMPLATE_HEADERS)
        writer.writerow(["Sarah Ahmed", "+447700900123", "sarah@example.com"])
        writer.writerow(["James Lee", "+447700900456", ""])
        return buf.getvalue()

    @staticmethod
    def _norm_header(h: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(h or "").strip().lower())

    @staticmethod
    def parse_recipient_file(content: bytes, filename: str) -> list[dict[str, str]]:
        name = str(filename or "").lower()
        rows: list[dict[str, str]] = []
        if name.endswith(".xlsx") or name.endswith(".xls"):
            try:
                import openpyxl
            except ImportError as e:
                raise ValueError("Excel upload requires openpyxl on the server. Use CSV for now.") from e
            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            ws = wb.active
            header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
            if not header_row:
                return []
            headers = [ServiceOrderService._norm_header(x) for x in header_row]
            for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                data = {headers[i]: (str(row[i]).strip() if i < len(row) and row[i] is not None else "") for i in range(len(headers))}
                parsed = ServiceOrderService._row_from_dict(data, idx)
                if parsed:
                    rows.append(parsed)
            return rows
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row: name, phone, email")
        for idx, raw in enumerate(reader, start=2):
            data = {ServiceOrderService._norm_header(k): str(v or "").strip() for k, v in raw.items()}
            parsed = ServiceOrderService._row_from_dict(data, idx)
            if parsed:
                rows.append(parsed)
        return rows

    @staticmethod
    def _row_from_dict(data: dict[str, str], row_number: int) -> dict[str, str] | None:
        name = data.get("name") or data.get("fullname") or data.get("contactname") or ""
        phone = data.get("phone") or data.get("mobile") or data.get("telephone") or data.get("phonenumber") or ""
        email = data.get("email") or data.get("emailaddress") or ""
        if not name and not phone:
            return None
        if not name or not phone:
            raise ValueError(f"Row {row_number}: name and phone are required")
        return {"name": name, "phone": phone, "email": email or None}

    @staticmethod
    def order_to_dict(order: ServiceOrder, *, include_recipients: bool = False, recipients: list[ServiceOrderRecipient] | None = None) -> dict[str, Any]:
        config = {}
        breakdown = []
        quote_meta: dict[str, Any] = {}
        report = None
        try:
            if order.config_json:
                config = json.loads(order.config_json)
        except Exception:
            config = {}
        try:
            if order.quote_breakdown_json:
                parsed = json.loads(order.quote_breakdown_json)
                if isinstance(parsed, dict):
                    breakdown = parsed.get("lines") or []
                    quote_meta = {
                        "survey_channel": parsed.get("survey_channel"),
                        "selected_package_id": parsed.get("selected_package_id"),
                    }
                else:
                    breakdown = parsed
        except Exception:
            breakdown = []
        try:
            if order.report_json:
                report = json.loads(order.report_json)
        except Exception:
            report = None
        out = {
            "id": order.id,
            "org_id": order.org_id,
            "user_id": order.user_id,
            "service_code": order.service_code,
            "title": order.title,
            "reference_id": order.reference_id,
            "campaign_id": order.campaign_id,
            "status": order.status,
            "payment_status": order.payment_status,
            "recipient_count": order.recipient_count,
            "quote_total_pence": order.quote_total_pence,
            "quote_total_gbp": f"£{int(order.quote_total_pence or 0) / 100:.2f}",
            "quote_breakdown": breakdown,
            "quote_survey_channel": quote_meta.get("survey_channel"),
            "quote_selected_package_id": quote_meta.get("selected_package_id"),
            "config": config,
            "run_mode": order.run_mode,
            "scheduled_start_at": order.scheduled_start_at.isoformat() if order.scheduled_start_at else None,
            "scheduled_end_at": order.scheduled_end_at.isoformat() if order.scheduled_end_at else None,
            "started_at": order.started_at.isoformat() if order.started_at else None,
            "completed_at": order.completed_at.isoformat() if order.completed_at else None,
            "payment_method": order.payment_method,
            "payment_note": order.payment_note,
            "admin_decision_note": order.admin_decision_note,
            "report": report,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        }
        if include_recipients:
            out["recipients"] = [ServiceOrderService.recipient_to_dict(r) for r in (recipients or [])]
        out["is_archived"] = ServiceOrderService.is_archived_order(order)
        if order.service_code == "survey":
            out["next_action"] = ServiceOrderService.survey_next_action(order)
            out["status_label"] = ServiceOrderService.survey_status_label(order)
            out["is_live"] = ServiceOrderService.is_live_survey(order)
            out["is_finished"] = ServiceOrderService.is_finished_survey(order)
            out["audit_timeline"] = ServiceOrderService.order_audit_timeline(order)
        if order.service_code == "interview":
            out["is_live"] = ServiceOrderService.is_live_interview(order)
            out["is_finished"] = ServiceOrderService.is_finished_interview(order)
            out["status_label"] = ServiceOrderService.interview_status_label(order)
            from app.services.interview_cv_email_service import interview_cv_phase_payload

            out["cv_collection"] = interview_cv_phase_payload(order)
        return out

    @staticmethod
    def recipient_to_dict(recipient: ServiceOrderRecipient) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            if recipient.result_json:
                parsed = json.loads(recipient.result_json)
                if isinstance(parsed, dict):
                    result = parsed
        except Exception:
            result = {}
        analysis = result.get("analysis") if isinstance(result.get("analysis"), dict) else {}
        out = {
            "id": recipient.id,
            "row_number": recipient.row_number,
            "name": recipient.name,
            "phone": recipient.phone,
            "email": recipient.email,
            "status": recipient.status,
            "duration_seconds": result.get("duration_seconds"),
            "call_summary": result.get("call_summary"),
            "sentiment": analysis.get("sentiment") or result.get("sentiment"),
            "short_summary": analysis.get("short_summary") or result.get("short_summary"),
            "created_at": recipient.created_at.isoformat() if recipient.created_at else None,
        }
        if recipient.cv_quality is not None or recipient.cv_filename or recipient.intake_source or recipient.cv_text:
            from app.services.interview_intake_service import compute_intake_errors
            from app.services.interview_ats_service import ats_display_for_recipient

            out.update(
                {
                    "cv_quality": recipient.cv_quality or "missing",
                    "cv_filename": recipient.cv_filename,
                    "intake_source": recipient.intake_source,
                    "intake_errors": compute_intake_errors(recipient),
                    "intake_ready": bool(str(recipient.name or "").strip() and str(recipient.phone or "").strip()),
                    "has_cv_file": bool(recipient.cv_storage_key or (recipient.cv_text or "").strip()),
                }
            )
            out.update(ats_display_for_recipient(recipient, position=""))
        return out

    @staticmethod
    def order_audit_timeline(order: ServiceOrder) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        def add(at, kind, label, detail=""):
            if not at:
                return
            events.append(
                {
                    "at": at.isoformat() if hasattr(at, "isoformat") else str(at),
                    "kind": kind,
                    "label": label,
                    "detail": detail or None,
                }
            )

        label_created = "Interview created" if order.service_code == "interview" else "Survey created"
        label_started = "Interview started" if order.service_code == "interview" else "Survey started"
        label_finished = "Interview finished" if order.service_code == "interview" else "Survey finished"
        label_paused = "Interview paused" if order.service_code == "interview" else "Survey paused"
        label_cancelled = "Interview cancelled" if order.service_code == "interview" else "Survey cancelled"

        add(order.created_at, "created", label_created)
        add(order.updated_at, "updated", "Last updated")
        if order.payment_status == "pending_approval":
            add(order.updated_at, "payment", "Cash payment submitted", order.payment_note)
        if order.payment_status == "approved":
            add(order.updated_at, "payment", "Payment approved", order.admin_decision_note or order.payment_note)
        if order.payment_status == "rejected":
            add(order.updated_at, "payment", "Payment rejected", order.admin_decision_note or order.payment_note)
        add(order.scheduled_start_at, "schedule", "Scheduled start")
        add(order.scheduled_end_at, "schedule", "Scheduled end")
        add(order.started_at, "status", label_started)
        add(order.completed_at, "status", label_finished)
        if order.status == "paused":
            add(order.updated_at, "status", label_paused)
        if order.status == "cancelled":
            add(order.completed_at or order.updated_at, "status", label_cancelled, order.admin_decision_note)
        events.sort(key=lambda e: e["at"] or "")
        return events

    @staticmethod
    def update_recipient(
        db: Session,
        order: ServiceOrder,
        recipient: ServiceOrderRecipient,
        payload: dict[str, Any],
    ) -> ServiceOrderRecipient:
        if recipient.order_id != order.id:
            raise ValueError("Recipient does not belong to this order")
        if order.status == "completed":
            raise ValueError("Cannot edit contacts on a completed survey")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Name is required")
            recipient.name = name
        if "phone" in payload:
            phone = str(payload.get("phone") or "").strip()
            if not phone:
                raise ValueError("Phone is required")
            recipient.phone = phone
        if "email" in payload:
            email = str(payload.get("email") or "").strip()
            recipient.email = email or None
        if "status" in payload and str(payload.get("status") or "").strip():
            recipient.status = str(payload.get("status")).strip()
        db.add(recipient)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(recipient)
        return recipient

    @staticmethod
    def survey_operations_overview(db: Session) -> dict[str, Any]:
        rows = list(
            db.execute(select(ServiceOrder).where(ServiceOrder.service_code == "survey")).scalars()
        )
        running = sum(1 for r in rows if r.status == "running")
        paused = sum(1 for r in rows if r.status == "paused")
        completed = sum(1 for r in rows if r.status == "completed")
        failed_pay = sum(1 for r in rows if r.payment_status == "rejected")
        live = sum(1 for r in rows if ServiceOrderService.is_live_survey(r))
        scheduled = sum(1 for r in rows if r.status == "scheduled")
        pending = sum(1 for r in rows if r.payment_status == "pending_approval")
        return {
            "total": len(rows),
            "live": live,
            "running": running,
            "paused": paused,
            "scheduled": scheduled,
            "completed": completed,
            "failed_payments": failed_pay,
            "pending_payment_approval": pending,
        }

    @staticmethod
    def interview_operations_overview(db: Session) -> dict[str, Any]:
        rows = list(
            db.execute(select(ServiceOrder).where(ServiceOrder.service_code == "interview")).scalars()
        )
        running = sum(1 for r in rows if r.status == "running")
        paused = sum(1 for r in rows if r.status == "paused")
        completed = sum(1 for r in rows if r.status == "completed")
        failed_pay = sum(1 for r in rows if r.payment_status == "rejected")
        live = sum(1 for r in rows if ServiceOrderService.is_live_interview(r))
        scheduled = sum(1 for r in rows if r.status == "scheduled")
        pending = sum(1 for r in rows if r.payment_status == "pending_approval")
        drafts = sum(1 for r in rows if r.status == "draft")
        return {
            "total": len(rows),
            "live": live,
            "running": running,
            "paused": paused,
            "scheduled": scheduled,
            "completed": completed,
            "failed_payments": failed_pay,
            "pending_payment_approval": pending,
            "drafts": drafts,
        }

    @staticmethod
    def is_archived_order(order: ServiceOrder) -> bool:
        return str(order.status or "") == "archived"

    @staticmethod
    def is_finished_interview(order: ServiceOrder) -> bool:
        return (
            order.service_code == "interview"
            and str(order.status or "") in {"completed", "cancelled"}
            and not ServiceOrderService.is_archived_order(order)
        )

    @staticmethod
    def is_live_interview(order: ServiceOrder) -> bool:
        return (
            order.service_code == "interview"
            and not ServiceOrderService.is_finished_interview(order)
            and not ServiceOrderService.is_archived_order(order)
        )

    @staticmethod
    def interview_status_label(order: ServiceOrder) -> str:
        if order.status == "running":
            return "Live"
        if order.status == "completed":
            return "Completed"
        if order.status == "cancelled":
            return "Cancelled"
        if order.status == "archived":
            return "Archived"
        if order.payment_status == "pending_approval":
            return "Awaiting payment"
        if order.status in {"quoted", "awaiting_payment"}:
            return "Quoted"
        if order.status == "scheduled":
            return "Scheduled"
        if order.status == "draft":
            return "Draft"
        return order.status or "—"

    @staticmethod
    def is_finished_survey(order: ServiceOrder) -> bool:
        return (
            order.service_code == "survey"
            and str(order.status or "") in {"completed", "cancelled"}
            and not ServiceOrderService.is_archived_order(order)
        )

    @staticmethod
    def is_live_survey(order: ServiceOrder) -> bool:
        return (
            order.service_code == "survey"
            and not ServiceOrderService.is_finished_survey(order)
            and not ServiceOrderService.is_archived_order(order)
        )

    @staticmethod
    def survey_status_label(order: ServiceOrder) -> str:
        ps = str(order.payment_status or "")
        st = str(order.status or "")
        if ps == "pending_approval":
            return "Pending payment"
        if ps == "rejected":
            return "Payment failed"
        if st == "draft":
            return "Draft"
        if st == "quoted":
            return "Quoted"
        if st == "awaiting_payment":
            return "Awaiting payment"
        if st == "scheduled":
            return "Scheduled"
        if st == "running":
            return "Running"
        if st == "paused":
            return "Paused"
        if st == "paid":
            return "Paid — ready"
        if st == "completed":
            return "Finished"
        if st == "cancelled":
            return "Cancelled"
        if st == "archived":
            return "Archived"
        return st.replace("_", " ").title()

    @staticmethod
    def survey_next_action(order: ServiceOrder) -> dict[str, Any]:
        config: dict[str, Any] = {}
        try:
            config = json.loads(order.config_json or "{}")
        except Exception:
            config = {}
        ps = str(order.payment_status or "")
        st = str(order.status or "")

        if st == "completed":
            return {"action": "view_report", "label": "View report", "hint": "Open anonymous aggregate results."}
        if st == "cancelled":
            return {"action": "reopen", "label": "Reopen survey", "hint": "Duplicate this survey to launch again."}
        if ps == "rejected":
            reason = (order.admin_decision_note or order.payment_note or "Payment was rejected.").strip()
            return {"action": "pay", "label": "Retry payment", "hint": reason, "reason": reason}
        if ps == "pending_approval":
            return {
                "action": "wait",
                "label": "Waiting for approval",
                "hint": "Admin must approve your cash payment before the survey can start.",
            }
        if ps == "unpaid" and st in {"draft", "quoted", "awaiting_payment"}:
            if not config.get("script_approved"):
                return {"action": "approve_prompt", "label": "Approve prompt", "hint": "Approve the AI script before paying."}
            if not order.scheduled_start_at:
                return {"action": "set_schedule", "label": "Set date and time", "hint": "Choose when calls should start and end."}
            if order.recipient_count <= 0:
                return {"action": "upload_contacts", "label": "Upload contacts", "hint": "Add a contact list to continue."}
            return {
                "action": "pay",
                "label": "Pay now",
                "hint": f"Total due: £{int(order.quote_total_pence or 0) / 100:.2f}",
            }
        if ps == "approved" and st in {"paid", "scheduled"}:
            if order.run_mode == "scheduled" and order.scheduled_start_at:
                return {"action": "wait", "label": "Scheduled", "hint": "Survey will start automatically at the scheduled time."}
            return {"action": "start", "label": "Start survey", "hint": "Payment approved — start outbound calls."}
        if st == "running":
            return {"action": "pause", "label": "Pause survey", "hint": "Pause outbound calls. You can resume later."}
        if st == "paused":
            return {"action": "resume", "label": "Resume survey", "hint": "Continue outbound calls."}
        return {"action": "edit", "label": "Review survey", "hint": "Open details to review settings."}

    @staticmethod
    def order_to_admin_dict(
        db: Session,
        order: ServiceOrder,
        *,
        include_recipients: bool = False,
        recipients: list[ServiceOrderRecipient] | None = None,
    ) -> dict[str, Any]:
        from app.models.organisation import Organisation
        from app.models.user import User

        out = ServiceOrderService.order_to_dict(order, include_recipients=include_recipients, recipients=recipients)
        org = db.get(Organisation, order.org_id)
        user = db.get(User, order.user_id)
        out["org_name"] = org.name if org else None
        out["org_phone"] = getattr(org, "contact_phone", None) if org else None
        out["owner_email"] = user.email if user else None
        return out

    @staticmethod
    def delete_order(db: Session, order: ServiceOrder) -> None:
        if order.status in {"running", "paused"}:
            raise ValueError("Stop the survey before deleting")
        if order.payment_status == "approved" and order.status not in {"completed", "cancelled", "draft", "quoted"}:
            raise ValueError("Cannot delete a paid survey that has started")
        db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
        db.delete(order)
        db.commit()

    @staticmethod
    def pause_order(db: Session, order: ServiceOrder) -> ServiceOrder:
        if order.status != "running":
            raise ValueError("Only running surveys can be paused")
        order.status = "paused"
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def resume_order(db: Session, order: ServiceOrder) -> ServiceOrder:
        if order.status != "paused":
            raise ValueError("Survey is not paused")
        if order.payment_status != "approved":
            raise ValueError("Payment must be approved before resuming")
        order.status = "running"
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        if order.service_code == "survey":
            from app.services.survey_call_dispatch_service import SurveyCallDispatchService, is_ai_call_survey_order

            if is_ai_call_survey_order(order):
                SurveyCallDispatchService.dial_next_recipient(db, order)
        return order

    @staticmethod
    def stop_order(db: Session, order: ServiceOrder, *, reason: str | None = None) -> ServiceOrder:
        if order.status not in {"running", "paused", "scheduled", "paid"}:
            raise ValueError("Survey is not active")
        now = datetime.utcnow()
        recipients = ServiceOrderService.get_recipients(db, order.id)
        for recipient in recipients:
            if str(recipient.status or "pending").lower() in {"pending", "calling"}:
                recipient.status = "cancelled"
                db.add(recipient)
        order.status = "cancelled" if order.started_at else "cancelled"
        if not order.started_at and order.payment_status == "approved":
            order.status = "cancelled"
        order.completed_at = now
        order.updated_at = now
        note = (reason or "").strip()
        if note:
            order.admin_decision_note = note
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def complete_order(db: Session, order: ServiceOrder) -> ServiceOrder:
        if order.status not in {"running", "paused"}:
            raise ValueError("Only running surveys can be finished")
        now = datetime.utcnow()
        order.status = "completed"
        order.completed_at = now
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def create_order(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        service_code: str,
        title: str,
        config: dict[str, Any] | None = None,
    ) -> ServiceOrder:
        if service_code not in {"survey", "interview"}:
            raise ValueError("service_code must be survey or interview")
        order = ServiceOrder(
            org_id=org_id,
            user_id=user_id,
            service_code=service_code,
            title=title.strip() or ("Survey order" if service_code == "survey" else "Interview order"),
            status="draft",
            payment_status="unpaid",
            config_json=json.dumps(config or {}, ensure_ascii=False),
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        if service_code == "interview":
            from app.services.interview_campaign_service import ensure_campaign_id
            from app.services.interview_reference_service import ensure_order_reference_id

            order = ensure_campaign_id(db, order)
            order = ensure_order_reference_id(db, order)
        return order

    @staticmethod
    def replace_recipients(db: Session, order: ServiceOrder, rows: list[dict[str, str]]) -> ServiceOrder:
        if order.payment_status == "approved":
            raise ValueError("Cannot change recipients after payment is approved")
        db.execute(delete(ServiceOrderRecipient).where(ServiceOrderRecipient.order_id == order.id))
        for i, row in enumerate(rows, start=1):
            db.add(
                ServiceOrderRecipient(
                    order_id=order.id,
                    row_number=i,
                    name=row["name"],
                    phone=row["phone"],
                    email=row.get("email"),
                    status="pending",
                )
            )
        order.recipient_count = len(rows)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def update_order(db: Session, order: ServiceOrder, payload: dict[str, Any]) -> ServiceOrder:
        if order.payment_status == "approved" and order.status in {"running", "completed"}:
            raise ValueError("Order can no longer be edited")
        config = {}
        try:
            config = json.loads(order.config_json or "{}")
        except Exception:
            config = {}
        if "config" in payload and isinstance(payload["config"], dict):
            config.update(payload["config"])
            order.config_json = json.dumps(config, ensure_ascii=False)
        if payload.get("title"):
            order.title = str(payload["title"]).strip()
        if payload.get("run_mode") in {"manual", "scheduled"}:
            order.run_mode = str(payload["run_mode"])
        if payload.get("scheduled_start_at"):
            order.scheduled_start_at = datetime.fromisoformat(str(payload["scheduled_start_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
        if payload.get("scheduled_end_at"):
            order.scheduled_end_at = datetime.fromisoformat(str(payload["scheduled_end_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def quote_order(db: Session, order: ServiceOrder) -> ServiceOrder:
        if order.recipient_count <= 0:
            raise ValueError("Upload a contact list before requesting a quote")
        if order.service_code == "interview":
            from app.services.interview_cv_email_service import assert_cv_collection_complete

            assert_cv_collection_complete(order)
        config = json.loads(order.config_json or "{}")
        quote = PlatformCatalogService.calculate_quote(
            db,
            service_code=order.service_code,
            recipient_count=order.recipient_count,
            options=config,
        )
        order.quote_total_pence = int(quote["total_pence"])
        order.quote_breakdown_json = json.dumps(quote, ensure_ascii=False)
        order.status = "quoted"
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def submit_cash_payment(db: Session, order: ServiceOrder, note: str | None = None) -> ServiceOrder:
        if order.status not in {"quoted", "draft"} or order.quote_total_pence <= 0:
            raise ValueError("Generate a quote before marking payment")
        order.payment_method = "cash"
        order.payment_status = "pending_approval"
        order.payment_note = (note or "").strip() or None
        order.status = "awaiting_payment"
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def admin_approve_payment(db: Session, order: ServiceOrder, note: str | None = None) -> ServiceOrder:
        if order.payment_status != "pending_approval":
            raise ValueError("Order is not awaiting payment approval")
        order.payment_status = "approved"
        order.status = "paid"
        order.admin_decision_note = (note or "").strip() or None
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def admin_reject_payment(db: Session, order: ServiceOrder, note: str | None = None) -> ServiceOrder:
        if order.payment_status != "pending_approval":
            raise ValueError("Order is not awaiting payment approval")
        order.payment_status = "rejected"
        order.status = "quoted"
        order.admin_decision_note = (note or "").strip() or None
        order.updated_at = datetime.utcnow()
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def schedule_order(db: Session, order: ServiceOrder) -> ServiceOrder:
        """Mark a paid order as scheduled/ready without dispatching calls."""
        if order.payment_status != "approved":
            raise ValueError("Payment must be approved before scheduling")
        if order.status in {"running", "completed"}:
            raise ValueError("Order is already running or completed")
        now = datetime.utcnow()
        if order.run_mode == "scheduled" and order.scheduled_start_at and now < order.scheduled_start_at:
            order.status = "scheduled"
        else:
            order.status = "paid"
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def start_order(db: Session, order: ServiceOrder) -> ServiceOrder:
        if order.payment_status != "approved":
            raise ValueError("Payment must be approved by admin before starting")
        if order.status == "paused":
            raise ValueError("Survey is paused — use resume instead")
        if order.status in {"running", "completed"}:
            raise ValueError("Order is already running or completed")
        if order.service_code == "interview":
            from app.services.interview_cv_email_service import (
                assert_ai_call_window_after_cv_collection,
                assert_cv_collection_complete,
            )

            assert_cv_collection_complete(order)
            assert_ai_call_window_after_cv_collection(order)
            config_iv = {}
            try:
                config_iv = json.loads(order.config_json or "{}")
            except Exception:
                config_iv = {}
            delivery = str(config_iv.get("delivery") or "ai_call").strip().lower()
            if delivery == "zoom":
                from app.services.interview_zoom_service import InterviewZoomService

                InterviewZoomService.start_campaign(db, order)
                db.refresh(order)
                return order
        now = datetime.utcnow()
        if order.run_mode == "scheduled":
            if order.scheduled_start_at and now < order.scheduled_start_at:
                order.status = "scheduled"
                order.updated_at = now
                db.add(order)
                db.commit()
                db.refresh(order)
                return order
        if order.service_code == "survey":
            config = {}
            try:
                config = json.loads(order.config_json or "{}")
            except Exception:
                config = {}
            channel = PlatformCatalogService.resolve_survey_channel(config)
            if channel == "ai_call":
                from app.services.survey_call_dispatch_service import SurveyCallDispatchService, is_ai_call_survey_order

                if is_ai_call_survey_order(order):
                    if not SurveyCallDispatchService.start_campaign(db, order):
                        raise ValueError(
                            "Could not start AI calls — check payment, approved script, voice agent, and calling window."
                        )
                    db.refresh(order)
                    return order
            elif channel != "ai_call":
                from app.services.survey_dispatch_service import SurveyDispatchService

                order.status = "running"
                order.started_at = now
                order.updated_at = now
                db.add(order)
                db.commit()
                db.refresh(order)
                SurveyDispatchService.dispatch_survey_order(db, order)
                db.refresh(order)
                return order
        if order.service_code == "interview":
            from app.services.interview_call_dispatch_service import (
                InterviewCallDispatchService,
                is_ai_call_interview_order,
            )

            if is_ai_call_interview_order(order):
                if not InterviewCallDispatchService.start_campaign(db, order):
                    raise ValueError(
                        "Could not start AI interviews — check payment, approved script, voice agent, and calling window."
                    )
                db.refresh(order)
                return order
        order.status = "running"
        order.started_at = now
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    @staticmethod
    def list_orders(db: Session, *, org_id: str | None = None, service_code: str | None = None, limit: int = 100) -> list[ServiceOrder]:
        stmt = select(ServiceOrder).order_by(ServiceOrder.created_at.desc()).limit(limit)
        if org_id:
            stmt = stmt.where(ServiceOrder.org_id == org_id)
        if service_code:
            stmt = stmt.where(ServiceOrder.service_code == service_code)
        return list(db.execute(stmt).scalars())

    @staticmethod
    def get_order(db: Session, order_id: str, *, org_id: str | None = None) -> ServiceOrder | None:
        stmt = select(ServiceOrder).where(ServiceOrder.id == order_id)
        if org_id:
            stmt = stmt.where(ServiceOrder.org_id == org_id)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_recipients(db: Session, order_id: str) -> list[ServiceOrderRecipient]:
        return list(
            db.execute(
                select(ServiceOrderRecipient)
                .where(ServiceOrderRecipient.order_id == order_id)
                .order_by(ServiceOrderRecipient.row_number.asc())
            ).scalars()
        )

    @staticmethod
    def get_recipient(db: Session, order_id: str, recipient_id: str) -> ServiceOrderRecipient | None:
        return db.execute(
            select(ServiceOrderRecipient).where(
                ServiceOrderRecipient.order_id == order_id,
                ServiceOrderRecipient.id == recipient_id,
            )
        ).scalar_one_or_none()
