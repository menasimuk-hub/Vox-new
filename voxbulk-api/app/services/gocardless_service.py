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
    def list_plans(db: Session) -> list[Plan]:
        BillingService.ensure_default_plans(db)
        return list(db.execute(select(Plan).order_by(Plan.price_gbp_pence.asc())).scalars())

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

