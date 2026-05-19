from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    price_gbp_pence: int
    interval: str
    created_at: datetime
    description: str | None = None
    """JSON array of feature strings (stored column); clients may parse for bullets."""
    features_json: str | None = None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    plan_id: str
    status: str
    current_period_end: datetime | None
    payment_provider: str | None = None
    payment_mode: str | None = None
    external_customer_id: str | None = None
    external_subscription_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SubscriptionWithPlanOut(BaseModel):
    subscription: SubscriptionOut | None = None
    plan: PlanOut | None = None
    test_cash_billing_enabled: bool = False


class BillingRedirectStartOut(BaseModel):
    ok: bool
    environment: str
    redirect_flow_id: str
    authorization_url: str
    cancel_url: str | None = None
    plan: PlanOut


class BillingRedirectCompleteIn(BaseModel):
    redirect_flow_id: str


class BillingRedirectCompleteOut(BaseModel):
    ok: bool
    status: str
    subscription: SubscriptionOut | None = None
    plan: PlanOut | None = None


class CashPlanSelectIn(BaseModel):
    plan_id: str | None = None
    plan_code: str | None = None

    @model_validator(mode="after")
    def require_plan_ref(self):
        if not (self.plan_id or "").strip() and not (self.plan_code or "").strip():
            raise ValueError("plan_id or plan_code required")
        if self.plan_id is not None:
            self.plan_id = self.plan_id.strip() or None
        if self.plan_code is not None:
            self.plan_code = self.plan_code.strip() or None
        return self


class DashboardMetricsOut(BaseModel):
    total_patients: int
    total_appointments: int
    total_call_logs: int
    total_whatsapp_logs: int
    appointment_status_counts: dict[str, int]

