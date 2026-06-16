export type PlanLike = {
  id?: string;
  code?: string;
  name?: string;
  sort_order?: number;
  price_gbp_pence?: number;
  is_enterprise?: boolean;
  is_featured?: boolean;
};

export type FeedbackPlanLike = {
  plan_id?: string | null;
  plan_name?: string | null;
  plan_code?: string | null;
  display_order?: number;
};

export function planRank(plan: PlanLike | null | undefined) {
  return Number(plan?.sort_order ?? 0);
}

export function feedbackPlanRank(pkg: FeedbackPlanLike | null | undefined) {
  return Number(pkg?.display_order ?? 0);
}

export function findPlanIndex(
  plans: PlanLike[],
  plan: PlanLike | null | undefined,
  currentPlanId?: string | null,
) {
  if (!plan && !currentPlanId) return -1;
  if (currentPlanId) {
    const bySessionId = plans.findIndex((p) => p.id && String(p.id) === String(currentPlanId));
    if (bySessionId >= 0) return bySessionId;
  }
  if (!plan) return -1;
  const byId = plans.findIndex((p) => p.id && plan.id && String(p.id) === String(plan.id));
  if (byId >= 0) return byId;
  return plans.findIndex((p) => String(p.code || "").toLowerCase() === String(plan.code || "").toLowerCase());
}

export function isSamePlan(
  a: PlanLike | null | undefined,
  b: PlanLike | null | undefined,
  plans: PlanLike[] = [],
  currentPlanId?: string | null,
) {
  if (!a || !b) return false;
  if (currentPlanId && b.id && String(currentPlanId) === String(b.id)) return true;
  if (a.id && b.id && String(a.id) === String(b.id)) return true;
  if (plans.length) {
    const ai = findPlanIndex(plans, a, currentPlanId);
    const bi = findPlanIndex(plans, b, currentPlanId);
    if (ai >= 0 && bi >= 0 && ai === bi) return true;
  }
  return String(a.code || "").toLowerCase() === String(b.code || "").toLowerCase();
}

export function planButtonLabel(
  plan: PlanLike,
  currentPlan: PlanLike | null | undefined,
  opts?: {
    busy?: boolean;
    plans?: PlanLike[];
    currentPlanId?: string | null;
    pendingPlanId?: string | null;
  },
) {
  if (opts?.busy) return "Redirecting to GoCardless…";
  if (plan.is_enterprise) return "Contact us";
  if (opts?.pendingPlanId && plan.id && String(opts.pendingPlanId) === String(plan.id)) {
    return "Downgrade scheduled";
  }
  const plans = opts?.plans || [];
  const currentPlanId = opts?.currentPlanId ?? null;
  if (currentPlan && plans.length) {
    const curIdx = findPlanIndex(plans, currentPlan, currentPlanId);
    const idx = findPlanIndex(plans, plan);
    if (curIdx >= 0 && idx >= 0) {
      if (idx === curIdx) return "Current plan";
      if (idx > curIdx) return `Upgrade to ${plan.name}`;
      if (idx < curIdx) return `Downgrade to ${plan.name}`;
    }
  }
  if (!currentPlan) return `Subscribe to ${plan.name}`;
  if (isSamePlan(plan, currentPlan, plans, currentPlanId)) return "Current plan";
  const oldRank = planRank(currentPlan);
  const newRank = planRank(plan);
  if (newRank > oldRank) return `Upgrade to ${plan.name}`;
  if (newRank < oldRank) return `Downgrade to ${plan.name}`;
  return `Switch to ${plan.name}`;
}

export function feedbackPlanButtonLabel(
  pkg: FeedbackPlanLike,
  packages: FeedbackPlanLike[],
  opts?: {
    busy?: boolean;
    currentPlanId?: string | null;
    pendingPlanId?: string | null;
  },
) {
  const name = pkg.plan_name || pkg.plan_code || "plan";
  if (opts?.busy) return "Redirecting to GoCardless…";
  if (!pkg.plan_id) return `Choose ${name}`;
  if (opts?.pendingPlanId && pkg.plan_id && String(opts.pendingPlanId) === String(pkg.plan_id)) {
    return "Downgrade scheduled";
  }
  if (!opts?.currentPlanId) return `Subscribe to ${name}`;
  if (opts.currentPlanId === pkg.plan_id) return "Current plan";
  const sorted = [...packages].sort((a, b) => feedbackPlanRank(a) - feedbackPlanRank(b));
  const curIdx = sorted.findIndex((p) => p.plan_id === opts.currentPlanId);
  const idx = sorted.findIndex((p) => p.plan_id === pkg.plan_id);
  if (curIdx >= 0 && idx >= 0) {
    if (idx === curIdx) return "Current plan";
    if (idx > curIdx) return `Upgrade to ${name}`;
    if (idx < curIdx) return `Downgrade to ${name}`;
  }
  return `Switch to ${name}`;
}

export function sortedPlans<T extends PlanLike>(plans: T[]) {
  return [...plans].sort(
    (a, b) => planRank(a) - planRank(b) || String(a.name || "").localeCompare(String(b.name || "")),
  );
}

export function planChangeToast(
  direction: string | undefined,
  planName: string,
  opts?: { awaitingAdmin?: boolean },
): string {
  if (opts?.awaitingAdmin) return `Plan change to ${planName} submitted — awaiting admin approval.`;
  if (direction === "upgrade") return `Upgraded to ${planName}. Pro-rata charge may apply via Direct Debit.`;
  if (direction === "downgrade") return `Downgrade to ${planName} scheduled for the end of your billing period.`;
  if (direction === "same") return `You are already on ${planName}.`;
  return `Plan updated to ${planName}.`;
}
