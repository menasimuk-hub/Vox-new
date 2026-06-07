import { describe, expect, it } from "vitest";

import { buildFullSurveyDraftConfig, hydrateSurveyDraftFromOrder } from "./survey-draft-config";
import {
  billingCheckErrorMessage,
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
});
