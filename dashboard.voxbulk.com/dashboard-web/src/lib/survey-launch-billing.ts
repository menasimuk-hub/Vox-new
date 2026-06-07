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
  if (input.hasData) return "ready";
  if (input.isLoading || input.isFetching) return "checking";
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

export function isWhatsAppAllowanceExhausted(
  eligibility: Pick<SurveyLaunchEligibility, "block_reason_code" | "billing"> | null | undefined,
): boolean {
  if (!eligibility) return false;
  if (eligibility.block_reason_code === "whatsapp_usage_limit") return true;
  const billing = eligibility.billing;
  return Boolean(billing?.has_whatsapp_allowance && (billing.whatsapp_remaining ?? 0) <= 0);
}

export function buildWhatsAppAllowanceNotice(
  eligibility: SurveyLaunchEligibility | null | undefined,
): string | null {
  if (!eligibility || !isWhatsAppAllowanceExhausted(eligibility)) return null;
  if (eligibility.block_reason) return eligibility.block_reason;
  const billing = eligibility.billing;
  const included = billing?.whatsapp_included ?? 0;
  const used = billing?.whatsapp_used ?? 0;
  const remaining = billing?.whatsapp_remaining ?? 0;
  const due = eligibility.amount_due_display || "—";
  return `Your WhatsApp allowance has been fully used. Included: ${included}, used: ${used}, remaining: ${remaining}. This launch would require additional billing of ${due}.`;
}

export type LaunchPricingBreakdown = {
  estimatedSend: string | null;
  minimumCharge: string | null;
  setupFee: string | null;
  totalDue: string | null;
  packageLabel: string | null;
  packageId: string | null;
};

export function buildLaunchPricingBreakdown(
  eligibility: SurveyLaunchEligibility | null | undefined,
): LaunchPricingBreakdown | null {
  if (!eligibility?.payment_required) return null;
  return {
    estimatedSend: eligibility.estimated_send_cost_display || null,
    minimumCharge: eligibility.minimum_charge_display || null,
    setupFee: eligibility.setup_fee_display || null,
    totalDue: eligibility.amount_due_display || null,
    packageLabel: eligibility.package_label || eligibility.billing?.plan_name || null,
    packageId: eligibility.package_id || null,
  };
}

export function mapBillingBlockReason(
  eligibility: Pick<SurveyLaunchEligibility, "block_reason" | "block_reason_code" | "summary"> | null | undefined,
): string | null {
  if (!eligibility) return null;
  if (eligibility.block_reason_code === "whatsapp_usage_limit" && eligibility.block_reason) {
    return eligibility.block_reason;
  }
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
