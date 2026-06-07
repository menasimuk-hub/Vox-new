import type { SurveyLaunchEligibility } from "@/lib/queries/index";

const BILLING_CHECK_TIMEOUT_MS = 15_000;

export { BILLING_CHECK_TIMEOUT_MS };

export type BillingCheckPhase = "idle" | "loading" | "ready" | "error" | "timeout";

export function logBillingCheck(
  tag: "start" | "done" | "timeout" | "error" | "blocked" | "allowed",
  ctx: Record<string, unknown>,
) {
  console.info(`[billing-check:${tag}]`, ctx);
}

export function launchEligibilityLogPayload(data: SurveyLaunchEligibility | null | undefined) {
  if (!data) return {};
  return {
    mode: data.mode,
    launch_action: data.launch_action,
    can_launch: data.can_launch,
    payment_required: data.payment_required,
    recipient_count: data.recipient_count,
    estimated_whatsapp_usage: data.estimated_whatsapp_usage,
    covered_by_allowance: data.covered_by_allowance,
    shortfall_units: data.shortfall_units,
    amount_due_display: data.amount_due_display,
    estimated_send_cost_display: data.estimated_send_cost_display,
    minimum_charge_display: data.minimum_charge_display,
    package_id: data.package_id,
    block_reason: data.block_reason,
    billing: data.billing,
  };
}

export function resolveBillingCheckPhase(input: {
  orderId: string | null;
  launchOpen: boolean;
  isLoading: boolean;
  isError: boolean;
  errorMessage: string | null;
  hasData: boolean;
  timedOut: boolean;
}): BillingCheckPhase {
  if (!input.launchOpen) return "idle";
  if (!input.orderId) return "error";
  if (input.timedOut) return "timeout";
  if (input.isError) return "error";
  if (input.isLoading && !input.hasData) return "loading";
  if (input.hasData) return "ready";
  return "loading";
}

export function billingCheckErrorMessage(
  phase: BillingCheckPhase,
  errorMessage: string | null,
  orderId: string | null,
): string | null {
  if (phase === "error" && !orderId) {
    return "Save your draft before checking billing.";
  }
  if (phase === "timeout") {
    return "Billing check timed out. Try Refresh or launch again.";
  }
  return errorMessage;
}
