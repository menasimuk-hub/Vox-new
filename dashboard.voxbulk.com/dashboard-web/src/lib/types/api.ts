export type ApiEnabledServices = {
  interview?: boolean;
  survey?: boolean;
  recovery?: boolean;
  follow_up?: boolean;
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
  total_patients?: number;
};

export type BillingSubscription = {
  subscription?: {
    status?: string;
    plan_id?: string;
  } | null;
  plan?: {
    id?: string;
    name?: string;
    price_pence?: number;
  } | null;
  pending_plan?: {
    id?: string;
    name?: string;
  } | null;
  test_cash_billing_enabled?: boolean;
  gocardless_checkout_available?: boolean;
  payment_options?: Record<string, unknown>;
};

export type UsageSummary = {
  usage?: Record<string, unknown> | null;
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
  }>;
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
};

export type BillingPlan = {
  id: string;
  name: string;
  price_pence?: number;
  description?: string;
};
