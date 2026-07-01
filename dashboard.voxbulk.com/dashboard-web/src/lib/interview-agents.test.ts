import { describe, expect, it } from "vitest";

import {
  agentRegionCode,
  buildRegionMenuOptions,
  interviewAgentDisplayName,
  resolveInterviewAgentDialect,
} from "./interview-agents";
import { regionMenuLabel, regionFlagImageUrl } from "./interview-agent-regions";
import type { InterviewAgent } from "@/lib/queries";

describe("resolveInterviewAgentDialect", () => {
  it("maps Sultan to SA Gulf", () => {
    const d = resolveInterviewAgentDialect({ id: "1", name: "Sultan", voice_label: "Sultan", language: "ar" });
    expect(d.dialect_code).toBe("SA");
    expect(d.dialect_label).toContain("Saudi");
  });

  it("maps Jammal - Ar to EG", () => {
    const d = resolveInterviewAgentDialect({
      id: "2",
      name: "Jammal - Ar",
      voice_label: "Jammal",
      language: "ar",
    });
    expect(d.dialect_code).toBe("EG");
  });

  it("uses accent_region for US agents", () => {
    const d = resolveInterviewAgentDialect({
      id: "3",
      name: "interview_US-Elena",
      voice_label: "Elena",
      accent_region: "US",
      flag_emoji: "🇺🇸",
      language: "en",
    });
    expect(d.dialect_code).toBe("US");
    expect(d.flag_emoji).toBe("🇺🇸");
  });
});

describe("interviewAgentDisplayName", () => {
  it("strips - Ar suffix", () => {
    expect(interviewAgentDisplayName({ id: "2", name: "Jammal - Ar" })).toBe("Jammal");
  });
});

describe("buildRegionMenuOptions", () => {
  it("builds English (GB) and English (US) labels with flags", () => {
    const agents: InterviewAgent[] = [
      { id: "1", name: "interview_GB-Leo", accent_region: "GB", language: "en" },
      { id: "2", name: "interview_US-Marcus", accent_region: "US", language: "en" },
    ];
    const options = buildRegionMenuOptions(agents);
    expect(options.map((o) => o.label)).toEqual(["English (GB)", "English (US)"]);
    expect(options[0]?.flagEmoji).toBe("🇬🇧");
  });

  it("includes Arabic regions", () => {
    const agents: InterviewAgent[] = [{ id: "3", name: "Sultan", accent_region: "SA", language: "ar" }];
    const options = buildRegionMenuOptions(agents);
    expect(options[0]?.label).toBe("Arabic (SA)");
    expect(options[0]?.language).toBe("ar");
  });
});

describe("regionMenuLabel", () => {
  it("formats English and Arabic menu labels", () => {
    expect(regionMenuLabel("GB")).toBe("English (GB)");
    expect(regionMenuLabel("IE")).toBe("English (IE)");
    expect(regionMenuLabel("SA")).toBe("Arabic (SA)");
  });
});

describe("regionFlagImageUrl", () => {
  it("returns flagcdn URL for Scotland only", () => {
    expect(regionFlagImageUrl("SC")).toContain("gb-sct");
    expect(regionFlagImageUrl("GB")).toBeNull();
  });
});

describe("agentRegionCode", () => {
  it("prefers accent_region", () => {
    expect(agentRegionCode({ id: "1", name: "x", accent_region: "CA" })).toBe("CA");
  });
});
