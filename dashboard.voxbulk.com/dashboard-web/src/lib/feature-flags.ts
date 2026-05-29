/** Recovery + follow-up modules: local dev only — stripped from production/VPS builds. */
export const showRecoveryModules = import.meta.env.DEV;

export function isRecoveryServiceKey(key: string) {
  return key === "recovery" || key === "followup";
}
