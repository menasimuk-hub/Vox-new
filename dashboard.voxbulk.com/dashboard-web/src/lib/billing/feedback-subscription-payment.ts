import { apiFetch } from "@/lib/api";
import {
  CARD_SUB_INTERVAL_KEY,
  CARD_SUB_PLAN_KEY,
  loadScript,
} from "@/lib/billing/subscription-payment";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";

export const CARD_FEEDBACK_SUB_PLAN_KEY = "voxbulk_card_feedback_sub_plan_id";

type CardStartResponse = {
  provider: string;
  currency: string;
  amount_minor: number;
  billing_interval: string;
  client_secret?: string;
  payment_intent_id?: string;
  publishable_key?: string;
  plan_id: string;
  checkout?: Record<string, unknown> & { environment?: string };
};

export async function fetchFeedbackPaymentProviders() {
  return apiFetch<Record<string, unknown>>("/customer-feedback/subscription/payment-providers");
}

export function feedbackCheckoutAvailable(providers: Record<string, unknown> | null | undefined): boolean {
  const primary = String(providers?.primary_provider || "gocardless").toLowerCase();
  if (primary === "gocardless") return Boolean(providers?.gocardless_available);
  if (primary === "airwallex") return Boolean(providers?.airwallex_available);
  if (primary === "stripe") return Boolean(providers?.stripe_available);
  return false;
}

export function feedbackUsesCardCheckout(providers: Record<string, unknown> | null | undefined): boolean {
  const primary = String(providers?.primary_provider || "gocardless").toLowerCase();
  return primary === "airwallex" || primary === "stripe";
}

export async function startFeedbackCardSubscription(
  planId: string,
  billingInterval: "monthly" | "yearly" = "monthly",
) {
  const result = await apiFetch<CardStartResponse>("/customer-feedback/subscription/card/start", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId, billing_interval: billingInterval }),
  });
  if (!result?.payment_intent_id) {
    throw new Error("Checkout did not return a payment intent");
  }
  sessionStorage.setItem(CARD_FEEDBACK_SUB_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SUB_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SUB_INTERVAL_KEY, billingInterval);

  if (result.provider === "airwallex") {
    if (!result.client_secret) throw new Error("Airwallex checkout is not configured");
    await redirectToAirwallexHostedCheckout({
      intent_id: result.payment_intent_id,
      client_secret: result.client_secret,
      currency: result.currency,
      environment: String(result.checkout?.environment || "demo"),
      pending: { flow: "feedback_subscription", payment_intent_id: result.payment_intent_id },
      returnPath: "/account/feedback/packages",
    });
    return result;
  }

  if (!result.publishable_key || !result.client_secret) {
    throw new Error("Stripe checkout is not configured");
  }
  await loadScript("https://js.stripe.com/v3");
  if (!window.Stripe) throw new Error("Stripe.js failed to load");
  const stripe = window.Stripe(result.publishable_key);
  const { error } = await stripe.confirmPayment({
    clientSecret: result.client_secret,
    confirmParams: {
      return_url: `${window.location.origin}/account/feedback/packages?billing=card_success`,
    },
  });
  if (error) throw new Error(error.message || "Stripe payment failed");
  return result;
}

export async function completeFeedbackCardSubscription(paymentIntentId: string) {
  const planId =
    sessionStorage.getItem(CARD_FEEDBACK_SUB_PLAN_KEY) || sessionStorage.getItem(CARD_SUB_PLAN_KEY) || "";
  const billingInterval = (sessionStorage.getItem(CARD_SUB_INTERVAL_KEY) || "monthly") as "monthly" | "yearly";
  const providers = await fetchFeedbackPaymentProviders();
  const provider = String(providers?.primary_provider || "stripe").toLowerCase();
  const normalized = provider === "airwallex" ? "airwallex" : "stripe";
  return apiFetch("/customer-feedback/subscription/card/complete", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      provider: normalized,
      payment_intent_id: paymentIntentId,
      billing_interval: billingInterval,
    }),
  });
}

export function clearFeedbackCardSubscriptionState() {
  try {
    sessionStorage.removeItem(CARD_FEEDBACK_SUB_PLAN_KEY);
  } catch {
    /* ignore */
  }
}
