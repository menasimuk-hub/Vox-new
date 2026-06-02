import * as React from "react";
import { Mail, Phone, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import { activityStatusLabel, activityStatusTone } from "@/components/candidate-activity-dialog";
import { useSendInterviewBookingInvites } from "@/lib/queries";

const BOOKING_TZ = "Europe/London";

function fmtBooked(iso?: string | null) {
  if (!iso) return null;
  try {
    const raw = String(iso).trim();
    const d = /[zZ]|[+-]\d{2}:\d{2}$/.test(raw) ? new Date(raw) : new Date(`${raw}Z`);
    return d.toLocaleString("en-GB", {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: BOOKING_TZ,
    });
  } catch {
    return iso;
  }
}

function canResendBookingInvite(activityStatus?: string | null) {
  const key = String(activityStatus || "").toLowerCase();
  return !["report_ready", "interview_completed", "scheduling_sent", "calling"].includes(key);
}

export type CandidateContactDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orderId: string;
  readOnly?: boolean;
  candidate: {
    id: string;
    name: string;
    email?: string;
    phone?: string;
    activity_status?: string;
    booked_start_at?: string | null;
  } | null;
};

export function CandidateContactDialog({ open, onOpenChange, orderId, readOnly = false, candidate }: CandidateContactDialogProps) {
  const resendM = useSendInterviewBookingInvites(orderId);
  const bookedLabel = fmtBooked(candidate?.booked_start_at);

  const onResend = async () => {
    if (!candidate?.id || !candidate.email) return;
    try {
      const result = await resendM.mutateAsync({
        force: true,
        recipient_ids: [candidate.id],
        channels: ["email"],
      });
      const sent = Number(result.email_sent || 0);
      if (sent > 0) {
        toast.success(`Booking invite resent to ${candidate.email}`);
      } else if (result.errors?.length) {
        toast.error(String(result.errors[0]));
      } else {
        toast.message("Invite was not sent — check candidate email and SMTP settings.");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not resend invite");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{candidate?.name || "Candidate"}</DialogTitle>
          <DialogDescription>
            {readOnly ? "Contact details (read-only — campaign stopped or finished)" : "Contact details and booking actions"}
          </DialogDescription>
        </DialogHeader>

        {candidate ? (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={activityStatusTone(candidate.activity_status)}>
                {activityStatusLabel(candidate.activity_status)}
              </StatusBadge>
              {bookedLabel ? (
                <span className="text-xs text-muted-foreground">Booked: {bookedLabel} UK</span>
              ) : null}
            </div>

            <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Email</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Mail className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 break-all font-medium">{candidate.email || "—"}</span>
                  {candidate.email && !readOnly && canResendBookingInvite(candidate.activity_status) ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="shrink-0 gap-1.5"
                      disabled={resendM.isPending}
                      onClick={() => void onResend()}
                    >
                      <Send className="size-3.5" />
                      {resendM.isPending ? "Sending…" : "Resend booking invite"}
                    </Button>
                  ) : null}
                </div>
              </div>

              <div>
                <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Contact number</p>
                <p className="mt-1 flex items-center gap-2 font-medium">
                  <Phone className="size-4 shrink-0 text-muted-foreground" />
                  {candidate.phone || "—"}
                </p>
              </div>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
