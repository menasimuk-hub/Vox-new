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
          <p className="font-medium text-foreground">Sending booking links to candidates</p>
          <ul className="mt-2 list-disc space-y-1.5 pl-4 text-muted-foreground">
            <li>
              After you save this URL, open <strong className="text-foreground">Results</strong> on an interview campaign and use{" "}
              <strong className="text-foreground">Send booking</strong>. Each selected candidate receives an email with your Google booking link.
            </li>
            <li>Each candidate needs an email address on their row in the campaign.</li>
            <li>
              Google Calendar only hosts the booking page — it does not send the invite email from your Gmail inbox. VoxBulk sends that email for you.
            </li>
            <li>If a candidate did not receive it, ask them to check spam or promotions. You can resend from Results if needed.</li>
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  );
}
