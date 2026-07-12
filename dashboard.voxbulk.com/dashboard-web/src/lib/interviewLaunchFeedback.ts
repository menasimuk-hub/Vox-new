import { toast } from "sonner";

export type InterviewInviteDispatch = {
  ok?: boolean;
  whatsapp_sent?: number;
  email_sent?: number;
  skipped_locked?: number;
  errors?: string[];
};

export type InterviewLaunchResult = {
  ok?: boolean;
  already_launched?: boolean;
  message?: string;
  status?: string;
  invites?: InterviewInviteDispatch | null;
};

export function launchResultHasOutbound(result: InterviewLaunchResult | null | undefined): boolean {
  const emailN = Number(result?.invites?.email_sent || 0);
  const waN = Number(result?.invites?.whatsapp_sent || 0);
  return emailN > 0 || waN > 0 || Boolean(result?.already_launched);
}

export function describeInterviewLaunchResult(result: InterviewLaunchResult | null | undefined): {
  tone: "success" | "warning" | "error";
  title: string;
  detail?: string;
} {
  const invites = result?.invites;
  const emailN = Number(invites?.email_sent || 0);
  const waN = Number(invites?.whatsapp_sent || 0);
  const errors = Array.isArray(invites?.errors) ? invites!.errors!.filter(Boolean) : [];
  const title = result?.message?.trim() || "Interview campaign launched.";
  const alreadyLive = Boolean(result?.already_launched) || emailN > 0 || waN > 0;

  if (emailN === 0 && waN === 0 && !alreadyLive) {
    if (errors.length > 0) {
      return { tone: "error", title, detail: errors.slice(0, 3).join(" · ") };
    }
    return {
      tone: "error",
      title: title || "Launch failed",
      detail: "No booking invite emails were sent — add candidate emails (or CVs with email) and try Resend.",
    };
  }
  if (result?.ok === false || emailN < 1) {
    return {
      tone: "warning",
      title: title || "Campaign is live with incomplete invites",
      detail:
        errors.slice(0, 3).join(" · ") ||
        (emailN < 1 && waN > 0
          ? "WhatsApp was sent but invite email was not — check Admin → Email (SMTP) and candidate emails."
          : "Some invites may need Resend from the results page."),
    };
  }
  if (errors.length > 0) {
    return { tone: "warning", title, detail: errors.slice(0, 3).join(" · ") };
  }
  return { tone: "success", title };
}

export function notifyInterviewLaunch(result: InterviewLaunchResult | null | undefined) {
  const { tone, title, detail } = describeInterviewLaunchResult(result);
  const message = detail ? `${title} — ${detail}` : title;
  if (tone === "error") toast.error(message);
  else if (tone === "warning") toast.warning(message);
  else toast.success(message);
}
