import type { SurveyLaunchEligibility } from "@/lib/queries/index";

const BILLING_CHECK_TIMEOUT_MS = 15_000;

export { BILLING_CHECK_TIMEOUT_MS };

/** Modal + billing check lifecycle. */
export type BillingCheckPhase = "idle" | "checking" | "ready" | "error" | "timeout";
export type LaunchModalPhase = BillingCheckPhase | "launching" | "success";

export function logBillingCheck(
  tag: "start" | "done" | "timeout" | "error" | "blocked" | "allowed" | "package" | "wallet" | "allowance" | "usage",
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
    block_reason_code: data.block_reason_code,
    billing: data.billing,
  };
}

export function resolveBillingCheckPhase(input: {
  orderId: string | null;
  launchOpen: boolean;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  errorMessage: string | null;
  hasData: boolean;
  timedOut: boolean;
}): BillingCheckPhase {
  if (!input.launchOpen) return "idle";
  if (!input.orderId) return "error";
  if (input.timedOut) return "timeout";
  if (input.isError) return "error";
  if ((input.isLoading || input.isFetching) && !input.hasData) return "checking";
  if (input.hasData) return "ready";
  return "checking";
}

export function resolveLaunchModalPhase(
  billingPhase: BillingCheckPhase,
  input: { launching: boolean; launchSuccess: boolean },
): LaunchModalPhase {
  if (input.launchSuccess) return "success";
  if (input.launching) return "launching";
  return billingPhase;
}

const BLOCK_REASON_MESSAGES: Record<string, string> = {
  no_recipients: "Upload at least one contact before launch.",
  package_not_found: "Package not found.",
  wallet_balance_low: "Wallet balance is too low.",
  allowance_exhausted: "Allowance exhausted.",
  whatsapp_usage_limit: "WhatsApp usage limit reached.",
  billing_check_timeout: "Billing check timed out.",
  billing_check_failed: "Unable to verify package and wallet right now.",
  quote_failed: "Unable to calculate launch pricing right now.",
  payment_required: "Purchase a package or add survey credits to launch.",
};

export function mapBillingBlockReason(
  eligibility: Pick<SurveyLaunchEligibility, "block_reason" | "block_reason_code" | "summary"> | null | undefined,
): string | null {
  if (!eligibility) return null;
  const code = String(eligibility.block_reason_code || "").trim();
  if (code && BLOCK_REASON_MESSAGES[code]) return BLOCK_REASON_MESSAGES[code];
  const reason = String(eligibility.block_reason || eligibility.summary || "").trim();
  return reason || null;
}

export function billingCheckErrorMessage(
  phase: BillingCheckPhase,
  errorMessage: string | null,
  orderId: string | null,
  eligibility?: Pick<SurveyLaunchEligibility, "block_reason" | "block_reason_code" | "summary" | "launch_action"> | null,
): string | null {
  if (phase === "error" && !orderId) {
    return "Save your draft before checking billing.";
  }
  if (phase === "timeout") {
    return BLOCK_REASON_MESSAGES.billing_check_timeout;
  }
  if (phase === "error") {
    return errorMessage || BLOCK_REASON_MESSAGES.billing_check_failed;
  }
  if (phase === "ready" && eligibility?.launch_action === "blocked") {
    return mapBillingBlockReason(eligibility);
  }
  return errorMessage;
}
