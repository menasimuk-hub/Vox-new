"""Billing foundation.

Manual cash billing is test-only. Production GoCardless creation still needs the
final hosted checkout/redirect decisions before real provider writes are enabled.
"""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.billing_redirect_flow import BillingRedirectFlow
from app.models.organisation import Organisation
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.services.billing_access_service import BillingAccessService
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
        return BillingAccessService.get_subscription(db, org_id, service_code="voxbulk")

    @staticmethod
    def _is_payg_like_plan(plan: Plan | None) -> bool:
        if plan is None:
            return True
        code = str(plan.code or "").strip().lower()
        if code in {"payg", "free", "topup"}:
            return True
        price = plan.price_gbp_pence
        return price is not None and int(price) <= 0

    @staticmethod
    def resolve_active_plan(db: Session, org_id: str) -> Plan | None:
        """Resolve the org's current plan from subscription, usage wallet, or pending checkout."""
        from app.services.usage_wallet_service import UsageWalletService

        BillingService.ensure_default_plans(db)
        sub = BillingService.get_subscription(db, org_id)

        sub_plan: Plan | None = None
        if sub is not None and sub.plan_id:
            sub_plan = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()

        usage = UsageWalletService.get_current(db, org_id)
        wallet_plan: Plan | None = None
        if usage is not None and usage.plan_code:
            wallet_plan = (
                db.execute(
                    select(Plan)
                    .where(Plan.code == str(usage.plan_code).strip().lower())
                    .order_by(Plan.sort_order.asc(), Plan.price_gbp_pence.desc())
                    .limit(1)
                )
                .scalars()
                .first()
            )

        # Active usage wallet often reflects the real package while subscription row is still payg.
        if wallet_plan is not None and not BillingService._is_payg_like_plan(wallet_plan):
            if BillingService._is_payg_like_plan(sub_plan):
                return wallet_plan

        if sub_plan is not None:
            return sub_plan

        if wallet_plan is not None:
            return wallet_plan

        if sub is not None and sub.pending_plan_id:
            plan = db.execute(select(Plan).where(Plan.id == sub.pending_plan_id)).scalar_one_or_none()
            if plan is not None:
                return plan

        if usage is not None and int(usage.calls_included or 0) > 0:
            matches = list(
                db.execute(
                    select(Plan).where(
                        Plan.is_active.is_(True),
                        Plan.calls_included == int(usage.calls_included),
                    )
                )
                .scalars()
                .all()
            )
            if len(matches) == 1:
                return matches[0]

        return None

    @staticmethod
    def repair_subscription_plan_id(db: Session, org_id: str) -> Subscription | None:
        """Self-heal stale subscription.plan_id when usage wallet still references a valid plan."""
        sub = BillingService.get_subscription(db, org_id)
        if sub is None:
            return None
        resolved = BillingService.resolve_active_plan(db, org_id)
        if resolved is None or str(sub.plan_id) == str(resolved.id):
            return sub
        existing = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()
        if existing is not None:
            return sub
        sub.plan_id = resolved.id
        sub.updated_at = datetime.utcnow()
        db.add(sub)
        db.commit()
        db.refresh(sub)
        logger.info(
            "subscription_plan_id_repaired",
            extra={"org_id": org_id, "plan_id": resolved.id, "plan_code": resolved.code},
        )
        return sub

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
        sub = BillingService.get_subscription(db, org_id)
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
        sub = BillingService.get_subscription(db, org_id)
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
        sub = BillingService.get_subscription(db, org_id)
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
            "cash_available": False,
            "cash_requires_admin_approval": False,
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

        sub = BillingService.get_subscription(db, org_id)
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
    def switch_to_pay_as_you_go(db: Session, *, org_id: str) -> tuple[Subscription, Plan]:
        """Move org to the zero-fee pay-as-you-go plan without a payment provider checkout."""
        from app.services.voxbulk_pricing_service import VoxbulkPricingService

        VoxbulkPricingService.ensure_seeded(db)
        plan = db.execute(select(Plan).where(Plan.code == "payg")).scalar_one_or_none()
        if plan is None or not bool(getattr(plan, "is_active", True)):
            raise ValueError("Pay as you go is not available")

        now = datetime.utcnow()
        sub = BillingService.get_subscription(db, org_id)
        period_end = now + timedelta(days=3650)
        if sub is None:
            sub = Subscription(
                org_id=org_id,
                plan_id=plan.id,
                status="active",
                current_period_end=period_end,
                payment_provider="payg",
                payment_mode="live",
                updated_at=now,
            )
            db.add(sub)
        else:
            sub.plan_id = plan.id
            sub.pending_plan_id = None
            sub.status = "active"
            sub.current_period_end = period_end
            sub.payment_provider = "payg"
            sub.updated_at = now
            db.add(sub)
        db.commit()
        db.refresh(sub)
        return sub, plan

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
        sub = BillingService.get_subscription(db, org_id)
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
    def _usable_dashboard_origin(origin: str) -> bool:
        raw = str(origin or "").strip().rstrip("/")
        if not raw.lower().startswith("https://"):
            return False
        lowered = raw.lower()
        if "localhost" in lowered or "127.0.0.1" in lowered:
            return False
        if any(port in lowered for port in (":5173", ":5174", ":5175", ":8000")):
            return False
        host = lowered.split("://", 1)[-1].split("/")[0].split(":")[0]
        return host.startswith("dashboard.")

    @staticmethod
    def _resolved_dashboard_origin() -> str:
        settings = get_settings()
        configured = str(settings.dashboard_app_origin or "").strip().rstrip("/")
        if BillingService._usable_dashboard_origin(configured):
            return configured
        if str(settings.env).lower() in {"production", "prod", "staging"}:
            return "https://dashboard.voxbulk.com"
        return configured or "http://localhost:5175"

    @staticmethod
    def _configured_redirect_url(config: dict[str, Any], key: str) -> str:
        from urllib.parse import urlparse

        raw = str(config.get(key) or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return ""
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if not BillingService._usable_dashboard_origin(origin):
            return ""
        return raw

    @staticmethod
    def _api_public_origin() -> str:
        dash = BillingService._resolved_dashboard_origin()
        if "dashboard." in dash:
            return dash.replace("dashboard.", "api.", 1)
        settings = get_settings()
        if str(settings.env).lower() in {"production", "prod", "staging"}:
            return "https://api.voxbulk.com"
        return "http://127.0.0.1:8000"

    @staticmethod
    def _dashboard_billing_path() -> str:
        return "/account/billing"

    @staticmethod
    def _dashboard_billing_url(origin: str, *, query: str = "") -> str:
        base = f"{str(origin or '').rstrip('/')}{BillingService._dashboard_billing_path()}"
        return f"{base}?{query}" if query else base

    @staticmethod
    def _gocardless_browser_return_url(session_token: str, *, billing: str) -> str:
        from urllib.parse import urlencode

        api_origin = BillingService._api_public_origin().rstrip("/")
        query = urlencode({"session_token": session_token, "billing": billing})
        return f"{api_origin}/billing/subscription/gocardless/browser-return?{query}"

    @staticmethod
    def _dashboard_packages_path() -> str:
        return "/account/packages"

    @staticmethod
    def _dashboard_packages_url(origin: str, *, query: str = "") -> str:
        base = f"{str(origin or '').rstrip('/')}{BillingService._dashboard_packages_path()}"
        return f"{base}?{query}" if query else base

    @staticmethod
    def _normalize_dashboard_return_url(url: str) -> str:
        """Rewrite legacy /packages return links to /account/packages."""
        from urllib.parse import urlparse, urlunparse

        raw = str(url or "").strip()
        if not raw:
            return raw
        parsed = urlparse(raw)
        path = parsed.path or ""
        if path.rstrip("/") in {"/packages", "packages"}:
            path = BillingService._dashboard_packages_path()
        return urlunparse(parsed._replace(path=path))

    @staticmethod
    def _default_success_url(config: dict[str, Any]) -> str:
        configured = BillingService._configured_redirect_url(config, "success_redirect_url")
        if configured:
            return BillingService._normalize_dashboard_return_url(configured)
        origin = BillingService._resolved_dashboard_origin()
        return BillingService._dashboard_packages_url(origin, query="billing=success")

    @staticmethod
    def _default_cancel_url(config: dict[str, Any]) -> str:
        configured = BillingService._configured_redirect_url(config, "cancel_redirect_url")
        if configured:
            return BillingService._normalize_dashboard_return_url(configured)
        origin = BillingService._resolved_dashboard_origin()
        return BillingService._dashboard_packages_url(origin, query="billing=cancelled")

    @staticmethod
    def _gocardless_metadata(**fields: str) -> dict[str, str]:
        """GoCardless allows at most 3 metadata keys per resource."""
        out: dict[str, str] = {}
        for key, value in fields.items():
            text = str(value or "").strip()
            if text:
                out[key] = text
            if len(out) >= 3:
                break
        return out

    @staticmethod
    def _raise_for_gocardless_error(response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        try:
            payload = response.json()
        except Exception:
            payload = {"error": response.text[:500]}
        message = payload.get("message") if isinstance(payload, dict) else None
        if not message and isinstance(payload, dict):
            errors = payload.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if isinstance(first, dict) and first.get("message"):
                    field = str(first.get("field") or "").strip()
                    message = f"{field}: {first['message']}" if field else str(first["message"])
        detail = message or str(payload)
        raise GoCardlessProviderError(f"GoCardless API error {response.status_code}: {detail}")

    @staticmethod
    def resolve_org_mandate_id(db: Session, org_id: str) -> str | None:
        """Resolve the active GoCardless mandate for an org (stored, or via the GC subscription)."""
        sub = BillingService.get_subscription(db, org_id)
        if sub is None or str(sub.payment_provider or "").strip().lower() != "gocardless":
            return None
        status = str(sub.status or "").strip().lower()
        if status not in {"active", "trial", "past_due"}:
            return None
        stored = str(getattr(sub, "mandate_id", None) or "").strip()
        mandate_status = str(getattr(sub, "mandate_status", None) or "").strip().lower()
        if stored and mandate_status not in {"cancelled", "failed", "expired"}:
            return stored

        ext_sub_id = str(sub.external_subscription_id or "").strip()
        if not ext_sub_id:
            return None
        config = BillingService._get_gocardless_config(db)
        headers = BillingService._gocardless_headers(config["access_token"])
        with httpx.Client(timeout=20) as client:
            sub_response = client.get(f"{config['api_base']}/subscriptions/{ext_sub_id}", headers=headers)
        BillingService._raise_for_gocardless_error(sub_response)
        subscription_payload = sub_response.json().get("subscriptions") or {}
        mandate_id = str((subscription_payload.get("links") or {}).get("mandate") or "").strip()
        if mandate_id and not stored:
            sub.mandate_id = mandate_id
            sub.mandate_status = sub.mandate_status or "active"
            db.add(sub)
            db.commit()
        return mandate_id or None

    @staticmethod
    def _org_plan_billing_amount(db: Session, org_id: str, plan: Plan) -> tuple[str, int]:
        from app.services.billing_currency import resolve_org_currency
        from app.services.plan_price_service import PlanPriceService

        org = db.get(Organisation, org_id)
        rates = PlanPriceService.rates_for_org(db, org, plan=plan)
        currency = str(rates.get("currency") or resolve_org_currency(db, org) or "GBP").upper()[:3]
        monthly_minor = int(rates.get("monthly_price_minor") or plan.price_gbp_pence or 0)
        return currency, monthly_minor

    @staticmethod
    def cancel_gocardless_payment(db: Session, payment_id: str) -> bool:
        pid = str(payment_id or "").strip()
        if not pid:
            return False
        config = BillingService._get_gocardless_config(db)
        headers = BillingService._gocardless_headers(config["access_token"])
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{config['api_base']}/payments/{pid}/actions/cancel",
                headers=headers,
                json={"data": {}},
            )
        if response.status_code >= 400:
            logger.warning("gocardless_payment_cancel_failed payment_id=%s status=%s", pid, response.status_code)
            return False
        return True

    @staticmethod
    def _cancel_gocardless_subscription(db: Session, external_subscription_id: str) -> bool:
        ext_id = str(external_subscription_id or "").strip()
        if not ext_id:
            return False
        config = BillingService._get_gocardless_config(db)
        headers = BillingService._gocardless_headers(config["access_token"])
        with httpx.Client(timeout=20) as client:
            response = client.post(
                f"{config['api_base']}/subscriptions/{ext_id}/actions/cancel",
                headers=headers,
                json={"data": {}},
            )
        if response.status_code >= 400:
            logger.warning("gocardless_subscription_cancel_failed sub_id=%s status=%s", ext_id, response.status_code)
            return False
        return True

    @staticmethod
    def _create_gocardless_subscription_on_mandate(
        db: Session,
        *,
        org_id: str,
        plan: Plan,
        mandate_id: str,
        client_email: str,
    ) -> str | None:
        currency, monthly_minor = BillingService._org_plan_billing_amount(db, org_id, plan)
        if monthly_minor <= 0:
            return None
        config = BillingService._get_gocardless_config(db)
        subscription_payload = {
            "subscriptions": {
                "amount": monthly_minor,
                "currency": currency,
                "name": f"VOXBULK.COM {plan.name}",
                "interval_unit": "monthly" if plan.interval == "monthly" else str(plan.interval or "monthly"),
                "links": {"mandate": mandate_id},
                "metadata": BillingService._gocardless_metadata(
                    org_id=org_id,
                    plan_id=plan.id,
                    client_email=client_email,
                ),
            }
        }
        with httpx.Client(timeout=20) as client:
            subscription_response = client.post(
                f"{config['api_base']}/subscriptions",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json=subscription_payload,
            )
        if subscription_response.status_code >= 400:
            BillingService._log_gocardless_http_failure(
                "subscription_create",
                response=subscription_response,
            )
            BillingService._raise_for_gocardless_error(subscription_response)
        provider_sub = subscription_response.json().get("subscriptions") or {}
        return str(provider_sub.get("id") or "").strip() or None

    @staticmethod
    def has_active_mandate(db: Session, org_id: str) -> bool:
        try:
            return bool(BillingService.resolve_org_mandate_id(db, org_id))
        except (GoCardlessConfigError, GoCardlessProviderError):
            return False

    @staticmethod
    def collect_mandate_payment(
        db: Session,
        *,
        org_id: str,
        amount_pence: int,
        description: str,
        currency: str = "GBP",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Charge an existing GoCardless direct-debit mandate (subscription customers)."""
        charge_pence = max(0, int(amount_pence or 0))
        if charge_pence <= 0:
            return None

        mandate_id = BillingService.resolve_org_mandate_id(db, org_id)
        if not mandate_id:
            return None

        config = BillingService._get_gocardless_config(db)
        headers = BillingService._gocardless_headers(config["access_token"])
        meta_fields = {"org_id": org_id, **(metadata or {})}
        payment_payload = {
            "payments": {
                "amount": charge_pence,
                "currency": str(currency or "GBP").upper()[:3],
                "description": str(description or "VOXBULK usage overage")[:255],
                "links": {"mandate": mandate_id},
                "metadata": BillingService._gocardless_metadata(**meta_fields),
            }
        }
        with httpx.Client(timeout=20) as client:
            payment_response = client.post(
                f"{config['api_base']}/payments",
                headers=headers,
                json=payment_payload,
            )
        BillingService._raise_for_gocardless_error(payment_response)
        provider_payment = payment_response.json().get("payments") or {}
        payment_id = str(provider_payment.get("id") or "").strip()
        if not payment_id:
            raise GoCardlessProviderError("GoCardless did not return a payment id")
        return {
            "payment_id": payment_id,
            "status": str(provider_payment.get("status") or "pending_submission"),
            "mandate_id": mandate_id,
            "amount_pence": charge_pence,
        }

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
        configured_success = BillingService._configured_redirect_url(config, "success_redirect_url")
        configured_cancel = BillingService._configured_redirect_url(config, "cancel_redirect_url")
        if configured_success:
            success_url = BillingService._normalize_dashboard_return_url(configured_success)
        else:
            success_url = BillingService._gocardless_browser_return_url(session_token, billing="success")
        if configured_cancel:
            cancel_url = BillingService._normalize_dashboard_return_url(configured_cancel)
        else:
            cancel_url = BillingService._gocardless_browser_return_url(session_token, billing="cancelled")
        payload = {
            "redirect_flows": {
                "description": f"VOXBULK.COM {plan.name} subscription",
                "session_token": session_token,
                "success_redirect_url": success_url,
                "prefilled_customer": {"email": user.email},
                "metadata": BillingService._gocardless_metadata(
                    org_id=org_id,
                    plan_id=plan.id,
                    client_email=user.email,
                ),
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
    def _activation_invoice_external_id(external_subscription_id: str, flow_id: str) -> str:
        sub_id = str(external_subscription_id or "").strip()
        if sub_id:
            return f"sub:{sub_id}:initial"
        return f"flow:{str(flow_id or '').strip()}:initial"

    @staticmethod
    def _log_gocardless_http_failure(step: str, *, redirect_flow_id: str, response: httpx.Response) -> None:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("message") or payload.get("error") or "")[:300]
        except Exception:
            detail = (response.text or "")[:300]
        logger.warning(
            "gocardless_complete_api_failed",
            extra={
                "step": step,
                "redirect_flow_id": redirect_flow_id,
                "status_code": response.status_code,
                "detail": detail,
            },
        )

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

        logger.info(
            "gocardless_complete_start",
            extra={"redirect_flow_id": flow_id, "org_id": org_id, "user_id": user_id},
        )

        row = (
            db.execute(
                select(BillingRedirectFlow)
                .where(
                    BillingRedirectFlow.redirect_flow_id == flow_id,
                    BillingRedirectFlow.org_id == org_id,
                    BillingRedirectFlow.user_id == user_id,
                )
                .order_by(BillingRedirectFlow.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        logger.info(
            "gocardless_complete_redirect_lookup",
            extra={
                "redirect_flow_id": flow_id,
                "found": row is not None,
                "flow_status": row.status if row else None,
                "plan_id": row.plan_id if row else None,
            },
        )
        if row is None:
            raise ValueError("Billing redirect flow not found")

        plan = db.execute(select(Plan).where(Plan.id == row.plan_id)).scalar_one_or_none()
        if plan is None:
            raise ValueError("Plan not found")

        if row.status == "completed":
            sub = BillingAccessService.get_subscription(
                db,
                org_id,
                service_code="customer_feedback" if str(row.flow_purpose or "") == "customer_feedback" else "voxbulk",
            )
            logger.info(
                "gocardless_complete_already_done",
                extra={"redirect_flow_id": flow_id, "org_id": org_id, "subscription_status": sub.status if sub else None},
            )
            return {"ok": True, "status": "completed", "subscription": sub, "plan": plan}

        config = BillingService._get_gocardless_config(db)
        with httpx.Client(timeout=20) as client:
            complete_response = client.post(
                f"{config['api_base']}/redirect_flows/{flow_id}/actions/complete",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json={"data": {"session_token": row.session_token}},
            )
        if complete_response.status_code >= 400:
            BillingService._log_gocardless_http_failure(
                "redirect_flow_complete",
                redirect_flow_id=flow_id,
                response=complete_response,
            )
        BillingService._raise_for_gocardless_error(complete_response)
        completed_flow = (complete_response.json().get("redirect_flows") or {})
        links = completed_flow.get("links") or {}
        mandate_id = str(links.get("mandate") or "").strip()
        customer_id = str(links.get("customer") or "").strip()
        logger.info(
            "gocardless_complete_api_success",
            extra={
                "redirect_flow_id": flow_id,
                "mandate_id": mandate_id,
                "customer_id": customer_id or None,
            },
        )
        if not mandate_id:
            raise GoCardlessProviderError("GoCardless did not return a mandate")

        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        prefilled_email = str((completed_flow.get("prefilled_customer") or {}).get("email") or "").strip()
        client_email = prefilled_email or (user.email if user else "")

        currency, monthly_minor = BillingService._org_plan_billing_amount(db, org_id, plan)
        external_subscription_id = BillingService._create_gocardless_subscription_on_mandate(
            db,
            org_id=org_id,
            plan=plan,
            mandate_id=mandate_id,
            client_email=client_email,
        )
        if not external_subscription_id:
            raise GoCardlessProviderError("GoCardless did not return a subscription id")
        logger.info(
            "gocardless_subscription_created",
            extra={
                "redirect_flow_id": flow_id,
                "mandate_id": mandate_id,
                "external_subscription_id": external_subscription_id or None,
            },
        )

        mandate_scheme = None
        try:
            with httpx.Client(timeout=20) as client:
                mandate_response = client.get(
                    f"{config['api_base']}/mandates/{mandate_id}",
                    headers=BillingService._gocardless_headers(config["access_token"]),
                )
            if mandate_response.status_code < 400:
                mandate_payload = mandate_response.json().get("mandates") or {}
                mandate_scheme = str(mandate_payload.get("scheme") or "").strip() or None
        except Exception:
            logger.warning("gocardless_mandate_scheme_lookup_failed mandate_id=%s", mandate_id)

        now = datetime.utcnow()
        service_code = "customer_feedback" if str(row.flow_purpose or "") == "customer_feedback" else "voxbulk"
        sub = BillingAccessService.get_subscription(db, org_id, service_code=service_code)
        if sub is None:
            sub = Subscription(org_id=org_id, plan_id=plan.id, service_code=service_code)
        sub.plan_id = plan.id
        sub.current_period_end = now + timedelta(days=30)
        sub.payment_provider = "gocardless"
        sub.payment_mode = str(config["environment"])
        sub.external_customer_id = customer_id or None
        sub.external_subscription_id = external_subscription_id or None
        sub.updated_at = now
        from app.services.billing_access_service import BillingAccessService

        BillingAccessService.apply_mandate_setup_access(
            db, sub=sub, mandate_id=mandate_id, scheme=mandate_scheme
        )
        db.add(sub)

        row.status = "completed"
        row.completed_at = now
        row.updated_at = now
        row.error_message = None
        db.add(row)
        db.commit()
        db.refresh(sub)
        logger.info(
            "gocardless_subscription_activated",
            extra={
                "redirect_flow_id": flow_id,
                "org_id": org_id,
                "subscription_id": sub.id,
                "subscription_status": sub.status,
                "external_subscription_id": external_subscription_id or None,
                "plan_id": plan.id,
            },
        )

        from app.models.organisation import Organisation
        from app.services.invoice_service import InvoiceService

        org = db.get(Organisation, org_id)
        if user is None:
            user = db.get(User, user_id)
        invoice_email = prefilled_email or (org.contact_email if org else "") or (user.email if user else "")
        external_invoice_id = BillingService._activation_invoice_external_id(external_subscription_id, flow_id)
        if not invoice_email:
            logger.warning(
                "gocardless_activation_invoice_skipped",
                extra={
                    "redirect_flow_id": flow_id,
                    "org_id": org_id,
                    "reason": "missing_client_email",
                    "external_invoice_id": external_invoice_id,
                },
            )
        else:
            try:
                act_currency, act_minor = BillingService._org_plan_billing_amount(db, org_id, plan)
                invoice, created, emailed = InvoiceService.issue_from_payment(
                    db,
                    org_id=org_id,
                    client_email=invoice_email,
                    subtotal_pence=act_minor,
                    currency=act_currency,
                    description=f"{plan.name} — subscription",
                    provider="gocardless",
                    external_invoice_id=external_invoice_id,
                    payment_reference=external_subscription_id or mandate_id,
                    payment_method="gocardless",
                    status="paid",
                    line_items=[
                        {
                            "description": f"{plan.name} — monthly subscription",
                            "quantity": 1,
                            "unit_pence": act_minor,
                            "total_pence": act_minor,
                        }
                    ],
                )
                from app.core.logging import safe_log_extra

                logger.info(
                    "gocardless_activation_invoice_success",
                    extra=safe_log_extra(
                        redirect_flow_id=flow_id,
                        org_id=org_id,
                        invoice_id=invoice.id,
                        external_invoice_id=external_invoice_id,
                        invoice_was_new=created,
                        emailed=emailed,
                    ),
                )
            except Exception as exc:
                logger.exception(
                    "gocardless_activation_invoice_failed",
                    extra={
                        "redirect_flow_id": flow_id,
                        "org_id": org_id,
                        "external_invoice_id": external_invoice_id,
                        "error": str(exc)[:500],
                    },
                )

        if service_code == "customer_feedback":
            from app.services.customer_feedback.billing_service import FeedbackBillingService

            FeedbackBillingService.on_subscription_activated(db, org_id=org_id, subscription=sub, plan=plan)
            FeedbackBillingService._tag_activation_invoice(db, org_id=org_id)

        return {"ok": True, "status": "completed", "subscription": sub, "plan": plan}

    @staticmethod
    def _fetch_gocardless_mandate_status(db: Session, mandate_id: str) -> str:
        mid = str(mandate_id or "").strip()
        if not mid:
            return ""
        config = BillingService._get_gocardless_config(db)
        with httpx.Client(timeout=20) as client:
            response = client.get(
                f"{config['api_base']}/mandates/{mid}",
                headers=BillingService._gocardless_headers(config["access_token"]),
            )
        if response.status_code >= 400:
            return ""
        payload = response.json().get("mandates") or {}
        return str(payload.get("status") or "").strip().lower()

    @staticmethod
    def _cancel_gocardless_mandate(db: Session, mandate_id: str) -> bool:
        mid = str(mandate_id or "").strip()
        if not mid:
            return True
        try:
            config = BillingService._get_gocardless_config(db)
            with httpx.Client(timeout=20) as client:
                response = client.post(
                    f"{config['api_base']}/mandates/{mid}/actions/cancel",
                    headers=BillingService._gocardless_headers(config["access_token"]),
                    json={},
                )
            if response.status_code >= 400:
                logger.warning(
                    "gocardless_mandate_cancel_failed mandate_id=%s status=%s",
                    mid,
                    response.status_code,
                )
                return False
            return True
        except Exception:
            logger.exception("gocardless_mandate_cancel_exception mandate_id=%s", mid)
            return False

    @staticmethod
    def start_mandate_update_redirect_flow(
        db: Session,
        *,
        org_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        sub = BillingService.get_subscription(db, org_id)
        if sub is None:
            raise ValueError("No subscription found")
        if str(sub.payment_provider or "").strip().lower() != "gocardless":
            raise ValueError("Direct Debit is not configured for this subscription")

        previous_mandate_id = str(getattr(sub, "mandate_id", None) or "").strip()
        mandate_status = str(getattr(sub, "mandate_status", None) or "").strip().lower()
        if not previous_mandate_id or mandate_status in {"cancelled", "failed", "expired"}:
            previous_mandate_id = BillingService.resolve_org_mandate_id(db, org_id) or ""
        if not previous_mandate_id:
            raise ValueError("No active Direct Debit mandate to update")

        plan = db.execute(select(Plan).where(Plan.id == sub.plan_id)).scalar_one_or_none()
        if plan is None:
            raise ValueError("Plan not found")

        user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if user is None:
            raise ValueError("Unknown user")

        config = BillingService._get_gocardless_config(db)
        session_token = secrets.token_urlsafe(32)
        success_url = BillingService._gocardless_browser_return_url(session_token, billing="mandate_success")
        cancel_url = BillingService._gocardless_browser_return_url(session_token, billing="mandate_cancelled")
        payload = {
            "redirect_flows": {
                "description": "Update Direct Debit details",
                "session_token": session_token,
                "success_redirect_url": success_url,
                "prefilled_customer": {"email": user.email},
                "metadata": BillingService._gocardless_metadata(
                    org_id=org_id,
                    plan_id=plan.id,
                    client_email=user.email,
                ),
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
            plan_id=plan.id,
            redirect_flow_id=redirect_flow_id,
            session_token=session_token,
            environment=str(config["environment"]),
            status="created",
            authorization_url=authorization_url,
            flow_purpose="mandate_update",
            previous_mandate_id=previous_mandate_id,
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
        }

    @staticmethod
    def complete_mandate_update_redirect_flow(
        db: Session,
        *,
        org_id: str,
        user_id: str,
        redirect_flow_id: str,
    ) -> dict[str, Any]:
        flow_id = str(redirect_flow_id or "").strip()
        if not flow_id:
            raise ValueError("redirect_flow_id required")

        row = (
            db.execute(
                select(BillingRedirectFlow)
                .where(
                    BillingRedirectFlow.redirect_flow_id == flow_id,
                    BillingRedirectFlow.org_id == org_id,
                    BillingRedirectFlow.user_id == user_id,
                    BillingRedirectFlow.flow_purpose == "mandate_update",
                )
                .order_by(BillingRedirectFlow.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if row is None:
            raise ValueError("Mandate update redirect flow not found")

        sub = BillingService.get_subscription(db, org_id)
        if sub is None:
            raise ValueError("Subscription not found")

        if row.status == "completed":
            return {"ok": True, "status": "completed", "subscription": sub}

        previous_mandate_id = str(row.previous_mandate_id or "").strip()
        config = BillingService._get_gocardless_config(db)
        with httpx.Client(timeout=20) as client:
            complete_response = client.post(
                f"{config['api_base']}/redirect_flows/{flow_id}/actions/complete",
                headers=BillingService._gocardless_headers(config["access_token"]),
                json={"data": {"session_token": row.session_token}},
            )
        if complete_response.status_code >= 400:
            BillingService._log_gocardless_http_failure(
                "mandate_update_complete",
                redirect_flow_id=flow_id,
                response=complete_response,
            )
        BillingService._raise_for_gocardless_error(complete_response)

        completed_flow = (complete_response.json().get("redirect_flows") or {})
        links = completed_flow.get("links") or {}
        new_mandate_id = str(links.get("mandate") or "").strip()
        if not new_mandate_id:
            raise GoCardlessProviderError("GoCardless did not return a mandate")

        mandate_status = BillingService._fetch_gocardless_mandate_status(db, new_mandate_id)
        if mandate_status not in {"active", "pending_submission", "submitted"}:
            raise GoCardlessProviderError(f"Mandate is not active yet (status={mandate_status or 'unknown'})")

        mandate_scheme = None
        try:
            with httpx.Client(timeout=20) as client:
                mandate_response = client.get(
                    f"{config['api_base']}/mandates/{new_mandate_id}",
                    headers=BillingService._gocardless_headers(config["access_token"]),
                )
            if mandate_response.status_code < 400:
                mandate_payload = mandate_response.json().get("mandates") or {}
                mandate_scheme = str(mandate_payload.get("scheme") or "").strip() or None
        except Exception:
            logger.warning("gocardless_mandate_scheme_lookup_failed mandate_id=%s", new_mandate_id)

        from app.services.billing_access_service import BillingAccessService

        BillingAccessService.apply_mandate_setup_access(
            db, sub=sub, mandate_id=new_mandate_id, scheme=mandate_scheme
        )

        plan = db.get(Plan, sub.plan_id)
        org = db.get(Organisation, org_id)
        user = db.get(User, user_id)
        client_email = str((org.contact_email if org else "") or (user.email if user else "")).strip()
        if plan is not None and client_email:
            old_ext = str(sub.external_subscription_id or "").strip()
            if old_ext:
                BillingService._cancel_gocardless_subscription(db, old_ext)
            new_ext = BillingService._create_gocardless_subscription_on_mandate(
                db,
                org_id=org_id,
                plan=plan,
                mandate_id=new_mandate_id,
                client_email=client_email,
            )
            if new_ext:
                sub.external_subscription_id = new_ext

        old_cancelled = True
        if previous_mandate_id and previous_mandate_id != new_mandate_id:
            old_cancelled = BillingService._cancel_gocardless_mandate(db, previous_mandate_id)
            if not old_cancelled:
                logger.warning(
                    "gocardless_old_mandate_cancel_skipped org_id=%s old=%s new=%s",
                    org_id,
                    previous_mandate_id,
                    new_mandate_id,
                )

        now = datetime.utcnow()
        row.status = "completed"
        row.completed_at = now
        row.updated_at = now
        row.error_message = None
        db.add(row)
        db.add(sub)
        db.commit()
        db.refresh(sub)

        return {
            "ok": True,
            "status": "completed",
            "subscription": sub,
            "mandate_id": new_mandate_id,
            "previous_mandate_cancelled": old_cancelled,
        }

    # Per-order GoCardless redirect checkout removed — PAYG launches are paid from the
    # wallet (Stripe/Airwallex top-ups) and subscription extras are collected via the
    # existing mandate (see LaunchBillingService).

