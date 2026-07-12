import { apiFetch } from "@/lib/api";

export const GC_FLOW_KEY = "voxbulk_gc_redirect_flow_id";
export const GC_FEEDBACK_FLOW_KEY = "voxbulk_gc_feedback_redirect_flow_id";
export const GC_MANDATE_FLOW_KEY = "voxbulk_gc_mandate_redirect_flow_id";
export const GC_ORDER_FLOW_KEY = "voxbulk_gc_order_redirect_flow_id";
export const GC_ORDER_ID_KEY = "voxbulk_gc_order_id";

export type BillingReturnParams = {
  billing: string;
  orderBilling: string;
  redirectFlowId: string;
  orderId: string;
};

export function readBillingReturnParams(): BillingReturnParams {
  try {
    const params = new URLSearchParams(window.location.search);
    return {
      billing: (params.get("billing") || "").trim().toLowerCase(),
      orderBilling: (params.get("order_billing") || "").trim().toLowerCase(),
      redirectFlowId: (params.get("redirect_flow_id") || "").trim(),
      orderId: (params.get("order_id") || "").trim(),
    };
  } catch {
    return { billing: "", orderBilling: "", redirectFlowId: "", orderId: "" };
  }
}

export function resolveRedirectFlowId(
  params: BillingReturnParams,
  kind: "subscription" | "order" | "mandate",
) {
  const key =
    kind === "order" ? GC_ORDER_FLOW_KEY : kind === "mandate" ? GC_MANDATE_FLOW_KEY : GC_FLOW_KEY;
  try {
    const stored = (sessionStorage.getItem(key) || "").trim();
    if (stored) return stored;
  } catch {
    /* ignore */
  }
  if (params.redirectFlowId && kind === "subscription") {
    try {
      const feedbackStored = (sessionStorage.getItem(GC_FEEDBACK_FLOW_KEY) || "").trim();
      if (feedbackStored && feedbackStored === params.redirectFlowId) return "";
    } catch {
      /* ignore */
    }
  }
  if (params.redirectFlowId && kind !== "subscription") return params.redirectFlowId;
  return "";
}

export type SubscriptionCheckoutKind = "feedback" | "core" | null;

export function resolveSubscriptionCheckoutKind(params: BillingReturnParams): SubscriptionCheckoutKind {
  const urlId = (params.redirectFlowId || "").trim();
  try {
    const feedbackStored = (sessionStorage.getItem(GC_FEEDBACK_FLOW_KEY) || "").trim();
    if (feedbackStored && (!urlId || feedbackStored === urlId)) return "feedback";
    const coreStored = (sessionStorage.getItem(GC_FLOW_KEY) || "").trim();
    if (coreStored && (!urlId || coreStored === urlId)) return "core";
  } catch {
    /* ignore */
  }
  return null;
}

export function resolveFeedbackRedirectFlowId(params: BillingReturnParams) {
  if (resolveSubscriptionCheckoutKind(params) !== "feedback") return "";
  try {
    const stored = (sessionStorage.getItem(GC_FEEDBACK_FLOW_KEY) || "").trim();
    if (stored) return stored;
  } catch {
    /* ignore */
  }
  return (params.redirectFlowId || "").trim();
}

export function resolveCoreRedirectFlowId(params: BillingReturnParams) {
  if (resolveSubscriptionCheckoutKind(params) !== "core") return "";
  return resolveRedirectFlowId(params, "subscription") || (params.redirectFlowId || "").trim();
}

export function clearBillingReturnState(kind?: "subscription" | "order" | "mandate" | "all") {
  try {
    if (!kind || kind === "all" || kind === "subscription") sessionStorage.removeItem(GC_FLOW_KEY);
    if (!kind || kind === "all" || kind === "mandate") sessionStorage.removeItem(GC_MANDATE_FLOW_KEY);
    if (!kind || kind === "all" || kind === "order") sessionStorage.removeItem(GC_ORDER_FLOW_KEY);
    if (!kind || kind === "all" || kind === "order") sessionStorage.removeItem(GC_ORDER_ID_KEY);
  } catch {
    /* ignore */
  }
}

export function clearBillingQuery() {
  try {
    const url = new URL(window.location.href);
    url.searchParams.delete("billing");
    url.searchParams.delete("order_billing");
    url.searchParams.delete("redirect_flow_id");
    // Keep order_id — it identifies the interview/survey draft, not only billing return.
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  } catch {
    /* ignore */
  }
}

export async function startGoCardlessSubscription(planId: string, billingInterval: "monthly" | "yearly" = "monthly") {
  const result = await apiFetch<{
    redirect_flow_id?: string;
    authorization_url?: string;
    environment?: string;
  }>("/billing/subscription/gocardless/start", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId, billing_interval: billingInterval }),
  });
  const redirectFlowId = result?.redirect_flow_id;
  const authorizationUrl = result?.authorization_url;
  if (!redirectFlowId || !authorizationUrl) {
    throw new Error("GoCardless did not return a checkout URL");
  }
  sessionStorage.setItem(GC_FLOW_KEY, redirectFlowId);
  window.location.assign(authorizationUrl);
}

export async function completeGoCardlessSubscription(redirectFlowId: string) {
  return apiFetch("/billing/subscription/gocardless/complete", {
    method: "POST",
    body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
  });
}

export async function startFeedbackGoCardlessSubscription(
  planId: string,
  billingInterval: "monthly" | "yearly" = "monthly",
) {
  const result = await apiFetch<{
    redirect_flow_id?: string;
    authorization_url?: string;
  }>("/customer-feedback/subscription/gocardless/start", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId, billing_interval: billingInterval }),
  });
  const redirectFlowId = result?.redirect_flow_id;
  const authorizationUrl = result?.authorization_url;
  if (!redirectFlowId || !authorizationUrl) {
    throw new Error("GoCardless did not return a checkout URL");
  }
  sessionStorage.setItem(GC_FEEDBACK_FLOW_KEY, redirectFlowId);
  window.location.assign(authorizationUrl);
}

export async function completeFeedbackGoCardlessSubscription(redirectFlowId: string) {
  return apiFetch("/customer-feedback/subscription/gocardless/complete", {
    method: "POST",
    body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
  });
}

export function clearFeedbackBillingReturnState() {
  try {
    sessionStorage.removeItem(GC_FEEDBACK_FLOW_KEY);
  } catch {
    /* ignore */
  }
}

export async function startGoCardlessMandateUpdate() {
  const result = await apiFetch<{
    redirect_flow_id?: string;
    authorization_url?: string;
    environment?: string;
  }>("/billing/subscription/gocardless/mandate/start", {
    method: "POST",
    body: "{}",
  });
  const redirectFlowId = result?.redirect_flow_id;
  const authorizationUrl = result?.authorization_url;
  if (!redirectFlowId || !authorizationUrl) {
    throw new Error("GoCardless did not return a checkout URL");
  }
  sessionStorage.setItem(GC_MANDATE_FLOW_KEY, redirectFlowId);
  window.location.assign(authorizationUrl);
}

export async function completeGoCardlessMandateUpdate(redirectFlowId: string) {
  return apiFetch<{ ok?: boolean; status?: string; mandate_id?: string }>(
    "/billing/subscription/gocardless/mandate/complete",
    {
      method: "POST",
      body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
    },
  );
}

export async function startGoCardlessOrderPayment(orderId: string) {
  const result = await apiFetch<{
    redirect_flow_id?: string;
    authorization_url?: string;
  }>(`/service-orders/${encodeURIComponent(orderId)}/gocardless/start`, {
    method: "POST",
    body: "{}",
  });
  const redirectFlowId = result?.redirect_flow_id;
  const authorizationUrl = result?.authorization_url;
  if (!redirectFlowId || !authorizationUrl) {
    throw new Error("GoCardless did not return a checkout URL");
  }
  sessionStorage.setItem(GC_ORDER_FLOW_KEY, redirectFlowId);
  sessionStorage.setItem(GC_ORDER_ID_KEY, orderId);
  window.location.assign(authorizationUrl);
}

export async function completeGoCardlessOrderPayment(redirectFlowId: string) {
  return apiFetch<{ order?: { id?: string; payment_status?: string; service_code?: string; status?: string } }>(
    "/service-orders/gocardless/complete",
    {
      method: "POST",
      body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
    },
  );
}

export async function startPaidInterviewOrder(orderId: string) {
  return apiFetch<{
    ok?: boolean;
    already_launched?: boolean;
    message?: string;
    status?: string;
    invites?: { whatsapp_sent?: number; email_sent?: number; errors?: string[] };
    email_delivery?: { can_send_email?: boolean; smtp_missing_fields?: string[]; interview_from_email?: string };
  }>(`/service-orders/${encodeURIComponent(orderId)}/interview/launch`, {
    method: "POST",
    body: JSON.stringify({
      channels: ["email", "whatsapp"],
      force_resend: true,
      force_email: true,
    }),
  });
}

export async function startPaidSurveyOrder(orderId: string, runMode: "now" | "schedule" = "now") {
  return apiFetch<{ ok?: boolean; message?: string; status?: string }>(
    `/service-orders/${encodeURIComponent(orderId)}/survey/launch`,
    {
      method: "POST",
      body: JSON.stringify({ run_mode: runMode }),
    },
  );
}

export async function sendInterviewBookingInvites(orderId: string, force = false) {
  return apiFetch<{ whatsapp_sent?: number; email_sent?: number; errors?: string[] }>(
    `/service-orders/${encodeURIComponent(orderId)}/interview-booking/send-invites`,
    { method: "POST", body: JSON.stringify({ force_resend: force }) },
  );
}

export function gocardlessAvailable(subscription: Record<string, unknown> | null | undefined) {
  const paymentOptions = (subscription?.payment_options || {}) as Record<string, unknown>;
  return Boolean(paymentOptions.gocardless_available || subscription?.gocardless_checkout_available);
}
