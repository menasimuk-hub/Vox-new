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

type InviteDispatch = { ok?: boolean; email_sent?: number; whatsapp_sent?: number; errors?: string[] };

/** True when any booking invite left the system (email and/or WhatsApp). */
export function bookingInvitesWereSent(config: Record<string, unknown>): boolean {
  if (config.booking_invites_sent_at) return true;
  const dispatch = config.last_invite_dispatch as InviteDispatch | undefined;
  if (!dispatch) return false;
  return Number(dispatch.email_sent || 0) > 0 || Number(dispatch.whatsapp_sent || 0) > 0;
}

export type InterviewCampaignLaunchedOpts = {
  paymentStatus?: string | null;
  config?: Record<string, unknown> | null;
};

/**
 * True after Launch has made the campaign live.
 * Status `paid` with approved payment is the normal post-schedule state (manual run mode).
 * Invite markers are preferred when present; bare paid+approved still counts so results/resend work.
 */
export function isInterviewCampaignLaunched(
  status?: string | null,
  opts?: InterviewCampaignLaunchedOpts,
): boolean {
  const st = String(status || "").toLowerCase();
  if (["running", "scheduled", "paused", "completed"].includes(st)) return true;
  if (st === "paid" && String(opts?.paymentStatus || "").toLowerCase() === "approved") {
    const cfg = opts?.config;
    if (!cfg) return true;
    // When config is available, prefer invite markers so the create wizard can still
    // show "Launch — send booking invites" after payment approved but before invites succeed.
    if (bookingInvitesWereSent(cfg)) return true;
    return false;
  }
  return false;
}

/** Resend booking invites: hidden before launch and when campaign is read-only. */
export function campaignAllowsResendBookingInvites(opts: {
  orderStatus?: string | null;
  paymentStatus?: string | null;
  config?: Record<string, unknown> | null;
}): boolean {
  if (isInterviewCampaignReadOnly(opts.orderStatus)) return false;
  return isInterviewCampaignLaunched(opts.orderStatus, {
    paymentStatus: opts.paymentStatus,
    config: opts.config,
  });
}

const RESEND_BOOKING_INVITE_DENY = new Set([
  "interview_completed",
  "report_ready",
  "calling",
  "booked",
  "booked_waiting",
  "scheduling_sent",
  "call_failed",
  "auto_excluded",
]);

const RESEND_BOOKING_INVITE_STATUSES = new Set([
  "pending",
  "awaiting_booking",
  "booking_email_sent",
  "booking_cancelled",
]);

/** Resend pre-call booking invite — only before the AI interview call starts/finishes. */
export function candidateAllowsResendBookingInvite(opts: {
  orderStatus?: string | null;
  paymentStatus?: string | null;
  config?: Record<string, unknown> | null;
  activityStatus?: string | null;
  recipientStatus?: string | null;
  interviewCompleted?: boolean;
}): boolean {
  if (isInterviewCampaignReadOnly(opts.orderStatus)) return false;
  if (
    !isInterviewCampaignLaunched(opts.orderStatus, {
      paymentStatus: opts.paymentStatus,
      config: opts.config,
    })
  ) {
    return false;
  }
  if (opts.interviewCompleted) return false;
  const recipient = String(opts.recipientStatus || "").toLowerCase();
  if (recipient === "completed" || recipient === "done") return false;
  const activity = String(opts.activityStatus || "pending").toLowerCase();
  if (RESEND_BOOKING_INVITE_DENY.has(activity)) return false;
  return RESEND_BOOKING_INVITE_STATUSES.has(activity);
}

export function canShowResendBookingInvite(opts: {
  orderStatus?: string | null;
  paymentStatus?: string | null;
  config?: Record<string, unknown> | null;
  activityStatus?: string | null;
}): boolean {
  return candidateAllowsResendBookingInvite(opts);
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

/**
 * Client-side phone gate for launch (E.164 / length only).
 * Call-allowlist failure must not block launch — those candidates interview via web meeting.
 */
export function candidatePhoneBlocksLaunch(opts: {
  phone?: string | null;
  /** @deprecated Ignored — allowlist no longer blocks interview launch. */
  phoneCallAllowed?: boolean | null;
  /** @deprecated Ignored — allowlist no longer blocks interview launch. */
  phoneCallBlockReason?: string | null;
}): string | null {
  const phone = String(opts.phone || "").trim();
  if (!phone) return null; // email-only candidates allowed
  const digits = phone.replace(/\D/g, "");
  if (digits.length < 8 || digits.length > 15) {
    return "Phone number must be in E.164 format, for example +447700900123";
  }
  return null;
}

/** Soft copy when AI phone dial is unavailable but web meeting + WA still work. */
export const INTERVIEW_WEB_MEETING_ONLY_HINT =
  "AI phone call not available for this country — interview will use web meeting";
