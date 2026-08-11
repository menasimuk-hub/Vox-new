import { describe, expect, it } from "vitest";

import { openPricingTabPath, parseDemoRoute, pricingTabForService } from "./ai-demo-highlight";

describe("pricingTabForService", () => {
  it("maps product codes to packages tabs", () => {
    expect(pricingTabForService("feedback")).toBe("feedback");
    expect(pricingTabForService("customer_feedback")).toBe("feedback");
    expect(pricingTabForService("expo")).toBe("expo");
    expect(pricingTabForService("smart_card")).toBe("smartCard");
    expect(pricingTabForService("recruitment")).toBe("core");
    expect(pricingTabForService("surveys")).toBe("core");
    expect(pricingTabForService(undefined)).toBe("core");
  });

  it("builds packages deep links", () => {
    expect(openPricingTabPath("feedback")).toBe("/account/packages?tab=feedback");
    expect(openPricingTabPath("smart-card")).toBe("/account/packages?tab=smartCard");
  });
});

describe("parseDemoRoute", () => {
  it("splits path and query for pricing navigation", () => {
    expect(parseDemoRoute("/account/packages?tab=feedback")).toEqual({
      pathname: "/account/packages",
      search: { tab: "feedback" },
    });
  });

  it("normalizes bare paths", () => {
    expect(parseDemoRoute("feedback")).toEqual({ pathname: "/feedback", search: {} });
  });
});
