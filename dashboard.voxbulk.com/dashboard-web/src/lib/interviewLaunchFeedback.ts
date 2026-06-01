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
  message?: string;
  invites?: InterviewInviteDispatch | null;
};

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

  if (emailN === 0 && waN === 0 && errors.length > 0) {
    return { tone: "error", title, detail: errors.slice(0, 3).join(" · ") };
  }
  if (errors.length > 0) {
    return { tone: "warning", title, detail: errors.slice(0, 3).join(" · ") };
  }
  if (emailN === 0 && waN === 0) {
    return { tone: "warning", title: "Campaign scheduled but no booking invites were delivered." };
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
