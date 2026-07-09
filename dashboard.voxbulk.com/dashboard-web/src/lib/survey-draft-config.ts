/**
 * Build and restore the full survey draft config for PATCH /service-orders.
 * Wizard state wins for editable fields; generated builder artifacts are preserved
 * from waPreview or the last persisted order config.
 */

import type { AiFollowUpConfig } from "@/components/ai-follow-up-step";
import { aiFollowUpFromApi, aiFollowUpToApi } from "@/components/ai-follow-up-step";

export type SurveyDraftWizardSnapshot = {
  channel: "whatsapp" | "phone" | null;
  goal: string;
  script: string;
  anonymous: boolean;
  packageId: string;
  industryId: string;
  primarySurveyTypeId: string;
  orderedServiceTagIds: string[];
  selectedServiceTagIds: string[];
  selectedServiceTemplateIds: Record<string, string>;
  welcomeTemplateId: string;
  thankYouTemplateId: string;
  pageCount: 3 | 4 | 5 | 6;
  privacyMode: "off" | "on";
  surveyVariant: "standard" | "anonymous";
  allowFinalAdditionalFeedback: boolean;
  autoSelectSteps: boolean;
  resolvedPageRoles: string[];
  waPreview: Record<string, unknown> | null;
  approved: boolean;
  agentId?: string;
  systemPrompt?: string;
  expectedDurationMinutes?: number;
  aiFollowUp?: AiFollowUpConfig;
};

const BUILDER_PERSIST_KEYS = [
  "builder_runtime",
  "builder_runtime_hash",
  "builder_step_sequence",
  "builder_template_ids",
  "wa_template_id",
  "whatsapp_flow",
  "tell_us_more_template_id",
  "flow_engine",
  "flow_definition_id",
  "flow_snapshot",
  "flow_snapshot_json",
  "order_config_flow",
  "page_roles",
  "allow_follow_up",
] as const;

const PAGE_COUNT_TO_LENGTH: Record<3 | 4 | 5 | 6, "short" | "standard" | "detailed"> = {
  3: "short",
  4: "short",
  5: "standard",
  6: "detailed",
};

function compactRecord(input: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(input)) {
    if (value === undefined) continue;
    out[key] = value;
  }
  return out;
}

function selectedServiceTemplateIdsNumeric(
  selected: Record<string, string>,
): Record<string, number> | undefined {
  const out: Record<string, number> = {};
  for (const [typeId, raw] of Object.entries(selected)) {
    const num = Number(raw);
    if (Number.isFinite(num) && num > 0) out[typeId] = num;
  }
  return Object.keys(out).length ? out : undefined;
}

function pickBuilderFields(
  waPreview: Record<string, unknown> | null | undefined,
  persisted: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const source = waPreview || persisted || {};
  const out: Record<string, unknown> = {};
  for (const key of BUILDER_PERSIST_KEYS) {
    if (source[key] !== undefined && source[key] !== null) {
      out[key] = source[key];
    }
  }
  return out;
}

/** Merge wizard state + generated/persisted builder fields into one config patch. */
export function buildFullSurveyDraftConfig(
  wizard: SurveyDraftWizardSnapshot,
  persistedConfig?: Record<string, unknown> | null,
  options?: { organisationName?: string },
): Record<string, unknown> {
  const persisted = persistedConfig || {};
  const builder = pickBuilderFields(wizard.waPreview, persisted);
  const typeIds = wizard.orderedServiceTagIds.length
    ? wizard.orderedServiceTagIds
    : wizard.selectedServiceTagIds;
  const selectedTemplates = selectedServiceTemplateIdsNumeric(wizard.selectedServiceTemplateIds);

  if (wizard.channel === "whatsapp") {
    const welcome = wizard.welcomeTemplateId ? Number(wizard.welcomeTemplateId) : undefined;
    const thankYou = wizard.thankYouTemplateId ? Number(wizard.thankYouTemplateId) : undefined;
    const isBuilderFlow =
      Array.isArray(builder.builder_step_sequence) && (builder.builder_step_sequence as unknown[]).length > 0;

    return compactRecord({
      ...builder,
      goal: wizard.goal,
      organisation_name: options?.organisationName || persisted.organisation_name || undefined,
      client_name: options?.organisationName || persisted.client_name || undefined,
      delivery: "whatsapp",
      survey_channel: "whatsapp",
      channels: ["whatsapp"],
      anonymous_responses: wizard.anonymous,
      script: wizard.script,
      package_id: wizard.packageId || persisted.package_id || undefined,
      industry_id: wizard.industryId || persisted.industry_id || undefined,
      survey_type_id: wizard.primarySurveyTypeId || persisted.survey_type_id || undefined,
      selected_survey_type_ids: typeIds.length ? typeIds : undefined,
      selected_service_template_ids: selectedTemplates,
      welcome_template_id:
        welcome && Number.isFinite(welcome) && welcome > 0
          ? welcome
          : persisted.welcome_template_id,
      thank_you_template_id:
        thankYou && Number.isFinite(thankYou) && thankYou > 0
          ? thankYou
          : persisted.thank_you_template_id,
      survey_length: PAGE_COUNT_TO_LENGTH[wizard.pageCount],
      page_count: wizard.pageCount,
      privacy_mode: wizard.privacyMode,
      survey_variant: wizard.surveyVariant,
      allow_final_additional_feedback: wizard.allowFinalAdditionalFeedback,
      auto_select_steps: wizard.autoSelectSteps,
      selected_step_roles: wizard.autoSelectSteps ? undefined : wizard.resolvedPageRoles,
      ai_follow_up: wizard.aiFollowUp ? aiFollowUpToApi(wizard.aiFollowUp) : undefined,
      ...(wizard.approved || isBuilderFlow
        ? {
            page_roles: builder.page_roles || wizard.resolvedPageRoles,
          }
        : {}),
      ...(isBuilderFlow
        ? {
            flow_engine: "linear",
            flow_definition_id: null,
            flow_snapshot: null,
            flow_snapshot_json: null,
          }
        : {}),
    });
  }

  return compactRecord({
    goal: wizard.goal,
    delivery: "ai_call",
    survey_channel: "ai_call",
    anonymous_responses: wizard.anonymous,
    script: wizard.script,
    approved_script: wizard.approved ? wizard.script : persisted.approved_script || undefined,
    generated_script_draft: wizard.script,
    script_approved: wizard.approved,
    agent_id: wizard.agentId || persisted.agent_id || undefined,
    system_prompt: wizard.systemPrompt || persisted.system_prompt || undefined,
    estimated_duration_min: wizard.expectedDurationMinutes ?? persisted.estimated_duration_min ?? undefined,
    package_id: wizard.packageId || persisted.package_id || undefined,
  });
}

export type HydratedSurveyDraftState = {
  surveyName: string;
  goal?: string;
  script?: string;
  industryId?: string;
  selectedServiceTagIds?: string[];
  orderedServiceTagIds?: string[];
  welcomeTemplateId?: string;
  thankYouTemplateId?: string;
  selectedServiceTemplateIds?: Record<string, string>;
  packageId?: string;
  privacyMode?: "off" | "on";
  allowFinalAdditionalFeedback?: boolean;
  startAt?: string;
  endAt?: string;
  channel?: "whatsapp" | "phone";
  anonymous?: boolean;
  pageCount?: 3 | 4 | 5 | 6;
  autoSelectSteps?: boolean;
  manualMiddleRoles?: string[];
  approved?: boolean;
  agentId?: string;
  systemPrompt?: string;
  expectedDurationMinutes?: number;
  waPreview?: Record<string, unknown> | null;
  aiFollowUp?: AiFollowUpConfig;
};

function toLocalInput(iso?: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

/** Map API order + config into wizard state (pure — used by page hydration and tests). */
export function hydrateSurveyDraftFromOrder(order: {
  survey_name?: string | null;
  title?: string | null;
  scheduled_start_at?: string | null;
  scheduled_end_at?: string | null;
  config?: Record<string, unknown> | null;
}): HydratedSurveyDraftState {
  const cfg = (order.config || {}) as Record<string, unknown>;
  const out: HydratedSurveyDraftState = {
    surveyName: String(order.survey_name || order.title || cfg.survey_name || "").trim(),
  };

  if (cfg.goal) out.goal = String(cfg.goal);
  const scriptText = String(cfg.approved_script || cfg.generated_script_draft || cfg.script || "").trim();
  if (scriptText) out.script = scriptText;
  if (cfg.agent_id) out.agentId = String(cfg.agent_id);
  if (cfg.system_prompt) out.systemPrompt = String(cfg.system_prompt);
  if (cfg.estimated_duration_min != null) out.expectedDurationMinutes = Number(cfg.estimated_duration_min);
  if (cfg.script_approved === true || cfg.approved_script) out.approved = true;
  if (cfg.industry_id) out.industryId = String(cfg.industry_id);
  if (Array.isArray(cfg.selected_survey_type_ids)) {
    const ids = cfg.selected_survey_type_ids.map(String);
    out.selectedServiceTagIds = ids;
    out.orderedServiceTagIds = ids;
  }
  if (cfg.welcome_template_id) out.welcomeTemplateId = String(cfg.welcome_template_id);
  if (cfg.thank_you_template_id) out.thankYouTemplateId = String(cfg.thank_you_template_id);
  if (cfg.package_id) out.packageId = String(cfg.package_id);
  if (cfg.privacy_mode === "on" || cfg.privacy_mode === "off") out.privacyMode = cfg.privacy_mode;
  if (typeof cfg.allow_final_additional_feedback === "boolean") {
    out.allowFinalAdditionalFeedback = cfg.allow_final_additional_feedback;
  }
  if (typeof cfg.anonymous_responses === "boolean") out.anonymous = cfg.anonymous_responses;
  if (typeof cfg.auto_select_steps === "boolean") out.autoSelectSteps = cfg.auto_select_steps;
  if (typeof cfg.page_count === "number" && [3, 4, 5, 6].includes(cfg.page_count)) {
    out.pageCount = cfg.page_count as 3 | 4 | 5 | 6;
  }

  const templateMap = cfg.selected_service_template_ids;
  if (templateMap && typeof templateMap === "object" && !Array.isArray(templateMap)) {
    const selected: Record<string, string> = {};
    for (const [typeId, raw] of Object.entries(templateMap as Record<string, unknown>)) {
      selected[typeId] = String(raw);
    }
    out.selectedServiceTemplateIds = selected;
  }

  const pageRoles = cfg.page_roles || cfg.selected_step_roles;
  if (Array.isArray(pageRoles)) {
    const roles = pageRoles.map(String);
    const middle = roles.filter((r) => r !== "start" && r !== "completion");
    if (middle.length) out.manualMiddleRoles = middle;
  }

  if (order.scheduled_start_at) out.startAt = toLocalInput(order.scheduled_start_at);
  if (order.scheduled_end_at) out.endAt = toLocalInput(order.scheduled_end_at);

  const delivery = String(cfg.delivery || cfg.survey_channel || "");
  if (delivery === "whatsapp" || delivery === "ai_call") {
    out.channel = delivery === "whatsapp" ? "whatsapp" : "phone";
  }

  if (cfg.builder_runtime || cfg.builder_step_sequence) {
    out.approved = true;
    out.waPreview = pickBuilderFields(cfg, cfg);
    if (cfg.approved_script) out.waPreview.approved_script = cfg.approved_script;
    if (cfg.script) out.waPreview.approved_script = cfg.script;
  }

  if (cfg.ai_follow_up) {
    out.aiFollowUp = aiFollowUpFromApi(cfg.ai_follow_up as Record<string, unknown>);
  }

  return out;
}
