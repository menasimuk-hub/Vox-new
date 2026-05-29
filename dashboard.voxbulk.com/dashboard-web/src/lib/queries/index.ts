import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
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
export const queryKeys = {
  session: ["session"] as const,
  homeSummary: ["dashboard", "home-summary"] as const,
  serviceOrders: (code: string) => ["service-orders", code] as const,
  serviceOrder: (id: string) => ["service-orders", "detail", id] as const,
  credits: ["service-orders", "credits"] as const,
  billingSubscription: ["billing", "subscription"] as const,
  billingPlans: ["billing", "plans"] as const,
  billingPricing: (market: string, orgCountry = "") => ["billing", "pricing", market, orgCountry] as const,
  billingWallet: ["billing", "wallet"] as const,
  billingUsage: ["billing", "usage-summary"] as const,
  billingInvoices: ["billing", "invoices"] as const,
  organisation: ["organisations", "me"] as const,
  interviewReports: (period: string) => ["service-orders", "interview-reports", period] as const,
  interviewResults: (orderId: string) => ["service-orders", orderId, "interview-results"] as const,
  surveyResults: (orderId: string) => ["service-orders", orderId, "survey-results"] as const,
  surveyPackages: ["service-orders", "survey-packages"] as const,
  serviceCatalog: ["service-orders", "catalog"] as const,
  interviewDraft: ["service-orders", "interview-draft"] as const,
  interviewAgents: ["service-orders", "interview-agents"] as const,
  interviewBilling: ["service-orders", "interview-billing"] as const,
  orderRecipients: (orderId: string) => ["service-orders", orderId, "recipients"] as const,
  recoveryJobs: ["calls", "recovery", "jobs"] as const,
  callLogs: ["calls"] as const,
  supportTickets: ["support", "tickets"] as const,
  supportTicket: (id: string) => ["support", "tickets", id] as const,
  faq: ["faq"] as const,
  schedulingStatus: ["service-orders", "scheduling", "status"] as const,
  serviceApiSettings: ["organisations", "service-api-settings"] as const,
};

export function useHomeSummary() {
  return useQuery({
    queryKey: queryKeys.homeSummary,
    queryFn: () => apiFetch<HomeSummary>("/dashboard/home-summary"),
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

export function useWalletTopup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { amount_pence?: number; tier_id?: string }) =>
      apiFetch("/billing/wallet/topup", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.billingWallet });
    },
  });
}

export function useBillingUsage() {
  return useQuery({
    queryKey: queryKeys.billingUsage,
    queryFn: () => apiFetch<UsageSummary>("/billing/usage-summary"),
  });
}

export function useBillingInvoices() {
  return useQuery({
    queryKey: queryKeys.billingInvoices,
    queryFn: () => apiFetch<Invoice[]>("/billing/invoices"),
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
    mutationFn: (orderId: string) =>
      apiFetch(`/service-orders/${encodeURIComponent(orderId)}`, { method: "DELETE" }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
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

export function useInterviewResults(orderId: string | null) {
  return useQuery({
    queryKey: queryKeys.interviewResults(orderId || ""),
    queryFn: () => apiFetch<Record<string, unknown>>(`/service-orders/${encodeURIComponent(orderId!)}/interview-results`),
    enabled: Boolean(orderId),
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
};

export function useInterviewDraft(options?: { forceNew?: boolean }) {
  const forceNew = Boolean(options?.forceNew);
  return useQuery({
    queryKey: [...queryKeys.interviewDraft, forceNew ? "new" : "latest"],
    queryFn: async () => {
      if (forceNew) {
        return apiFetch<InterviewDraftPayload>("/service-orders/interview/draft/new", {
          method: "POST",
          body: "{}",
        });
      }
      const draft = await apiFetch<InterviewDraftPayload>("/service-orders/interview/draft");
      if (draft?.order) return draft;
      return apiFetch<InterviewDraftPayload>("/service-orders/interview/draft/new", {
        method: "POST",
        body: "{}",
      });
    },
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
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
      void qc.invalidateQueries({ queryKey: ["service-orders"] });
    },
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
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: queryKeys.interviewDraft });
      const orderId = String(vars.order_id || "");
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
      void qc.invalidateQueries({ queryKey: queryKeys.serviceOrder(order.id) });
      void qc.invalidateQueries({ queryKey: queryKeys.homeSummary });
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
  });
}

export function useSchedulingStatus() {
  return useQuery({
    queryKey: queryKeys.schedulingStatus,
    queryFn: () => apiFetch<Record<string, unknown>>("/service-orders/scheduling/status"),
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
};

export function useInterviewAgents() {
  return useQuery({
    queryKey: queryKeys.interviewAgents,
    queryFn: async () => {
      const data = await apiFetch<{ agents?: InterviewAgent[] }>("/service-orders/interview-agents");
      return data.agents || [];
    },
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
