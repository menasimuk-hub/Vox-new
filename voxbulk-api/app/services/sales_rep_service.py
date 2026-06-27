"""Salesman (Task 8) service: reps, their customers, demo sends, offers, and commission."""

from __future__ import annotations

import json
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

    # ---- customers -----------------------------------------------------------
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
            "status": c.status,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

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
            customer.offer_sent_at = datetime.utcnow()
            if customer.status == "lead":
                customer.status = "contacted"
        customer.offer_log_json = json.dumps(log)
        customer.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": ok, "message": "Sent." if ok else f"Send failed: {log.get('error') or 'unknown error'}"}

    @staticmethod
    def send_demo_wa(db: Session, *, customer: SalesCustomer) -> dict[str, Any]:
        if not customer.mobile:
            return {"ok": False, "message": "Customer has no mobile number."}
        try:
            from app.services.telnyx_messaging_service import TelnyxMessagingService

            body = "Hi! This is a quick VoxBulk demo survey — how would you rate your last visit? Reply 1-5."
            res = TelnyxMessagingService.send_whatsapp(db, to_number=customer.mobile, body=body)
            return {"ok": bool(getattr(res, "ok", True)), "message": "Demo WhatsApp survey sent."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"WhatsApp not available: {e}"}

    @staticmethod
    def send_demo_call(db: Session, *, rep: SalesRep, customer: SalesCustomer) -> dict[str, Any]:
        if not customer.mobile:
            return {"ok": False, "message": "Customer has no mobile number."}
        try:
            from app.services.telnyx_voice_service import TelnyxVoiceAdapter

            config = SalesRepService._telnyx_config(db)
            from_number = (
                rep.caller_id
                or str(config.get("default_outbound_number") or config.get("from_phone_number") or "").strip()
            )
            if not from_number:
                return {"ok": False, "message": "No caller ID / outbound number configured for voice."}
            res = TelnyxVoiceAdapter.start_outbound_call(
                to_number=customer.mobile,
                from_number=from_number,
                config=config,
                client_state={"sales_demo": True},
            )
            return {"ok": bool(getattr(res, "ok", False)), "message": getattr(res, "detail", None) or "Demo call started."}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": f"Voice not available: {e}"}

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
