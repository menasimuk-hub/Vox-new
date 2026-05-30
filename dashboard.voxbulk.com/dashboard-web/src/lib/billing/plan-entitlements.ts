type PlanLike = {
  code?: string | null;
  name?: string | null;
  price_gbp_pence?: number | null;
  interval?: string | null;
  is_enterprise?: boolean | null;
  is_payg?: boolean | null;
};

const CV_EMAIL_BLOCKED = new Set(["payg", "free", "topup"]);
const CV_EMAIL_INCLUDED = new Set(["starter", "pro", "business", "enterprise", "practice", "group"]);

/** Match backend plan_allows_cv_email — used when billing_context is stale or missing. */
export function planAllowsCvEmail(plan: PlanLike | null | undefined): boolean {
  if (!plan) return false;
  const code = String(plan.code || "").trim().toLowerCase();
  if (CV_EMAIL_BLOCKED.has(code) || plan.is_payg) return false;
  if (CV_EMAIL_INCLUDED.has(code)) return true;
  if (plan.is_enterprise) return true;
  const interval = String(plan.interval || "monthly").trim().toLowerCase();
  const price = Number(plan.price_gbp_pence ?? 0);
  return interval === "monthly" && price > 0;
}

export function interviewBillingFromSources(
  billingContext: Record<string, unknown> | null | undefined,
  sessionPlan: PlanLike | null | undefined,
) {
  const fromApi = Boolean(billingContext?.cv_email_allowed);
  const fromSession = planAllowsCvEmail(sessionPlan);
  const cvEmailAllowed = fromApi || fromSession;
  const planName = String(
    billingContext?.plan_name || sessionPlan?.name || "",
  ).trim();
  const hasPackageSub =
    Boolean(billingContext?.has_active_subscription) ||
    (cvEmailAllowed && Boolean(sessionPlan?.code) && !CV_EMAIL_BLOCKED.has(String(sessionPlan?.code || "").toLowerCase()));
  const blockReason = cvEmailAllowed
    ? ""
    : String(
        billingContext?.cv_email_block_reason ||
          "CV email collection is included on Starter, Pro, and Business packages.",
      );
  return { cvEmailAllowed, planName, hasPackageSub, blockReason };
}
