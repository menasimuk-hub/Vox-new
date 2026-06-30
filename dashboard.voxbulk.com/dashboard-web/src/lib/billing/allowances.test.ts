import { describe, expect, it } from "vitest";

import { allowanceAlertsToItems } from "@/components/billing/billing-smart-alerts";
import { formatAllowancePeriod, formatRemaining, groupAllowancesByProduct, pickAllowances } from "./allowances";
import type { AllowanceRow } from "./allowances";

const CORE_ROWS: AllowanceRow[] = [
  { product: "core", key: "calls", label: "AI call minutes", used: 42, included: 500, remaining: 458, unit: "min" },
  { product: "core", key: "whatsapp", label: "WA survey recipients", used: 10, included: 200, remaining: 190, unit: "recipients" },
];

describe("formatRemaining", () => {
  it("shows unlimited for unlimited rows", () => {
    expect(formatRemaining({ ...CORE_ROWS[0], unlimited: true, included: 0 })).toBe("Unlimited");
  });

  it("shows pay per use when no included allowance", () => {
    expect(formatRemaining({ ...CORE_ROWS[0], included: 0, remaining: null })).toBe("Pay per use");
  });
});

describe("groupAllowancesByProduct", () => {
  it("splits core and feedback", () => {
    const grouped = groupAllowancesByProduct([
      ...CORE_ROWS,
      { product: "feedback", key: "feedback_wa", label: "WA", used: 1, included: 100, remaining: 99, unit: "responses" },
    ]);
    expect(grouped.core).toHaveLength(2);
    expect(grouped.feedback).toHaveLength(1);
  });
});

describe("pickAllowances", () => {
  it("returns rows in key order", () => {
    const picked = pickAllowances(CORE_ROWS, ["whatsapp", "calls"]);
    expect(picked.map((r) => r.key)).toEqual(["whatsapp", "calls"]);
  });
});

describe("formatAllowancePeriod", () => {
  it("formats start and end", () => {
    const label = formatAllowancePeriod("2026-06-01T00:00:00", "2026-06-30T00:00:00");
    expect(label).toContain("–");
  });
});

describe("allowanceAlertsToItems", () => {
  it("maps warning alerts to amber tone", () => {
    const items = allowanceAlertsToItems([
      { key: "calls", level: "warning", message: "Running low on AI call minutes", pct_used: 82 },
    ]);
    expect(items[0].tone).toBe("warning");
    expect(items[0].title).toContain("Running low");
  });

  it("maps critical alerts to destructive tone", () => {
    const items = allowanceAlertsToItems([
      { key: "whatsapp", level: "critical", message: "WA survey recipients allowance used up", pct_used: 100 },
    ]);
    expect(items[0].tone).toBe("destructive");
  });
});

describe("dual product layout", () => {
  it("has both core and feedback rows for dual-product orgs", () => {
    const grouped = groupAllowancesByProduct([
      ...CORE_ROWS,
      { product: "feedback", key: "feedback_wa", label: "WA responses", used: 18, included: 500, remaining: 482, unit: "responses" },
      { product: "feedback", key: "feedback_web", label: "Web surveys", used: 2, included: 0, remaining: null, unit: "surveys", unlimited: true },
    ]);
    expect(grouped.core.length).toBeGreaterThan(0);
    expect(grouped.feedback.length).toBe(2);
  });
});
