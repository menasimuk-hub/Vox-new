import { apiFetch } from "@/lib/api";

export const CARD_FEEDBACK_SUB_PLAN_KEY = "voxbulk_card_feedback_sub_plan_id";

export async function fetchFeedbackPaymentProviders() {
  return apiFetch<Record<string, unknown>>("/customer-feedback/subscription/payment-providers");
}

export function feedbackCheckoutAvailable(providers: Record<string, unknown> | null | undefined): boolean {
  return Boolean(providers?.gocardless_available);
}

/** Customer Feedback is GoCardless-only — card signup is blocked. */
export function feedbackUsesCardCheckout(_providers: Record<string, unknown> | null | undefined): boolean {
  return false;
}

export async function startFeedbackCardSubscription(
  _planId: string,
  _billingInterval: "monthly" | "yearly" = "monthly",
): Promise<never> {
  throw new Error("Customer Feedback is Direct Debit (GoCardless) only.");
}

export async function completeFeedbackCardSubscription(_paymentIntentId: string): Promise<never> {
  throw new Error("Customer Feedback is Direct Debit (GoCardless) only.");
}

export function clearFeedbackCardSubscriptionState() {
  try {
    sessionStorage.removeItem(CARD_FEEDBACK_SUB_PLAN_KEY);
  } catch {
    /* ignore */
  }
}
