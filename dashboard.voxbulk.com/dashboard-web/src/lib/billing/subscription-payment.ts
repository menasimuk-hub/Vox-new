import { apiFetch } from "@/lib/api";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";

export const CARD_SUB_PLAN_KEY = "voxbulk_card_sub_plan_id";
export const CARD_SUB_INTERVAL_KEY = "voxbulk_card_sub_interval";

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
};

declare global {
  interface Window {
    Stripe?: (key: string) => import("@stripe/stripe-js").Stripe;
  }
}

export function loadScript(src: string) {
  return new Promise<void>((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve();
      return;
    }
    const s = document.createElement("script");
    s.src = src;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

export function primarySubscriptionProvider(subscription: Record<string, unknown> | null | undefined): string {
  const opts = (subscription?.payment_options || {}) as Record<string, unknown>;
  return String(opts.primary_provider || "gocardless").toLowerCase();
}

export function cardSubscriptionAvailable(subscription: Record<string, unknown> | null | undefined): boolean {
  const opts = (subscription?.payment_options || {}) as Record<string, unknown>;
  return Boolean(opts.stripe_available || opts.airwallex_available);
}

export function gocardlessSubscriptionAvailable(subscription: Record<string, unknown> | null | undefined): boolean {
  const opts = (subscription?.payment_options || {}) as Record<string, unknown>;
  return Boolean(opts.gocardless_available || subscription?.gocardless_checkout_available);
}

export function coreCheckoutAvailable(subscription: Record<string, unknown> | null | undefined): boolean {
  return gocardlessSubscriptionAvailable(subscription) || cardSubscriptionAvailable(subscription);
}

export type PaymentMethodChoice = "gocardless" | "stripe";

export function availablePaymentMethods(
  subscription: Record<string, unknown> | null | undefined,
): PaymentMethodChoice[] {
  const methods: PaymentMethodChoice[] = [];
  if (gocardlessSubscriptionAvailable(subscription)) methods.push("gocardless");
  if (cardSubscriptionAvailable(subscription)) methods.push("stripe");
  return methods;
}

export async function startCardSubscription(
  planId: string,
  billingInterval: "monthly" | "yearly" = "monthly",
  paymentMethod: "stripe" | "airwallex" = "stripe",
) {
  const result = await apiFetch<CardStartResponse>("/billing/subscription/card/start", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      billing_interval: billingInterval,
      payment_method: paymentMethod,
    }),
  });

  // Promo trial / 100% discount — no card charge.
  if (result?.provider === "promo_discount" || result?.paid) {
    return result;
  }

  if (!result?.payment_intent_id) {
    throw new Error("Checkout did not return a payment intent");
  }
  sessionStorage.setItem(CARD_SUB_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SUB_INTERVAL_KEY, billingInterval);

  if (result.provider === "airwallex") {
    if (!result.client_secret) throw new Error("Airwallex checkout is not configured");
    await redirectToAirwallexHostedCheckout({
      intent_id: result.payment_intent_id,
      client_secret: result.client_secret,
      currency: result.currency,
      environment: String(result.checkout?.environment || "demo"),
      pending: { flow: "subscription", payment_intent_id: result.payment_intent_id },
      returnPath: "/account/packages",
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
    confirmParams: { return_url: `${window.location.origin}/account/packages?billing=card_success` },
  });
  if (error) throw new Error(error.message || "Stripe payment failed");
  return result;
}

export async function completeCardSubscription(paymentIntentId: string) {
  const planId = sessionStorage.getItem(CARD_SUB_PLAN_KEY) || "";
  const billingInterval = (sessionStorage.getItem(CARD_SUB_INTERVAL_KEY) || "monthly") as "monthly" | "yearly";
  const providers = await apiFetch<{ primary_provider?: string; stripe_available?: boolean }>(
    "/billing/subscription/payment-providers",
  );
  const provider = String(providers?.primary_provider || "stripe").toLowerCase();
  const normalized = provider === "airwallex" ? "airwallex" : "stripe";
  return apiFetch("/billing/subscription/card/complete", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      provider: normalized,
      payment_intent_id: paymentIntentId,
      billing_interval: billingInterval,
    }),
  });
}

export function clearCardSubscriptionState() {
  try {
    sessionStorage.removeItem(CARD_SUB_PLAN_KEY);
    sessionStorage.removeItem(CARD_SUB_INTERVAL_KEY);
  } catch {
    /* ignore */
  }
}
