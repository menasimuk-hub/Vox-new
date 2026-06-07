/** Human-readable label for a WA survey template row (Step 1, Step 2, …). */
export function surveyTemplateLabel(
  row: Record<string, unknown> | null | undefined,
  fallback: string,
  questionNumber?: number,
): string {
  const fromRow = String(row?.display_name || row?.title || row?.name || "").trim();
  if (fromRow) return fromRow.split(" — ")[0].trim();
  const fb = String(fallback || "").trim();
  if (fb) return fb.split(" — ")[0].trim();
  if (questionNumber && questionNumber > 0) return `Question ${questionNumber}`;
  return "Survey question";
}
