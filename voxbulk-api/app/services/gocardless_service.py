"""Billing foundation.

Manual cash billing is test-only. Production GoCardless creation still needs the
final hosted checkout/redirect decisions before real provider writes are enabled.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.provider_settings import ProviderSettingsService


_DEFAULT_PLANS: list[dict] = [
    {
        "code": "starter",
        "name": "Starter",
        "price_gbp_pence": 9900,
        "interval": "monthly",
        "description": "Ideal for a single practice getting started with automated recovery.",
        "features": [
            "1 branch · up to 2 dentists",
            "100 recovery touches / month",
            "WhatsApp + voice outreach",
            "Dentally integration",
            "Email support",
        ],
    },
    {
        "code": "practice",
        "name": "Practice",
        "price_gbp_pence": 19900,
        "interval": "monthly",
        "description": "Most teams: multi-chair clinics that want full reporting and priority support.",
        "features": [
            "Up to 3 branches",
            "300 recovery touches / month",
            "No-show follow-up workflows",
            "PDF reports & dashboards",
            "Priority support",
        ],
    },
    {
        "code": "group",
        "name": "Group",
        "price_gbp_pence": 39900,
        "interval": "monthly",
        "description": "Multi-site groups needing SLAs, analytics, and flexible seats.",
        "features": [
            "Unlimited branches",
            "600+ recovery touches / month",
            "Advanced analytics",
            "Dedicated account manager",
            "API access",
        ],
    },
]


class GoCardlessConfigError(ValueError):
    pass


class GoCardlessProviderError(RuntimeError):
    pass


class BillingService:
    GOCARDLESS_VERSION = "2015-07-06"

    @staticmethod
    def ensure_default_plans(db: Session) -> None:
        n = db.execute(select(func.count()).select_from(Plan)).scalar_one()
        if int(n or 0) > 0:
            return
        now = datetime.utcnow()
        for row in _DEFAULT_PLANS:
            db.add(
                Plan(
                    code=row["code"],
                    name=row["name"],
                    price_gbp_pence=int(row["price_gbp_pence"]),
                    interval=str(row["interval"]),
                    description=row.get("description"),
                    features_json=json.dumps(row.get("features") or []),
                    created_at=now,
                )
            )
        db.commit()

    @staticmethod
    def get_subscription(db: Session, org_id: str) -> Subscription | None:
        return db.execute(select(Subscription).where(Subscription.org_id == org_id)).scalar_one_or_none()

    @staticmethod
    def list_plans(db: Session, *, active_only: bool = False) -> list[Plan]:
        BillingService.ensure_default_plans(db)
        q = select(Plan).order_by(Plan.sort_order.asc(), Plan.price_gbp_pence.asc())
        if active_only:
            q = q.where(Plan.is_active.is_(True))
        return list(db.execute(q).scalars().all())

    @staticmethod
    def change_plan(
        db: Session,
        *,
        org_id: str,
        plan_id: str | None = None,
        plan_code: str | None = None,
    ) -> tuple[Subscription, Plan, str]:
        """Change subscription plan. Returns (subscription, new_plan, direction)."""
        BillingService.ensure_default_plans(db)
        sub = BillingService.get_subscription(db, org_id)
        old_plan = None
        if sub is not None:
            old_plan = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()

        new_plan = None
        if plan_id:
            new_plan = db.execute(select(Plan).where(Plan.id == plan_id)).scalar_one_or_none()
        if new_plan is None and plan_code:
            new_plan = db.execute(select(Plan).where(Plan.code == str(plan_code).strip().lower())).scalar_one_or_none()
        if new_plan is None:
            raise ValueError("Unknown plan")
        if not bool(getattr(new_plan, "is_active", True)):
            raise ValueError("Plan is not available")

        old_price = int(old_plan.price_gbp_pence or 0) if old_plan else 0
        new_price = int(new_plan.price_gbp_pence or 0)
        if new_price > old_price:
            direction = "upgrade"
        elif new_price < old_price:
            direction = "downgrade"
        else:
            direction = "same"

        sub = BillingService.request_cash_plan_pending(db, org_id=org_id, plan_id=new_plan.id)
        return sub, new_plan, direction

    @staticmethod
    def request_cash_plan_pending(
        db: Session,
        *,
        org_id: str,
        plan_id: str | None = None,
        plan_code: str | None = None,
    ) -> Subscription:
        """Cash/testing payment — holds the requested plan until admin approves."""
        BillingService.ensure_default_plans(db)
        plan = None
        if plan_id:
            plan = db.execute(select(Plan).where(Plan.id == plan_id)).scalar_one_or_none()
        if plan is None and plan_code:
            plan = db.execute(select(Plan).where(Plan.code == str(plan_code).strip().lower())).scalar_one_or_none()
        if plan is None:
            raise ValueError("Unknown plan")
        if not bool(getattr(plan, "is_active", True)):
            raise ValueError("Plan is not available")

        now = datetime.utcnow()
        sub = db.execute(select(Subscription).where(Subscription.org_id == org_id)).scalar_one_or_none()
        if sub is None:
            sub = Subscription(
                org_id=org_id,
                plan_id=plan.id,
                pending_plan_id=plan.id,
                status="pending_payment",
                current_period_end=None,
                payment_provider="manual_cash",
                payment_mode="test",
                updated_at=now,
            )
        else:
            if sub.status == "pending_payment" and sub.pending_plan_id and sub.payment_provider == "manual_cash":
                pass
            sub.pending_plan_id = plan.id
            sub.status = "pending_payment"
            sub.payment_provider = "manual_cash"
            sub.payment_mode = "test"
            sub.updated_at = now
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def approve_cash_subscription(db: Session, *, org_id: str) -> tuple[Subscription, Plan]:
        sub = db.execute(select(Subscription).where(Subscription.org_id == org_id)).scalar_one_or_none()
        if sub is None or sub.status != "pending_payment" or not sub.pending_plan_id:
            raise ValueError("No cash subscription awaiting approval")
        if sub.payment_provider != "manual_cash":
            raise ValueError("Subscription is not a cash payment request")

        plan = db.execute(select(Plan).where(Plan.id == sub.pending_plan_id)).scalar_one_or_none()
        if plan is None:
            raise ValueError("Pending plan not found")

        now = datetime.utcnow()
        sub.plan_id = plan.id
        sub.pending_plan_id = None
        sub.status = "active"
        sub.current_period_end = now + timedelta(days=30)
        sub.updated_at = now
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub, plan

    @staticmethod
    def reject_cash_subscription(db: Session, *, org_id: str) -> Subscription:
        sub = db.execute(select(Subscription).where(Subscription.org_id == org_id)).scalar_one_or_none()
        if sub is None or sub.status != "pending_payment" or not sub.pending_plan_id:
            raise ValueError("No cash subscription awaiting approval")
        if sub.payment_provider != "manual_cash":
            raise ValueError("Subscription is not a cash payment request")

        sub.pending_plan_id = None
        sub.status = "active" if sub.current_period_end else "trial"
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def list_pending_cash_subscriptions(db: Session, *, limit: int = 100) -> list[dict[str, Any]]:
        from app.models.organisation import Organisation

        rows = list(
            db.execute(
                select(Subscription, Organisation.name, Plan)
                .join(Organisation, Organisation.id == Subscription.org_id)
                .join(Plan, Plan.id == Subscription.pending_plan_id)
                .where(
                    Subscription.status == "pending_payment",
                    Subscription.payment_provider == "manual_cash",
                    Subscription.pending_plan_id.is_not(None),
                )
                .order_by(Subscription.updated_at.desc())
                .limit(limit)
            ).all()
        )
        out: list[dict[str, Any]] = []
        for sub, org_name, pending_plan in rows:
            current_plan = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()
            out.append(
                {
                    "org_id": sub.org_id,
                    "org_name": org_name,
                    "subscription_id": sub.id,
                    "current_plan_code": current_plan.code if current_plan else None,
                    "current_plan_name": current_plan.name if current_plan else None,
                    "pending_plan_id": pending_plan.id,
                    "pending_plan_code": pending_plan.code,
                    "pending_plan_name": pending_plan.name,
                    "pending_plan_price_gbp_pence": pending_plan.price_gbp_pence,
                    "updated_at": sub.updated_at,
                }
            )
        return out

    @staticmethod
    def payment_options(db: Session) -> dict[str, Any]:
        gc_cfg, gc_enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="gocardless")
        token = str((gc_cfg or {}).get("access_token") or "").strip()
        environment = str((gc_cfg or {}).get("environment") or "sandbox").strip().lower()
        gocardless_available = bool(gc_enabled and token)
        return {
            "cash_available": True,
            "cash_requires_admin_approval": True,
            "gocardless_available": gocardless_available,
            "gocardless_environment": environment if gocardless_available else None,
            "gocardless_auto_activate": True,
        }

    @staticmethod
    def test_gocardless_connection(db: Session) -> dict[str, Any]:
        config = BillingService._get_gocardless_config(db)
        with httpx.Client(timeout=20) as client:
            response = client.get(
                f"{config['api_base']}/creditors",
                headers=BillingService._gocardless_headers(config["access_token"]),
            )
        BillingService._raise_for_gocardless_error(response)
        body = response.json()
        creditors = body.get("creditors") or []
        first = creditors[0] if creditors else {}
        return {
            "ok": True,
            "environment": config["environment"],
            "creditor_count": len(creditors),
            "creditor_name": str(first.get("name") or "").strip() or None,
            "creditor_id": str(first.get("id") or "").strip() or None,
        }

    @staticmethod
    def assign_plan_cash(
        db: Session,
        *,
        org_id: str,
        plan_id: str | None = None,
        plan_code: str | None = None,
    ) -> Subscription:
        """Test/dev: immediate paid subscription without payment provider."""
        BillingService.ensure_default_plans(db)
        plan = None
        if plan_id:
            plan = db.execute(select(Plan).where(Plan.id == plan_id)).scalar_one_or_none()
        if plan is None and plan_code:
            code = str(plan_code).strip().lower()
            plan = db.execute(select(Plan).where(Plan.code == code)).scalar_one_or_none()
        if plan is None:
            raise ValueError("Unknown plan")

        sub = db.execute(select(Subscription).where(Subscription.org_id == org_id)).scalar_one_or_none()
        period_end = datetime.utcnow() + timedelta(days=30)
        if sub is None:
            sub = Subscription(
                org_id=org_id,
                plan_id=plan.id,
                status="active",
                current_period_end=period_end,
                payment_provider="manual_cash",
                payment_mode="test",
                updated_at=datetime.utcnow(),
            )
            db.add(sub)
        else:
            sub.plan_id = plan.id
            sub.status = "active"
            sub.current_period_end = period_end
            sub.payment_provider = "manual_cash"
            sub.payment_mode = "test"
            sub.external_customer_id = None
            sub.external_subscription_id = None
            sub.updated_at = datetime.utcnow()
            db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def mark_pending_provider_checkout(
        db: Session,
        *,
        org_id: str,
        plan_id: str | None = None,
        plan_code: str | None = None,
        provider: str = "gocardless",
    ) -> Subscription:
        """Record the selected package while the external payment provider checkout is pending."""
        BillingService.ensure_default_plans(db)
        plan = None
        if plan_id:
            plan = db.execute(select(Plan).where(Plan.id == plan_id)).scalar_one_or_none()
        if plan is None and plan_code:
            plan = db.execute(select(Plan).where(Plan.code == str(plan_code).strip().lower())).scalar_one_or_none()
        if plan is None:
            raise ValueError("Unknown plan")

        now = datetime.utcnow()
        sub = db.execute(select(Subscription).where(Subscription.org_id == org_id)).scalar_one_or_none()
        if sub is None:
            sub = Subscription(
                org_id=org_id,
                plan_id=plan.id,
                status="pending_payment",
                current_period_end=None,
                payment_provider=provider,
                payment_mode="production",
                updated_at=now,
            )
        else:
            sub.plan_id = plan.id
            sub.status = "pending_payment"
            sub.current_period_end = None
            sub.payment_provider = provider
            sub.payment_mode = "production"
            sub.updated_at = now
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub

    @staticmethod
    def _get_gocardless_config(db: Session) -> dict[str, Any]:
        cfg, enabled = ProviderSettingsService.get_platform_config_decrypted(db, provider="gocardless")
        config = cfg or {}
        token = str(config.get("access_token") or "").strip()
        if not enabled or not token:
            raise GoCardlessConfigError("GoCardless sandbox access token is not configured or enabled")
        environment = str(config.get("environment") or "sandbox").strip().lower()
        if environment not in {"sandbox", "live"}:
            environment = "sandbox"
        return {
            **config,
            "access_token": token,
            "environment": environment,
            "api_base": "https://api-sandbox.gocardless.com" if environment == "sandbox" else "https://api.gocardless.com",
        }

    @staticmethod
    def _gocardless_headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "GoCardless-Version": BillingService.GOCARDLESS_VERSION,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _default_success_url(config: dict[str, Any]) -> str:
        configured = str(config.get("success_redirect_url") or "").strip()
        if configured:
            return configured
        origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
        return f"{origin}/packages?billing=success"

    @staticmethod
    def _default_cancel_url(config: dict[str, Any]) -> str:
        configured = str(config.get("cancel_redirect_url") or "").strip()
        if configured:
            return configured
        origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
        return f"{origin}/packages?billing=cancelled"

    @staticmethod
    def _raise_for_gocardless_error(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            payload = response.json()
        except Exception:
            payload = {"error": response.text[:500]}
        raise GoCardlessProviderError(f"GoCardless API error {response.status_code}: {payload}")

    @staticmethod
    def start_gocardless_redirect_flow(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        plan_id: str | None = None,
        plan_code: str | None = None,
    ) -> dict[str, Any]:
        BillingService.ensure_default_plans(db)
        plan = None
        if plan_id:
            plan = db.execute(select(Plan).where(Plan.id == plan_id)).scalar_one_or_none()
        if plan is None and plan_code:
            plan = db.execute(select(Plan).where(Plan.code == str(plan_code).strip().lower())).scalar_one_or_none()
        if plan is None:
            raise ValueError("Unknown plan")

        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            raise ValueError("Unknown user")

        config = BillingService._get_gocardless_config(db)
        session_token = secrets.token_urlsafe(32)
        success_url = BillingService._default_success_url(config)
        cancel_url = BillingService._default_cancel_url(config)
        payload = {
            "redirect_flows": {
                "description": f"VOXBULK.COM {plan.name} subscription",
                "session_token": session_token,
                "success_redirect_url": success_url,
                "prefilled_customer": {"email": user.email},
                "metadata": {
                    "org_id": org_id,
                    "user_id": user_id,
                    "plan_id": plan.id,
                    "plan_code": plan.code,
                },
            }
        }

        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{config['api_base']}/redirect_flows",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json=payload,
            )
        BillingService._raise_for_gocardless_error(response)
        body = response.json()
        flow = body.get("redirect_flows") or {}
        redirect_flow_id = str(flow.get("id") or "").strip()
        authorization_url = str(flow.get("redirect_url") or "").strip()
        if not redirect_flow_id or not authorization_url:
            raise GoCardlessProviderError("GoCardless did not return a redirect flow URL")

        BillingService.mark_pending_provider_checkout(db, org_id=org_id, plan_id=plan.id, provider="gocardless")
        row = BillingRedirectFlow(
            org_id=org_id,
            user_id=user_id,
            plan_id=plan.id,
            redirect_flow_id=redirect_flow_id,
            session_token=session_token,
            environment=str(config["environment"]),
            status="created",
            authorization_url=authorization_url,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "ok": True,
            "environment": row.environment,
            "redirect_flow_id": redirect_flow_id,
            "authorization_url": authorization_url,
            "cancel_url": cancel_url,
            "plan": plan,
        }

    @staticmethod
    def complete_gocardless_redirect_flow(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        redirect_flow_id: str,
    ) -> dict[str, Any]:
        flow_id = str(redirect_flow_id or "").strip()
        if not flow_id:
            raise ValueError("redirect_flow_id required")

        row = db.execute(
            select(BillingRedirectFlow).where(
                BillingRedirectFlow.redirect_flow_id == flow_id,
                BillingRedirectFlow.org_id == org_id,
                BillingRedirectFlow.user_id == user_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Billing redirect flow not found")

        plan = db.execute(select(Plan).where(Plan.id == row.plan_id)).scalar_one_or_none()
        if plan is None:
            raise ValueError("Plan not found")

        if row.status == "completed":
            sub = BillingService.get_subscription(db, org_id)
            return {"ok": True, "status": "completed", "subscription": sub, "plan": plan}

        config = BillingService._get_gocardless_config(db)
        with httpx.Client(timeout=20) as client:
            complete_response = client.post(
                f"{config['api_base']}/redirect_flows/{flow_id}/actions/complete",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json={"data": {"session_token": row.session_token}},
            )
        BillingService._raise_for_gocardless_error(complete_response)
        completed_flow = (complete_response.json().get("redirect_flows") or {})
        links = completed_flow.get("links") or {}
        mandate_id = str(links.get("mandate") or "").strip()
        customer_id = str(links.get("customer") or "").strip()
        if not mandate_id:
            raise GoCardlessProviderError("GoCardless did not return a mandate")

        subscription_payload = {
            "subscriptions": {
                "amount": int(plan.price_gbp_pence or 0),
                "currency": "GBP",
                "name": f"VOXBULK.COM {plan.name}",
                "interval_unit": "monthly" if plan.interval == "monthly" else str(plan.interval or "monthly"),
                "links": {"mandate": mandate_id},
                "metadata": {
                    "org_id": org_id,
                    "user_id": user_id,
                    "plan_id": plan.id,
                    "plan_code": plan.code,
                    "client_email": str((completed_flow.get("prefilled_customer") or {}).get("email") or ""),
                },
            }
        }
        with httpx.Client(timeout=20) as client:
            subscription_response = client.post(
                f"{config['api_base']}/subscriptions",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json=subscription_payload,
            )
        BillingService._raise_for_gocardless_error(subscription_response)
        provider_sub = subscription_response.json().get("subscriptions") or {}
        external_subscription_id = str(provider_sub.get("id") or "").strip()

        now = datetime.utcnow()
        sub = db.execute(select(Subscription).where(Subscription.org_id == org_id)).scalar_one_or_none()
        if sub is None:
            sub = Subscription(org_id=org_id, plan_id=plan.id)
        sub.plan_id = plan.id
        sub.status = "active"
        sub.current_period_end = now + timedelta(days=30)
        sub.payment_provider = "gocardless"
        sub.payment_mode = str(config["environment"])
        sub.external_customer_id = customer_id or None
        sub.external_subscription_id = external_subscription_id or None
        sub.updated_at = now
        db.add(sub)

        row.status = "completed"
        row.completed_at = now
        row.updated_at = now
        row.error_message = None
        db.add(row)
        db.commit()
        db.refresh(sub)
        return {"ok": True, "status": "completed", "subscription": sub, "plan": plan}

    @staticmethod
    def _service_order_success_url(config: dict[str, Any], service_code: str) -> str:
        origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
        path = "survey" if service_code == "survey" else "interview"
        return f"{origin}/{path}?order_billing=success"

    @staticmethod
    def _service_order_cancel_url(config: dict[str, Any], service_code: str) -> str:
        origin = str(get_settings().dashboard_app_origin or "http://localhost:5175").rstrip("/")
        path = "survey" if service_code == "survey" else "interview"
        return f"{origin}/{path}?order_billing=cancelled"

    @staticmethod
    def start_service_order_gocardless_flow(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        order_id: str,
    ) -> dict[str, Any]:
        from app.models.service_order import ServiceOrder
        from app.services.platform_catalog_service import PlatformCatalogService

        order = PlatformCatalogService.get_order(db, order_id, org_id=org_id)
        if order is None:
            raise ValueError("Order not found")
        if order.status not in {"quoted", "draft"} or order.quote_total_pence <= 0:
            raise ValueError("Generate a quote before paying")
        if order.payment_status == "approved":
            raise ValueError("Order is already paid")

        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            raise ValueError("Unknown user")

        config = BillingService._get_gocardless_config(db)
        session_token = secrets.token_urlsafe(32)
        success_url = BillingService._service_order_success_url(config, order.service_code)
        cancel_url = BillingService._service_order_cancel_url(config, order.service_code)
        amount_gbp = f"£{(order.quote_total_pence / 100):.2f}"
        payload = {
            "redirect_flows": {
                "description": f"VOXBULK.COM {order.service_code} order — {amount_gbp}",
                "session_token": session_token,
                "success_redirect_url": success_url,
                "prefilled_customer": {"email": user.email},
                "metadata": {
                    "org_id": org_id,
                    "user_id": user_id,
                    "service_order_id": order.id,
                    "service_code": order.service_code,
                },
            }
        }

        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{config['api_base']}/redirect_flows",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json=payload,
            )
        BillingService._raise_for_gocardless_error(response)
        body = response.json()
        flow = body.get("redirect_flows") or {}
        redirect_flow_id = str(flow.get("id") or "").strip()
        authorization_url = str(flow.get("redirect_url") or "").strip()
        if not redirect_flow_id or not authorization_url:
            raise GoCardlessProviderError("GoCardless did not return a redirect flow URL")

        row = BillingRedirectFlow(
            org_id=org_id,
            user_id=user_id,
            plan_id=None,
            service_order_id=order.id,
            redirect_flow_id=redirect_flow_id,
            session_token=session_token,
            environment=str(config["environment"]),
            status="created",
            authorization_url=authorization_url,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {
            "ok": True,
            "environment": row.environment,
            "redirect_flow_id": redirect_flow_id,
            "authorization_url": authorization_url,
            "cancel_url": cancel_url,
            "order_id": order.id,
        }

    @staticmethod
    def complete_service_order_gocardless_flow(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        redirect_flow_id: str,
    ) -> dict[str, Any]:
        from app.models.service_order import ServiceOrder
        from app.services.platform_catalog_service import PlatformCatalogService

        flow_id = str(redirect_flow_id or "").strip()
        if not flow_id:
            raise ValueError("redirect_flow_id required")

        row = db.execute(
            select(BillingRedirectFlow).where(
                BillingRedirectFlow.redirect_flow_id == flow_id,
                BillingRedirectFlow.org_id == org_id,
                BillingRedirectFlow.user_id == user_id,
                BillingRedirectFlow.service_order_id.is_not(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise ValueError("Service order redirect flow not found")

        order = PlatformCatalogService.get_order(db, row.service_order_id or "", org_id=org_id)
        if order is None:
            raise ValueError("Order not found")

        if row.status == "completed" and order.payment_status == "approved":
            return {"ok": True, "status": "completed", "order": PlatformCatalogService.order_to_dict(order)}

        config = BillingService._get_gocardless_config(db)
        with httpx.Client(timeout=20) as client:
            complete_response = client.post(
                f"{config['api_base']}/redirect_flows/{flow_id}/actions/complete",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json={"data": {"session_token": row.session_token}},
            )
        BillingService._raise_for_gocardless_error(complete_response)
        completed_flow = (complete_response.json().get("redirect_flows") or {})
        links = completed_flow.get("links") or {}
        mandate_id = str(links.get("mandate") or "").strip()
        if not mandate_id:
            raise GoCardlessProviderError("GoCardless did not return a mandate")

        payment_payload = {
            "payments": {
                "amount": int(order.quote_total_pence or 0),
                "currency": "GBP",
                "description": f"VOXBULK {order.service_code} — {order.title}"[:255],
                "links": {"mandate": mandate_id},
                "metadata": {
                    "org_id": org_id,
                    "service_order_id": order.id,
                    "service_code": order.service_code,
                },
            }
        }
        with httpx.Client(timeout=20) as client:
            payment_response = client.post(
                f"{config['api_base']}/payments",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json=payment_payload,
            )
        BillingService._raise_for_gocardless_error(payment_response)
        provider_payment = payment_response.json().get("payments") or {}

        now = datetime.utcnow()
        order.payment_method = "gocardless"
        order.payment_status = "approved"
        order.payment_note = f"GoCardless sandbox payment {provider_payment.get('id') or ''}".strip()
        order.status = "paid"
        order.updated_at = now
        db.add(order)

        row.status = "completed"
        row.completed_at = now
        row.updated_at = now
        db.add(row)
        db.commit()
        db.refresh(order)
        return {"ok": True, "status": "completed", "order": PlatformCatalogService.order_to_dict(order)}

