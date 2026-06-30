"""Salesman (Task 8) service: reps, their customers, demo sends, offers, and commission."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.billing_invoice import BillingInvoice
from app.models.sales_rep import SalesCommission, SalesCustomer, SalesRep
from app.models.user import User

_CODE_RE = re.compile(r"^[A-Z0-9]{4,12}$")
logger = logging.getLogger(__name__)

# Fixed script for the salesman "Call & Survey" demo (matches the 'sales ai survey' agent).
# Salesmen never edit this — warm welcome, 3 questions, gentle "why" if unhappy, warm thanks.
DEMO_AI_SURVEY_SCRIPT = (
    "OPENING (warm welcome): Greet the customer warmly by first name, say this is a quick "
    "friendly survey on behalf of {org_name} and it only takes a minute.\n\n"
    "ASK THESE THREE QUESTIONS, ONE AT A TIME, IN ORDER:\n"
    "1. Overall, how would you rate your experience with us today — excellent, good, or poor?\n"
    "2. What did you enjoy most about your experience?\n"
    "3. Is there anything we could do to make it better next time?\n\n"
    "IF THE CUSTOMER IS UNHAPPY OR SAYS \"poor\": stay warm and empathetic, briefly acknowledge it, "
    "and gently ask why so we can improve. Never argue or get defensive.\n\n"
    "CLOSING (warm thanks): Thank the customer sincerely for their time and wish them a great day."
)


class SalesRepError(ValueError):
    pass


class SalesRepService:
    # ---- reps ----------------------------------------------------------------
    @staticmethod
    def normalize_code(raw: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()

    @staticmethod
    def rep_to_dict(rep: SalesRep, user: User | None = None) -> dict[str, Any]:
        return {
            "id": rep.id,
            "user_id": rep.user_id,
            "name": rep.name,
            "email": user.email if user else None,
            "promo_code": rep.promo_code,
            "country": rep.country,
            "caller_id": rep.caller_id,
            "is_active": bool(rep.is_active),
            "created_at": rep.created_at.isoformat() if rep.created_at else None,
        }

    @staticmethod
    def get_rep_for_user(db: Session, *, user_id: str) -> SalesRep | None:
        return db.execute(select(SalesRep).where(SalesRep.user_id == str(user_id))).scalar_one_or_none()

    @staticmethod
    def list_reps(db: Session) -> list[dict[str, Any]]:
        rows = db.execute(select(SalesRep).order_by(SalesRep.created_at.desc())).scalars().all()
        out: list[dict[str, Any]] = []
        for rep in rows:
            user = db.execute(select(User).where(User.id == rep.user_id)).scalar_one_or_none()
            d = SalesRepService.rep_to_dict(rep, user)
            stats = SalesRepService.dashboard_stats(db, rep)
            d["customers"] = stats["wallet"]["active_companies"]
            d["commission_minor"] = stats["wallet"]["commission_minor"]
            out.append(d)
        return out

    @staticmethod
    def create_rep(
        db: Session,
        *,
        email: str,
        password: str,
        name: str,
        promo_code: str,
        country: str | None = None,
        caller_id: str | None = None,
    ) -> SalesRep:
        email = str(email or "").strip().lower()
        if not email or "@" not in email:
            raise SalesRepError("A valid email is required.")
        if len(str(password or "")) < 6:
            raise SalesRepError("Password must be at least 6 characters.")
        code = SalesRepService.normalize_code(promo_code)
        if not _CODE_RE.match(code):
            raise SalesRepError("Promo code must be 4–12 letters/numbers (e.g. UK4F2A).")
        if db.execute(select(SalesRep).where(SalesRep.promo_code == code)).scalar_one_or_none():
            raise SalesRepError(f"Promo code {code} is already in use.")

        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email, password_hash=hash_password(password), is_active=True, is_superuser=False)
            db.add(user)
            db.flush()
        else:
            if db.execute(select(SalesRep).where(SalesRep.user_id == user.id)).scalar_one_or_none():
                raise SalesRepError("This user is already a salesman.")

        # A salesman needs an organisation membership so the dashboard login flow issues a token.
        # Give them a dedicated personal "Sales" workspace.
        from app.models.membership import OrganisationMembership
        from app.models.organisation import Organisation

        has_membership = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        ).scalar_one_or_none()
        if not has_membership:
            org = Organisation(name=f"{(name or email.split('@')[0])} — Sales", onboarding_state="onboarding_completed")
            db.add(org)
            db.flush()
            db.add(OrganisationMembership(org_id=org.id, user_id=user.id, role="sales"))
            db.flush()

        now = datetime.utcnow()
        rep = SalesRep(
            user_id=user.id,
            name=str(name or "").strip() or email.split("@")[0],
            promo_code=code,
            country=(str(country or "").strip().upper()[:2] or None),
            caller_id=(str(caller_id or "").strip() or None),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(rep)
        db.commit()
        db.refresh(rep)

        # Demo data is no longer auto-seeded on create. New salesmen start with an empty
        # workspace; seed demo data on demand with scripts/seed_sales_demo.py (./seed-sales-demo.sh).
        return rep

    @staticmethod
    def update_rep(db: Session, *, rep: SalesRep, patch: dict[str, Any]) -> SalesRep:
        if "name" in patch:
            rep.name = str(patch["name"] or "").strip()
        if "country" in patch:
            rep.country = (str(patch["country"] or "").strip().upper()[:2] or None)
        if "caller_id" in patch:
            rep.caller_id = (str(patch["caller_id"] or "").strip() or None)
        if "is_active" in patch:
            rep.is_active = bool(patch["is_active"])
        if "promo_code" in patch and patch["promo_code"]:
            code = SalesRepService.normalize_code(patch["promo_code"])
            if not _CODE_RE.match(code):
                raise SalesRepError("Promo code must be 4–12 letters/numbers.")
            existing = db.execute(select(SalesRep).where(SalesRep.promo_code == code)).scalar_one_or_none()
            if existing and existing.id != rep.id:
                raise SalesRepError(f"Promo code {code} is already in use.")
            rep.promo_code = code
        rep.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(rep)
        return rep

    @staticmethod
    def reset_password(db: Session, *, rep: SalesRep, new_password: str) -> None:
        if len(str(new_password or "")) < 6:
            raise SalesRepError("Password must be at least 6 characters.")
        user = db.execute(select(User).where(User.id == rep.user_id)).scalar_one_or_none()
        if user is None:
            raise SalesRepError("Login user not found for this salesman.")
        user.password_hash = hash_password(new_password)
        user.is_active = True
        db.commit()

    @staticmethod
    def delete_rep(db: Session, *, rep: SalesRep) -> None:
        custs = db.execute(
            select(SalesCustomer).where(SalesCustomer.sales_rep_id == rep.id)
        ).scalars().all()
        for c in custs:
            db.delete(c)
        comms = db.execute(
            select(SalesCommission).where(SalesCommission.sales_rep_id == rep.id)
        ).scalars().all()
        for cm in comms:
            db.delete(cm)
        user = db.execute(select(User).where(User.id == rep.user_id)).scalar_one_or_none()
        db.delete(rep)
        if user is not None:
            # Block dashboard login but keep the user row to preserve any history.
            user.is_active = False
        db.commit()

    # ---- customers -----------------------------------------------------------
    @staticmethod
    def _derive_stage(c: SalesCustomer) -> str:
        """Funnel stage derived from the customer's timestamps/flags (most-advanced wins)."""
        if c.status == "won" or c.org_id:
            return "won"
        if c.interested or c.offer_sent_at:
            return "interested"
        if c.demo_wa_sent_at or c.demo_call_sent_at:
            return "demoed"
        return "lead"

    @staticmethod
    def _timeline(c: SalesCustomer) -> list[dict[str, Any]]:
        """Ordered funnel events with timestamps (None = not reached yet)."""

        def iso(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        demo_at = c.demo_wa_sent_at or c.demo_call_sent_at
        return [
            {"key": "added", "label": "Added / visited", "at": iso(c.created_at)},
            {"key": "demoed", "label": "Demoed", "at": iso(demo_at)},
            {"key": "interested", "label": "Interested (offer sent)", "at": iso(c.interested_at or c.offer_sent_at)},
            {"key": "won", "label": "Signed up / won", "at": iso(c.updated_at) if (c.status == "won" or c.org_id) else None},
        ]

    @staticmethod
    def customer_to_dict(c: SalesCustomer) -> dict[str, Any]:
        return {
            "id": c.id,
            "full_name": c.full_name,
            "company_name": c.company_name,
            "address": c.address,
            "city": c.city,
            "country": c.country,
            "mobile": c.mobile,
            "email": c.email,
            "business_type": c.business_type,
            "branches": c.branches,
            "contact_person": c.contact_person,
            "org_id": c.org_id,
            "offer_details": c.offer_details,
            "offer_sent_at": c.offer_sent_at.isoformat() if c.offer_sent_at else None,
            "demo_wa_sent_at": c.demo_wa_sent_at.isoformat() if c.demo_wa_sent_at else None,
            "demo_call_sent_at": c.demo_call_sent_at.isoformat() if c.demo_call_sent_at else None,
            "interested": bool(c.interested),
            "interested_at": c.interested_at.isoformat() if c.interested_at else None,
            "status": c.status,
            "stage": SalesRepService._derive_stage(c),
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

    @staticmethod
    def get_customer_detail(db: Session, *, rep_id: str, customer_id: str) -> dict[str, Any] | None:
        cust = SalesRepService.get_customer(db, rep_id=rep_id, customer_id=customer_id)
        if cust is None:
            return None
        data = SalesRepService.customer_to_dict(cust)
        data["timeline"] = SalesRepService._timeline(cust)
        return data

    @staticmethod
    def list_customers(db: Session, *, rep_id: str) -> list[dict[str, Any]]:
        rows = (
            db.execute(
                select(SalesCustomer)
                .where(SalesCustomer.sales_rep_id == str(rep_id))
                .order_by(SalesCustomer.created_at.desc())
            )
            .scalars()
            .all()
        )
        return [SalesRepService.customer_to_dict(c) for c in rows]

    @staticmethod
    def get_customer(db: Session, *, rep_id: str, customer_id: str) -> SalesCustomer | None:
        return db.execute(
            select(SalesCustomer).where(
                SalesCustomer.id == str(customer_id), SalesCustomer.sales_rep_id == str(rep_id)
            )
        ).scalar_one_or_none()

    @staticmethod
    def upsert_customer(db: Session, *, rep_id: str, payload: dict[str, Any]) -> SalesCustomer:
        cid = str(payload.get("id") or "").strip()
        now = datetime.utcnow()
        cust = None
        if cid:
            cust = SalesRepService.get_customer(db, rep_id=rep_id, customer_id=cid)
            if cust is None:
                raise SalesRepError("Customer not found.")
        if cust is None:
            cust = SalesCustomer(sales_rep_id=str(rep_id), created_at=now)
            db.add(cust)
        for field in (
            "full_name",
            "company_name",
            "address",
            "city",
            "country",
            "mobile",
            "email",
            "business_type",
            "contact_person",
            "status",
            "offer_details",
        ):
            if field in payload:
                setattr(cust, field, (str(payload[field]).strip() if payload[field] is not None else None))
        if "branches" in payload:
            try:
                cust.branches = max(0, int(payload["branches"]))
            except (TypeError, ValueError):
                cust.branches = 1
        cust.updated_at = now
        db.commit()
        db.refresh(cust)
        return cust

    @staticmethod
    def delete_customer(db: Session, *, rep_id: str, customer_id: str) -> None:
        cust = SalesRepService.get_customer(db, rep_id=rep_id, customer_id=customer_id)
        if cust is None:
            raise SalesRepError("Customer not found.")
        db.delete(cust)
        db.commit()

    # ---- demo / offer sends (best-effort, never crash the request) -----------
    @staticmethod
    def _telnyx_config(db: Session) -> dict[str, Any]:
        from app.services.telnyx_messaging_service import TelnyxMessagingService

        return TelnyxMessagingService._config(db)

    @staticmethod
    def send_offer(db: Session, *, rep: SalesRep, customer: SalesCustomer, channel: str, offer_details: str) -> dict[str, Any]:
        offer_details = str(offer_details or "").strip() or "Special VoxBulk offer"
        customer.offer_details = offer_details
        signup = f"Use promo code {rep.promo_code} to claim your offer."
        body = f"Hi {customer.full_name or 'there'} — {offer_details}. {signup}"
        log: dict[str, Any] = {}
        ok = False
        if channel == "email":
            if not customer.email:
                return {"ok": False, "message": "Customer has no email."}
            try:
                from app.services.transactional_email_service import TransactionalEmailService

                sent, err = TransactionalEmailService.send_templated_optional(
                    db,
                    template_key="sales_offer",
                    to_email=customer.email,
                    variables={
                        "name": customer.full_name or "",
                        "offer": offer_details,
                        "promo_code": rep.promo_code,
                    },
                )
                ok = bool(sent)
                log = {"channel": "email", "ok": ok, "error": err}
            except Exception as e:  # noqa: BLE001
                log = {"channel": "email", "ok": False, "error": str(e)}
        elif channel == "wa":
            if not customer.mobile:
                return {"ok": False, "message": "Customer has no mobile number."}
            try:
                from app.services.telnyx_messaging_service import TelnyxMessagingService

                res = TelnyxMessagingService.send_whatsapp(db, to_number=customer.mobile, body=body)
                ok = bool(getattr(res, "ok", True))
                log = {"channel": "wa", "ok": ok}
            except Exception as e:  # noqa: BLE001
                log = {"channel": "wa", "ok": False, "error": str(e)}
        else:
            return {"ok": False, "message": "Unknown channel."}

        if ok:
            now = datetime.utcnow()
            customer.offer_sent_at = now
            # Sending an offer means the customer is interested.
            customer.interested = True
            if customer.interested_at is None:
                customer.interested_at = now
            if customer.status not in ("won", "interested"):
                customer.status = "interested"
        customer.offer_log_json = json.dumps(log)
        customer.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": ok, "message": "Sent." if ok else f"Send failed: {log.get('error') or 'unknown error'}"}

    @staticmethod
    def _mark_demoed(db: Session, customer: SalesCustomer, *, channel: str) -> None:
        """Record a demo send on the customer and advance the funnel stage."""
        now = datetime.utcnow()
        if channel == "wa":
            customer.demo_wa_sent_at = now
        elif channel == "call":
            customer.demo_call_sent_at = now
        if customer.status == "lead":
            customer.status = "demoed"
        customer.updated_at = now
        db.commit()

    @staticmethod
    def send_demo_wa(db: Session, *, customer: SalesCustomer) -> dict[str, Any]:
        if not customer.mobile:
            return {"ok": False, "message": "Customer has no mobile number."}
        try:
            from app.services.telnyx_messaging_service import TelnyxMessagingService

            body = "Hi! This is a quick VoxBulk demo survey — how would you rate your last visit? Reply 1-5."
            res = TelnyxMessagingService.send_whatsapp(db, to_number=customer.mobile, body=body)
            ok = bool(getattr(res, "ok", True))
            if ok:
                SalesRepService._mark_demoed(db, customer, channel="wa")
            return {"ok": ok, "message": "Demo WhatsApp survey sent."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"WhatsApp not available: {e}"}

    @staticmethod
    def _rep_workspace_org_id(db: Session, rep: SalesRep) -> str | None:
        from app.models.membership import OrganisationMembership

        m = db.execute(
            select(OrganisationMembership).where(OrganisationMembership.user_id == rep.user_id)
        ).scalar_one_or_none()
        return str(m.org_id) if m is not None else None

    @staticmethod
    def send_demo_call(db: Session, *, rep: SalesRep, customer: SalesCustomer) -> dict[str, Any]:
        """Run a live 3-question AI survey demo to the customer's number.

        Reuses the proven outbound survey pipeline (Telnyx assistant + dispatch) so the
        transcript and answers show up in the salesman's /surveys/results. Billing/eligibility
        is bypassed (demo=True); the number must still pass the Telnyx phone allowlist.
        """
        if not customer.mobile:
            return {"ok": False, "message": "Customer has no mobile number."}

        org_id = SalesRepService._rep_workspace_org_id(db, rep)
        if not org_id:
            return {"ok": False, "message": "Salesman has no workspace organisation."}

        try:
            from app.models.agent import AgentDefinition
            from app.services.platform_catalog_service import ServiceOrderService
            from app.services.survey_call_dispatch_service import SurveyCallDispatchService

            org_name = "VoxBulk"
            try:
                from app.models.organisation import Organisation

                org = db.get(Organisation, org_id)
                org_name = (org.name if org and org.name else org_name)
            except Exception:  # noqa: BLE001
                pass

            config: dict[str, Any] = {
                "survey_channel": "ai_call",
                "delivery": "ai_call",
                "demo": True,
                "script_approved": True,
                "organisation_name": org_name,
                "survey_organiser_name": org_name,
                "approved_script": DEMO_AI_SURVEY_SCRIPT,
            }
            agent = db.execute(
                select(AgentDefinition).where(AgentDefinition.slug == "sales-ai-survey")
            ).scalar_one_or_none()
            if agent is not None:
                config["agent_id"] = agent.id

            order = ServiceOrderService.create_order(
                db,
                org_id=org_id,
                user_id=str(rep.user_id),
                service_code="survey",
                title=f"AI Survey Demo · {customer.company_name or customer.full_name or customer.mobile}",
                config=config,
            )
            ServiceOrderService.replace_recipients(
                db,
                order,
                [{"name": customer.full_name or customer.company_name or "Customer", "phone": customer.mobile}],
            )

            now = datetime.utcnow()
            order.status = "running"
            order.payment_status = "approved"
            order.started_at = order.started_at or now
            order.updated_at = now
            db.add(order)
            db.commit()
            db.refresh(order)

            recipients = ServiceOrderService.get_recipients(db, order.id)
            if not recipients:
                return {"ok": False, "message": "Could not prepare the demo call recipient."}

            SurveyCallDispatchService.dial_recipient(db, order, recipients[0])
            SalesRepService._mark_demoed(db, customer, channel="call")
            return {"ok": True, "message": "AI survey demo call started — watch the transcript in Surveys results."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"Could not start the AI survey demo: {e}"}

    # ---- commission + dashboard ---------------------------------------------
    @staticmethod
    def _linked_org_ids(db: Session, rep: SalesRep) -> set[str]:
        """Orgs attributed to this rep: customers converted to orgs, or signed up via the rep promo code."""
        org_ids: set[str] = set()
        rows = db.execute(
            select(SalesCustomer.org_id).where(
                SalesCustomer.sales_rep_id == rep.id, SalesCustomer.org_id.isnot(None)
            )
        ).scalars().all()
        org_ids.update(str(x) for x in rows if x)
        try:
            from app.models.org_usage_period import OrgUsagePeriod

            via_code = db.execute(
                select(OrgUsagePeriod.org_id).where(OrgUsagePeriod.promo_code == rep.promo_code)
            ).scalars().all()
            org_ids.update(str(x) for x in via_code if x)
        except Exception:  # noqa: BLE001
            pass
        return org_ids

    @staticmethod
    def get_rep_for_org(db: Session, *, org_id: str) -> SalesRep | None:
        """Reverse of _linked_org_ids: find the salesman attributed to an org."""
        org_id = str(org_id or "")
        if not org_id:
            return None
        cust = db.execute(
            select(SalesCustomer).where(SalesCustomer.org_id == org_id).order_by(SalesCustomer.created_at.asc())
        ).scalars().first()
        if cust is not None:
            rep = db.get(SalesRep, cust.sales_rep_id)
            if rep is not None:
                return rep
        try:
            from app.models.org_usage_period import OrgUsagePeriod

            code = db.execute(
                select(OrgUsagePeriod.promo_code).where(
                    OrgUsagePeriod.org_id == org_id, OrgUsagePeriod.promo_code.isnot(None)
                )
            ).scalars().first()
            if code:
                return db.execute(
                    select(SalesRep).where(SalesRep.promo_code == SalesRepService.normalize_code(code))
                ).scalar_one_or_none()
        except Exception:  # noqa: BLE001
            pass
        return None

    @staticmethod
    def accrue_commission_for_paid_invoice(
        db: Session, invoice: BillingInvoice, *, force_subscription: bool = False
    ) -> SalesCommission | None:
        """Best-effort: accrue a salesman commission when a linked org pays a subscription invoice.

        Rule (commission_kind="subscription"):
          - Monthly plans: full 2nd month → commission equals the 2nd paid subscription invoice amount.
          - Yearly plans: one month of a yearly plan → commission equals invoice amount / 12.
        Idempotent: at most one subscription commission per (rep, org). Never raises.

        Pass force_subscription=True for flows that are known subscription payments but where the
        invoice row is not tagged kind="subscription" (e.g. GoCardless Direct Debit webhook).
        """
        try:
            if str(getattr(invoice, "status", "") or "").lower() != "paid":
                return None
            if not force_subscription and str(getattr(invoice, "kind", "") or "").lower() != "subscription":
                return None
            org_id = str(getattr(invoice, "org_id", "") or "")
            if not org_id:
                return None
            rep = SalesRepService.get_rep_for_org(db, org_id=org_id)
            if rep is None or not rep.is_active:
                return None

            # Idempotency: one subscription commission per rep+org.
            existing = db.execute(
                select(SalesCommission).where(
                    SalesCommission.sales_rep_id == rep.id,
                    SalesCommission.org_id == org_id,
                    SalesCommission.kind.in_(["monthly_2nd", "yearly_1mo"]),
                )
            ).scalar_one_or_none()
            if existing is not None:
                return None

            interval = SalesRepService._org_plan_interval(db, org_id)
            amount = int(getattr(invoice, "amount_gbp_pence", 0) or 0)
            currency = str(getattr(invoice, "currency", "") or "GBP")

            if interval == "yearly":
                kind = "yearly_1mo"
                commission_minor = max(0, round(amount / 12))
                note = "One month of a yearly plan."
            else:
                # Monthly: only accrue once the 2nd subscription invoice is paid.
                paid_count = db.execute(
                    select(BillingInvoice).where(
                        BillingInvoice.org_id == org_id,
                        BillingInvoice.kind == "subscription",
                        BillingInvoice.status == "paid",
                    )
                ).scalars().all()
                if len(paid_count) < 2:
                    return None
                kind = "monthly_2nd"
                commission_minor = amount
                note = "Full 2nd month subscription."

            if commission_minor <= 0:
                return None

            link_cust = db.execute(
                select(SalesCustomer).where(
                    SalesCustomer.sales_rep_id == rep.id, SalesCustomer.org_id == org_id
                )
            ).scalars().first()

            comm = SalesCommission(
                sales_rep_id=rep.id,
                sales_customer_id=link_cust.id if link_cust is not None else None,
                org_id=org_id,
                invoice_id=getattr(invoice, "id", None),
                amount_minor=commission_minor,
                currency=currency,
                kind=kind,
                status="pending",
                note=note,
            )
            db.add(comm)
            db.commit()
            db.refresh(comm)
            return comm
        except Exception:  # noqa: BLE001 — commission accrual must never break a payment
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
            return None

    @staticmethod
    def _org_plan_interval(db: Session, org_id: str) -> str:
        try:
            from app.models.plan import Plan
            from app.models.subscription import Subscription

            sub = db.execute(
                select(Subscription)
                .where(Subscription.org_id == org_id)
                .order_by(Subscription.created_at.desc())
            ).scalars().first()
            if sub is not None and sub.plan_id:
                plan = db.get(Plan, sub.plan_id)
                if plan is not None and getattr(plan, "interval", None):
                    return "yearly" if str(plan.interval).lower().startswith(("year", "annual")) else "monthly"
        except Exception:  # noqa: BLE001
            pass
        return "monthly"

    @staticmethod
    def dashboard_stats(db: Session, rep: SalesRep) -> dict[str, Any]:
        customers = db.execute(
            select(SalesCustomer).where(SalesCustomer.sales_rep_id == rep.id)
        ).scalars().all()
        org_ids = SalesRepService._linked_org_ids(db, rep)

        paid_invoices: list[BillingInvoice] = []
        if org_ids:
            paid_invoices = db.execute(
                select(BillingInvoice).where(
                    BillingInvoice.org_id.in_(list(org_ids)),
                    BillingInvoice.status == "paid",
                )
            ).scalars().all()
        total_paid_minor = sum(int(getattr(inv, "amount_gbp_pence", 0) or 0) for inv in paid_invoices)

        commissions = db.execute(
            select(SalesCommission).where(SalesCommission.sales_rep_id == rep.id)
        ).scalars().all()
        commission_minor = sum(int(c.amount_minor or 0) for c in commissions)
        commission_paid_minor = sum(int(c.amount_minor or 0) for c in commissions if c.status == "paid")

        won = [c for c in customers if c.status == "won" or c.org_id]
        return {
            "won_deals": {
                "count": len(won),
                "total_value_minor": total_paid_minor,
                "companies": [
                    {"name": c.company_name or c.full_name, "org_id": c.org_id}
                    for c in won
                ],
            },
            "wallet": {
                "active_companies": len(org_ids),
                "codes_used": len([c for c in customers if c.offer_sent_at]),
                "revenue_minor": total_paid_minor,
                "commission_minor": commission_minor,
                "commission_paid_minor": commission_paid_minor,
                "commission_pending_minor": commission_minor - commission_paid_minor,
            },
            "visited_count": len(customers),
        }
