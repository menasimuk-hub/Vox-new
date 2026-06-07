function shortenText(text: string, maxLen = 60): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= maxLen) return cleaned;
  return `${cleaned.slice(0, maxLen - 1).trim()}…`;
}

function normalizeCompare(value: string): string {
  return String(value || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

/** True when label is really the survey title/goal — must not be used as a step name. */
export function isCampaignCopyLabel(candidate: string, rejectTitles: string[] = []): boolean {
  const c = normalizeCompare(candidate);
  if (!c) return false;
  for (const raw of rejectTitles) {
    const r = normalizeCompare(raw);
    if (!r) continue;
    if (c === r || c.includes(r) || r.includes(c)) return true;
    const cShort = c.slice(0, 60);
    const rShort = r.slice(0, 60);
    if (cShort && (cShort === rShort || cShort.includes(rShort) || rShort.includes(cShort) || r.includes(cShort))) {
      return true;
    }
  }
  return false;
}

export type SurveyStepLabelOptions = {
  fallback?: string;
  questionNumber?: number;
  surveyTypeName?: string;
  rejectTitles?: string[];
};

/** Shared resolver — matches backend resolve_step_display_name priority. */
export function resolveSurveyStepLabel(
  row: Record<string, unknown> | null | undefined,
  options?: SurveyStepLabelOptions,
): string {
  const rejectTitles = (options?.rejectTitles || []).filter(Boolean);
  const surveyTypeName = String(options?.surveyTypeName || options?.fallback || "").trim();
  const questionNumber = options?.questionNumber ?? 0;

  for (const key of ["display_name", "template_name", "title", "name"] as const) {
    const fromRow = String(row?.[key] || "").trim();
    if (fromRow && !isCampaignCopyLabel(fromRow, rejectTitles)) {
      return fromRow.split(" — ")[0].trim();
    }
  }

  const rawText = String(row?.text || row?.body || row?.body_preview || "").trim();
  if (rawText && !isCampaignCopyLabel(rawText, rejectTitles)) {
    const fromText = shortenText(rawText);
    if (fromText && !isCampaignCopyLabel(fromText, rejectTitles)) return fromText;
  }

  if (questionNumber > 0) return `Question ${questionNumber}`;

  if (surveyTypeName && !isCampaignCopyLabel(surveyTypeName, rejectTitles)) {
    return surveyTypeName.split(" — ")[0].trim();
  }

  return "Question 1";
}

/** Human-readable label for a WA survey template row (Step 1, Step 2, …). */
export function surveyTemplateLabel(
  row: Record<string, unknown> | null | undefined,
  fallback: string,
  questionNumber?: number,
  rejectTitles: string[] = [],
): string {
  return resolveSurveyStepLabel(row, {
    fallback,
    questionNumber,
    surveyTypeName: fallback,
    rejectTitles,
  });
}

/** First middle-step label from a saved/generated survey config. */
export function firstStepLabelFromConfig(
  config: Record<string, unknown> | null | undefined,
  rejectTitles: string[] = [],
): string {
  if (!config) return "";
  const reject = [
    ...rejectTitles,
    String(config.goal || ""),
    String(config.title || ""),
  ].filter(Boolean);
  const runtime = config.builder_runtime as Record<string, unknown> | undefined;
  const runtimeTypeName = String(runtime?.survey_type_name || config.survey_type_name || "").trim();
  const runtimeSeq = (runtime?.step_sequence || []) as Array<Record<string, unknown>>;
  if (Array.isArray(runtimeSeq) && runtimeSeq[0]) {
    return resolveSurveyStepLabel(runtimeSeq[0], {
      surveyTypeName: runtimeTypeName,
      questionNumber: 1,
      rejectTitles: reject,
    });
  }
  const seq = (config.builder_step_sequence || []) as Array<Record<string, unknown>>;
  if (Array.isArray(seq) && seq[0]) {
    return resolveSurveyStepLabel(seq[0], {
      surveyTypeName: runtimeTypeName,
      questionNumber: 1,
      rejectTitles: reject,
    });
  }
  return "";
}

/** Reject API-provided step label when it is actually the campaign title/goal. */
export function sanitizeStepLabelFromApi(label: string, rejectTitles: string[] = []): string {
  const trimmed = String(label || "").trim();
  if (!trimmed || isCampaignCopyLabel(trimmed, rejectTitles)) return "";
  return trimmed;
}
