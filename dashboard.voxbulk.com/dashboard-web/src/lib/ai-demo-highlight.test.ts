import { describe, expect, it } from "vitest";

import { parseDemoRoute } from "./ai-demo-highlight";

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
