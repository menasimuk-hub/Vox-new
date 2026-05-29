export type PlanLike = {
  id?: string;
  code?: string;
  name?: string;
  sort_order?: number;
  price_gbp_pence?: number;
  is_enterprise?: boolean;
  is_featured?: boolean;
};

export function planRank(plan: PlanLike | null | undefined) {
  return Number(plan?.sort_order || 0) * 1_000_000 + Number(plan?.price_gbp_pence || 0);
}

export function findPlanIndex(plans: PlanLike[], plan: PlanLike | null | undefined) {
  if (!plan) return -1;
  const byId = plans.findIndex((p) => p.id && plan.id && String(p.id) === String(plan.id));
  if (byId >= 0) return byId;
  return plans.findIndex((p) => String(p.code || "").toLowerCase() === String(plan.code || "").toLowerCase());
}

export function isSamePlan(a: PlanLike | null | undefined, b: PlanLike | null | undefined, plans: PlanLike[] = []) {
  if (!a || !b) return false;
  if (a.id && b.id && String(a.id) === String(b.id)) return true;
  if (plans.length) {
    const ai = findPlanIndex(plans, a);
    const bi = findPlanIndex(plans, b);
    if (ai >= 0 && bi >= 0 && ai === bi) return true;
  }
  return String(a.code || "").toLowerCase() === String(b.code || "").toLowerCase();
}

export function planButtonLabel(
  plan: PlanLike,
  currentPlan: PlanLike | null | undefined,
  opts?: { busy?: boolean; plans?: PlanLike[] },
) {
  if (opts?.busy) return "Redirecting to GoCardless…";
  if (plan.is_enterprise) return "Contact us";
  const plans = opts?.plans || [];
  if (currentPlan && plans.length) {
    const curIdx = findPlanIndex(plans, currentPlan);
    const idx = findPlanIndex(plans, plan);
    if (curIdx >= 0 && idx >= 0) {
      if (idx === curIdx) return "Current plan";
      if (idx > curIdx) return `Upgrade to ${plan.name}`;
      if (idx < curIdx) return `Downgrade to ${plan.name}`;
    }
  }
  if (!currentPlan) return `Subscribe to ${plan.name}`;
  if (isSamePlan(plan, currentPlan, plans)) return "Current plan";
  const oldRank = planRank(currentPlan);
  const newRank = planRank(plan);
  if (newRank > oldRank) return `Upgrade to ${plan.name}`;
  if (newRank < oldRank) return `Downgrade to ${plan.name}`;
  return `Switch to ${plan.name}`;
}

export function sortedPlans<T extends PlanLike>(plans: T[]) {
  return [...plans].sort(
    (a, b) => planRank(a) - planRank(b) || String(a.name || "").localeCompare(String(b.name || "")),
  );
}
