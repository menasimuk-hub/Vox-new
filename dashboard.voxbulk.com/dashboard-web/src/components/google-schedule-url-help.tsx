import * as React from "react";
import { CircleHelp, ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const GOOGLE_APPOINTMENTS_HELP = "https://support.google.com/calendar/answer/10729728";
const GOOGLE_CALENDAR = "https://calendar.google.com/calendar/u/0/r/appointments";

export function GoogleScheduleUrlHelp() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0 text-muted-foreground" aria-label="How to get Google appointment schedule URL">
          <CircleHelp className="size-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Google appointment schedule URL</DialogTitle>
          <DialogDescription>
            After connecting Google Calendar, paste the public booking page link for your appointment schedule. VoxBulk uses it when you send human interview links from Results.
          </DialogDescription>
        </DialogHeader>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-foreground">
          <li>
            Open{" "}
            <a href={GOOGLE_CALENDAR} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline">
              Google Calendar → Appointment schedules
              <ExternalLink className="size-3" />
            </a>
          </li>
          <li>Create a schedule (or open an existing one) with the duration and availability you want.</li>
          <li>
            Open the schedule → <strong>Share</strong> or <strong>Booking page</strong> → copy the public link. It usually looks like{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">calendar.google.com/calendar/appointments/…</code> or{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">calendar.app.google/…</code>
          </li>
          <li>Paste that full URL here and click <strong>Save schedule</strong>. Status should show connected with your schedule ready.</li>
        </ol>
        <p className="text-sm text-muted-foreground">
          <a href={GOOGLE_APPOINTMENTS_HELP} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline">
            Google Help: Create appointment schedules
            <ExternalLink className="size-3" />
          </a>
        </p>
        <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
          <p className="font-medium text-foreground">About email when sending booking links</p>
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-muted-foreground">
            <li>
              Interview invites are sent by <strong className="text-foreground">VoxBulk email (SMTP)</strong>, not from your Gmail account. Google Calendar only provides the booking page URL.
            </li>
            <li>
              If email fails, ask your admin to check <strong className="text-foreground">Admin → Email / notification settings</strong> and that the{" "}
              <code className="text-xs">interview_scheduling_invite</code> template exists.
            </li>
            <li>Each candidate needs an email address on the campaign recipient row.</li>
            <li>Google&apos;s booking page may not pre-fill the guest email from the link — the candidate opens the URL from the VoxBulk email we send.</li>
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  );
}
