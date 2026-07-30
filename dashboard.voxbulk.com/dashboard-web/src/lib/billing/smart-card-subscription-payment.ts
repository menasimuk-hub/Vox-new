import { apiFetch } from "@/lib/api";
import { loadScript } from "@/lib/billing/subscription-payment";
import { redirectToAirwallexHostedCheckout } from "@/lib/billing/airwallex-hpp";

export const CARD_SMART_CARD_PLAN_KEY = "voxbulk_card_smart_card_plan_id";
export const CARD_SMART_CARD_SEATS_KEY = "voxbulk_card_smart_card_seats";
export const CARD_SMART_CARD_PROVIDER_KEY = "voxbulk_card_smart_card_provider";

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
  publishable_key?: string;
  plan_id: string;
  checkout?: Record<string, unknown> & { environment?: string };
};

export async function startSmartCardSeatCheckout(planId: string, seatQuantity: number) {
  const result = await apiFetch<SeatCheckoutResponse>("/smart-card/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_id: planId, seat_quantity: seatQuantity }),
  });
  const intentId = result.intent_id || result.payment_intent_id || "";
  if (!intentId) throw new Error("Checkout did not return a payment intent");

  sessionStorage.setItem(CARD_SMART_CARD_PLAN_KEY, planId);
  sessionStorage.setItem(CARD_SMART_CARD_SEATS_KEY, String(seatQuantity));
  sessionStorage.setItem(CARD_SMART_CARD_PROVIDER_KEY, result.provider);

  if (result.provider === "airwallex") {
    if (!result.client_secret) throw new Error("Airwallex checkout is not configured");
    await redirectToAirwallexHostedCheckout({
      intent_id: intentId,
      client_secret: result.client_secret,
      currency: result.currency,
      environment: String(result.checkout?.environment || "demo"),
      pending: { flow: "smart_card_subscription", payment_intent_id: intentId },
      returnPath: "/account/smart-card/packages",
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
      return_url: `${window.location.origin}/account/smart-card/packages?billing=card_success`,
    },
  });
  if (error) throw new Error(error.message || "Stripe payment failed");
  return result;
}

export async function completeSmartCardSeatCheckout(paymentIntentId: string) {
  const planId = sessionStorage.getItem(CARD_SMART_CARD_PLAN_KEY) || "";
  const seats = Number(sessionStorage.getItem(CARD_SMART_CARD_SEATS_KEY) || "0");
  const provider = (sessionStorage.getItem(CARD_SMART_CARD_PROVIDER_KEY) || "stripe").toLowerCase();
  return apiFetch("/smart-card/billing/complete", {
    method: "POST",
    body: JSON.stringify({
      plan_id: planId,
      provider: provider === "airwallex" ? "airwallex" : "stripe",
      payment_intent_id: paymentIntentId,
      seat_quantity: seats > 0 ? seats : undefined,
    }),
  });
}
