import { apiFetch } from "@/lib/api";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";

export const CARD_SUB_PLAN_KEY = "voxbulk_card_sub_plan_id";
export const CARD_SUB_INTERVAL_KEY = "voxbulk_card_sub_interval";
export const CARD_SUB_PROVIDER_KEY = "voxbulk_card_sub_provider";

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
  /** When true, open StripeCardCheckoutDialog — do not call confirmPayment bare. */
  needs_stripe_elements?: boolean;
  return_url?: string;
};

/** Payload for Stripe Payment Element dialog (subscription checkout). */
export type StripeElementsCheckout = {
  needs_stripe_elements: true;
  provider: "stripe";
  publishable_key: string;
  client_secret: string;
  payment_intent_id: string;
  return_url: string;
  plan_id: string;
  currency: string;
  amount_minor: number;
  billing_interval: string;
  /** setup = save card for trial (SetupIntent); payment = charge now */
  mode?: "setup" | "payment";
  trial_days?: number;
};

export function isStripeElementsCheckout(
  result: CardStartResponse | StripeElementsCheckout | null | undefined,
): result is StripeElementsCheckout {
  return Boolean(result && (result as StripeElementsCheckout).needs_stripe_elements === true);
}

declare global {
  interface Window {
    Stripe?: (key: string) => import("@stripe/stripe-js").Stripe;
  }
}

const loadedScripts: Record<string, Promise<void>> = {};

export function loadScript(src: string) {
  if (!loadedScripts[src]) {
    loadedScripts[src] = new Promise<void>((resolve, reject) => {
      const existing = document.querySelector(`script[src="${src}"]`) as HTMLScriptElement | null;
      if (existing) {
        if (src.includes("js.stripe.com") && window.Stripe) {
          resolve();
          return;
        }
        existing.addEventListener("load", () => resolve(), { once: true });
        existing.addEventListener("error", () => reject(new Error(`Failed to load ${src}`)), { once: true });
        // Already-complete script tags may not fire load again.
        if (src.includes("js.stripe.com")) {
          const start = Date.now();
          const tick = () => {
            if (window.Stripe) {
              resolve();
              return;
            }
            if (Date.now() - start > 8000) {
              reject(new Error("Stripe.js failed to load"));
              return;
            }
            window.setTimeout(tick, 50);
          };
          tick();
        }
        return;
      }
      const s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.head.appendChild(s);
    });
  }
  return loadedScripts[src];
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

/**
 * Starts card subscription checkout.
 * Stripe: returns `{ needs_stripe_elements: true, ... }` for Payment Element UI.
 * Airwallex: redirects to hosted page.
 * Promo/trial: returns paid result with no charge.
 */
export async function startCardSubscription(
  planId: string,
  billingInterval: "monthly" | "yearly" = "monthly",
  paymentMethod: "stripe" | "airwallex" = "stripe",
  options?: { returnPath?: string },
): Promise<CardStartResponse | StripeElementsCheckout> {
  const result = await apiFetch<CardStartResponse>("/billing/subscription/card/start", {
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
  sessionStorage.setItem(CARD_SUB_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SUB_INTERVAL_KEY, billingInterval);
  sessionStorage.setItem(CARD_SUB_PROVIDER_KEY, String(result.provider || paymentMethod));

  if (result.provider === "airwallex") {
    if (!result.client_secret) throw new Error("Airwallex checkout is not configured");
    await redirectToAirwallexHostedCheckout({
      intent_id: result.payment_intent_id,
      client_secret: result.client_secret,
      currency: result.currency,
      environment: String(result.checkout?.environment || "demo"),
      pending: { flow: "subscription", payment_intent_id: result.payment_intent_id },
      returnPath: options?.returnPath || "/account/packages",
    });
    return result;
  }

  if (!result.publishable_key || !result.client_secret) {
    throw new Error("Stripe checkout is not configured");
  }

  const returnPath = options?.returnPath || "/account/packages";
  const return_url = `${window.location.origin}${returnPath}${returnPath.includes("?") ? "&" : "?"}billing=card_success`;

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

export async function completeCardSubscription(paymentIntentId: string) {
  const planId = sessionStorage.getItem(CARD_SUB_PLAN_KEY) || "";
  const billingInterval = (sessionStorage.getItem(CARD_SUB_INTERVAL_KEY) || "monthly") as "monthly" | "yearly";
  const stored = (sessionStorage.getItem(CARD_SUB_PROVIDER_KEY) || "").toLowerCase();
  let provider = stored === "airwallex" ? "airwallex" : stored === "stripe" ? "stripe" : "";
  if (!provider) {
    // Fallback only when session was lost (e.g. new tab after 3DS).
    const providers = await apiFetch<{ primary_provider?: string; stripe_available?: boolean }>(
      "/billing/subscription/payment-providers",
    );
    const primary = String(providers?.primary_provider || "stripe").toLowerCase();
    provider = primary === "airwallex" ? "airwallex" : "stripe";
  }
  return apiFetch("/billing/subscription/card/complete", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      provider,
      payment_intent_id: paymentIntentId,
      billing_interval: billingInterval,
    }),
  });
}

export function clearCardSubscriptionState() {
  try {
    sessionStorage.removeItem(CARD_SUB_PLAN_KEY);
    sessionStorage.removeItem(CARD_SUB_INTERVAL_KEY);
    sessionStorage.removeItem(CARD_SUB_PROVIDER_KEY);
  } catch {
    /* ignore */
  }
}
