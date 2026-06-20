import { keepPreviousData, useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch, apiUploadFiles } from "@/lib/api";
import { writeSessionToStorage } from "@/lib/session-storage";
import {
  BILLING_CHECK_TIMEOUT_MS,
  launchEligibilityLogPayload,
  logBillingCheck,
} from "@/lib/survey-launch-billing";
import { showRecoveryModules } from "@/lib/feature-flags";
import type {
  ApiEnabledServices,
  BillingPlan,
  HomeSummary,
  Invoice,
  Organisation,
  ServiceOrder,
  UsageSummary,
} from "@/lib/types/api";
import type { AssistantChatContext, AssistantChatResponse } from "@/lib/types/assistant";
export const queryKeys = {
  session: ["session"] as const,
  homeSummary: ["dashboard", "home-summary"] as const,
  serviceOrders: (code: string) => ["service-orders", code] as const,
  serviceOrder: (id: string) => ["service-orders", "detail", id] as const,
  credits: ["service-orders", "credits"] as const,
  billingSubscription: ["billing", "subscription"] as const,
  billingSubscriptionCancellation: ["billing", "subscription", "cancellation"] as const,
  billingPlans: ["billing", "plans"] as const,
  billingPricing: (market: string, orgCountry = "") => ["billing", "pricing", market, orgCountry] as const,
  billingWallet: ["billing", "wallet"] as const,
  billingUsage: ["billing", "usage-summary"] as const,
  billingUsageBreakdown: (filters: Record<string, string>) => ["billing", "usage-breakdown", filters] as const,
  billingRequests: ["billing", "requests"] as const,
  notifications: ["notifications"] as const,
  notificationUnread: ["notifications", "unread-count"] as const,
  billingInvoices: ["billing", "invoices"] as const,
  billingAccess: ["billing", "access"] as const,
  organisation: ["organisations", "me"] as const,
  myOrganisations: ["auth", "my-organisations"] as const,
  pendingInvites: ["auth", "pending-invites"] as const,
  interviewReports: (period: string) => ["service-orders", "interview-reports", period] as const,
  interviewResults: (orderId: string) => ["service-orders", orderId, "interview-results"] as const,
  surveyResults: (orderId: string) => ["service-orders", orderId, "survey-results"] as const,
  surveyPackages: ["service-orders", "survey-packages"] as const,
  serviceCatalog: ["service-orders", "catalog"] as const,
  interviewDraft: ["service-orders", "interview-draft"] as const,
  interviewAgents: ["service-orders", "interview-agents"] as const,
  surveyAgents: ["service-orders", "survey-agents"] as const,
  interviewBilling: ["service-orders", "interview-billing"] as const,
  orderRecipients: (orderId: string) => ["service-orders", orderId, "recipients"] as const,
  surveyLaunchEligibility: (orderId: string, cacheKey = "") =>
    ["service-orders", orderId, "launch-eligibility", cacheKey] as const,
  interviewRecipientActivity: (orderId: string, recipientId: string) =>
    ["service-orders", orderId, "recipients", recipientId, "activity"] as const,
  recoveryJobs: ["calls", "recovery", "jobs"] as const,
  callLogs: ["calls"] as const,
  supportTickets: ["support", "tickets"] as const,
  supportTicket: (id: string) => ["support", "tickets", id] as const,
  faq: ["faq"] as const,
  schedulingStatus: ["service-orders", "scheduling", "status"] as const,
  hubspotStatus: ["service-orders", "hubspot", "status"] as const,
  integrationsCatalogue: ["service-orders", "integrations", "catalogue"] as const,
  hubspotContacts: (limit?: number) => ["service-orders", "hubspot", "contacts", limit ?? 50] as const,
  crmSyncStatus: ["service-orders", "crm", "sync-status"] as const,
  crmContacts: (limit?: number) => ["service-orders", "crm", "contacts", limit ?? 50] as const,
  serviceApiSettings: ["organisations", "service-api-settings"] as const,
  teamMembers: ["organisations", "team", "members"] as const,
  teamInvites: ["organisations", "team", "invites"] as const,
  optOuts: ["organisations", "opt-outs"] as const,
  auditLog: ["organisations", "audit-log"] as const,
  deletionStatus: ["organisations", "deletion-status"] as const,
  feedbackLocations: ["customer-feedback", "locations"] as const,
  feedbackIndustries: ["customer-feedback", "catalog", "industries"] as const,
  feedbackSurveyTypes: (industryId: string) => ["customer-feedback", "catalog", "survey-types", industryId] as const,
  feedbackResults: (filters: Record<string, string>) => ["customer-feedback", "results", filters] as const,
  feedbackResultsInsights: (filters: Record<string, string>) =>
    ["customer-feedback", "results", "insights", filters] as const,
  feedbackResultsCompare: (locationIds: string) => ["customer-feedback", "results", "compare", locationIds] as const,
  feedbackPackages: ["customer-feedback", "packages"] as const,
  feedbackSubscriptionCancellation: ["customer-feedback", "subscription", "cancellation"] as const,
  feedbackSubscription: ["customer-feedback", "subscription"] as const,
};

export type FeedbackLocation = {
  id: string;
  org_id?: string;
  name: string;
  branch_code?: string | null;
  industry_id: string;
  industry_name?: string | null;
  survey_type_id: string;
  survey_type_name?: string | null;
  selected_survey_type_ids?: string[];
  open_question_enabled?: boolean;
  marketing_opt_in_enabled?: boolean;
  qr_token?: string;
  status: string;
  scan_count: number;
  trigger_text: string;
  wa_url: string;
  qr_image_url: string;
  created_at?: string | null;
};

export type FeedbackLocationPreview = {
  preview?: boolean;
  trigger_text: string;
  wa_url: string;
  qr_image_url: string;
  selected_survey_type_ids?: string[];
  open_question_enabled?: boolean;
  marketing_opt_in_enabled?: boolean;
};

export type CreateFeedbackLocationInput = {
  industry_id: string;
  survey_type_id?: string;
  selected_survey_type_ids?: string[];
  name: string;
  branch_code?: string;
  status?: string;
  open_question_enabled?: boolean;
  marketing_opt_in_enabled?: boolean;
};

export type UpdateFeedbackLocationInput = {
  selected_survey_type_ids?: string[];
  open_question_enabled?: boolean;
  marketing_opt_in_enabled?: boolean;
  name?: string;
  status?: string;
};

export type FeedbackIndustry = {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number;
};

export type FeedbackSurveyType = {
  id: string;
  industry_id: string;
  slug: string;
  name: string;
  description?: string | null;
  is_active?: boolean;
  sort_order?: number;
};

export type FeedbackPackage = {
  id: string;
  plan_id: string;
  plan_code?: string | null;
  plan_name?: string | null;
  market_zone?: string;
  max_locations: number;
  wa_units_included: number;
  admin_notes?: string | null;
  is_active?: boolean;
  is_featured?: boolean;
  display_order?: number;
  features?: string[];
  prices?: Array<{ currency: string; monthly_price_minor: number }>;
};

export type FeedbackSubscription = {
  active: boolean;
  status: string;
  plan_id?: string | null;
  plan_name?: string | null;
  service_code?: string;
  max_locations?: number;
  wa_units_included?: number;
  wa_units_used?: number;
  wa_units_remaining?: number;
  payment_provider?: string | null;
  current_period_end?: string | null;
};

export type FeedbackCompareLocation = {
  id: string;
  name: string;
  color: string;
  responses: number;
  invited: number;
  satisfaction_pct: number | null;
  recommend_pct: number | null;
  sentiment_pct: { happy: number; neutral: number; unhappy: number };
  weekly_trend: number[];
  per_question: Record<string, number>;
  industry_name?: string | null;
};

export type FeedbackComparePayload = {
  ok?: boolean;
  locations: FeedbackCompareLocation[];
  shared_questions: Array<{ key: string; title: string; short: string }>;
  all_questions: Array<{ key: string; title: string; short: string }>;
};

export type FeedbackResultsPayload = {
  ok?: boolean;
  location_name?: string | null;
  locations: FeedbackLocation[];
  survey_types?: Array<{ id: string; name: string; slug?: string }>;
  summary: {
    sessions: number;
    completed_sessions: number;
    responses: number;
    total_scans: number;
    satisfaction_pct?: number | null;
    recommend_pct?: number | null;
    completion_rate_pct?: number | null;
    sentiment_counts?: { unhappy: number; neutral: number; happy: number };
    unhappy_count?: number;
  };
  aggregates?: FeedbackAggregateBlock[];
  weekly_trend?: Array<{ week: string; satisfaction?: number | null; positive?: number | null; responses?: number }>;
  respondents?: FeedbackRespondent[];
  open_comments?: FeedbackOpenComment[];
  rows: Array<{
    id: string;
    session_id?: string;
    location_id: string;
    location_name?: string | null;
    survey_type_id?: string;
    survey_type_name?: string | null;
    question_key?: string;
    question?: string | null;
    answer_text?: string;
    original_text?: string | null;
    answer_source?: string | null;
    visitor_phone?: string | null;
    created_at?: string | null;
  }>;
};

export type FeedbackAggregateBlock = {
  question_key?: string;
  question?: string;
  step_role?: string | null;
  total?: number;
  visualization?: string;
  breakdown?: Array<{ label: string; key: string; count: number; pct: number }>;
  responses?: Array<{ answer: string; count: number }>;
};

export type FeedbackRespondent = {
  id?: string;
  phone?: string | null;
  location_id?: string;
  location_name?: string | null;
  completed_at?: string | null;
  is_unhappy?: boolean;
  flagged?: boolean;
  sentiment_label?: string | null;
  answers?: Array<{ question?: string; answer?: string; step_role?: string | null; answer_source?: string }>;
  quote?: string | null;
};

export type FeedbackOpenComment = {
  id?: string;
  session_id?: string;
  text?: string;
  original_text?: string | null;
  answer_source?: string;
  theme?: string | null;
  sentiment?: string;
  created_at?: string | null;
};

export type FeedbackResultsInsightsPayload = {
  ok?: boolean;
  ai?: {
    themes?: Array<{ label: string; value: number; sentiment: string }>;
    recommendations?: Array<{ title: string; text: string; impact?: string }>;
    generated_at?: string | null;
    source?: string;
  };
  open_comments?: FeedbackOpenComment[];
};

export function useHomeSummary() {
  return useQuery({
    queryKey: queryKeys.homeSummary,
    queryFn: () => apiFetch<HomeSummary>("/dashboard/home-summary"),
    staleTime: 1000 * 60 * 2, // Home data fresh for 2 minutes
  });
}

export function useServiceOrders(serviceCode: "interview" | "survey") {
  return useQuery({
    queryKey: queryKeys.serviceOrders(serviceCode),
    queryFn: () => apiFetch<ServiceOrder[]>(`/service-orders?service_code=${serviceCode}`),
  });
}

export function usePromoCredits() {
  return useQuery({
    queryKey: queryKeys.credits,
    queryFn: () => apiFetch<Record<string, unknown>>("/service-orders/credits"),
  });
}

export function useBillingSubscription() {
  return useQuery({
    queryKey: queryKeys.billingSubscription,
    queryFn: () => apiFetch("/billing/subscription"),
    refetchOnMount: "always",
  });
}

export function useBillingSubscriptionCancellation() {
  return useQuery({
    queryKey: queryKeys.billingSubscriptionCancellation,
    queryFn: () => apiFetch("/billing/subscription/cancellation"),
    refetchOnMount: "always",
  });
}

export type BillingUsageBreakdownFilters = {
  service_code?: string;
  status?: string;
  billing_source?: string;
  search?: string;
  limit?: number;
  offset?: number;
};

export function useBillingUsageBreakdown(filters: BillingUsageBreakdownFilters = {}) {
  const params = new URLSearchParams();
  if (filters.service_code) params.set("service_code", filters.service_code);
  if (filters.status) params.set("status", filters.status);
  if (filters.billing_source) params.set("billing_source", filters.billing_source);
  if (filters.search) params.set("search", filters.search);
  if (filters.limit) params.set("limit", String(filters.limit));
  if (filters.offset) params.set("offset", String(filters.offset));
  const qs = params.toString();
  const filterKey = Object.fromEntries(params.entries());
  return useQuery({
    queryKey: queryKeys.billingUsageBreakdown(filterKey),
    queryFn: () => apiFetch<Record<string, unknown>>(`/billing/usage-breakdown${qs ? `?${qs}` : ""}`),
    refetchOnMount: "always",
  });
}

export function useBillingRequests(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return useQuery({
    queryKey: [...queryKeys.billingRequests, status || ""],
    queryFn: () => apiFetch<{ items: Array<Record<string, unknown>> }>(`/billing/requests${qs}`),
    refetchOnMount: "always",
  });
}

export function useNotifications(limit = 10, unreadOnly = false) {
  return useQuery({
    queryKey: [...queryKeys.notifications, limit, unreadOnly],
    queryFn: () =>
      apiFetch<Array<Record<string, unknown>>>(
        `/notifications?limit=${limit}${unreadOnly ? "&unread_only=true" : ""}`,
      ),
    refetchInterval: 60_000,
  });
}

export function useUnreadNotifications(limit = 10) {
  return useNotifications(limit, true);
}

export function useNotificationUnreadCount() {
  return useQuery({
    queryKey: queryKeys.notificationUnread,
    queryFn: () => apiFetch<{ count: number }>("/notifications/unread-count"),
    refetchInterval: 60_000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notificationId: number) =>
      apiFetch(`/notifications/${notificationId}/read`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.notifications });
      void qc.invalidateQueries({ queryKey: queryKeys.notificationUnread });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<{ marked: number }>("/notifications/read-all", { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.notifications });
      void qc.invalidateQueries({ queryKey: queryKeys.notificationUnread });
    },
  });
}

export function useBillingPlans() {
  return useQuery({
    queryKey: queryKeys.billingPlans,
    queryFn: () => apiFetch<BillingPlan[]>("/billing/plans"),
  });
}

export function useBillingPricing(market = "gbp", orgCountry = "") {
  return useQuery({
    queryKey: queryKeys.billingPricing(market, orgCountry),
    queryFn: () => apiFetch<Record<string, unknown>>(`/billing/pricing?market=${encodeURIComponent(market)}`),
  });
}

export function useBillingWallet() {
  return useQuery({
    queryKey: queryKeys.billingWallet,
    queryFn: () => apiFetch<{ wallet_balance_pence: number; wallet_balance_gbp: string }>("/billing/wallet"),
  });
}

export type WalletTopupOptions = {
  ok: boolean;
  currency: string;
  providers: Array<{ id: string; label: string; publishable_key?: string }>;
  suggested_amounts: Array<Record<string, unknown>>;
  min_amount_minor: number;
  min_amount_display: string;
  wallet_balance_minor: number;
  wallet_balance_display: string;
};

export function useWalletTopupOptions() {
  return useQuery({
    queryKey: ["billing", "wallet", "topup-options"],
    queryFn: () => apiFetch<WalletTopupOptions>("/billing/wallet/topup/options"),
  });
}

export function useWalletTopupIntent() {
  return useMutation({
    mutationFn: (body: { provider: string; amount_minor: number }) =>
      apiFetch<{
        ok: boolean;
        provider: string;
        payment_intent_id: string;
        client_secret: string;
        publishable_key?: string;
        amount_minor: number;
        currency: string;
      }>("/billing/wallet/topup/intent", { method: "POST", body: JSON.stringify(body) }),
  });
}

export function useWalletTopupConfirm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { provider: string; payment_intent_id: string }) =>
      apiFetch<Record<string, unknown>>("/billing/wallet/topup/confirm", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.billingWallet });
      void qc.invalidateQueries({ queryKey: ["billing", "wallet", "topup-options"] });
      void qc.invalidateQueries({ queryKey: ["billing", "wallet", "transactions"] });
    },
  });
}

export function useWalletTransactions(limit = 50) {
  return useQuery({
    queryKey: ["billing", "wallet", "transactions", limit],
    queryFn: () =>
      apiFetch<{ ok: boolean; transactions: Array<Record<string, unknown>> }>(
        `/billing/wallet/transactions?limit=${limit}`,
      ),
  });
}

export function useBillingUsage() {
  return useQuery({
    queryKey: queryKeys.billingUsage,
    queryFn: () => apiFetch<UsageSummary>("/billing/usage-summary"),
    refetchOnMount: "always",
  });
}

export function useBillingInvoices() {
  return useQuery({
    queryKey: queryKeys.billingInvoices,
    queryFn: () => apiFetch<Invoice[]>("/billing/invoices"),
    refetchOnMount: "always",
  });
}

export function usePayInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { invoiceId: string; method?: string }) =>
      apiFetch<{ ok: boolean; method?: string; invoice?: Invoice }>(
        `/billing/invoices/${encodeURIComponent(args.invoiceId)}/pay`,
        {
          method: "POST",
          body: JSON.stringify({ method: args.method || "wallet" }),
        },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.billingInvoices });
      void qc.invalidateQueries({ queryKey: queryKeys.billingUsage });
      void qc.invalidateQueries({ queryKey: ["billing", "wallet"] });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
    },
  });
}

export function useBillingAccess() {
  return useQuery({
    queryKey: queryKeys.billingAccess,
    queryFn: () =>
      apiFetch<{
        can_launch: boolean;
        launch_block_reason?: string | null;
        credit_limit_exceeded?: boolean;
        outstanding_display?: string;
        credit_limit_display?: string;
        pending_first_payment?: boolean;
        subscription_status?: string | null;
        allow_overage?: boolean;
      }>("/billing/access"),
    refetchOnMount: "always",
  });
}

export function useArchiveOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderId: string) =>
      apiFetch(`/service-orders/${encodeURIComponent(orderId)}/archive`, { method: "POST" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
    },
  });
}

export function useDeleteOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: string | { orderId: string; confirmRunningDelete?: boolean }) => {
      const orderId = typeof args === "string" ? args : args.orderId;
      const confirmRunningDelete = typeof args === "object" && args.confirmRunningDelete;
      const qs = confirmRunningDelete ? "?confirm_running_delete=true" : "";
      return apiFetch(`/service-orders/${encodeURIComponent(orderId)}${qs}`, { method: "DELETE" });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
    },
  });
}

export function useDuplicateSurveyOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderId: string) =>
      apiFetch<{ ok: boolean; order: ServiceOrder }>(
        `/service-orders/${encodeURIComponent(orderId)}/duplicate`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
    },
  });
}

export function useStopSurveyOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orderId: string) =>
      apiFetch(`/service-orders/${encodeURIComponent(orderId)}/stop`, {
        method: "POST",
        body: JSON.stringify({}),
      }),
    onSuccess: (_data, orderId) => {
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(orderId) });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
    },
  });
}

export function useSaveEnabledServices() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiEnabledServices) =>
      apiFetch<{ enabled_services: ApiEnabledServices }>("/organisations/me/enabled-services", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.organisation });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
    },
  });
}

export function useServiceOrder(orderId: string | null) {
  return useQuery({
    queryKey: queryKeys.serviceOrder(orderId || ""),
    queryFn: () => apiFetch<ServiceOrder>(`/service-orders/${encodeURIComponent(orderId!)}`),
    enabled: Boolean(orderId),
  });
}

export function invalidateInterviewOrderQueries(qc: ReturnType<typeof useQueryClient>, orderId?: string | null) {
  void qc.invalidateQueries({ queryKey: ["service-orders"] });
  void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
  void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
  if (orderId) {
    void qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(orderId) });
    void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(orderId) });
    void qc.invalidateQueries({ queryKey: queryKeys.interviewResults(orderId) });
  }
}

export function useInterviewResults(orderId: string | null) {
  return useQuery({
    queryKey: queryKeys.interviewResults(orderId || ""),
    queryFn: () => apiFetch<Record<string, unknown>>(`/service-orders/${encodeURIComponent(orderId!)}/interview-results`),
    enabled: Boolean(orderId),
    refetchInterval: (query) => {
      const status = String((query.state.data?.order as { status?: string } | undefined)?.status || "").toLowerCase();
      if (["running", "scheduled", "paid"].includes(status)) return 8000;
      return false;
    },
  });
}

export function useInterviewRecipientDetail(orderId: string | null, recipientId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["service-orders", orderId, "interview-detail", recipientId],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(
        `/service-orders/${encodeURIComponent(orderId!)}/recipients/${encodeURIComponent(recipientId!)}/interview-detail`,
      ),
    enabled: Boolean(orderId && recipientId && enabled),
  });
}

export function useStartGoCardlessSubscription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) =>
      apiFetch<{ redirect_flow_id?: string; authorization_url?: string }>("/billing/subscription/gocardless/start", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.billingSubscription });
    },
  });
}

export function useCompleteGoCardlessSubscription() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (redirectFlowId: string) =>
      apiFetch("/billing/subscription/gocardless/complete", {
        method: "POST",
        body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.billingSubscription });
      void qc.invalidateQueries({ queryKey: queryKeys.session });
    },
  });
}

export function useSurveyResults(orderId: string | null) {
  return useQuery({
    queryKey: queryKeys.surveyResults(orderId || ""),
    queryFn: () => apiFetch<Record<string, unknown>>(`/service-orders/${encodeURIComponent(orderId!)}/survey-results`),
    enabled: Boolean(orderId),
    refetchInterval: (query) => {
      const summary = (query.state.data?.summary || {}) as Record<string, unknown>;
      const completed = Number(summary.completed_count || 0);
      const total = Number(summary.total_recipients || 0);
      const pendingAnalysis = Number(summary.pending_analysis ?? Math.max(0, total - completed));
      if (pendingAnalysis > 0 || (total > 0 && completed < total)) {
        return 5000;
      }
      return false;
    },
  });
}

export function useInterviewReports(period = "month") {
  return useQuery({
    queryKey: queryKeys.interviewReports(period),
    queryFn: () => apiFetch<Record<string, unknown>>(`/service-orders/interview-reports?period=${encodeURIComponent(period)}`),
  });
}

export function useSurveyPackages() {
  return useQuery({
    queryKey: queryKeys.surveyPackages,
    queryFn: () => apiFetch<Record<string, unknown>>("/service-orders/survey-packages"),
  });
}

export function useServiceCatalog() {
  return useQuery({
    queryKey: queryKeys.serviceCatalog,
    queryFn: () => apiFetch<Record<string, unknown>[]>("/service-orders/catalog"),
  });
}

export type InterviewDraftPayload = {
  order: ServiceOrder | null;
  recipients?: Record<string, unknown>[];
  summary?: Record<string, unknown>;
  billing_context?: Record<string, unknown>;
  interview_zoom_enabled?: boolean;
  interview_delivery_options?: string[];
};

export type CvCollectionLimits = {
  plan_included?: number;
  period_used?: number;
  plan_balance_remaining?: number | null;
  reserved_across_active?: number;
  remaining?: number | null;
  unlimited?: boolean;
  default_max_cvs?: number | null;
  available_for_order?: number | null;
  ats_parsing_pence?: number;
  ai_screening_pence?: number;
  combined_pence?: number;
  combined_gbp?: string;
  combined_label?: string;
  cost_per_cv_label?: string;
  overage_breakdown?: string;
  overage_unit_detail?: string;
  connection_fee_pence?: number;
  interview_per_min_pence?: number;
  duration_minutes?: number;
  call_cost_pence?: number;
  overage_unit_price_pence?: number;
  overage_unit_price_gbp?: string;
};

export function useInterviewCvCollectionLimits(orderId: string | null, enabled = true) {
  const id = String(orderId || "").trim();
  return useQuery({
    queryKey: [...queryKeys.interviewDraft, id || "none", "cv-limits"],
    queryFn: () =>
      apiFetch<CvCollectionLimits>(
        `/service-orders/interview/cv-collection-limits?order_id=${encodeURIComponent(id)}`,
      ),
    enabled: Boolean(id) && enabled,
    staleTime: 10_000,
  });
}

export function useInterviewDraft(options?: { orderId?: string | null }) {
  const orderId = String(options?.orderId || "").trim();

  return useQuery({
    queryKey: [...queryKeys.interviewDraft, orderId || "none"],
    queryFn: async () =>
      apiFetch<InterviewDraftPayload>(
        `/service-orders/interview/draft?order_id=${encodeURIComponent(orderId)}`,
      ),
    enabled: Boolean(orderId),
    staleTime: 5_000,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      const status = String(query.state.data?.order?.status || "").toLowerCase();
      if (["running", "scheduled", "paid"].includes(status)) return 8000;
      return false;
    },
    placeholderData: (previous) => previous,
  });
}

export function useCreateNewInterviewDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<InterviewDraftPayload>("/service-orders/interview/draft/new", {
        method: "POST",
        body: "{}",
      }),
    onSuccess: (data) => {
      const id = String(data?.order?.id || "").trim();
      if (id) {
        qc.setQueryData([...queryKeys.interviewDraft, id], data);
      }
    },
  });
}

export function useInterviewRecipientActivity(
  orderId: string | null | undefined,
  recipientId: string | null | undefined,
  enabled = true,
) {
  const oid = String(orderId || "").trim();
  const rid = String(recipientId || "").trim();
  return useQuery({
    queryKey: queryKeys.interviewRecipientActivity(oid || "none", rid || "none"),
    queryFn: () =>
      apiFetch<{
        recipient_id: string;
        name?: string;
        email?: string;
        phone?: string;
        status?: string;
        activity_status?: string;
        booked_start_at?: string | null;
        booked_end_at?: string | null;
        booking_url?: string | null;
        events?: { at: string; code: string; label: string; detail?: string | null }[];
      }>(`/service-orders/${encodeURIComponent(oid)}/recipients/${encodeURIComponent(rid)}/activity`),
    enabled: enabled && Boolean(oid) && Boolean(rid),
    staleTime: 5_000,
  });
}

export function useSaveInterviewDraft() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<InterviewDraftPayload>("/service-orders/interview/draft", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: (data, vars) => {
      const orderId = String(vars.order_id || data?.order?.id || "");
      if (orderId && data) {
        qc.setQueryData([...queryKeys.interviewDraft, orderId], data);
      }
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
      if (orderId) void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(orderId) });
    },
  });
}

export function usePatchServiceOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, body }: { orderId: string; body: Record<string, unknown> }) =>
      apiFetch<ServiceOrder>(`/service-orders/${encodeURIComponent(orderId)}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: (order) => {
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrders("survey") });
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrders("interview") });
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(order.id) });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
    },
  });
}

export function useStopInterviewCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, reason }: { orderId: string; reason?: string }) =>
      apiFetch<ServiceOrder>(`/service-orders/${encodeURIComponent(orderId)}/stop`, {
        method: "POST",
        body: JSON.stringify({ reason: reason || "Stopped by user" }),
      }),
    onSuccess: (order) => {
      invalidateInterviewOrderQueries(qc, order.id);
    },
  });
}

export function useCreateServiceOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<ServiceOrder>("/service-orders", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
    },
  });
}

export function useUpdateOrganisation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Organisation>("/organisations/me", { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.organisation });
      void qc.invalidateQueries({ queryKey: ["billing", "pricing"] });
      void qc.invalidateQueries({ queryKey: queryKeys.session });
    },
  });
}

export function useSaveServiceApiSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch("/organisations/me/service-api-settings", { method: "PUT", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.serviceApiSettings });
    },
  });
}

export function useCreateSupportTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { category: string; subject: string; message: string; priority?: string }) =>
      apiFetch("/support/tickets", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.supportTickets });
    },
  });
}

export function useReplySupportTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ticketId, message }: { ticketId: string; message: string }) =>
      apiFetch(`/support/tickets/${encodeURIComponent(ticketId)}/reply`, {
        method: "POST",
        body: JSON.stringify({ message }),
      }),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: queryKeys.supportTickets });
      void qc.invalidateQueries({ queryKey: queryKeys.supportTicket(vars.ticketId) });
    },
  });
}

export function useCloseSupportTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ticketId: string) =>
      apiFetch(`/support/tickets/${encodeURIComponent(ticketId)}/close`, { method: "POST" }),
    onSuccess: (_data, ticketId) => {
      void qc.invalidateQueries({ queryKey: queryKeys.supportTickets });
      void qc.invalidateQueries({ queryKey: queryKeys.supportTicket(ticketId) });
    },
  });
}

export function useOrderRecipients(orderId: string | null) {
  return useQuery({
    queryKey: queryKeys.orderRecipients(orderId || ""),
    queryFn: () => apiFetch<{ recipients?: Record<string, unknown>[] }>(`/service-orders/${encodeURIComponent(orderId!)}/recipients`),
    enabled: Boolean(orderId),
  });
}

export function useRecoveryJobs() {
  return useQuery({
    queryKey: queryKeys.recoveryJobs,
    queryFn: () => apiFetch<Record<string, unknown>[]>("/calls/recovery/jobs"),
    enabled: showRecoveryModules,
  });
}

export function useCallLogs() {
  return useQuery({
    queryKey: queryKeys.callLogs,
    queryFn: () => apiFetch<Record<string, unknown>[]>("/calls"),
    enabled: showRecoveryModules,
  });
}

export function useSupportTickets(statusFilter?: string) {
  const qs = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : "";
  return useQuery({
    queryKey: [...queryKeys.supportTickets, statusFilter || "all"],
    queryFn: () => apiFetch<Record<string, unknown>[]>(`/support/tickets${qs}`),
  });
}

export function useSupportTicket(ticketId: string | null) {
  return useQuery({
    queryKey: queryKeys.supportTicket(ticketId || ""),
    queryFn: () => apiFetch<Record<string, unknown>>(`/support/tickets/${encodeURIComponent(ticketId!)}`),
    enabled: Boolean(ticketId),
  });
}

export function useFaq() {
  return useQuery({
    queryKey: queryKeys.faq,
    queryFn: () => apiFetch<Record<string, unknown>[]>("/faq"),
  });
}

export function useOrganisation() {
  return useQuery({
    queryKey: queryKeys.organisation,
    queryFn: () => apiFetch<Organisation>("/organisations/me"),
    staleTime: 1000 * 60 * 5, // Org data fresh for 5 minutes
  });
}

export type MyOrganisationRow = {
  org_id: string;
  name: string;
  role: string;
  is_owner: boolean;
};

export function useMyOrganisations() {
  return useQuery({
    queryKey: queryKeys.myOrganisations,
    queryFn: () =>
      apiFetch<{ organisations: MyOrganisationRow[]; active_org_id: string }>("/auth/my-organisations"),
    staleTime: 1000 * 60,
  });
}

export function useSwitchOrganisation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (orgId: string) =>
      apiFetch<{ access_token: string; org_id: string; user_id: string }>("/auth/switch-organisation", {
        method: "POST",
        body: JSON.stringify({ org_id: orgId }),
      }),
    onSuccess: (data) => {
      writeSessionToStorage(data.access_token, data.org_id, data.user_id);
      qc.clear();
      window.location.href = "/";
    },
  });
}

export type PendingInviteRow = {
  token: string;
  org_id: string;
  organisation_name: string;
  role: string;
  expires_at?: string | null;
};

export function usePendingInvites() {
  return useQuery({
    queryKey: queryKeys.pendingInvites,
    queryFn: () => apiFetch<{ invites: PendingInviteRow[] }>("/auth/pending-invites"),
    staleTime: 1000 * 60,
  });
}

export function useAcceptInviteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      apiFetch<{ access_token: string; org_id: string; user_id: string }>("/auth/accept-invite-session", {
        method: "POST",
        body: JSON.stringify({ token }),
      }),
    onSuccess: (data) => {
      writeSessionToStorage(data.access_token, data.org_id, data.user_id);
      qc.clear();
      window.location.href = "/";
    },
  });
}

export function useSchedulingStatus() {
  return useQuery({
    queryKey: queryKeys.schedulingStatus,
    queryFn: () => apiFetch<Record<string, unknown>>("/service-orders/scheduling/status"),
  });
}

export function useHubSpotStatus() {
  return useQuery({
    queryKey: queryKeys.hubspotStatus,
    queryFn: () => apiFetch<Record<string, unknown>>("/service-orders/hubspot/status"),
  });
}

export type IntegrationCatalogueView = {
  key: string;
  group: "booking" | "crm";
  label: string;
  short_description: string;
  icon_slug: string;
  platform_ready: boolean;
  visible_to_orgs: boolean;
  connected: boolean;
  connected_account: string | null;
  connected_at: string | null;
  last_check_ok: boolean | null;
  last_check_at: string | null;
  blocked_reason: string | null;
  actions: {
    connect_url?: string;
    disconnect_url: string;
    test_url: string;
    connect_token_url?: string;
  };
  extra: Record<string, unknown>;
};

export type IntegrationCatalogue = {
  booking: IntegrationCatalogueView[];
  crm: IntegrationCatalogueView[];
  active_booking_provider: string | null;
};

export function useIntegrationsCatalogue() {
  return useQuery({
    queryKey: queryKeys.integrationsCatalogue,
    queryFn: () => apiFetch<IntegrationCatalogue>("/service-orders/integrations"),
  });
}

export type IntegrationTestResult = {
  ok: boolean;
  checked_at?: string;
  latency_ms?: number;
  summary?: string;
  checks?: Array<{ name: string; status: "ok" | "fail"; message: string }>;
};

export function useTestIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerKey: string) =>
      apiFetch<IntegrationTestResult>(
        `/service-orders/integrations/${encodeURIComponent(providerKey)}/test`,
        { method: "POST" },
      ),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.integrationsCatalogue });
    },
  });
}

export function useDisconnectIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerKey: string) =>
      apiFetch<Record<string, unknown>>(
        `/service-orders/integrations/${encodeURIComponent(providerKey)}/disconnect`,
        { method: "POST" },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.integrationsCatalogue });
      void qc.invalidateQueries({ queryKey: queryKeys.schedulingStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.hubspotStatus });
    },
  });
}

export function useConnectMicrosoftCalendar() {
  return useMutation({
    mutationFn: async (replace = false) => {
      const data = await apiFetch<{ authorize_url?: string }>(
        `/service-orders/scheduling/oauth/microsoft-calendar/start${replace ? "?replace=true" : ""}`,
      );
      if (data?.authorize_url) {
        window.location.href = data.authorize_url;
      }
      return data;
    },
  });
}

export type HubSpotContactRow = {
  id: string;
  hubspot_contact_id: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  synced_at?: string | null;
};

export function useHubSpotContacts(limit = 50, enabled = true) {
  return useQuery({
    queryKey: queryKeys.hubspotContacts(limit),
    queryFn: () =>
      apiFetch<{ ok: boolean; items: HubSpotContactRow[]; count: number }>(
        `/service-orders/hubspot/contacts?limit=${limit}`,
      ),
    enabled,
  });
}

export function useSyncHubSpotContacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: { limit?: number }) =>
      apiFetch<{ ok: boolean; imported: number; updated: number; skipped: number; has_more?: boolean; message?: string }>(
        "/service-orders/hubspot/contacts/sync",
        { method: "POST", body: JSON.stringify(body ?? {}) },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.hubspotStatus });
      void qc.invalidateQueries({ queryKey: ["service-orders", "hubspot", "contacts"] });
    },
  });
}

export function useImportHubSpotToOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { order_id: string; contact_ids: string[] }) =>
      apiFetch<{ ok: boolean; added: number; skipped: number; recipient_count: number }>(
        "/service-orders/hubspot/contacts/import-to-order",
        { method: "POST", body: JSON.stringify(body) },
      ),
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(variables.order_id) });
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrders("survey") });
    },
  });
}

export function usePatchHubSpotSyncSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { field_map?: Record<string, string>; auto_sync_results_back?: boolean }) =>
      apiFetch<Record<string, unknown>>("/service-orders/hubspot/sync-settings", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.hubspotStatus });
    },
  });
}

export type CrmContactRow = {
  id: string;
  external_id?: string;
  name: string;
  email?: string | null;
  phone?: string | null;
  synced_at?: string | null;
};

export function useCrmSyncStatus(enabled = true) {
  return useQuery({
    queryKey: queryKeys.crmSyncStatus,
    queryFn: () => apiFetch<Record<string, unknown>>("/service-orders/crm/sync-status"),
    enabled,
  });
}

export function useCrmContacts(limit = 50, enabled = true) {
  return useQuery({
    queryKey: queryKeys.crmContacts(limit),
    queryFn: () =>
      apiFetch<{ ok: boolean; provider?: string; items: CrmContactRow[]; count: number }>(
        `/service-orders/crm/contacts?limit=${limit}`,
      ),
    enabled,
  });
}

export function useSyncCrmContacts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body?: { limit?: number }) =>
      apiFetch<{ ok: boolean; imported: number; updated: number; skipped: number; has_more?: boolean }>(
        "/service-orders/crm/contacts/sync",
        { method: "POST", body: JSON.stringify(body ?? {}) },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.crmSyncStatus });
      void qc.invalidateQueries({ queryKey: ["service-orders", "crm", "contacts"] });
      void qc.invalidateQueries({ queryKey: queryKeys.integrationsCatalogue });
    },
  });
}

export function useImportCrmToOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { order_id: string; contact_ids: string[] }) =>
      apiFetch<{ ok: boolean; added: number; skipped: number; recipient_count: number }>(
        "/service-orders/crm/contacts/import-to-order",
        { method: "POST", body: JSON.stringify(body) },
      ),
    onSuccess: (_data, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(variables.order_id) });
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrders("survey") });
    },
  });
}

export function usePatchCrmSyncSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { auto_sync_results_back?: boolean; field_map?: Record<string, string> }) =>
      apiFetch<Record<string, unknown>>("/service-orders/crm/sync-settings", {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.crmSyncStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.integrationsCatalogue });
      void qc.invalidateQueries({ queryKey: queryKeys.hubspotStatus });
    },
  });
}

export type HubSpotSurveyResultSyncResponse = {
  ok: boolean;
  skipped?: boolean;
  reason?: string;
  contact_id?: string;
  contact_url?: string;
  properties_updated?: boolean;
  note_created?: boolean;
  properties_warning?: string;
};

export function usePushSurveyResultToHubSpot(orderId: string | null | undefined) {
  return useMutation({
    mutationFn: (recipientId: string) =>
      apiFetch<HubSpotSurveyResultSyncResponse>(
        `/service-orders/${encodeURIComponent(String(orderId))}/recipients/${encodeURIComponent(recipientId)}/hubspot/sync-result`,
        { method: "POST" },
      ),
  });
}

export function useServiceApiSettings() {
  return useQuery({
    queryKey: queryKeys.serviceApiSettings,
    queryFn: () => apiFetch<Record<string, unknown>>("/organisations/me/service-api-settings"),
  });
}

export type InterviewAgent = {
  id: string;
  name: string;
  voice_label?: string;
  voice_type_label?: string;
  is_default_for_org?: boolean;
  is_platform_default?: boolean;
  is_zone_match?: boolean;
  market_zone?: string;
};

export function pickDefaultInterviewAgent(agents: InterviewAgent[]): InterviewAgent | undefined {
  if (!agents.length) return undefined;
  return (
    agents.find((a) => a.is_default_for_org) ||
    agents.find((a) => a.is_zone_match) ||
    agents.find((a) => a.is_platform_default) ||
    agents[0]
  );
}

export function useInterviewAgents() {
  return useQuery({
    queryKey: queryKeys.interviewAgents,
    queryFn: async () => {
      const data = await apiFetch<{ agents?: InterviewAgent[] }>("/service-orders/interview-agents");
      return data.agents || [];
    },
  });
}

export type SurveyAgent = InterviewAgent;

export function pickDefaultSurveyAgent(agents: SurveyAgent[]): SurveyAgent | undefined {
  if (!agents.length) return undefined;
  return (
    agents.find((a) => a.is_default_for_org) ||
    agents.find((a) => a.is_zone_match) ||
    agents.find((a) => a.is_platform_default) ||
    agents[0]
  );
}

export function useSurveyAgents() {
  return useQuery({
    queryKey: queryKeys.surveyAgents,
    queryFn: async () => {
      const data = await apiFetch<{ agents?: SurveyAgent[] }>("/service-orders/survey-agents");
      return data.agents || [];
    },
  });
}

export function useGenerateSurveyScript() {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Record<string, unknown>>("/dashboard/service-scripts/generate", {
        method: "POST",
        body: JSON.stringify({ ...body, service_code: "survey" }),
      }),
  });
}

export function useGenerateInterviewScript() {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Record<string, unknown>>("/dashboard/service-scripts/generate", {
        method: "POST",
        body: JSON.stringify({ ...body, service_code: "interview" }),
      }),
  });
}

export function useInterviewAtsQuote(orderId: string | null) {
  return useMutation({
    mutationFn: (force?: boolean) =>
      apiFetch<Record<string, unknown>>(
        `/service-orders/${encodeURIComponent(orderId!)}/interview/ats/quote${force ? "?force=true" : ""}`,
      ),
  });
}

export function useRunInterviewAts(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { confirm_charge?: boolean; force?: boolean }) =>
      apiFetch<Record<string, unknown>>(`/service-orders/${encodeURIComponent(orderId!)}/interview/ats/run`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
      if (orderId) void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(orderId) });
      void qc.invalidateQueries({ queryKey: queryKeys.billingUsage });
    },
  });
}

export function useApplyInterviewAtsThreshold(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { min_ats_score: number }) =>
      apiFetch<{
        ok?: boolean;
        min_ats_score?: number;
        eligible_count?: number;
        rejected_count?: number;
        restored_count?: number;
        total_scored?: number;
      }>(`/service-orders/${encodeURIComponent(orderId!)}/interview/ats/apply-threshold`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
      if (orderId) void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(orderId) });
    },
  });
}

export function usePatchInterviewRecipient(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { recipientId: string; phone?: string; email?: string; name?: string }) =>
      apiFetch<Record<string, unknown>>(
        `/service-orders/${encodeURIComponent(orderId!)}/recipients/${encodeURIComponent(args.recipientId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            ...(args.phone !== undefined ? { phone: args.phone } : {}),
            ...(args.email !== undefined ? { email: args.email } : {}),
            ...(args.name !== undefined ? { name: args.name } : {}),
          }),
        },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
      if (orderId) void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(orderId) });
    },
  });
}

/** PATCH recipient on any service order (survey, interview, etc.). */
export function usePatchOrderRecipient(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { recipientId: string; phone?: string; email?: string; name?: string }) =>
      apiFetch<Record<string, unknown>>(
        `/service-orders/${encodeURIComponent(orderId!)}/recipients/${encodeURIComponent(args.recipientId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            ...(args.phone !== undefined ? { phone: args.phone } : {}),
            ...(args.email !== undefined ? { email: args.email } : {}),
            ...(args.name !== undefined ? { name: args.name } : {}),
          }),
        },
      ),
    onSuccess: () => {
      if (orderId) {
        void qc.invalidateQueries({ queryKey: queryKeys.orderRecipients(orderId) });
        void qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(orderId) });
      }
    },
  });
}

export function useLaunchInterviewCampaign(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ ok?: boolean; message?: string; invites?: { whatsapp_sent?: number; email_sent?: number; errors?: string[] } }>(
        `/service-orders/${encodeURIComponent(orderId!)}/interview/launch`,
        {
          method: "POST",
          body: JSON.stringify({
            channels: ["email", "whatsapp"],
            force_resend: true,
            force_email: true,
          }),
        },
      ),
    onSuccess: () => {
      invalidateInterviewOrderQueries(qc, orderId);
    },
  });
}

export function useSendInterviewBookingInvites(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (opts?: { force?: boolean; recipient_ids?: string[]; channels?: string[] }) => {
      const force = typeof opts === "boolean" ? opts : Boolean(opts?.force);
      const recipient_ids = typeof opts === "object" && opts ? opts.recipient_ids : undefined;
      const channels = typeof opts === "object" && opts ? opts.channels : undefined;
      return apiFetch<{ whatsapp_sent?: number; email_sent?: number; skipped_locked?: number; errors?: string[] }>(
        `/service-orders/${encodeURIComponent(orderId!)}/interview-booking/send-invites`,
        {
          method: "POST",
          body: JSON.stringify({
            force_resend: force,
            force_email: force,
            channels: channels?.length ? channels : ["email", "whatsapp"],
            ...(recipient_ids?.length ? { recipient_ids } : {}),
          }),
        },
      );
    },
    onSuccess: () => {
      invalidateInterviewOrderQueries(qc, orderId);
    },
  });
}

export type WhatsappTemplateRow = {
  id?: string;
  template_id?: string;
  name?: string;
  language?: string;
  category?: string;
  status?: string;
  body_preview?: string | null;
  purpose?: string;
  purpose_label?: string;
};

export type WhatsappTemplatesResponse = {
  templates: WhatsappTemplateRow[];
  grouped: Record<string, WhatsappTemplateRow[]>;
  counts: Record<string, number>;
};

export function useWhatsappTemplates() {
  return useQuery({
    queryKey: ["service-orders", "whatsapp-templates"],
    queryFn: () => apiFetch<WhatsappTemplatesResponse>("/service-orders/whatsapp-templates?approved_only=true"),
  });
}

export function useWaSurveyIndustries() {
  return useQuery({
    queryKey: ["dashboard", "wa-survey-industries"],
    queryFn: () => apiFetch<{ ok?: boolean; industries?: Array<Record<string, unknown>> }>("/dashboard/service-scripts/wa-survey/industries"),
  });
}

export function useWaSurveyTypes(industryId?: string | null) {
  const qs = industryId ? `?industry_id=${encodeURIComponent(industryId)}` : "";
  return useQuery({
    queryKey: ["dashboard", "wa-survey-types", industryId || ""],
    queryFn: () =>
      apiFetch<{ ok?: boolean; types?: Array<Record<string, unknown>> }>(`/dashboard/service-scripts/wa-survey/types${qs}`),
    enabled: Boolean(industryId),
  });
}

export function useWaSurveySystemTemplates() {
  return useQuery({
    queryKey: ["dashboard", "wa-survey-system-templates"],
    queryFn: () =>
      apiFetch<{ ok?: boolean; templates?: Record<string, Array<Record<string, unknown>>> }>(
        "/dashboard/service-scripts/wa-survey/system-templates",
      ),
  });
}

export function useWaSurveyStepBank(surveyTypeId: string | null, privacyMode: "off" | "on") {
  const variant = privacyMode === "on" ? "anonymous" : "standard";
  return useQuery({
    queryKey: ["dashboard", "wa-survey-step-bank", surveyTypeId, privacyMode],
    enabled: Boolean(surveyTypeId),
    queryFn: () =>
      apiFetch<Record<string, unknown>>(
        `/dashboard/service-scripts/wa-survey/types/${encodeURIComponent(surveyTypeId!)}/step-bank?variant=${encodeURIComponent(variant)}&privacy_mode=${encodeURIComponent(privacyMode)}`,
      ),
  });
}

export function useWaSurveyLibraryTemplates(typeIds: string[], privacyMode: "off" | "on", enabled = true) {
  return useQueries({
    queries: typeIds.map((surveyTypeId) => ({
      queryKey: ["dashboard", "wa-survey-library-templates", surveyTypeId, privacyMode],
      enabled: enabled && Boolean(surveyTypeId),
      queryFn: () =>
        apiFetch<{ ok?: boolean; templates?: Array<Record<string, unknown>> }>(
          `/dashboard/service-scripts/wa-survey/types/${encodeURIComponent(surveyTypeId)}/library-templates?privacy_mode=${encodeURIComponent(privacyMode)}`,
        ),
    })),
  });
}

export function useGenerateWaSurvey() {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Record<string, unknown>>("/dashboard/service-scripts/wa-survey/generate", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useSendWaSurveyTest() {
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<Record<string, unknown>>("/dashboard/service-scripts/wa-survey/send-test", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useSendInterviewScheduling(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { recipient_ids: string[]; channels?: string[] }) =>
      apiFetch<Record<string, unknown>>(
        `/service-orders/${encodeURIComponent(orderId!)}/interview-scheduling/send`,
        { method: "POST", body: JSON.stringify(body) },
      ),
    onSuccess: () => {
      if (orderId) void qc.invalidateQueries({ queryKey: queryKeys.interviewResults(orderId) });
    },
  });
}

export function useSaveInterviewShortlist(orderId: string | null) {
  return useMutation({
    mutationFn: (recipient_ids: string[]) =>
      apiFetch(`/service-orders/${encodeURIComponent(orderId!)}/interview-shortlist`, {
        method: "PATCH",
        body: JSON.stringify({ recipient_ids }),
      }),
  });
}

export function useOrderQuote(orderId: string | null) {
  return useMutation({
    mutationFn: () =>
      apiFetch<ServiceOrder>(`/service-orders/${encodeURIComponent(orderId!)}/quote`, { method: "POST", body: "{}" }),
  });
}

export type SurveyLaunchEligibility = {
  order_id?: string;
  campaign_name?: string;
  survey_channel?: string;
  recipient_count?: number;
  estimated_whatsapp_usage?: number;
  can_launch?: boolean;
  payment_required?: boolean;
  mode?: string;
  launch_action?: "launch" | "pay_and_launch" | "topup_required" | "blocked";
  wallet_balance_minor?: number;
  wallet_balance_display?: string | null;
  wallet_charge_minor?: number;
  wallet_shortfall_minor?: number;
  dd_charge_minor?: number;
  summary?: string;
  block_reason?: string | null;
  block_reason_code?: string | null;
  allowance_exhausted?: boolean;
  covered_by_allowance?: number;
  covered_recipients?: number;
  extra_recipients?: number;
  covered_by_promo_credits?: number;
  shortfall_units?: number;
  wa_survey_extra_pence?: number;
  wa_survey_extra_display?: string | null;
  extra_cost_pence?: number;
  extra_cost_display?: string | null;
  amount_due_pence?: number;
  amount_due_display?: string | null;
  estimated_send_cost_pence?: number;
  estimated_send_cost_display?: string | null;
  minimum_charge_pence?: number;
  minimum_charge_display?: string | null;
  setup_fee_pence?: number;
  setup_fee_display?: string | null;
  package_id?: string | null;
  pricing_lines?: Array<Record<string, unknown>>;
  pricing_source?: string | null;
  quote_total_display?: string | null;
  remaining_whatsapp_after_launch?: number;
  remaining_promo_credits_after_launch?: number;
  package_label?: string | null;
  billing?: {
    has_active_subscription?: boolean;
    plan_name?: string | null;
    whatsapp_remaining?: number;
    whatsapp_included?: number;
    survey_credits?: number;
    has_whatsapp_allowance?: boolean;
    is_payg_plan?: boolean;
    whatsapp_used?: number;
    shared_package_pool?: boolean;
    package_included?: number;
    package_used?: number;
    package_remaining?: number;
    calls_remaining?: number;
    channel_whatsapp_used?: number;
    channel_calls_used?: number;
    package_remaining_display?: string | null;
    estimated_wa_surveys?: number;
    estimated_ai_minutes?: number;
    estimate_source?: string | null;
    estimate_label?: string | null;
  };
};

const launchEligibilityInFlight = new Map<string, Promise<SurveyLaunchEligibility>>();

export async function fetchSurveyLaunchEligibility(
  orderId: string,
  signal?: AbortSignal,
  options?: { force?: boolean },
) {
  if (options?.force) launchEligibilityInFlight.delete(orderId);

  const existing = launchEligibilityInFlight.get(orderId);
  if (existing) {
    logBillingCheck("start", { orderId, deduped: true, timeoutMs: BILLING_CHECK_TIMEOUT_MS });
    return existing;
  }

  const refreshParam = options?.force ? "?refresh=1" : "";
  const promise = (async () => {
    logBillingCheck("start", { orderId, timeoutMs: BILLING_CHECK_TIMEOUT_MS, force: Boolean(options?.force) });
    try {
      const data = await apiFetch<SurveyLaunchEligibility>(
        `/service-orders/${encodeURIComponent(orderId)}/launch-eligibility${refreshParam}`,
        { signal },
      );
      logBillingCheck("done", { orderId, ...launchEligibilityLogPayload(data) });
      if (data.can_launch) {
        logBillingCheck("allowed", { orderId, mode: data.mode, launch_action: data.launch_action });
      } else if (
        data.block_reason_code === "whatsapp_usage_limit" ||
        data.block_reason ||
        data.launch_action === "blocked"
      ) {
        logBillingCheck(data.launch_action === "pay_and_launch" ? "pay_required" : "blocked", {
          orderId,
          mode: data.mode,
          code: data.block_reason_code,
          reason: data.block_reason || data.summary,
        });
      }
      return data;
    } catch (error) {
      if (signal?.aborted) {
        logBillingCheck("timeout", { orderId, timeoutMs: BILLING_CHECK_TIMEOUT_MS });
        throw new Error("Billing check timed out. Try again.");
      }
      logBillingCheck("error", {
        orderId,
        message: error instanceof Error ? error.message : String(error),
      });
      throw error;
    } finally {
      launchEligibilityInFlight.delete(orderId);
    }
  })();

  launchEligibilityInFlight.set(orderId, promise);
  return promise;
}

export function useSurveyLaunchEligibility(orderId: string | null, cacheKey = "") {
  return useQuery({
    queryKey: queryKeys.surveyLaunchEligibility(orderId || "", cacheKey),
    queryFn: () => fetchSurveyLaunchEligibility(orderId!),
    enabled: false,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 30 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    retry: false,
  });
}

export function useLaunchSurveyCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      orderId,
      run_mode = "now",
    }: {
      orderId: string;
      run_mode?: "now" | "schedule";
    }) =>
      apiFetch<{ ok?: boolean; message?: string; status?: string; order_id?: string; order?: { id?: string } }>(
        `/service-orders/${encodeURIComponent(orderId)}/survey/launch`,
        {
          method: "POST",
          body: JSON.stringify({ run_mode }),
        },
      ),
    onSuccess: (_data, variables) => {
      const launchedId = variables.orderId;
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(launchedId) });
      void qc.invalidateQueries({ queryKey: queryKeys.surveyLaunchEligibility(launchedId) });
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrders("survey") });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
      void qc.invalidateQueries({ queryKey: queryKeys.credits });
      void qc.invalidateQueries({ queryKey: queryKeys.billingUsage });
    },
  });
}

export function usePaySurveyPromoCredits(orderId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch(`/service-orders/${encodeURIComponent(orderId!)}/pay-promo-credits`, {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => {
      if (orderId) {
        void qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(orderId) });
        void qc.invalidateQueries({ queryKey: queryKeys.surveyLaunchEligibility(orderId) });
        void qc.invalidateQueries({ queryKey: queryKeys.credits });
      }
    },
  });
}

export type TeamMember = {
  user_id: string;
  email: string;
  is_active: boolean;
  role: string;
  linked_at?: string;
};

export type TeamInvite = {
  id: string;
  email: string;
  role: string;
  created_at?: string;
  expires_at?: string;
  is_expired?: boolean;
  signup_url: string;
};

export type OptOutEntry = {
  id: string;
  phone: string;
  phone_e164: string;
  name?: string | null;
  contact_name?: string | null;
  reason?: string | null;
  created_at?: string;
};

export type AuditEntry = {
  id: string;
  action: string;
  detail?: string | null;
  actor_email?: string | null;
  event_type?: string | null;
  created_at?: string;
};

export type DeletionStatus = {
  deletion_status: string;
  deletion_label: string;
  deletion_requested_at?: string | null;
  deletion_request_id?: string | null;
  can_cancel: boolean;
  can_request: boolean;
  sla_message: string;
  pending_message: string;
  message?: string;
};

export function useTeamMembers() {
  return useQuery({
    queryKey: queryKeys.teamMembers,
    queryFn: () => apiFetch<TeamMember[]>("/organisations/me/team/members"),
  });
}

export function useTeamInvites() {
  return useQuery({
    queryKey: queryKeys.teamInvites,
    queryFn: () => apiFetch<TeamInvite[]>("/organisations/me/team/invites"),
  });
}

export function useCreateTeamInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; role: string; send_email?: boolean }) =>
      apiFetch<TeamInvite & { invite_id?: string; email_sent?: boolean }>("/organisations/me/team/invites", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.teamInvites });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
    },
  });
}

export function useRevokeTeamInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) =>
      apiFetch(`/organisations/me/team/invites/${encodeURIComponent(inviteId)}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.teamInvites });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
    },
  });
}

export function useRemoveTeamMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      apiFetch(`/organisations/me/team/members/${encodeURIComponent(userId)}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.teamMembers });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
    },
  });
}

export function useOptOuts() {
  return useQuery({
    queryKey: queryKeys.optOuts,
    queryFn: () => apiFetch<OptOutEntry[]>("/organisations/me/opt-outs"),
  });
}

export function useAddOptOut() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { phone: string; name?: string; reason?: string }) =>
      apiFetch<OptOutEntry>("/organisations/me/opt-outs", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.optOuts });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
    },
  });
}

export function useRemoveOptOut() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/organisations/me/opt-outs/${encodeURIComponent(id)}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.optOuts });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
    },
  });
}

export function useAuditLog() {
  return useQuery({
    queryKey: queryKeys.auditLog,
    queryFn: () => apiFetch<AuditEntry[]>("/organisations/me/audit-log"),
  });
}

export function useDeletionStatus() {
  return useQuery({
    queryKey: queryKeys.deletionStatus,
    queryFn: () => apiFetch<DeletionStatus>("/organisations/me/deletion-status"),
    retry: false,
  });
}

export function useRequestAccountDeletion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { confirm: string; reason?: string }) =>
      apiFetch<DeletionStatus & { ok: boolean; request_id?: string }>("/organisations/me/delete-account", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.deletionStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
      void qc.invalidateQueries({ queryKey: queryKeys.session });
    },
  });
}

export function useCancelAccountDeletion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<DeletionStatus & { ok: boolean }>("/organisations/me/cancel-delete-account", {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.deletionStatus });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
      void qc.invalidateQueries({ queryKey: queryKeys.session });
    },
  });
}

export function useTestServiceApiSettings() {
  return useMutation({
    mutationFn: () => apiFetch<{ ok: boolean; message?: string }>("/organisations/me/service-api-settings/test", { method: "POST", body: "{}" }),
  });
}

export function useUploadOrgLogo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => apiUploadFiles("/organisations/me/logo", [file], "file"),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.organisation });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
    },
  });
}

export function useDeleteOrgLogo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch("/organisations/me/logo", { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.organisation });
      void qc.invalidateQueries({ queryKey: queryKeys.auditLog });
    },
  });
}

export function useFeedbackLocations() {
  return useQuery({
    queryKey: queryKeys.feedbackLocations,
    queryFn: async () => {
      const data = await apiFetch<{ ok?: boolean; items?: FeedbackLocation[] }>("/customer-feedback/locations");
      return data.items || [];
    },
  });
}

export function useFeedbackIndustries() {
  return useQuery({
    queryKey: queryKeys.feedbackIndustries,
    queryFn: async () => {
      const data = await apiFetch<{ ok?: boolean; items?: FeedbackIndustry[] }>("/customer-feedback/catalog/industries");
      return data.items || [];
    },
  });
}

export function useFeedbackSurveyTypes(industryId?: string | null) {
  const qs = industryId ? `?industry_id=${encodeURIComponent(industryId)}` : "";
  return useQuery({
    queryKey: queryKeys.feedbackSurveyTypes(industryId || ""),
    queryFn: async () => {
      const data = await apiFetch<{ ok?: boolean; items?: FeedbackSurveyType[] }>(
        `/customer-feedback/catalog/survey-types${qs}`,
      );
      return data.items || [];
    },
    enabled: Boolean(industryId),
  });
}

export function useFeedbackResults(filters: { location_id?: string; survey_type_id?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.location_id) params.set("location_id", filters.location_id);
  if (filters.survey_type_id) params.set("survey_type_id", filters.survey_type_id);
  const qs = params.toString();
  const filterKey = Object.fromEntries(params.entries());
  return useQuery({
    queryKey: queryKeys.feedbackResults(filterKey),
    queryFn: () =>
      apiFetch<FeedbackResultsPayload>(`/customer-feedback/results${qs ? `?${qs}` : ""}`),
  });
}

export function useFeedbackResultsInsights(filters: { location_id?: string; survey_type_id?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.location_id) params.set("location_id", filters.location_id);
  if (filters.survey_type_id) params.set("survey_type_id", filters.survey_type_id);
  const qs = params.toString();
  const filterKey = Object.fromEntries(params.entries());
  return useQuery({
    queryKey: queryKeys.feedbackResultsInsights(filterKey),
    queryFn: () =>
      apiFetch<FeedbackResultsInsightsPayload>(`/customer-feedback/results/insights${qs ? `?${qs}` : ""}`),
    staleTime: 1000 * 60 * 5,
  });
}

export function useFeedbackResultsCompare(locationIds: string[]) {
  const key = [...locationIds].sort().join(",");
  return useQuery({
    queryKey: queryKeys.feedbackResultsCompare(key),
    queryFn: () =>
      apiFetch<FeedbackComparePayload>(
        `/customer-feedback/results/compare?location_ids=${encodeURIComponent(key)}`,
      ),
    enabled: locationIds.length > 0,
    placeholderData: keepPreviousData,
    retry: 1,
  });
}

export function useFeedbackPackages() {
  return useQuery({
    queryKey: queryKeys.feedbackPackages,
    queryFn: async () => {
      const data = await apiFetch<{ ok?: boolean; items?: FeedbackPackage[] }>("/customer-feedback/packages");
      return data.items || [];
    },
  });
}

export function useFeedbackSubscription() {
  return useQuery({
    queryKey: queryKeys.feedbackSubscription,
    queryFn: async () => {
      const data = await apiFetch<{ ok?: boolean } & FeedbackSubscription>("/customer-feedback/subscription");
      return data;
    },
    refetchOnMount: "always",
  });
}

export function useFeedbackSubscriptionCancellation() {
  return useQuery({
    queryKey: queryKeys.feedbackSubscriptionCancellation,
    queryFn: () => apiFetch("/customer-feedback/subscription/cancellation"),
    refetchOnMount: "always",
  });
}

export function useSetBillingOverage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (allow_overage: boolean) =>
      apiFetch<{ ok?: boolean; allow_overage?: boolean }>("/billing/overage", {
        method: "PATCH",
        body: JSON.stringify({ allow_overage }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.billingAccess });
      void qc.invalidateQueries({ queryKey: queryKeys.billingUsage });
    },
  });
}

export async function changeFeedbackPlan(planId: string) {
  return apiFetch<{
    ok?: boolean;
    direction?: string;
    subscription?: FeedbackSubscription;
    pending_plan_id?: string | null;
  }>("/customer-feedback/subscription/change-plan", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId }),
  });
}

export async function changeCorePlan(planId: string) {
  return apiFetch<{
    ok?: boolean;
    direction?: string;
    awaiting_admin_approval?: boolean;
    subscription?: Record<string, unknown>;
    plan?: { id?: string; name?: string; code?: string };
    pending_plan?: { id?: string; name?: string; code?: string } | null;
    billing?: { pro_rata_minor?: number; invoice_id?: string | null };
  }>("/billing/subscription/change-plan", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId }),
  });
}

export function usePreviewFeedbackLocation() {
  return useMutation({
    mutationFn: (body: CreateFeedbackLocationInput) =>
      apiFetch<{ ok?: boolean; item?: FeedbackLocationPreview }>("/customer-feedback/locations/preview", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}

export function useCreateFeedbackLocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateFeedbackLocationInput) =>
      apiFetch<{ ok?: boolean; item?: FeedbackLocation }>("/customer-feedback/locations", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.feedbackLocations });
      void qc.invalidateQueries({ queryKey: queryKeys.feedbackResults({}) });
    },
  });
}

export function useUpdateFeedbackLocation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ locationId, body }: { locationId: string; body: UpdateFeedbackLocationInput }) =>
      apiFetch<{ ok?: boolean; item?: FeedbackLocation }>(`/customer-feedback/locations/${locationId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.feedbackLocations });
      void qc.invalidateQueries({ queryKey: queryKeys.feedbackResults({}) });
    },
  });
}

export function useAssistantChat() {
  return useMutation({
    mutationFn: (body: {
      message: string;
      history?: Array<{ role: string; text: string }>;
      context?: AssistantChatContext;
    }) =>
      apiFetch<AssistantChatResponse>("/assistant/chat", {
        method: "POST",
        body: JSON.stringify({
          message: body.message,
          history: body.history || [],
          context: body.context || {},
        }),
      }),
  });
}

export function useAssistantConfirm() {
  return useMutation({
    mutationFn: (body: { action_id: string; confirmed?: boolean }) =>
      apiFetch<AssistantChatResponse>("/assistant/confirm", {
        method: "POST",
        body: JSON.stringify({ action_id: body.action_id, confirmed: body.confirmed ?? true }),
      }),
  });
}

export function useAssistantReportSupport() {
  return useMutation({
    mutationFn: (body: { support_report_token: string }) =>
      apiFetch<import("@/lib/types/assistant").AssistantReportSupportResponse>("/assistant/report-support", {
        method: "POST",
        body: JSON.stringify(body),
      }),
  });
}
