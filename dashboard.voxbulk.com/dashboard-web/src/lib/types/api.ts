export type ApiEnabledServices = {
  interview?: boolean;
  survey?: boolean;
  customer_feedback?: boolean;
  appointments?: boolean;
  recovery?: boolean;
  follow_up?: boolean;
  campaigns?: boolean;
};

export type Organisation = {
  id: string;
  name?: string;
  display_name?: string;
  contact_email?: string;
  contact_phone?: string;
  contact_name?: string | null;
  website?: string | null;
  country?: string | null;
  address_line1?: string | null;
  city?: string | null;
  postcode?: string | null;
  enabled_services?: ApiEnabledServices;
  allowed_services?: ApiEnabledServices;
  visible_services?: ApiEnabledServices;
  logo_url?: string | null;
};

export type UserPhoneStatus = {
  phone_number?: string | null;
  phone_e164?: string | null;
  verification_status?: string;
};

export type UserProfile = {
  id: string;
  email?: string;
  role?: string;
  org_id?: string;
  phone?: UserPhoneStatus;
  is_sales_rep?: boolean;
  sales_rep_id?: string | null;
};

export type ServiceOrderReport = {
  responded?: number;
  completed?: number;
  sent?: number;
  reached?: number;
  interviewed?: number;
};

export type ServiceOrder = {
  id: string;
  org_id: string;
  service_code: "interview" | "survey" | string;
  title: string;
  survey_name?: string;
  reference_id?: string | null;
  campaign_id?: string | null;
  survey_id?: string | null;
  status: string;
  payment_status?: string | null;
  status_label?: string;
  workflow_state?: string;
  workflow_label?: string;
  pay_action?: string | null;
  can_launch?: boolean;
  can_pay?: boolean;
  is_running?: boolean;
  quote_total_pence?: number;
  recipient_count?: number;
  quote_total_gbp?: string;
  report?: ServiceOrderReport | null;
  is_live?: boolean;
  is_finished?: boolean;
  is_archived?: boolean;
  scheduled_start_at?: string | null;
  scheduled_end_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  config?: Record<string, unknown>;
  first_step_name?: string;
  step_labels?: string[];
};

export type HomeSummary = {
  enabled_services?: ApiEnabledServices;
  interview?: {
    live?: number;
    finished?: number;
    archived?: number;
    running?: number;
    candidates?: number;
    calls_attempted?: number;
    calls_completed?: number;
    recommended_advance?: number;
  };
  survey?: {
    live?: number;
    finished?: number;
    archived?: number;
    running?: number;
    paused?: number;
    responses?: number;
    sent?: number;
    completion_rate?: number;
  };
  recovery?: {
    queue_pending?: number;
    total_calls?: number;
    whatsapp_sent?: number;
  };
  feedback?: {
    qr_scans_today?: number;
    total_scans?: number;
    sentiment?: { excellent?: number; good?: number; poor?: number };
    unhappy?: Array<{
      id?: string;
      reason?: string;
      branch?: string;
      when?: string;
    }>;
    recent?: Array<{
      svc?: string;
      who?: string;
      what?: string;
      chip?: string;
      tone?: "ok" | "bad" | "info";
      when?: string;
    }>;
  };
  total_patients?: number;
};

export type BillingSubscription = {
  subscription?: {
    status?: string;
    plan_id?: string;
    pending_plan_id?: string | null;
    payment_provider?: string | null;
  } | null;
  plan?: {
    id?: string;
    code?: string;
    name?: string;
    sort_order?: number;
    price_gbp_pence?: number;
    price_pence?: number;
  } | null;
  pending_plan?: {
    id?: string;
    name?: string;
    code?: string;
  } | null;
  test_cash_billing_enabled?: boolean;
  gocardless_checkout_available?: boolean;
  payment_options?: Record<string, unknown>;
};

export type BillingMonitorPayload = {
  shared_package_pool?: boolean;
  value_pool_active?: boolean;
  commercial?: {
    package_remaining_pence?: number;
    package_remaining_display?: string;
    package_used_pence?: number;
    package_used_display?: string;
    package_included_pence?: number;
    package_included_display?: string;
    wallet_balance_pence?: number;
    wallet_balance_display?: string;
    primary_source?: string;
  };
  capacity_estimates?: {
    estimated_wa_surveys?: number;
    estimated_ai_minutes?: number;
    source?: string;
    label?: string;
    disclaimer?: string;
  };
  actual_usage?: {
    whatsapp_used?: number;
    calls_used?: number;
    sms_used?: number;
    survey_credits?: number;
    interview_credits?: number;
  };
  status?: {
    payment_status?: string;
    billing_period_start?: string | null;
    billing_period_end?: string | null;
    open_invoices_count?: number;
    overage_pending_pence?: number;
    overage_pending_display?: string;
    overage_risk?: boolean;
    in_soft_cap_grace?: boolean;
    next_action?: string;
    next_action_label?: string;
    next_invoice?: {
      amount_pence?: number | null;
      amount_display?: string;
      charge_date?: string | null;
      charge_date_display?: string;
      payment_method_label?: string;
      can_update_mandate?: boolean;
    };
  };
};

export type UsageSummary = {
  usage?: Record<string, unknown> | null;
  billing_monitor?: BillingMonitorPayload;
  meters?: Array<{
    key: string;
    label: string;
    used?: number;
    included?: number;
    remaining?: number | null;
    percent?: number;
    unit?: string;
    unlimited?: boolean;
    display_gbp?: string;
    informational?: boolean;
    estimate_source?: string;
    sublabel?: string;
  }>;
  allowances?: Array<{
    product: string;
    key: string;
    label: string;
    used: number;
    included: number;
    remaining: number | null;
    unit: string;
    unlimited?: boolean;
    period_start?: string | null;
    period_end?: string | null;
    pct_used?: number;
    shared_pool?: boolean;
  }>;
  allowance_alerts?: Array<{
    product?: string;
    key?: string;
    level: string;
    message: string;
    pct_used?: number;
  }>;
  billing_snapshot?: {
    has_core_subscription?: boolean;
    is_payg?: boolean;
    shared_package_pool?: boolean;
    wallet_balance_display?: string;
    wallet_balance_pence?: number;
  };
  wallet_balance_pence?: number;
  wallet_balance_gbp?: string;
  promo_credits?: { survey_credits?: number; interview_credits?: number };
  overage_pending_pence?: number;
  overage_pending_gbp?: string;
  estimated_overage_gbp?: number;
  period_start?: string | null;
  period_end?: string | null;
  current_plan?: { name?: string; price_gbp_pence?: number; code?: string } | null;
  subscription?: { status?: string } | null;
  open_invoices_count?: number;
  payment_status?: string;
  next_action?: string;
  next_action_label?: string;
};

export type InvoicePaymentContext = {
  payable?: boolean;
  partial_wallet_supported?: boolean;
  amount_due_minor?: number;
  amount_due_display?: string;
  payment_status?: string;
  payment_method?: string | null;
  dd_status?: string | null;
  kind?: string | null;
  order_id?: string | null;
  methods?: Array<Record<string, unknown>>;
  available_methods?: Array<Record<string, unknown>>;
  next_steps?: string[];
  wallet_balance_minor?: number;
  wallet_balance_display?: string;
  wallet_shortfall_minor?: number;
  wallet_shortfall_display?: string | null;
  card_available?: boolean;
  mandate_active?: boolean;
  lifecycle?: InvoiceLifecyclePolicy;
};

export type InvoiceLifecyclePolicy = {
  can_edit?: boolean;
  can_void?: boolean;
  is_locked?: boolean;
  lock_reason?: string | null;
  suggested_action?: string | null;
  suggested_action_label?: string | null;
  editable_fields?: string[];
  status?: string;
};

export type Invoice = {
  id: string;
  invoice_number?: string;
  issued_at?: string;
  created_at?: string;
  total_pence?: number;
  total_gbp?: string;
  status?: string;
  description?: string | null;
  provider?: string | null;
  kind?: string | null;
  order_id?: string | null;
  payable?: boolean;
  payment_context?: InvoicePaymentContext;
  lifecycle?: InvoiceLifecyclePolicy;
};

export type BillingPlan = {
  id: string;
  name: string;
  price_pence?: number;
  description?: string;
};
