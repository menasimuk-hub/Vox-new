import { describe, expect, it } from "vitest";

import { buildFullSurveyDraftConfig, hydrateSurveyDraftFromOrder } from "./survey-draft-config";
import {
  billingCheckErrorMessage,
  buildLaunchPricingBreakdown,
  buildWhatsAppAllowanceNotice,
  mapBillingBlockReason,
  resolveBillingCheckPhase,
} from "./survey-launch-billing";

describe("buildFullSurveyDraftConfig", () => {
  it("persists wizard + builder fields together", () => {
    const config = buildFullSurveyDraftConfig(
      {
        channel: "whatsapp",
        goal: "Measure satisfaction",
        script: "Question 1",
        anonymous: false,
        packageId: "pkg-1",
        industryId: "ind-1",
        primarySurveyTypeId: "type-1",
        orderedServiceTagIds: ["type-1", "type-2"],
        selectedServiceTagIds: ["type-1"],
        selectedServiceTemplateIds: { "type-1": "101", "type-2": "102" },
        welcomeTemplateId: "10",
        thankYouTemplateId: "11",
        pageCount: 5,
        privacyMode: "off",
        surveyVariant: "standard",
        allowFinalAdditionalFeedback: true,
        autoSelectSteps: true,
        resolvedPageRoles: ["start", "rating", "completion"],
        approved: true,
        waPreview: {
          builder_step_sequence: [{ step_role: "rating", text: "Rate us" }],
          builder_template_ids: [10, 101, 11],
        },
      },
      { package_id: "legacy-pkg" },
    );

    expect(config.goal).toBe("Measure satisfaction");
    expect(config.selected_survey_type_ids).toEqual(["type-1", "type-2"]);
    expect(config.selected_service_template_ids).toEqual({ "type-1": 101, "type-2": 102 });
    expect(config.allow_final_additional_feedback).toBe(true);
    expect(config.builder_step_sequence).toEqual([{ step_role: "rating", text: "Rate us" }]);
    expect(config.package_id).toBe("pkg-1");
  });

  it("persists phone survey approval fields", () => {
    const config = buildFullSurveyDraftConfig(
      {
        channel: "phone",
        goal: "NPS check",
        script: "INTRO\nHi\n\nQUESTIONS\n1. Score?\n\nCLOSING\nThanks",
        anonymous: true,
        packageId: "pkg-phone",
        industryId: "",
        primarySurveyTypeId: "",
        orderedServiceTagIds: [],
        selectedServiceTagIds: [],
        selectedServiceTemplateIds: {},
        welcomeTemplateId: "",
        thankYouTemplateId: "",
        pageCount: 4,
        privacyMode: "off",
        surveyVariant: "standard",
        allowFinalAdditionalFeedback: false,
        autoSelectSteps: true,
        resolvedPageRoles: [],
        waPreview: null,
        approved: true,
        agentId: "agent-1",
        systemPrompt: "Be concise.",
        expectedDurationMinutes: 3,
      },
      {},
    );

    expect(config.survey_channel).toBe("ai_call");
    expect(config.script_approved).toBe(true);
    expect(config.approved_script).toContain("QUESTIONS");
    expect(config.agent_id).toBe("agent-1");
    expect(config.system_prompt).toBe("Be concise.");
    expect(config.estimated_duration_min).toBe(3);
  });
});

describe("hydrateSurveyDraftFromOrder", () => {
  it("restores saved survey settings", () => {
    const hydrated = hydrateSurveyDraftFromOrder({
      survey_name: "Campaign A",
      config: {
        goal: "Goal text",
        industry_id: "ind-1",
        selected_survey_type_ids: ["type-1"],
        selected_service_template_ids: { "type-1": 55 },
        welcome_template_id: 10,
        thank_you_template_id: 11,
        page_count: 4,
        privacy_mode: "on",
        allow_final_additional_feedback: true,
        auto_select_steps: false,
        page_roles: ["start", "rating", "completion"],
        builder_step_sequence: [{ step_role: "rating", text: "Rate us" }],
        delivery: "whatsapp",
      },
    });

    expect(hydrated.surveyName).toBe("Campaign A");
    expect(hydrated.orderedServiceTagIds).toEqual(["type-1"]);
    expect(hydrated.selectedServiceTemplateIds).toEqual({ "type-1": "55" });
    expect(hydrated.pageCount).toBe(4);
    expect(hydrated.approved).toBe(true);
    expect(hydrated.channel).toBe("whatsapp");
  });

  it("restores phone survey script and agent fields", () => {
    const hydrated = hydrateSurveyDraftFromOrder({
      survey_name: "Phone survey",
      scheduled_start_at: "2026-06-10T09:00:00Z",
      scheduled_end_at: "2026-06-10T17:00:00Z",
      config: {
        goal: "Feedback",
        delivery: "ai_call",
        approved_script: "INTRO\nHello\n\nQUESTIONS\n1. How was it?\n\nCLOSING\nThanks",
        script_approved: true,
        agent_id: "agent-survey-1",
        system_prompt: "Survey tone",
        estimated_duration_min: 4,
      },
    });

    expect(hydrated.channel).toBe("phone");
    expect(hydrated.approved).toBe(true);
    expect(hydrated.agentId).toBe("agent-survey-1");
    expect(hydrated.script).toContain("How was it?");
    expect(hydrated.expectedDurationMinutes).toBe(4);
  });
});

describe("survey launch billing UI helpers", () => {
  it("maps block reason codes to user-facing messages", () => {
    expect(mapBillingBlockReason({ block_reason_code: "package_not_found", block_reason: "x", summary: "y" })).toBe(
      "Package not found.",
    );
    expect(mapBillingBlockReason({ block_reason_code: "billing_check_timeout", block_reason: "x", summary: "y" })).toBe(
      "Billing check timed out.",
    );
  });

  it("resolves checking phase while fetch is in flight", () => {
    expect(
      resolveBillingCheckPhase({
        orderId: "ord-1",
        launchOpen: true,
        isLoading: false,
        isFetching: true,
        isError: false,
        errorMessage: null,
        hasData: false,
        timedOut: false,
      }),
    ).toBe("checking");
  });

  it("shows timeout error message", () => {
    expect(billingCheckErrorMessage("timeout", null, "ord-1", null)).toBe("Billing check timed out.");
  });

  it("keeps ready phase when cached data exists during refetch", () => {
    expect(
      resolveBillingCheckPhase({
        orderId: "ord-1",
        launchOpen: true,
        isLoading: false,
        isFetching: true,
        isError: false,
        errorMessage: null,
        hasData: true,
        timedOut: false,
      }),
    ).toBe("ready");
  });

  it("builds whatsapp allowance notice from live-like payload", () => {
    const notice = buildWhatsAppAllowanceNotice({
      mode: "subscription_overage",
      summary:
        "Plan includes: 86 WA survey recipients/month. Extra recipients: £0.49 each after allowance is used.",
      extra_recipients: 1,
      extra_cost_display: "£0.49",
      wa_survey_extra_display: "£0.49",
      payment_required: false,
      billing: {
        whatsapp_included: 86,
        whatsapp_used: 124,
        whatsapp_remaining: 0,
        has_whatsapp_allowance: true,
      },
    });
    expect(notice).toContain("Plan includes:");
    expect(notice).toContain("Extra recipients:");
  });

  it("builds explicit pricing breakdown lines", () => {
    const breakdown = buildLaunchPricingBreakdown({
      payment_required: true,
      amount_due_display: "£0.49",
      wa_survey_extra_display: "£0.49",
      billing: { whatsapp_included: 118, has_whatsapp_allowance: true },
    });
    expect(breakdown?.planIncludes).toContain("118");
    expect(breakdown?.extraRecipientsLine).toContain("£0.49");
    expect(breakdown?.interviewWhatsApp).toContain("included");
    expect(breakdown?.aiPhoneSurvey).toContain("connection + minutes");
    expect(breakdown?.totalDue).toBe("£0.49");
  });
});
