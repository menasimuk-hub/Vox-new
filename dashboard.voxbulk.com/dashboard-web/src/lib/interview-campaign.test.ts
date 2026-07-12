import { describe, expect, it } from "vitest";

import {
  bookingInvitesWereSent,
  candidatePhoneBlocksLaunch,
  isInterviewCampaignLaunched,
} from "./interview-campaign";
import { describeInterviewLaunchResult, launchResultHasOutbound } from "./interviewLaunchFeedback";

describe("isInterviewCampaignLaunched", () => {
  it("treats scheduled/running as launched", () => {
    expect(isInterviewCampaignLaunched("scheduled")).toBe(true);
    expect(isInterviewCampaignLaunched("running")).toBe(true);
  });

  it("does not treat bare paid as launched without invites when config is provided", () => {
    expect(
      isInterviewCampaignLaunched("paid", {
        paymentStatus: "approved",
        config: {},
      }),
    ).toBe(false);
  });

  it("treats paid + approved as launched when config is omitted (results/resend)", () => {
    expect(
      isInterviewCampaignLaunched("paid", {
        paymentStatus: "approved",
      }),
    ).toBe(true);
  });

  it("treats paid + invites as launched", () => {
    expect(
      isInterviewCampaignLaunched("paid", {
        paymentStatus: "approved",
        config: { booking_invites_sent_at: "2026-07-01T12:00:00" },
      }),
    ).toBe(true);
  });
});

describe("bookingInvitesWereSent", () => {
  it("counts partial dispatch with WhatsApp only", () => {
    expect(
      bookingInvitesWereSent({
        last_invite_dispatch: { ok: false, email_sent: 0, whatsapp_sent: 2 },
      }),
    ).toBe(true);
  });

  it("is false when nothing was sent", () => {
    expect(
      bookingInvitesWereSent({
        last_invite_dispatch: { ok: false, email_sent: 0, whatsapp_sent: 0 },
      }),
    ).toBe(false);
  });
});

describe("candidatePhoneBlocksLaunch", () => {
  it("allows empty phone (email-only)", () => {
    expect(candidatePhoneBlocksLaunch({ phone: "" })).toBeNull();
  });

  it("blocks too-short numbers", () => {
    expect(candidatePhoneBlocksLaunch({ phone: "123" })).toMatch(/E\.164/);
  });

  it("blocks allowlist reasons when present", () => {
    expect(
      candidatePhoneBlocksLaunch({
        phone: "+447700900123",
        phoneCallAllowed: false,
        phoneCallBlockReason: "Region not allowed",
      }),
    ).toBe("Region not allowed");
  });
});

describe("launch feedback", () => {
  it("marks already-live when WhatsApp sent without email", () => {
    const result = {
      ok: false,
      already_launched: true,
      invites: { email_sent: 0, whatsapp_sent: 1, errors: ["SMTP disabled"] },
      message: "Campaign is live but invite delivery was incomplete.",
    };
    expect(launchResultHasOutbound(result)).toBe(true);
    expect(describeInterviewLaunchResult(result).tone).toBe("warning");
  });

  it("errors when nothing was sent", () => {
    const result = {
      ok: false,
      already_launched: false,
      invites: { email_sent: 0, whatsapp_sent: 0, errors: ["bad phone"] },
    };
    expect(launchResultHasOutbound(result)).toBe(false);
    expect(describeInterviewLaunchResult(result).tone).toBe("error");
  });
});
