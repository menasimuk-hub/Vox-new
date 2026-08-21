import { apiFetch } from "@/lib/api";
import type { StripeElementsCheckout } from "@/lib/billing/subscription-payment";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";

export const CARD_SMART_CARD_PLAN_KEY = "voxbulk_card_smart_card_plan_id";
export const CARD_SMART_CARD_SEATS_KEY = "voxbulk_card_smart_card_seats";
export const CARD_SMART_CARD_PROVIDER_KEY = "voxbulk_card_smart_card_provider";
export const CARD_SMART_CARD_INTERVAL_KEY = "voxbulk_card_smart_card_interval";
export const GC_SMART_CARD_FLOW_KEY = "voxbulk_gc_smart_card_redirect_flow_id";

type SeatCheckoutResponse = {
  ok?: boolean;
  provider: string;
  currency: string;
  amount_minor: number;
  seat_quantity: number;
  billing_interval: string;
  client_secret?: string;
  intent_id?: string;
  payment_intent_id?: string;
  setup_intent_id?: string;
  publishable_key?: string;
  plan_id: string;
  paid?: boolean;
  subscription_id?: string;
  checkout?: Record<string, unknown> & { environment?: string };
  needs_stripe_elements?: boolean;
  return_url?: string;
  trial_days?: number;
  mode?: "setup" | "payment";
  after_trial_amount_minor?: number;
  environment?: string;
  livemode?: boolean;
  stripe_mode?: string;
};

export async function startSmartCardSeatCheckout(
  planId: string,
  seatQuantity: number,
  billingInterval: "monthly" | "yearly" = "yearly",
  paymentMethod: "stripe" | "airwallex" = "stripe",
  options?: { returnPath?: string },
): Promise<SeatCheckoutResponse | StripeElementsCheckout> {
  const result = await apiFetch<SeatCheckoutResponse>("/smart-card/billing/checkout", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      seat_quantity: seatQuantity,
      billing_interval: billingInterval,
      provider: paymentMethod,
    }),
  });

  if (result.provider === "promo_discount" && result.paid) {
    return result;
  }

  const intentId = result.intent_id || result.setup_intent_id || result.payment_intent_id || "";
  if (!intentId) throw new Error("Checkout did not return a payment intent");

  sessionStorage.setItem(CARD_SMART_CARD_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SMART_CARD_SEATS_KEY, String(seatQuantity));
  sessionStorage.setItem(CARD_SMART_CARD_PROVIDER_KEY, result.provider);
  sessionStorage.setItem(CARD_SMART_CARD_INTERVAL_KEY, billingInterval);

  if (result.provider === "airwallex") {
    if (!result.client_secret) throw new Error("Airwallex checkout is not configured");
    await redirectToAirwallexHostedCheckout({
      intent_id: intentId,
      client_secret: result.client_secret,
      currency: result.currency,
      environment: String(result.checkout?.environment || "demo"),
      pending: { flow: "smart_card_subscription", payment_intent_id: intentId },
      returnPath: options?.returnPath || "/account/packages?tab=smartCard",
    });
    return result;
  }

  if (!result.publishable_key || !result.client_secret) {
    throw new Error("Stripe checkout is not configured");
  }

  const returnPath = options?.returnPath || "/account/packages?tab=smartCard";
  const return_url = `${window.location.origin}${returnPath}${returnPath.includes("?") ? "&" : "?"}billing=card_success`;

  return {
    needs_stripe_elements: true,
    provider: "stripe",
    publishable_key: result.publishable_key,
    client_secret: result.client_secret,
    payment_intent_id: intentId,
    return_url,
    plan_id: result.plan_id || planId,
    currency: result.currency,
    amount_minor: result.amount_minor,
    billing_interval: result.billing_interval || billingInterval,
    mode: result.mode === "setup" || intentId.startsWith("seti_") ? "setup" : "payment",
    trial_days: result.trial_days || 0,
    environment: result.environment,
    livemode: result.livemode,
    stripe_mode: result.stripe_mode,
  };
}

export async function completeSmartCardSeatCheckout(paymentIntentId: string) {
  const planId = sessionStorage.getItem(CARD_SMART_CARD_PLAN_KEY) || "";
  const seats = Number(sessionStorage.getItem(CARD_SMART_CARD_SEATS_KEY) || "0");
  const provider = (sessionStorage.getItem(CARD_SMART_CARD_PROVIDER_KEY) || "stripe").toLowerCase();
  const interval = (sessionStorage.getItem(CARD_SMART_CARD_INTERVAL_KEY) || "yearly").toLowerCase();
  return apiFetch("/smart-card/billing/complete", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      provider: provider === "airwallex" ? "airwallex" : "stripe",
      payment_intent_id: paymentIntentId,
      seat_quantity: seats > 0 ? seats : undefined,
      billing_interval: interval === "monthly" ? "monthly" : "yearly",
    }),
  });
}

export function clearSmartCardCardCheckoutState() {
  try {
    sessionStorage.removeItem(CARD_SMART_CARD_PLAN_KEY);
    sessionStorage.removeItem(CARD_SMART_CARD_SEATS_KEY);
    sessionStorage.removeItem(CARD_SMART_CARD_PROVIDER_KEY);
    sessionStorage.removeItem(CARD_SMART_CARD_INTERVAL_KEY);
  } catch {
    /* ignore */
  }
}

export async function startSmartCardGoCardless(
  planId: string,
  seatQuantity: number,
  billingInterval: "monthly" | "yearly" = "monthly",
) {
  const result = await apiFetch<{
    redirect_flow_id?: string;
    authorization_url?: string;
  }>("/smart-card/billing/gocardless/start", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      seat_quantity: seatQuantity,
      billing_interval: billingInterval,
    }),
  });
  const redirectFlowId = result?.redirect_flow_id;
  const authorizationUrl = result?.authorization_url;
  if (!redirectFlowId || !authorizationUrl) {
    throw new Error("GoCardless did not return a redirect URL");
  }
  sessionStorage.setItem(GC_SMART_CARD_FLOW_KEY, redirectFlowId);
  window.location.assign(authorizationUrl);
  return result;
}

export async function completeSmartCardGoCardless(redirectFlowId: string) {
  return apiFetch("/smart-card/billing/gocardless/complete", {
    method: "POST",
    body: JSON.stringify({ redirect_flow_id: redirectFlowId }),
  });
}
