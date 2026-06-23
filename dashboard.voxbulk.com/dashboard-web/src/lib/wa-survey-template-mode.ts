export type WaPrivacyMode = "off" | "on";

/** Survey-type library templates stay on named/standard rows regardless of anonymous mode. */
export const SURVEY_TYPE_LIBRARY_PRIVACY_MODE: WaPrivacyMode = "off";

export function filterSystemTemplatesByPrivacy(
  rows: Array<Record<string, unknown>>,
  privacyMode: WaPrivacyMode,
): Array<Record<string, unknown>> {
  return rows.filter((row) => {
    const privacy = String(row.privacy_mode || "").toLowerCase();
    const variant = String(row.variant_type || "").toLowerCase();
    const isAnonymous = privacy === "on" || variant === "anonymous";
    return privacyMode === "on" ? isAnonymous : !isAnonymous;
  });
}

/** True when the catalog row has at least one sendable WA template linked. */
export function surveyTypeHasWaTemplate(row: Record<string, unknown> | null | undefined): boolean {
  if (!row) return false;
  if (typeof row.has_wa_template === "boolean") return row.has_wa_template;
  const std = Number(row.standard_template_count || 0);
  const anon = Number(row.anonymous_template_count || 0);
  if (std + anon > 0) return true;
  return String(row.status_label || "").trim() === "Ready";
}
