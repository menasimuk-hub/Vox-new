"""Customer Feedback promo campaigns — quote, pay-then-run, dispatch."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.billing_invoice import BillingInvoice
from app.models.customer_feedback import (
    FeedbackMarketingSubscriber,
    FeedbackPromoCampaign,
)
from app.models.organisation import Organisation
from app.services.billing_currency import resolve_org_currency
from app.services.customer_feedback.billing_service import FeedbackBillingService
from app.services.customer_feedback.feedback_wa_send_service import FeedbackWaSendService

PHONE_RE = re.compile(r"^\+?\d{6,15}$")

# Mirrors vox-connect-suite campaign2-templates (10 pre-approved promo templates).
PROMO_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "tpl_generic",
        "name": "Generic announcement",
        "category": "MARKETING",
        "scenario": "One template that fits anything — offer, news, reminder",
        "body": "Hello 👋\n\n{{1}}\n\nTap below for details: {{2}}",
        "footer": "Reply STOP to opt out.",
        "variables": ["promo", "link"],
    },
    {
        "id": "tpl_seasonal_sale",
        "name": "Seasonal sale",
        "category": "MARKETING",
        "scenario": "Limited-time % off everything",
        "body": "Our seasonal sale is here 🎉\n\n{{1}} off everything until Sunday.\n\nTap below to book your slot.",
        "footer": "Reply STOP to opt out.",
        "variables": ["promo", "link"],
    },
    {
        "id": "tpl_promo_code",
        "name": "Promo code drop",
        "category": "MARKETING",
        "scenario": "Single-use discount code",
        "body": "Here's your exclusive code: *{{1}}*\n\nSave on your next visit when you book this week.",
        "footer": "One use per customer.",
        "variables": ["code"],
    },
    {
        "id": "tpl_new_service",
        "name": "New service launch",
        "category": "MARKETING",
        "scenario": "Announce a brand-new service",
        "body": "Big news ✨\n\nWe just launched {{1}}. Be one of the first to try it.\n\nLearn more: {{2}}",
        "footer": "Limited slots this month.",
        "variables": ["promo", "link"],
    },
    {
        "id": "tpl_flash_sale",
        "name": "Flash sale (24h)",
        "category": "MARKETING",
        "scenario": "Urgent 24-hour offer",
        "body": "⚡ Flash sale — ends tonight!\n\n{{1}}\n\nBook now: {{2}}",
        "footer": "Reply STOP to opt out.",
        "variables": ["promo", "link"],
    },
    {
        "id": "tpl_event_invite",
        "name": "Event invitation",
        "category": "MARKETING",
        "scenario": "Invite customers to an event",
        "body": "You're invited 🎉\n\nJoin us on {{1}}.\n\nRSVP: {{2}}",
        "footer": "Reply STOP to opt out.",
        "variables": ["date", "link"],
    },
    {
        "id": "tpl_loyalty_reward",
        "name": "Loyalty reward",
        "category": "MARKETING",
        "scenario": "Thank loyal customers with a reward",
        "body": "Thank you for being a loyal customer 💛\n\nEnjoy {{1}} on your next visit.\n\nClaim: {{2}}",
        "footer": "Reply STOP to opt out.",
        "variables": ["promo", "link"],
    },
    {
        "id": "tpl_win_back",
        "name": "Win-back offer",
        "category": "MARKETING",
        "scenario": "Re-engage inactive customers",
        "body": "We miss you! Come back and enjoy {{1}}.\n\nBook here: {{2}}",
        "footer": "Reply STOP to opt out.",
        "variables": ["promo", "link"],
    },
    {
        "id": "tpl_birthday",
        "name": "Birthday treat",
        "category": "MARKETING",
        "scenario": "Birthday month special",
        "body": "Happy birthday month 🎂\n\nTreat yourself with {{1}}.\n\nRedeem: {{2}}",
        "footer": "Reply STOP to opt out.",
        "variables": ["promo", "link"],
    },
    {
        "id": "tpl_referral",
        "name": "Refer a friend",
        "category": "MARKETING",
        "scenario": "Referral programme push",
        "body": "Refer a friend and you both get {{1}}.\n\nShare your link: {{2}}",
        "footer": "Reply STOP to opt out.",
        "variables": ["promo", "link"],
    },
]

_TEMPLATE_BY_ID = {t["id"]: t for t in PROMO_TEMPLATES}


class FeedbackPromoCampaignError(ValueError):
    pass


def _normalize_phones(raw: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        phone = str(item or "").strip().replace(" ", "")
        if not phone:
            continue
        if not phone.startswith("+"):
            phone = f"+{phone.lstrip('0')}"
        if not PHONE_RE.match(phone) or phone in seen:
            continue
        seen.add(phone)
        out.append(phone)
    return out


def _promo_rate_minor(db: Session, org_id: str) -> int:
    sub = FeedbackBillingService.get_active_subscription(db, org_id)
    if sub is None:
        return 5
    pkg = FeedbackBillingService.get_package_for_plan(db, sub.plan_id)
    return int(pkg.promo_message_cost_minor or 5) if pkg else 5


def _promo_meta_template_name(template_id: str) -> str:
    slug = re.sub(r"[^a-z0-9_]+", "_", str(template_id or "").lower()).strip("_")
    return f"cfs_promo_{slug or 'generic'}_v1"[:512]


def _promo_template_components(
    template: dict[str, Any],
    variables: dict[str, str],
) -> list[dict[str, Any]] | None:
    var_list = list(template.get("variables") or [])
    if not var_list:
        return None
    values: list[str] = []
    for key in var_list:
        if key == "promo":
            values.append(str(variables.get("promo") or variables.get("code") or variables.get("date") or "—")[:1024])
        elif key == "code":
            values.append(str(variables.get("code") or "—")[:1024])
        elif key == "link":
            values.append(str(variables.get("link") or "—")[:1024])
        elif key == "date":
            values.append(str(variables.get("date") or "—")[:1024])
        else:
            values.append(str(variables.get(key) or "—")[:1024])
    return [{"type": "body", "parameters": [{"type": "text", "text": v} for v in values]}]


def _render_body(template: dict[str, Any], variables: dict[str, str]) -> str:
    body = str(template.get("body") or "")
    var_list = list(template.get("variables") or [])
    if "promo" in var_list:
        body = body.replace("{{1}}", variables.get("promo") or variables.get("code") or variables.get("date") or "")
    if "code" in var_list and "promo" not in var_list:
        body = body.replace("{{1}}", variables.get("code") or "")
    if "date" in var_list and "promo" not in var_list:
        body = body.replace("{{1}}", variables.get("date") or "")
    if "link" in var_list:
        body = body.replace("{{2}}", variables.get("link") or "")
    return body.strip()


class FeedbackPromoCampaignService:
    @staticmethod
    def list_templates() -> list[dict[str, Any]]:
        return PROMO_TEMPLATES

    @staticmethod
    def _campaign_dict(row: FeedbackPromoCampaign) -> dict[str, Any]:
        return {
            "id": row.id,
            "template_id": row.template_id,
            "template_name": row.template_name,
            "message_body": row.message_body,
            "variables": json.loads(row.variables_json) if row.variables_json else {},
            "use_opt_in_audience": row.use_opt_in_audience,
            "opt_in_count": row.opt_in_count,
            "manual_count": row.manual_count,
            "recipient_count": row.recipient_count,
            "cost_minor": row.cost_minor,
            "currency": row.currency,
            "status": row.status,
            "invoice_id": row.invoice_id,
            "sent_count": row.sent_count,
            "yes_count": row.yes_count,
            "no_count": row.no_count,
            "launched_at": row.launched_at.isoformat() if row.launched_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    @staticmethod
    def quote(
        db: Session,
        *,
        org_id: str,
        template_id: str,
        variables: dict[str, str],
        use_opt_in: bool,
        manual_phones: list[str],
    ) -> dict[str, Any]:
        template = _TEMPLATE_BY_ID.get(template_id)
        if template is None:
            raise FeedbackPromoCampaignError("Unknown template")
        opt_in_count = 0
        if use_opt_in:
            opt_in_count = int(
                db.execute(
                    select(func.count())
                    .select_from(FeedbackMarketingSubscriber)
                    .where(
                        FeedbackMarketingSubscriber.org_id == org_id,
                        FeedbackMarketingSubscriber.is_active.is_(True),
                    )
                ).scalar_one()
                or 0
            )
        manual = _normalize_phones(manual_phones)
        manual_only = [p for p in manual if not use_opt_in or True]
        recipient_count = opt_in_count + len(manual_only)
        rate = _promo_rate_minor(db, org_id)
        org = db.get(Organisation, org_id)
        currency = resolve_org_currency(org) if org else "GBP"
        return {
            "template": template,
            "message_preview": _render_body(template, variables),
            "opt_in_count": opt_in_count,
            "manual_count": len(manual_only),
            "recipient_count": recipient_count,
            "rate_minor": rate,
            "cost_minor": recipient_count * rate,
            "currency": currency,
        }

    @staticmethod
    def create_campaign(db: Session, *, org_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        template_id = str(payload.get("template_id") or "")
        template = _TEMPLATE_BY_ID.get(template_id)
        if template is None:
            raise FeedbackPromoCampaignError("Unknown template")
        variables = dict(payload.get("variables") or {})
        use_opt_in = bool(payload.get("use_opt_in_audience", True))
        manual = _normalize_phones(list(payload.get("manual_phones") or []))
        quote = FeedbackPromoCampaignService.quote(
            db,
            org_id=org_id,
            template_id=template_id,
            variables=variables,
            use_opt_in=use_opt_in,
            manual_phones=manual,
        )
        if quote["recipient_count"] <= 0:
            raise FeedbackPromoCampaignError("Add at least one recipient (opt-in list or phone numbers).")
        now = datetime.utcnow()
        row = FeedbackPromoCampaign(
            id=str(uuid.uuid4()),
            org_id=org_id,
            template_id=template_id,
            template_name=str(template["name"]),
            message_body=str(quote["message_preview"]),
            variables_json=json.dumps(variables),
            use_opt_in_audience=use_opt_in,
            manual_recipients_json=json.dumps(manual),
            opt_in_count=int(quote["opt_in_count"]),
            manual_count=int(quote["manual_count"]),
            recipient_count=int(quote["recipient_count"]),
            cost_minor=int(quote["cost_minor"]),
            currency=str(quote["currency"]),
            status="awaiting_payment",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return FeedbackPromoCampaignService._campaign_dict(row)

    @staticmethod
    def list_campaigns(db: Session, *, org_id: str) -> list[dict[str, Any]]:
        rows = list(
            db.execute(
                select(FeedbackPromoCampaign)
                .where(FeedbackPromoCampaign.org_id == org_id)
                .order_by(FeedbackPromoCampaign.created_at.desc())
                .limit(50)
            )
            .scalars()
            .all()
        )
        return [FeedbackPromoCampaignService._campaign_dict(r) for r in rows]

    @staticmethod
    def dashboard_stats(db: Session, *, org_id: str) -> dict[str, Any]:
        rows = list(
            db.execute(select(FeedbackPromoCampaign).where(FeedbackPromoCampaign.org_id == org_id)).scalars().all()
        )
        sent = sum(int(r.sent_count or 0) for r in rows)
        yes = sum(int(r.yes_count or 0) for r in rows)
        no = sum(int(r.no_count or 0) for r in rows)
        response_rate = (yes + no) / sent * 100 if sent else 0
        positive_rate = yes / (yes + no) * 100 if (yes + no) else 0
        return {
            "totals": {"sent": sent, "coming": yes, "not_interested": no},
            "response_rate": round(response_rate, 1),
            "positive_rate": round(positive_rate, 1),
            "campaigns": [FeedbackPromoCampaignService._campaign_dict(r) for r in rows[:20]],
        }

    @staticmethod
    def checkout(db: Session, *, org_id: str, campaign_id: str) -> dict[str, Any]:
        row = db.get(FeedbackPromoCampaign, campaign_id)
        if row is None or row.org_id != org_id:
            raise FeedbackPromoCampaignError("Campaign not found")
        if row.status not in {"awaiting_payment", "draft"}:
            raise FeedbackPromoCampaignError("Campaign is not awaiting payment")
        if row.invoice_id:
            inv = db.get(BillingInvoice, row.invoice_id)
            if inv is not None:
                return {"ok": True, "invoice_id": inv.id, "invoice_number": inv.invoice_number, "status": inv.status}
        from app.services.org_control_center_actions_service import OrgControlCenterActionsService

        result = OrgControlCenterActionsService.create_invoice(
            db,
            org_id,
            amount_minor=int(row.cost_minor),
            invoice_type="service_order",
            note=f"Promo campaign — {row.template_name} ({row.opt_in_count} opt-in + {row.manual_count} uploaded)",
        )
        invoice = result.get("invoice") or {}
        invoice_id = str(invoice.get("id") or "")
        row.invoice_id = invoice_id or None
        row.status = "pending_payment"
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return {
            "ok": True,
            "invoice_id": invoice_id,
            "invoice_number": invoice.get("invoice_number"),
            "status": invoice.get("status"),
            "cost_minor": row.cost_minor,
            "currency": row.currency,
        }

    @staticmethod
    def launch(db: Session, *, org_id: str, campaign_id: str) -> dict[str, Any]:
        row = db.get(FeedbackPromoCampaign, campaign_id)
        if row is None or row.org_id != org_id:
            raise FeedbackPromoCampaignError("Campaign not found")
        if row.status == "completed":
            return {"ok": True, "status": "completed", "sent_count": row.sent_count}
        if row.status not in {"pending_payment", "paid", "queued"}:
            raise FeedbackPromoCampaignError("Campaign must be paid before launch")
        if row.invoice_id:
            inv = db.get(BillingInvoice, row.invoice_id)
            if inv is None or str(inv.status or "").lower() not in {"paid", "settled", "complete"}:
                raise FeedbackPromoCampaignError("Invoice must be paid before launch")
        recipients: list[str] = []
        if row.use_opt_in_audience:
            subs = list(
                db.execute(
                    select(FeedbackMarketingSubscriber.phone_e164).where(
                        FeedbackMarketingSubscriber.org_id == org_id,
                        FeedbackMarketingSubscriber.is_active.is_(True),
                    )
                )
                .scalars()
                .all()
            )
            recipients.extend(subs)
        if row.manual_recipients_json:
            try:
                manual = json.loads(row.manual_recipients_json)
                if isinstance(manual, list):
                    recipients.extend(_normalize_phones([str(x) for x in manual]))
            except json.JSONDecodeError:
                pass
        recipients = list(dict.fromkeys(recipients))
        template = _TEMPLATE_BY_ID.get(str(row.template_id or ""))
        variables: dict[str, str] = {}
        if row.variables_json:
            try:
                parsed = json.loads(row.variables_json)
                if isinstance(parsed, dict):
                    variables = {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                variables = {}
        sent = 0
        for phone in recipients:
            try:
                if template is not None:
                    meta_name = _promo_meta_template_name(str(row.template_id or ""))
                    components = _promo_template_components(template, variables)
                    body = str(row.message_body or _render_body(template, variables)).strip()
                    langs = ["en_GB", "en_US", "en"]
                    result = None
                    for lang in langs:
                        from app.services.telnyx_messaging_service import TelnyxMessagingService

                        attempt = TelnyxMessagingService.send_whatsapp(
                            db,
                            to_number=phone,
                            body=body,
                            template_name=meta_name,
                            template_language=lang,
                            template_components=components,
                            org_id=org_id,
                            meter_usage=False,
                            service_code="customer_feedback",
                        )
                        result = attempt
                        if attempt.ok:
                            break
                else:
                    result = FeedbackWaSendService.send_plain_or_template(
                        db,
                        to_number=phone,
                        body=row.message_body,
                        org_id=org_id,
                        require_template=True,
                    )
                if result and result.ok:
                    sent += 1
            except Exception:
                continue
        row.status = "completed"
        row.sent_count = sent
        row.launched_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        db.add(row)
        db.commit()
        return {"ok": True, "status": "completed", "sent_count": sent, "recipient_count": len(recipients)}
