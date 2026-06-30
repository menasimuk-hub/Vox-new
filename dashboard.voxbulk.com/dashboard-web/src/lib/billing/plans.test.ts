import { describe, expect, it } from "vitest";

import { findCurrentPlanIndex, findPlanIndex, isSamePlan, planButtonLabel, subscribePlanLabel } from "./plans";

const PAYG_PLAN = { id: "plan-payg", code: "payg", name: "Pay as you go", sort_order: 0 };

const CORE_PLANS = [
  { id: "plan-starter", code: "starter", name: "Starter", sort_order: 1 },
  { id: "plan-growth", code: "growth", name: "Growth", sort_order: 2 },
  { id: "plan-pro", code: "pro", name: "Pro", sort_order: 3 },
];

describe("isSamePlan", () => {
  it("does not treat every card as current when session plan is outside the catalog", () => {
    const feedbackPlan = { id: "cf-starter-id", code: "cf_starter_gb", name: "Feedback Starter" };
    for (const core of CORE_PLANS) {
      expect(isSamePlan(core, feedbackPlan, CORE_PLANS, "cf-starter-id")).toBe(false);
    }
  });

  it("matches the same core plan by id", () => {
    const growth = CORE_PLANS[1];
    expect(isSamePlan(growth, growth, CORE_PLANS, "plan-starter")).toBe(true);
  });

  it("matches plans in the same catalog slot by code", () => {
    expect(isSamePlan(CORE_PLANS[0], { code: "starter" }, CORE_PLANS)).toBe(true);
  });
});

describe("findCurrentPlanIndex", () => {
  it("prefers currentPlanId when it exists in the catalog", () => {
    expect(findCurrentPlanIndex(CORE_PLANS, null, "plan-growth")).toBe(1);
  });

  it("falls back to currentPlan object when id is not in catalog", () => {
    const feedbackPlan = { id: "cf-starter-id", code: "cf_starter_gb", name: "Feedback Starter" };
    expect(findCurrentPlanIndex(CORE_PLANS, feedbackPlan, "cf-starter-id")).toBe(-1);
  });
});

describe("planButtonLabel", () => {
  it("shows subscribe labels when current plan is not in core catalog", () => {
    const feedbackPlan = { id: "cf-starter-id", code: "cf_starter_gb", name: "Feedback Starter", sort_order: 0 };
    expect(planButtonLabel(CORE_PLANS[0], feedbackPlan, { plans: CORE_PLANS, currentPlanId: "cf-starter-id" })).toBe(
      "Subscribe to Starter",
    );
    expect(planButtonLabel(CORE_PLANS[2], feedbackPlan, { plans: CORE_PLANS, currentPlanId: "cf-starter-id" })).toBe(
      "Subscribe to Pro",
    );
  });

  it("shows current plan for the active core subscription", () => {
    expect(
      planButtonLabel(CORE_PLANS[1], CORE_PLANS[1], { plans: CORE_PLANS, currentPlanId: "plan-growth" }),
    ).toBe("Current plan");
  });

  it("shows current plan on pending target when it is also the active plan", () => {
    expect(
      planButtonLabel(CORE_PLANS[0], CORE_PLANS[0], {
        plans: CORE_PLANS,
        currentPlanId: "plan-starter",
        pendingPlanId: "plan-starter",
      }),
    ).toBe("Current plan");
  });

  it("uses short PAYG subscribe label", () => {
    expect(subscribePlanLabel(PAYG_PLAN)).toBe("Subscribe PAYG");
    expect(planButtonLabel(PAYG_PLAN, null, { plans: [PAYG_PLAN, ...CORE_PLANS] })).toBe("Subscribe PAYG");
  });
});

describe("findPlanIndex", () => {
  it("returns -1 for plans not in the list", () => {
    expect(findPlanIndex(CORE_PLANS, { id: "missing", code: "cf_starter_gb" })).toBe(-1);
  });
});
