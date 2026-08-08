import { apiFetch } from "@/lib/api";
import {
  CARD_SUB_INTERVAL_KEY,
  CARD_SUB_PLAN_KEY,
  type StripeElementsCheckout,
} from "@/lib/billing/subscription-payment";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";

export const CARD_FEEDBACK_SUB_PLAN_KEY = "voxbulk_card_feedback_sub_plan_id";
export const CARD_FEEDBACK_PROVIDER_KEY = "voxbulk_card_feedback_provider";

type CardStartResponse = {
  provider: string;
  currency: string;
  amount_minor: number;
  billing_interval: string;
  client_secret?: string;
  payment_intent_id?: string;
  publishable_key?: string;
  plan_id: string;
  paid?: boolean;
  trial_days?: number;
  checkout?: Record<string, unknown> & { environment?: string };
  needs_stripe_elements?: boolean;
  return_url?: string;
};

export async function fetchFeedbackPaymentProviders() {
  return apiFetch<Record<string, unknown>>("/customer-feedback/subscription/payment-providers");
}

export function feedbackCheckoutAvailable(providers: Record<string, unknown> | null | undefined): boolean {
  return Boolean(providers?.gocardless_available || providers?.stripe_available || providers?.airwallex_available);
}

export function feedbackUsesCardCheckout(providers: Record<string, unknown> | null | undefined): boolean {
  return Boolean(providers?.stripe_available || providers?.airwallex_available);
}

export async function startFeedbackCardSubscription(
  planId: string,
  billingInterval: "monthly" | "yearly" = "monthly",
  paymentMethod: "stripe" | "airwallex" = "stripe",
): Promise<CardStartResponse | StripeElementsCheckout> {
  const result = await apiFetch<CardStartResponse>("/customer-feedback/subscription/card/start", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      billing_interval: billingInterval,
      payment_method: paymentMethod,
    }),
  });

  if (result?.provider === "promo_discount" || result?.paid) {
    return result;
  }

  if (!result?.payment_intent_id) {
    throw new Error("Checkout did not return a payment intent");
  }
  sessionStorage.setItem(CARD_FEEDBACK_SUB_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SUB_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SUB_INTERVAL_KEY, billingInterval);
  sessionStorage.setItem(CARD_FEEDBACK_PROVIDER_KEY, result.provider);

  if (result.provider === "airwallex") {
    if (!result.client_secret) throw new Error("Airwallex checkout is not configured");
    await redirectToAirwallexHostedCheckout({
      intent_id: result.payment_intent_id,
      client_secret: result.client_secret,
      currency: result.currency,
      environment: String(result.checkout?.environment || "demo"),
      pending: { flow: "feedback_subscription", payment_intent_id: result.payment_intent_id },
      returnPath: "/account/packages?tab=feedback",
    });
    return result;
  }

  if (!result.publishable_key || !result.client_secret) {
    throw new Error("Stripe checkout is not configured");
  }

  const return_url = `${window.location.origin}/account/packages?tab=feedback&billing=card_success`;
  return {
    needs_stripe_elements: true,
    provider: "stripe",
    publishable_key: result.publishable_key,
    client_secret: result.client_secret,
    payment_intent_id: result.payment_intent_id,
    return_url,
    plan_id: result.plan_id || planId,
    currency: result.currency,
    amount_minor: result.amount_minor,
    billing_interval: result.billing_interval || billingInterval,
  };
}

export async function completeFeedbackCardSubscription(paymentIntentId: string) {
  const planId =
    sessionStorage.getItem(CARD_FEEDBACK_SUB_PLAN_KEY) || sessionStorage.getItem(CARD_SUB_PLAN_KEY) || "";
  const billingInterval = (sessionStorage.getItem(CARD_SUB_INTERVAL_KEY) || "monthly") as "monthly" | "yearly";
  const stored = (sessionStorage.getItem(CARD_FEEDBACK_PROVIDER_KEY) || "").toLowerCase();
  const normalized = stored === "airwallex" ? "airwallex" : "stripe";
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
    sessionStorage.removeItem(CARD_FEEDBACK_PROVIDER_KEY);
  } catch {
    /* ignore */
  }
}
