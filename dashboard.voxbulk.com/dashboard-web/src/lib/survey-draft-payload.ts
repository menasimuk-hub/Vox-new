import { normalizeSurveyName } from "@/lib/survey-title";

/**
 * Survey draft save shape.
 * - survey_name is the user-facing campaign name (Step 1 field).
 * - title is NOT sent from the dashboard; API mirrors survey_name → service_orders.title.
 */
export type SurveyDraftConfigPatch = Record<string, unknown> & {
  survey_name: string;
};

export type SurveyDraftPatchBody = {
  scheduled_start_at?: string | null;
  scheduled_end_at?: string | null;
  run_mode?: "manual" | "scheduled";
  config: SurveyDraftConfigPatch;
};

export type SurveyDraftCreateBody = {
  service_code: "survey";
  config: SurveyDraftConfigPatch & {
    goal?: string;
    delivery?: string;
    anonymous_responses?: boolean;
    script?: string;
    package_id?: string;
  };
};

/** Normalize Step 1 survey name for persistence. */
export function resolveSurveyNameForSave(surveyName: string): string {
  return normalizeSurveyName(surveyName);
}

/** Build PATCH body — config.survey_name only; no top-level title. */
export function buildSurveyDraftPatchBody(
  surveyName: string,
  config: Record<string, unknown>,
  extras?: Omit<SurveyDraftPatchBody, "config">,
): SurveyDraftPatchBody {
  const survey_name = resolveSurveyNameForSave(surveyName);
  return {
    ...extras,
    config: {
      ...config,
      survey_name,
    },
  };
}

/** Build POST body for first create — survey_name in config; API sets legacy title. */
export function buildSurveyDraftCreateBody(
  surveyName: string,
  config: Record<string, unknown>,
): SurveyDraftCreateBody {
  const survey_name = resolveSurveyNameForSave(surveyName);
  return {
    service_code: "survey",
    config: {
      ...config,
      survey_name,
    },
  };
}
