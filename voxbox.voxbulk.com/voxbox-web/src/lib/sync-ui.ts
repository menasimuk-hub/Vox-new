/** Pure helpers for VoxBox sync refresh races and toast status. */

export type SyncOutcomeKind = "success" | "partial" | "error";

export interface SyncOutcomeInput {
  ok?: boolean;
  partial?: boolean;
  syncedAccounts?: number;
  fetched?: number;
  message?: string;
  errors?: string[];
}

/** Only apply list results from the latest in-flight request generation. */
export function shouldApplyListResult(requestGeneration: number, currentGeneration: number): boolean {
  return requestGeneration === currentGeneration;
}

export function classifySyncOutcome(res: SyncOutcomeInput | null | undefined): SyncOutcomeKind {
  if (!res) return "error";
  const errors = Array.isArray(res.errors) ? res.errors.filter(Boolean) : [];
  if (res.ok && errors.length === 0) return "success";
  if (res.partial || ((res.syncedAccounts ?? 0) > 0 && errors.length > 0)) return "partial";
  if (!res.ok || errors.length > 0) return "error";
  return "success";
}

export function syncOutcomeToastMessage(res: SyncOutcomeInput | null | undefined, kind: SyncOutcomeKind): string {
  const base = (res?.message || "").trim();
  if (kind === "success") {
    return base || "All accounts synced.";
  }
  if (kind === "partial") {
    return base || "Sync finished with some account errors.";
  }
  const err = res?.errors?.[0];
  return base || err || "Sync failed.";
}
