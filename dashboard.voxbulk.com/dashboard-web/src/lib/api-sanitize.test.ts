import { describe, expect, it } from "vitest";

import { sanitizeUserError } from "./api";

describe("sanitizeUserError", () => {
  it("does not map WA survey send failures to the voice preview hint", () => {
    const message =
      "Could not send the welcome message. Check Telnyx settings and template approval.";
    expect(sanitizeUserError(message, "/dashboard/service-scripts/wa-survey/send-test")).toBe(
      "Could not send the welcome message. Check WhatsApp settings and template approval.",
    );
  });

  it("keeps the voice preview hint for voice preview endpoints", () => {
    const message = "Telnyx API error: invalid assistant";
    expect(sanitizeUserError(message, "/dashboard/agents/voice-preview")).toBe(
      "Voice preview unavailable — check the Assistant ID and ElevenLabs voice in Admin → Agents.",
    );
  });

  it("passes through provider-neutral WhatsApp errors unchanged", () => {
    const message =
      "Could not send the WhatsApp message. Check Admin → Connection Profiles and template approval.";
    expect(sanitizeUserError(message, "/dashboard/service-scripts/wa-survey/send-test")).toBe(message);
  });
});
