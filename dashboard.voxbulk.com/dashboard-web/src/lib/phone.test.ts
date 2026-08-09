import { describe, expect, it } from "vitest";

import { dialPrefixForOrg, ensurePhoneCountryCode, orgDialRegion } from "./phone";

describe("orgDialRegion / dialPrefixForOrg", () => {
  it("uses ISO country_code when present", () => {
    expect(orgDialRegion("United Kingdom", "AE")).toBe("AE");
    expect(dialPrefixForOrg(null, "AU")).toBe("+61");
  });

  it("maps country names and defaults to GB", () => {
    expect(orgDialRegion("Australia", null)).toBe("AU");
    expect(orgDialRegion(null, null)).toBe("GB");
    expect(dialPrefixForOrg("United Arab Emirates", null)).toBe("+971");
  });
});

describe("ensurePhoneCountryCode", () => {
  it("leaves empty and already-international numbers alone", () => {
    expect(ensurePhoneCountryCode("")).toBe("");
    expect(ensurePhoneCountryCode("+447911123456")).toBe("+447911123456");
    expect(ensurePhoneCountryCode("00447911123456")).toBe("+447911123456");
  });

  it("prepends dial for local numbers and strips trunk 0", () => {
    expect(ensurePhoneCountryCode("07911123456", "+44")).toBe("+447911123456");
    expect(ensurePhoneCountryCode("7911123456", "+44")).toBe("+447911123456");
    expect(ensurePhoneCountryCode("501234567", "+971")).toBe("+971501234567");
  });

  it("does not double the dial digits", () => {
    expect(ensurePhoneCountryCode("447911123456", "+44")).toBe("+447911123456");
  });
});
