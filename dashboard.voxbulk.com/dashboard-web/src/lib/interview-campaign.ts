/** Default ATS cutoff when none saved on the order (0–100). */
export const DEFAULT_MIN_ATS_SCORE = 40;

/** Unsaved ATS cutoff hint colour (amber). */
export const ATS_CUTOFF_PENDING_COLOR = "#b45309";

/** Single label whenever ATS is running — do not substitute other wording. */
export const ATS_ANALYZING_LABEL = "Analyzing…";

export type InterviewCandidateAtsFields = {
  ats: number | null;
  atsStatus?: string;
  activityStatus?: string;
  /** e.g. "Auto-excluded · matched: …" for keyword exclusions */
  activityStatusLabel?: string;
};

export function isAtsAnalyzingStatus(status?: string | null): boolean {
  const st = String(status || "").toLowerCase();
  return st === "pending" || st === "analyzing";
}

/** True when this row still needs an ATS score (not complete/failed). */
export function candidateNeedsAtsScore(candidate: InterviewCandidateAtsFields): boolean {
  const st = String(candidate.atsStatus || "").toLowerCase();
  if (isAtsAnalyzingStatus(st)) return true;
  if (st === "complete" && candidate.ats != null) return false;
  if (st === "failed") return false;
  return candidate.ats == null;
}

/** Table/cell display — always show Analyzing while queued or during optimistic run. */
export function resolveCandidateAtsDisplay(
  candidate: InterviewCandidateAtsFields,
  opts?: { optimisticAnalyzing?: boolean },
): { score: number | null; status: string } {
  if (opts?.optimisticAnalyzing || isAtsAnalyzingStatus(candidate.atsStatus)) {
    return { score: null, status: "analyzing" };
  }
  return { score: candidate.ats ?? null, status: String(candidate.atsStatus || "") };
}

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

/** True after Launch — booking invites may be sent or resent. */
export function isInterviewCampaignLaunched(status?: string | null): boolean {
  return ["running", "scheduled", "paused", "completed"].includes(String(status || "").toLowerCase());
}

type InviteDispatch = { ok?: boolean; email_sent?: number; whatsapp_sent?: number; errors?: string[] };

/** True when a launch successfully dispatched booking invites (not draft-only config). */
export function bookingInvitesWereSent(config: Record<string, unknown>): boolean {
  if (!config.booking_invites_sent_at) return false;
  const dispatch = config.last_invite_dispatch as InviteDispatch | undefined;
  if (dispatch?.ok === false) return false;
  return dispatch?.ok === true;
}

/** Resend booking invites: hidden before launch, shown once launched. */
export function campaignAllowsResendBookingInvites(opts: {
  orderStatus?: string | null;
}): boolean {
  return isInterviewCampaignLaunched(opts.orderStatus);
}

export function canShowResendBookingInvite(opts: {
  orderStatus?: string | null;
}): boolean {
  return campaignAllowsResendBookingInvites(opts);
}

/** True when candidate has a completed ATS score at or above the campaign cutoff and is not excluded. */
export function isScreeningEligibleCandidate(
  candidate: InterviewCandidateAtsFields,
  minAtsScore: number,
): boolean {
  const atsStatus = String(candidate.atsStatus || "").toLowerCase();
  if (atsStatus !== "complete" || candidate.ats == null) return false;

  const label = String(candidate.activityStatusLabel || "").toLowerCase();
  if (label.includes("matched:")) return false;

  // Score vs applied cutoff is authoritative (stale auto_excluded flags must not block launch).
  return candidate.ats >= minAtsScore;
}

export function countScreeningEligibleCandidates(
  candidates: InterviewCandidateAtsFields[],
  minAtsScore: number,
): number {
  return candidates.filter((c) => isScreeningEligibleCandidate(c, minAtsScore)).length;
}
