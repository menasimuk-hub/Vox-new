import * as React from "react";
import { Mail, Phone, Send } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import { activityStatusLabel, activityStatusTone } from "@/components/candidate-activity-dialog";
import { candidateAllowsResendBookingInvite } from "@/lib/interview-campaign";
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
  return candidateAllowsResendBookingInvite(activityStatus);
}

export type CandidateContactDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orderId: string;
  readOnly?: boolean;
  /** Hide resend until campaign is launched and first invites were sent. */
  allowResendBookingInvite?: boolean;
  candidate: {
    id: string;
    name: string;
    email?: string;
    outreach_email?: string;
    phone?: string;
    activity_status?: string;
    booked_start_at?: string | null;
    invite_email_failed?: string | null;
  } | null;
};

export function CandidateContactDialog({
  open,
  onOpenChange,
  orderId,
  readOnly = false,
  allowResendBookingInvite = false,
  candidate,
}: CandidateContactDialogProps) {
  const resendM = useSendInterviewBookingInvites(orderId);
  const bookedLabel = fmtBooked(candidate?.booked_start_at);

  const deliverTo = String(candidate?.outreach_email || candidate?.email || "").trim();

  const onResend = async () => {
    if (!candidate?.id) return;
    if (!deliverTo) {
      toast.error("No email on file for this candidate — add an email or re-upload a CV with contact details.");
      return;
    }
    try {
      const result = await resendM.mutateAsync({
        force: true,
        recipient_ids: [candidate.id],
        channels: ["email", "whatsapp"],
      });
      const sent = Number(result.email_sent || 0);
      const wa = Number(result.whatsapp_sent || 0);
      if (sent > 0 || wa > 0) {
        const parts: string[] = [];
        if (sent) parts.push(`email to ${deliverTo}`);
        if (wa) parts.push("WhatsApp");
        toast.success(`Booking invite resent (${parts.join(", ")}).`);
      } else if (result.errors?.length) {
        toast.error(String(result.errors[0]));
      } else if (candidate.invite_email_failed) {
        toast.error(String(candidate.invite_email_failed));
      } else {
        toast.error("Invite was not sent — check Admin → Email (SMTP enabled) and candidate contact details.");
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
                  <span className="min-w-0 flex-1 break-all font-medium">{deliverTo || "—"}</span>
                  {deliverTo && !readOnly && allowResendBookingInvite && canResendBookingInvite(candidate.activity_status) ? (
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
