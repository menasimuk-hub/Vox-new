function shortenText(text: string, maxLen = 60): string {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  if (cleaned.length <= maxLen) return cleaned;
  return `${cleaned.slice(0, maxLen - 1).trim()}…`;
}

/** Shared resolver — matches backend resolve_step_display_name priority. */
export function resolveSurveyStepLabel(
  row: Record<string, unknown> | null | undefined,
  options?: { fallback?: string; questionNumber?: number; surveyTypeName?: string },
): string {
  const surveyTypeName = String(options?.surveyTypeName || options?.fallback || "").trim();
  const questionNumber = options?.questionNumber ?? 0;
  const fromRow = String(
    row?.display_name || row?.template_name || row?.title || row?.name || "",
  ).trim();
  if (fromRow) return fromRow.split(" — ")[0].trim();
  if (questionNumber === 1 && surveyTypeName) return surveyTypeName.split(" — ")[0].trim();
  const fromText = shortenText(String(row?.text || row?.body || ""));
  if (fromText) return fromText;
  if (questionNumber > 0) return `Question ${questionNumber}`;
  if (surveyTypeName) return surveyTypeName.split(" — ")[0].trim();
  return "Survey question";
}

/** Human-readable label for a WA survey template row (Step 1, Step 2, …). */
export function surveyTemplateLabel(
  row: Record<string, unknown> | null | undefined,
  fallback: string,
  questionNumber?: number,
): string {
  return resolveSurveyStepLabel(row, {
    fallback,
    questionNumber,
    surveyTypeName: fallback,
  });
}

/** First middle-step label from a saved/generated survey config. */
export function firstStepLabelFromConfig(config: Record<string, unknown> | null | undefined): string {
  if (!config) return "";
  const surveyTypeName = String(config.survey_type_name || "").trim();
  const runtime = config.builder_runtime as Record<string, unknown> | undefined;
  const runtimeTypeName = String(runtime?.survey_type_name || surveyTypeName).trim();
  const runtimeSeq = (runtime?.step_sequence || []) as Array<Record<string, unknown>>;
  if (Array.isArray(runtimeSeq) && runtimeSeq[0]) {
    return resolveSurveyStepLabel(runtimeSeq[0], {
      surveyTypeName: runtimeTypeName,
      questionNumber: 1,
      fallback: runtimeTypeName,
    });
  }
  const seq = (config.builder_step_sequence || []) as Array<Record<string, unknown>>;
  if (Array.isArray(seq) && seq[0]) {
    return resolveSurveyStepLabel(seq[0], {
      surveyTypeName: runtimeTypeName || surveyTypeName,
      questionNumber: 1,
      fallback: runtimeTypeName || surveyTypeName,
    });
  }
  return runtimeTypeName || surveyTypeName;
}
