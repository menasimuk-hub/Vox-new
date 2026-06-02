/** Interview campaigns are read-only once stopped or finished. */
export function isInterviewCampaignReadOnly(status?: string | null): boolean {
  return ["cancelled", "completed", "archived"].includes(String(status || "").toLowerCase());
}

export function interviewCampaignReadOnlyLabel(status?: string | null): string {
  const key = String(status || "").toLowerCase();
  if (key === "cancelled") return "This campaign was stopped — all actions are read-only.";
  if (key === "completed") return "This campaign is finished — all actions are read-only.";
  if (key === "archived") return "This campaign is archived — all actions are read-only.";
  return "This campaign is read-only.";
}
