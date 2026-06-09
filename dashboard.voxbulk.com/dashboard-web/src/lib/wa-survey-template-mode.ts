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
