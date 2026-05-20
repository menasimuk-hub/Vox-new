from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.platform_service import PlatformService, ServicePricingRule
from app.models.service_order import ServiceOrder, ServiceOrderRecipient


class PlatformCatalogService:
    DEFAULT_SERVICES = [
        {
            "code": "survey",
            "name": "Survey",
            "description": "Bulk WhatsApp + AI call surveys with smart reporting.",
            "service_kind": "order",
            "sort_order": 10,
            "rules": [
                {"channel": "base", "rule_type": "flat_per_order", "label": "Survey setup fee", "base_fee_pence": 500},
                {"channel": "whatsapp", "rule_type": "bundle", "label": "WhatsApp — 100 contacts", "bundle_size": 100, "bundle_price_pence": 1500},
                {"channel": "call", "rule_type": "per_person", "label": "AI call — per contact", "unit_price_pence": 18},
            ],
        },
        {
            "code": "interview",
            "name": "Interview",
            "description": "AI phone or Zoom interview screening campaigns.",
            "service_kind": "order",
            "sort_order": 20,
            "rules": [
                {"channel": "ai_call", "rule_type": "per_person", "label": "Interview AI call — per person", "unit_price_pence": 350},
                {"channel": "zoom", "rule_type": "per_person", "label": "Interview Zoom — per person", "unit_price_pence": 500},
            ],
        },
    ]

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
                existing = db.execute(
                    select(ServicePricingRule.id).where(
                        ServicePricingRule.service_id == row.id,
                        ServicePricingRule.channel == rule["channel"],
                        ServicePricingRule.rule_type == rule["rule_type"],
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                db.add(
                    ServicePricingRule(
                        service_id=row.id,
                        channel=str(rule["channel"]),
                        rule_type=str(rule["rule_type"]),
                        label=str(rule["label"]),
                        base_fee_pence=int(rule.get("base_fee_pence") or 0),
                        unit_price_pence=int(rule.get("unit_price_pence") or 0),
                        bundle_size=int(rule["bundle_size"]) if rule.get("bundle_size") else None,
                        bundle_price_pence=int(rule["bundle_price_pence"]) if rule.get("bundle_price_pence") else None,
                        is_active=True,
                    )
                )
        db.commit()

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
        stmt = select(ServicePricingRule).where(ServicePricingRule.service_id == service_id).order_by(ServicePricingRule.sort_order.asc())
        if active_only:
            stmt = stmt.where(ServicePricingRule.is_active.is_(True))
        return list(db.execute(stmt).scalars())

    @staticmethod
    def _line_amount(rule: ServicePricingRule, count: int) -> tuple[int, str]:
        count = max(int(count or 0), 0)
        rt = str(rule.rule_type)
        if rt == "flat_per_order":
            amt = int(rule.base_fee_pence or 0)
            return amt, f"{rule.label}: £{amt / 100:.2f}"
        if rt == "per_person":
            amt = count * int(rule.unit_price_pence or 0)
            return amt, f"{rule.label}: {count} × £{int(rule.unit_price_pence or 0) / 100:.2f} = £{amt / 100:.2f}"
        if rt == "bundle":
            size = max(int(rule.bundle_size or 1), 1)
            price = int(rule.bundle_price_pence or 0)
            blocks = math.ceil(count / size) if count else 0
            amt = blocks * price
            return amt, f"{rule.label}: {blocks} block(s) = £{amt / 100:.2f}"
        if rt == "flat_plus_per_person":
            amt = int(rule.base_fee_pence or 0) + count * int(rule.unit_price_pence or 0)
            return amt, f"{rule.label}: £{amt / 100:.2f}"
        return 0, rule.label

    @staticmethod
    def calculate_quote(db: Session, *, service_code: str, recipient_count: int, options: dict[str, Any] | None = None) -> dict[str, Any]:
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
            channels = ["base", "whatsapp", "call"]
            for ch in channels:
                rule = next((r for r in rules if r.channel == ch), None)
                if rule is None:
                    continue
                amt, detail = PlatformCatalogService._line_amount(rule, count)
                total += amt
                lines.append({"channel": ch, "label": rule.label, "amount_pence": amt, "detail": detail})
        elif service_code == "interview":
            delivery = str(options.get("delivery") or "ai_call").strip().lower()
            if delivery not in {"ai_call", "zoom"}:
                raise ValueError("Interview delivery must be ai_call or zoom")
            rule = next((r for r in rules if r.channel == delivery), None)
            if rule is None:
                raise ValueError(f"No pricing rule for interview channel: {delivery}")
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
            "total_gbp": f"£{total / 100:.2f}",
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
        report = None
        try:
            if order.config_json:
                config = json.loads(order.config_json)
        except Exception:
            config = {}
        try:
            if order.quote_breakdown_json:
                parsed = json.loads(order.quote_breakdown_json)
                breakdown = parsed.get("lines") if isinstance(parsed, dict) else parsed
        except Exception:
            breakdown = []
        try:
            if order.report_json:
                report = json.loads(order.report_json)
        except Exception:
            report = None
        out = {
            "id": order.id,
            "service_code": order.service_code,
            "title": order.title,
            "status": order.status,
            "payment_status": order.payment_status,
            "recipient_count": order.recipient_count,
            "quote_total_pence": order.quote_total_pence,
            "quote_total_gbp": f"£{int(order.quote_total_pence or 0) / 100:.2f}",
            "quote_breakdown": breakdown,
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
            out["recipients"] = [
                {
                    "id": r.id,
                    "row_number": r.row_number,
                    "name": r.name,
                    "phone": r.phone,
                    "email": r.email,
                    "status": r.status,
                }
                for r in (recipients or [])
            ]
        return out

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
    def start_order(db: Session, order: ServiceOrder) -> ServiceOrder:
        if order.payment_status != "approved":
            raise ValueError("Payment must be approved by admin before starting")
        if order.status in {"running", "completed"}:
            raise ValueError("Order is already running or completed")
        now = datetime.utcnow()
        if order.run_mode == "scheduled":
            if order.scheduled_start_at and now < order.scheduled_start_at:
                order.status = "scheduled"
                order.updated_at = now
                db.add(order)
                db.commit()
                db.refresh(order)
                return order
        order.status = "running"
        order.started_at = now
        order.updated_at = now
        db.add(order)
        db.commit()
        db.refresh(order)
        if order.service_code == "survey":
            from app.services.survey_dispatch_service import SurveyDispatchService

            SurveyDispatchService.dispatch_survey_order(db, order)
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
