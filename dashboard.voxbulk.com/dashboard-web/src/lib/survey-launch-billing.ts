import type { SurveyLaunchEligibility } from "@/lib/queries/index";



const BILLING_CHECK_TIMEOUT_MS = 15_000;



export { BILLING_CHECK_TIMEOUT_MS };



/** Modal + billing check lifecycle. */

export type BillingCheckPhase = "idle" | "checking" | "ready" | "error" | "timeout";

export type LaunchModalPhase = BillingCheckPhase | "launching" | "success";



export function logBillingCheck(

  tag: "start" | "done" | "timeout" | "error" | "blocked" | "allowed" | "package" | "wallet" | "allowance" | "usage" | "pay_required",

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

    covered_recipients: data.covered_recipients,

    extra_recipients: data.extra_recipients,

    covered_by_allowance: data.covered_by_allowance,

    shortfall_units: data.shortfall_units,

    amount_due_display: data.amount_due_display,

    extra_cost_display: data.extra_cost_display,

    wa_survey_extra_display: data.wa_survey_extra_display,

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

  wallet_insufficient: "Wallet balance is too low — top up to launch.",

};



export function formatWaExtraRate(display?: string | null) {

  return display || "£0.49";

}



export function formatPlanIncludesRecipients(included: number) {

  return `Plan includes: ${included.toLocaleString()} WA survey recipients/month.`;

}



export function formatExtraRecipientsLine(extraDisplay?: string | null) {

  return `Extra recipients: ${formatWaExtraRate(extraDisplay)} each after allowance is used.`;

}



export const PRICING_COPY = {

  interviewWhatsAppIncluded: "Interview WhatsApp: included.",

  aiPhoneSurveyBilling: "AI phone survey: billed by connection + minutes.",

} as const;



export function isWhatsAppAllowanceExhausted(

  eligibility: Pick<SurveyLaunchEligibility, "mode" | "billing"> | null | undefined,

): boolean {

  if (!eligibility) return false;

  if (eligibility.mode === "subscription_overage") return true;

  const billing = eligibility.billing;

  if (billing?.shared_package_pool) {
    return Boolean(billing.has_whatsapp_allowance && (billing.package_remaining ?? 0) <= 0);
  }

  return Boolean(billing?.has_whatsapp_allowance && (billing.whatsapp_remaining ?? 0) <= 0);

}



export function formatPlanIncludesCallMinutes(included: number) {
  return `Plan includes: ${included.toLocaleString()} call minutes/month.`;
}

export function buildPhoneMinutesAllowanceNotice(
  eligibility: SurveyLaunchEligibility | null | undefined,
): string | null {
  if (!eligibility) return null;
  const channel = String((eligibility as { survey_channel?: string }).survey_channel || "").toLowerCase();
  if (channel && channel !== "ai_call") return null;

  const billing = eligibility.billing as
    | {
        calls_included?: number;
        calls_remaining?: number;
        has_call_allowance?: boolean;
      }
    | undefined;
  const included = billing?.calls_included ?? 0;
  const estimated = Number((eligibility as { estimated_call_minutes?: number }).estimated_call_minutes ?? 0);
  const covered = Number((eligibility as { covered_call_minutes?: number }).covered_call_minutes ?? 0);
  const extra = Number((eligibility as { extra_call_minutes?: number }).extra_call_minutes ?? 0);
  const remaining = Number(
    (eligibility as { remaining_call_minutes_after_launch?: number }).remaining_call_minutes_after_launch ?? 0,
  );

  if (eligibility.summary && String(eligibility.mode || "").startsWith("subscription_phone")) {
    return eligibility.summary;
  }

  if (included > 0 && estimated > 0) {
    if (extra > 0) {
      return (
        `${formatPlanIncludesCallMinutes(included)} This launch uses ${estimated} minute${estimated === 1 ? "" : "s"} ` +
        `(${covered} included, ${extra} extra · ${eligibility.amount_due_display || "invoiced on next bill"}).`
      );
    }
    return (
      `${formatPlanIncludesCallMinutes(included)} This launch uses ${estimated} minute${estimated === 1 ? "" : "s"} ` +
      `(${remaining} remaining after launch).`
    );
  }

  if (eligibility.mode === "payg" && eligibility.summary) return eligibility.summary;
  return null;
}

export function buildSurveyAllowanceNotice(
  eligibility: SurveyLaunchEligibility | null | undefined,
): string | null {
  return buildWhatsAppAllowanceNotice(eligibility) || buildPhoneMinutesAllowanceNotice(eligibility);
}

export function buildWhatsAppAllowanceNotice(

  eligibility: SurveyLaunchEligibility | null | undefined,

): string | null {

  if (!eligibility) return null;

  if (eligibility.summary) return eligibility.summary;

  const billing = eligibility.billing;

  const included = billing?.whatsapp_included ?? 0;

  const extra = eligibility.extra_recipients ?? eligibility.shortfall_units ?? 0;

  const extraRate = formatWaExtraRate(eligibility.wa_survey_extra_display);

  if (extra > 0) {

    return `${formatPlanIncludesRecipients(included)} ${formatExtraRecipientsLine(extraRate)} This launch uses ${extra.toLocaleString()} extra recipient${extra === 1 ? "" : "s"} (${eligibility.extra_cost_display || eligibility.amount_due_display || "—"} invoiced).`;

  }

  if (isWhatsAppAllowanceExhausted(eligibility)) {
    if (billing?.shared_package_pool) {
      return `No remaining package balance. ${formatExtraRecipientsLine(extraRate)} Extra usage will be invoiced or charged from wallet when you launch.`;
    }
    return `${formatPlanIncludesRecipients(included)} ${formatExtraRecipientsLine(extraRate)}`;
  }

  return null;

}



export type LaunchPricingBreakdown = {

  planIncludes: string | null;

  extraRecipientsLine: string | null;

  coveredRecipients: number | null;

  extraRecipients: number | null;

  extraCost: string | null;

  totalDue: string | null;

  interviewWhatsApp: string;

  aiPhoneSurvey: string;

};



export function buildLaunchPricingBreakdown(

  eligibility: SurveyLaunchEligibility | null | undefined,

): LaunchPricingBreakdown | null {

  if (!eligibility) return null;

  const billing = eligibility.billing;

  const included = billing?.whatsapp_included ?? 0;

  const extraRate = formatWaExtraRate(eligibility.wa_survey_extra_display);

  return {

    planIncludes: billing?.has_whatsapp_allowance ? formatPlanIncludesRecipients(included) : null,

    extraRecipientsLine: formatExtraRecipientsLine(extraRate),

    coveredRecipients: eligibility.covered_recipients ?? eligibility.covered_by_allowance ?? null,

    extraRecipients: eligibility.extra_recipients ?? eligibility.shortfall_units ?? null,

    extraCost: eligibility.extra_cost_display || null,

    totalDue: eligibility.amount_due_display || null,

    interviewWhatsApp: PRICING_COPY.interviewWhatsAppIncluded,

    aiPhoneSurvey: PRICING_COPY.aiPhoneSurveyBilling,

  };

}



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

  if (phase === "ready" && eligibility?.launch_action === "topup_required") {

    return mapBillingBlockReason(eligibility) || BLOCK_REASON_MESSAGES.wallet_insufficient;

  }

  if (phase === "ready" && eligibility?.launch_action === "blocked") {

    return mapBillingBlockReason(eligibility);

  }

  return errorMessage;

}


