import { describe, expect, it } from "vitest";

import { interviewAgentDisplayName, resolveInterviewAgentDialect } from "./interview-agents";
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
