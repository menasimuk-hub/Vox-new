import { describe, expect, it } from "vitest";

import {
  SURVEY_TYPE_LIBRARY_PRIVACY_MODE,
  filterActiveSurveyTemplates,
  filterApprovedSurveyTemplates,
  filterSelectableSurveyTemplates,
  filterSystemTemplatesByPrivacy,
} from "./wa-survey-template-mode";

describe("wa-survey-template-mode", () => {
  const rows = [
    { id: 1, name: "Named welcome", privacy_mode: "off", variant_type: "standard", is_approved: true },
    { id: 2, name: "Anonymous welcome", privacy_mode: "on", variant_type: "anonymous", is_approved: true },
  ];

  it("filters global system templates by anonymous vs named mode", () => {
    expect(filterSystemTemplatesByPrivacy(rows, "off").map((r) => r.id)).toEqual([1]);
    expect(filterSystemTemplatesByPrivacy(rows, "on").map((r) => r.id)).toEqual([2]);
  });

  it("keeps survey-type library templates on named mode regardless of wizard privacy", () => {
    expect(SURVEY_TYPE_LIBRARY_PRIVACY_MODE).toBe("off");
  });

  it("drops templates hidden from surveys", () => {
    const mixed = [
      { id: 1, active_for_survey: true, is_approved: true },
      { id: 2, active_for_survey: false },
      { id: 3 },
    ];
    expect(filterActiveSurveyTemplates(mixed).map((r) => r.id)).toEqual([1, 3]);
    expect(filterSystemTemplatesByPrivacy([{ id: 1, privacy_mode: "off", active_for_survey: false, is_approved: true }], "off")).toEqual([]);
  });

  it("filterSelectableSurveyTemplates hides disabled and unapproved rows", () => {
    const rows = [
      { id: 1, active_for_survey: true, is_approved: true },
      { id: 2, active_for_survey: true, is_approved: false },
      { id: 3, active_for_survey: false, approval_status: "APPROVED" },
      { id: 4, active_for_survey: true, approval_status: "PENDING" },
      { id: 5, active_for_survey: true, approval_status: "APPROVED" },
    ];
    expect(filterSelectableSurveyTemplates(rows).map((r) => r.id)).toEqual([1, 5]);
  });
});
