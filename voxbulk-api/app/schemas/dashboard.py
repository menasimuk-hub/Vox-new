from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    price_gbp_pence: int | None = None
    interval: str
    created_at: datetime
    description: str | None = None
    """JSON array of feature strings (stored column); clients may parse for bullets."""
    features_json: str | None = None
    calls_included: int = 0
    whatsapp_included: int = 0
    sms_included: int = 0
    cv_scans_included: int = 0
    overage_per_min_pence: int = 0
    per_min_pence: int = 0
    trial_days_default: int = 0
    service_kind: str = "voxbulk"
    is_featured: bool = False
    is_enterprise: bool = False
    is_active: bool = True
    sort_order: int = 100


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    plan_id: str
    pending_plan_id: str | None = None
    status: str
    current_period_end: datetime | None
    payment_provider: str | None = None
    payment_mode: str | None = None
    external_customer_id: str | None = None
    external_subscription_id: str | None = None
    mandate_id: str | None = None
    mandate_status: str | None = None
    billing_interval: str | None = "monthly"
    created_at: datetime
    updated_at: datetime | None = None


class SubscriptionWithPlanOut(BaseModel):
    subscription: SubscriptionOut | None = None
    plan: PlanOut | None = None
    pending_plan: PlanOut | None = None
    test_cash_billing_enabled: bool = False
    gocardless_checkout_available: bool = False
    payment_options: dict | None = None


class PaymentOptionsOut(BaseModel):
    cash_available: bool = True
    cash_requires_admin_approval: bool = True
    gocardless_available: bool = False
    gocardless_environment: str | None = None
    gocardless_auto_activate: bool = True


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
    billing_interval: str = "monthly"

    @model_validator(mode="after")
    def normalize_interval(self):
        raw = str(self.billing_interval or "monthly").strip().lower()
        self.billing_interval = "yearly" if raw == "yearly" else "monthly"
        return self

    @model_validator(mode="after")
    def require_plan_ref(self):
        if not (self.plan_id or "").strip() and not (self.plan_code or "").strip():
            raise ValueError("plan_id or plan_code required")
        if self.plan_id is not None:
            self.plan_id = self.plan_id.strip() or None
        if self.plan_code is not None:
            self.plan_code = self.plan_code.strip() or None
        return self


class SubscriptionCancellationRequestIn(BaseModel):
    cancellation_type: str = "period_end"
    reason: str | None = None
    requested_refund_type: str = "none"


class RefundReviewOut(BaseModel):
    id: str
    org_id: str
    subscription_id: str | None = None
    requested_refund_type: str
    review_status: str
    calculated_unused_value_pence: int | None = None
    approved_wallet_credit_pence: int = 0
    approved_external_refund_pence: int = 0
    source_payment_provider: str | None = None
    source_payment_reference: str | None = None
    admin_notes: str | None = None
    wallet_transaction_id: str | None = None
    credit_note_id: str | None = None
    requested_at: str | None = None
    resolved_at: str | None = None


class SubscriptionCancellationOut(BaseModel):
    status: str
    effective_subscription_status: str | None = None
    cancellation_type: str | None = None
    cancellation_reason: str | None = None
    requested_at: str | None = None
    effective_at: str | None = None
    current_period_end: str | None = None
    requested_refund_type: str | None = None
    calculated_unused_value_pence: int = 0
    calculated_unused_value_display: str | None = None
    can_request_cancellation: bool = False
    can_reverse_cancellation: bool = False
    can_request_immediate_cancellation: bool = False
    outstanding_invoice_minor: int = 0
    refund_review: RefundReviewOut | None = None
    policy_notes: dict | None = None


class DashboardMetricsOut(BaseModel):
    total_patients: int
    total_appointments: int
    total_call_logs: int
    total_whatsapp_logs: int
    appointment_status_counts: dict[str, int]

