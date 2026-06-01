import * as React from "react";
import {
  Activity,
  CalendarCheck,
  CalendarX2,
  Mail,
  MessageCircle,
  Phone,
  PhoneCall,
  Send,
  UserPlus,
  FileCheck,
  Link2,
} from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useInterviewRecipientActivity } from "@/lib/queries";

export type CandidateActivityEvent = {
  at: string;
  code: string;
  label: string;
  detail?: string | null;
};

export function activityStatusLabel(status?: string | null) {
  const key = String(status || "").toLowerCase();
  const labels: Record<string, string> = {
    pending: "Pending",
    booking_email_sent: "Booking email sent",
    awaiting_booking: "Awaiting booking",
    booked: "Appointment booked",
    booked_waiting: "Appointment booked",
    booking_cancelled: "Appointment cancelled",
    calling: "Calling",
    interview_completed: "Interview done",
    report_ready: "Report ready",
    call_failed: "Call failed",
    scheduling_sent: "Scheduling sent",
  };
  return labels[key] || (key ? key.replace(/_/g, " ") : "Pending");
}

export function activityStatusTone(
  status?: string | null,
): "live" | "scheduled" | "finished" | "paused" | "quoted" | "awaiting-payment" {
  const key = String(status || "").toLowerCase();
  if (key === "booking_cancelled" || key === "call_failed") return "paused";
  if (key === "booked" || key === "booked_waiting" || key === "calling") return "live";
  if (key === "report_ready" || key === "interview_completed") return "finished";
  if (key === "booking_email_sent" || key === "awaiting_booking") return "scheduled";
  return "quoted";
}

function fmtWhen(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function eventIcon(code: string) {
  switch (String(code || "").toLowerCase()) {
    case "added":
      return UserPlus;
    case "invite_email":
    case "confirm_email":
    case "cancel_email":
      return Mail;
    case "invite_wa":
    case "confirm_wa":
      return MessageCircle;
    case "invite_sent":
      return Send;
    case "booked":
      return CalendarCheck;
    case "rescheduled":
      return CalendarCheck;
    case "cancelled":
      return CalendarX2;
    case "calling":
      return PhoneCall;
    case "call_done":
      return Phone;
    case "analysis":
      return FileCheck;
    case "scheduling":
      return Link2;
    default:
      return Activity;
  }
}

type CandidateActivityDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orderId: string;
  recipientId: string | null;
  candidateName?: string;
};

export function CandidateActivityDialog({
  open,
  onOpenChange,
  orderId,
  recipientId,
  candidateName,
}: CandidateActivityDialogProps) {
  const activityQ = useInterviewRecipientActivity(orderId, recipientId, open);
  const data = activityQ.data;
  const events = (data?.events || []) as CandidateActivityEvent[];
  const displayName = data?.name || candidateName || "Candidate";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 pr-6">
            <Activity className="size-5 shrink-0 text-primary" />
            Candidate activity
          </DialogTitle>
          <DialogDescription>{displayName}</DialogDescription>
        </DialogHeader>

        {activityQ.isLoading ? (
          <div className="space-y-3 py-2">
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : activityQ.isError ? (
          <p className="text-sm text-destructive">Could not load activity. Try again.</p>
        ) : data ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-muted/30 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone={activityStatusTone(data.activity_status)}>
                  {activityStatusLabel(data.activity_status)}
                </StatusBadge>
                {data.booked_start_at ? (
                  <span className="text-xs text-muted-foreground">
                    Appointment: {fmtWhen(data.booked_start_at)}
                  </span>
                ) : null}
              </div>
              {(data.phone || data.email) && (
                <div className="mt-2 space-y-0.5 text-xs text-muted-foreground">
                  {data.phone ? <div>{data.phone}</div> : null}
                  {data.email ? <div>{data.email}</div> : null}
                </div>
              )}
            </div>

            <div>
              <h4 className="mb-3 text-sm font-medium">All activity</h4>
              {events.length === 0 ? (
                <p className="text-sm text-muted-foreground">No activity recorded yet.</p>
              ) : (
                <ul className="space-y-0">
                  {events.map((ev, idx) => {
                    const Icon = eventIcon(ev.code);
                    const isLast = idx === events.length - 1;
                    return (
                      <li key={`${ev.code}-${ev.at}-${idx}`} className="relative flex gap-3 pb-4">
                        {!isLast ? (
                          <span
                            className="absolute left-[11px] top-7 bottom-0 w-px bg-border"
                            aria-hidden
                          />
                        ) : null}
                        <span className="relative z-[1] mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-background">
                          <Icon className="size-3.5 text-muted-foreground" />
                        </span>
                        <div className="min-w-0 flex-1 pt-0.5">
                          <div className="text-sm font-medium leading-snug">{ev.label}</div>
                          <div className="text-xs text-muted-foreground">{fmtWhen(ev.at)}</div>
                          {ev.detail ? (
                            <div className="mt-1 text-xs text-muted-foreground">{ev.detail}</div>
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
