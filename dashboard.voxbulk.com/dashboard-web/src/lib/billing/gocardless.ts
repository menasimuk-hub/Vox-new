import { apiFetch } from "@/lib/api";

export const GC_FLOW_KEY = "voxbulk_gc_redirect_flow_id";
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

export function resolveRedirectFlowId(params: BillingReturnParams, kind: "subscription" | "order") {
  if (params.redirectFlowId) return params.redirectFlowId;
  const key = kind === "order" ? GC_ORDER_FLOW_KEY : GC_FLOW_KEY;
  try {
    return (sessionStorage.getItem(key) || "").trim();
  } catch {
    return "";
  }
}

export function clearBillingReturnState(kind?: "subscription" | "order" | "all") {
  try {
    if (!kind || kind === "all" || kind === "subscription") sessionStorage.removeItem(GC_FLOW_KEY);
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

export async function startGoCardlessSubscription(planId: string) {
  const result = await apiFetch<{
    redirect_flow_id?: string;
    authorization_url?: string;
    environment?: string;
  }>("/billing/subscription/gocardless/start", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId }),
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
    message?: string;
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
