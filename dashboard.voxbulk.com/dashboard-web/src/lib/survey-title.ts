/** Campaign/survey display name — separate from goal text and step labels. */
export function normalizeSurveyName(name: string, fallback = "Survey draft"): string {
  const value = String(name || "").trim();
  return value || fallback;
}

/** Derive a short order title from survey goal text without mid-word truncation. */
export function surveyTitleFromGoal(goal: string, maxLen = 80): string {
  const g = String(goal || "").trim();
  if (!g) return "Survey draft";
  if (g.length <= maxLen) return g;
  const cut = g.slice(0, maxLen);
  const lastSpace = cut.lastIndexOf(" ");
  if (lastSpace > 40) return `${cut.slice(0, lastSpace).trim()}…`;
  return `${cut.trim()}…`;
}
