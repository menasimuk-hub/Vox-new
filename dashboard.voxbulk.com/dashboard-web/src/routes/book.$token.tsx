import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import {
  CalendarClock,
  CalendarPlus,
  CheckCircle2,
  Clock,
  Copy,
  ExternalLink,
  Link2,
  Loader2,
  XCircle,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { publicApiFetch, getApiBaseUrl } from "@/lib/api";

export const Route = createFileRoute("/book/$token")({
  head: () => ({ meta: [{ title: "Book your interview — VoxBulk" }] }),
  validateSearch: (search: Record<string, unknown>) => ({
    reschedule: search.reschedule === "1" || search.reschedule === 1 || search.reschedule === true,
  }),
  component: PublicBookingPage,
});

type BookingPage = {
  token: string;
  candidate_name: string;
  role: string;
  organisation_name?: string;
  window_start: string;
  window_end: string;
  slot_minutes: number;
  available_slots: string[];
  booked_start_at?: string | null;
  booked_end_at?: string | null;
  already_booked: boolean;
  cancelled_at?: string | null;
  booking_closed?: boolean;
  closed_message?: string | null;
  can_reschedule?: boolean;
  can_cancel?: boolean;
  display_timezone?: string;
  display_timezone_label?: string;
  calling_hours_label?: string;
  channel?: string | null;
  channel_options?: {
    phone_available?: boolean;
    meeting_available?: boolean;
    default_channel?: string;
  };
  booking_url?: string | null;
  meeting_url?: string | null;
  calendar_google_url?: string | null;
  calendar_outlook_url?: string | null;
  calendar_ics_url?: string | null;
};

/** Default when API does not send candidate timezone. */
const DEFAULT_BOOKING_TZ = "Europe/London";

function resolveBookingTz(data?: { display_timezone?: string }) {
  return data?.display_timezone || DEFAULT_BOOKING_TZ;
}

function resolveBookingTzLabel(data?: { display_timezone_label?: string }) {
  return data?.display_timezone_label || "UK time (GMT/BST)";
}

type DayPart = "all" | "morning" | "afternoon" | "evening";

function parseUtc(iso: string) {
  const raw = String(iso || "").trim();
  if (!raw) return new Date(NaN);
  if (!/[zZ]|[+-]\d{2}:\d{2}$/.test(raw)) return new Date(`${raw}Z`);
  return new Date(raw);
}

function localDateParts(iso: string, tz: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    year: "numeric",
    month: "numeric",
    day: "numeric",
  }).formatToParts(parseUtc(iso));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return { year: get("year"), month: get("month"), day: get("day") };
}

function localHour(iso: string, tz: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    hour: "numeric",
    hour12: false,
  }).formatToParts(parseUtc(iso));
  return Number(parts.find((p) => p.type === "hour")?.value ?? 0);
}

function localCalendarDate(iso: string, tz: string): Date {
  const { year, month, day } = localDateParts(iso, tz);
  return new Date(year, month - 1, day);
}

function fmtDate(iso: string, tz: string) {
  try {
    return parseUtc(iso).toLocaleDateString("en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
      timeZone: tz,
    });
  } catch {
    return iso;
  }
}

function fmtTime(iso: string, tz: string) {
  try {
    return parseUtc(iso).toLocaleTimeString("en-GB", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZone: tz,
    });
  } catch {
    return iso;
  }
}

function fmtWindow(iso: string, tz: string) {
  try {
    return parseUtc(iso).toLocaleString("en-GB", {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: tz,
    });
  } catch {
    return iso;
  }
}

function dayKey(iso: string, tz: string) {
  const { year, month, day } = localDateParts(iso, tz);
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function dayPartForSlot(iso: string, tz: string): Exclude<DayPart, "all"> {
  const hour = localHour(iso, tz);
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}

function startOfDay(date: Date) {
  const d = new Date(date);
  d.setHours(0, 0, 0, 0);
  return d;
}

function groupSlotsByDay(slots: string[], tz: string) {
  const groups = new Map<string, string[]>();
  for (const slot of slots) {
    const key = dayKey(slot, tz);
    const list = groups.get(key) || [];
    list.push(slot);
    groups.set(key, list);
  }
  return Array.from(groups.entries()).map(([key, daySlots]) => ({
    dayKey: key,
    date: localCalendarDate(daySlots[0], tz),
    label: fmtDate(daySlots[0], tz),
    slots: daySlots.sort((a, b) => parseUtc(a).getTime() - parseUtc(b).getTime()),
  }));
}

function CopyLinkRow({ label, href }: { label: string; href: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="mt-0.5 block truncate text-sm font-medium text-primary underline-offset-2 hover:underline"
        >
          {href}
        </a>
      </div>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="shrink-0 gap-1.5"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(href);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          } catch {
            /* ignore */
          }
        }}
      >
        {copied ? <CheckCircle2 className="size-3.5" /> : <Copy className="size-3.5" />}
        {copied ? "Copied" : "Copy"}
      </Button>
    </div>
  );
}

function CalendarSlotPicker({
  data,
  picked,
  onPick,
  actionLabel,
  busy,
  error,
  onSubmit,
}: {
  data: BookingPage;
  picked: string | null;
  onPick: (slot: string) => void;
  actionLabel: string;
  busy?: boolean;
  error?: string | null;
  onSubmit: () => void;
}) {
  const bookingTz = resolveBookingTz(data);
  const bookingTzLabel = resolveBookingTzLabel(data);
  const slotGroups = React.useMemo(
    () => (data.available_slots ? groupSlotsByDay(data.available_slots, bookingTz) : []),
    [data.available_slots, bookingTz],
  );

  const daysWithSlots = React.useMemo(() => slotGroups.map((g) => g.date), [slotGroups]);
  const [selectedDay, setSelectedDay] = React.useState<Date | undefined>(undefined);
  const [dayPart, setDayPart] = React.useState<DayPart>("all");

  React.useEffect(() => {
    if (!slotGroups.length) {
      setSelectedDay(undefined);
      return;
    }
    if (picked) {
      setSelectedDay(localCalendarDate(picked, bookingTz));
      return;
    }
    setSelectedDay((current) => {
      if (current && slotGroups.some((g) => g.date.toDateString() === current.toDateString())) {
        return current;
      }
      return slotGroups[0]?.date;
    });
  }, [slotGroups, picked, bookingTz]);

  const activeGroup = React.useMemo(
    () => slotGroups.find((g) => selectedDay && g.date.toDateString() === selectedDay.toDateString()),
    [slotGroups, selectedDay],
  );

  const filteredSlots = React.useMemo(() => {
    const slots = activeGroup?.slots || [];
    if (dayPart === "all") return slots;
    return slots.filter((slot) => dayPartForSlot(slot, bookingTz) === dayPart);
  }, [activeGroup, dayPart, bookingTz]);

  const partCounts = React.useMemo(() => {
    const slots = activeGroup?.slots || [];
    return {
      all: slots.length,
      morning: slots.filter((s) => dayPartForSlot(s, bookingTz) === "morning").length,
      afternoon: slots.filter((s) => dayPartForSlot(s, bookingTz) === "afternoon").length,
      evening: slots.filter((s) => dayPartForSlot(s, bookingTz) === "evening").length,
    };
  }, [activeGroup, bookingTz]);

  const windowStart = localCalendarDate(data.window_start, bookingTz);
  const windowEnd = localCalendarDate(data.window_end, bookingTz);
  const isDayAvailable = (date: Date) => daysWithSlots.some((d) => d.toDateString() === date.toDateString());

  if (data.available_slots.length === 0) {
    return (
      <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
        No slots left in this window. Please contact the hiring team.
      </p>
    );
  }

  const partTabs: { id: DayPart; label: string }[] = [
    { id: "all", label: "All" },
    { id: "morning", label: "Morning" },
    { id: "afternoon", label: "Afternoon" },
    { id: "evening", label: "Evening" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(280px,320px)_1fr] lg:items-start">
        <div className="rounded-2xl border border-border bg-background p-4 shadow-sm">
          <p className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">1. Choose a date</p>
          <Calendar
            mode="single"
            selected={selectedDay}
            onSelect={(day) => {
              if (!day) return;
              setSelectedDay(startOfDay(day));
              setDayPart("all");
              onPick("");
            }}
            defaultMonth={selectedDay || daysWithSlots[0]}
            disabled={(date) =>
              date < startOfDay(windowStart) || date > startOfDay(windowEnd) || !isDayAvailable(date)
            }
            modifiers={{ hasSlots: daysWithSlots }}
            modifiersClassNames={{ hasSlots: "font-semibold text-primary" }}
            className="mx-auto"
          />
          <p className="mt-3 text-center text-[11px] text-muted-foreground">
            Highlighted days have open times · {bookingTzLabel}
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">2. Choose a time</p>
            <p className="mt-1 text-base font-semibold text-foreground">
              {activeGroup ? activeGroup.label : "Select a highlighted date"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {data.slot_minutes}-minute slots · {data.calling_hours_label || "9:00 am – 5:30 pm UK"}
            </p>
          </div>

          {activeGroup ? (
            <>
              <div className="flex flex-wrap gap-2">
                {partTabs.map((tab) => {
                  const count = partCounts[tab.id];
                  if (tab.id !== "all" && count === 0) return null;
                  const active = dayPart === tab.id;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => setDayPart(tab.id)}
                      className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                        active
                          ? "bg-primary text-primary-foreground shadow-sm"
                          : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                      }`}
                    >
                      {tab.label}
                      <span className="ml-1 opacity-70">({count})</span>
                    </button>
                  );
                })}
              </div>

              {filteredSlots.length ? (
                <div className="grid max-h-[22rem] grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3 md:grid-cols-4">
                  {filteredSlots.map((slot) => {
                    const selected = picked === slot;
                    return (
                      <button
                        key={slot}
                        type="button"
                        onClick={() => onPick(slot)}
                        className={`rounded-xl border px-3 py-3 text-center transition ${
                          selected
                            ? "border-primary bg-primary text-primary-foreground shadow-sm"
                            : "border-border bg-background hover:border-primary/50 hover:bg-primary/5"
                        }`}
                      >
                        <span className="block text-sm font-semibold tabular-nums tracking-tight">
                          {fmtTime(slot, bookingTz)}
                        </span>
                        <span className={`mt-0.5 block text-[10px] ${selected ? "opacity-80" : "text-muted-foreground"}`}>
                          {bookingTzLabel}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
                  No {dayPart} times on this day — try another period or date.
                </p>
              )}
            </>
          ) : (
            <p className="rounded-lg border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
              Tap a highlighted date on the calendar to see available times.
            </p>
          )}
        </div>
      </div>

      {picked ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Selected</p>
            <p className="mt-0.5 text-sm font-medium">
              {fmtDate(picked, bookingTz)} · <span className="tabular-nums">{fmtTime(picked, bookingTz)}</span>
            </p>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="size-3.5" />
            {data.slot_minutes} min
          </div>
        </div>
      ) : null}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <Button className="h-12 w-full text-base" disabled={!picked || busy} onClick={onSubmit}>
        {busy ? "Saving…" : actionLabel}
      </Button>
    </div>
  );
}

function PublicBookingPage() {
  const { token } = Route.useParams();
  const { reschedule: openReschedule } = Route.useSearch();
  const qc = useQueryClient();
  const [picked, setPicked] = React.useState<string | null>(null);
  const [channelChoice, setChannelChoice] = React.useState<"phone" | "meeting">("phone");
  const [mode, setMode] = React.useState<"book" | "reschedule">("book");

  const pageQ = useQuery({
    queryKey: ["public-booking", token],
    queryFn: () => publicApiFetch<BookingPage>(`/public/interview-booking/${encodeURIComponent(token)}`),
  });

  const [confirmNotice, setConfirmNotice] = React.useState<string | null>(null);
  const confirmM = useMutation({
    mutationFn: (slot: string) =>
      publicApiFetch<{
        message?: string;
        confirmation_email_sent?: boolean;
        confirmation_email_error?: string;
      }>(`/public/interview-booking/${encodeURIComponent(token)}/confirm`, {
        method: "POST",
        body: JSON.stringify({ slot_start_at: slot, channel: channelChoice }),
      }),
    onSuccess: (res) => {
      setConfirmNotice(
        res?.message ||
          (res?.confirmation_email_sent
            ? "Confirmation email sent — check inbox and spam."
            : "Slot confirmed. If you do not receive an email shortly, note your booked time on this page."),
      );
      setMode("book");
      setPicked(null);
      void qc.invalidateQueries({ queryKey: ["public-booking", token] });
    },
  });

  const rescheduleM = useMutation({
    mutationFn: (slot: string) =>
      publicApiFetch(`/public/interview-booking/${encodeURIComponent(token)}/reschedule`, {
        method: "POST",
        body: JSON.stringify({ slot_start_at: slot }),
      }),
    onSuccess: () => {
      setMode("book");
      setPicked(null);
      void qc.invalidateQueries({ queryKey: ["public-booking", token] });
    },
  });

  const cancelM = useMutation({
    mutationFn: () =>
      publicApiFetch(`/public/interview-booking/${encodeURIComponent(token)}/cancel`, {
        method: "POST",
        body: "{}",
      }),
    onSuccess: () => {
      setMode("book");
      setPicked(null);
      void qc.invalidateQueries({ queryKey: ["public-booking", token] });
    },
  });

  const data = pageQ.data;
  const bookingTz = resolveBookingTz(data);
  const bookingTzLabel = resolveBookingTzLabel(data);

  React.useEffect(() => {
    if (!data?.channel_options) return;
    const defaultChannel = String(data.channel_options.default_channel || "phone").toLowerCase();
    setChannelChoice(defaultChannel === "meeting" ? "meeting" : "phone");
  }, [data?.channel_options, data?.token]);

  React.useEffect(() => {
    if (openReschedule && data?.already_booked) {
      setMode("reschedule");
    }
  }, [openReschedule, data?.already_booked]);

  const activeError =
    (confirmM.error instanceof Error && confirmM.error.message) ||
    (rescheduleM.error instanceof Error && rescheduleM.error.message) ||
    (cancelM.error instanceof Error && cancelM.error.message) ||
    null;
  const busy = confirmM.isPending || rescheduleM.isPending || cancelM.isPending;

  if (pageQ.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (pageQ.isError || !data) {
    const errMsg = pageQ.error instanceof Error ? pageQ.error.message : "This booking link is invalid or has expired.";
    const interviewComplete = /already complete|no longer available/i.test(errMsg);

    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <div className="flex items-center gap-2">
              {interviewComplete ? (
                <CheckCircle2 className="size-5 text-primary" />
              ) : (
                <XCircle className="size-5 text-muted-foreground" />
              )}
              <CardTitle>{interviewComplete ? "Interview complete" : "Link unavailable"}</CardTitle>
            </div>
            <CardDescription>{errMsg}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (data.booking_closed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <div className="flex items-center gap-2">
              <XCircle className="size-5 text-muted-foreground" />
              <CardTitle>Campaign closed</CardTitle>
            </div>
            <CardDescription>
              {data.closed_message ||
                `The ${data.role} role${data.organisation_name ? ` at ${data.organisation_name}` : ""} is no longer accepting bookings.`}
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (data.cancelled_at && !data.already_booked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-8">
        <Card className="w-full max-w-3xl">
          <CardHeader>
            <div className="flex items-center gap-2 text-muted-foreground">
              <XCircle className="size-5" />
              <CardTitle>Interview cancelled</CardTitle>
            </div>
            <CardDescription>
              Hi {data.candidate_name}, your {data.role} interview booking was cancelled. A confirmation email was sent if
              we have your address on file. Pick a new time below if you still want to take part.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <CalendarSlotPicker
              data={data}
              picked={picked}
              onPick={(slot) => setPicked(slot || null)}
              actionLabel="Book a new time"
              busy={busy}
              error={activeError}
              onSubmit={() => picked && confirmM.mutate(picked)}
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (data.already_booked && data.booked_start_at && mode !== "reschedule") {
    const bookingLink =
      data.booking_url ||
      (typeof window !== "undefined" ? `${window.location.origin}/book/${encodeURIComponent(token)}` : "");
    const icsUrl =
      data.calendar_ics_url ||
      `${getApiBaseUrl()}/public/interview-booking/${encodeURIComponent(token)}/calendar.ics`;

    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-8">
        <Card className="w-full max-w-lg">
          <CardHeader>
            <div className="flex items-center gap-2 text-success">
              <CheckCircle2 className="size-5" />
              <CardTitle>You're booked</CardTitle>
            </div>
            <CardDescription>
              Hi {data.candidate_name}, your {data.role} slot is confirmed.
            </CardDescription>
            {confirmNotice ? (
              <p
                className={
                  confirmNotice.includes("could not send")
                    ? "text-sm text-destructive"
                    : "text-sm text-muted-foreground"
                }
              >
                {confirmNotice}
              </p>
            ) : null}
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-4 text-sm">
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Date</p>
                <p className="mt-1 text-base font-medium">{fmtDate(data.booked_start_at, bookingTz)}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Time</p>
                <p className="mt-1 text-base font-medium">{fmtTime(data.booked_start_at, bookingTz)}</p>
              </div>
              {data.organisation_name ? <p className="text-muted-foreground">{data.organisation_name}</p> : null}
              {data.channel === "meeting" && data.meeting_url ? (
                <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm">
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">Online meeting</p>
                  <a
                    href={data.meeting_url}
                    className="mt-1 block font-medium text-primary underline-offset-2 hover:underline"
                  >
                    Join your interview room at the booked time
                  </a>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">We will call you on the number you provided.</p>
              )}
            </div>

            <div className="space-y-2">
              <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <Link2 className="size-3.5" />
                Your booking link
              </p>
              {bookingLink ? <CopyLinkRow label="Save this page" href={bookingLink} /> : null}
              {data.meeting_url ? <CopyLinkRow label="Meeting room" href={data.meeting_url} /> : null}
            </div>

            <div className="space-y-2">
              <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <CalendarPlus className="size-3.5" />
                Add to your calendar
              </p>
              <div className="grid gap-2 sm:grid-cols-3">
                {data.calendar_google_url ? (
                  <a
                    href={data.calendar_google_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2.5 text-sm font-medium hover:bg-muted/50"
                  >
                    Google
                    <ExternalLink className="size-3.5 opacity-60" />
                  </a>
                ) : null}
                {data.calendar_outlook_url ? (
                  <a
                    href={data.calendar_outlook_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2.5 text-sm font-medium hover:bg-muted/50"
                  >
                    Outlook
                    <ExternalLink className="size-3.5 opacity-60" />
                  </a>
                ) : null}
                <a
                  href={icsUrl}
                  className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-background px-3 py-2.5 text-sm font-medium hover:bg-muted/50"
                >
                  Apple / .ics
                  <ExternalLink className="size-3.5 opacity-60" />
                </a>
              </div>
            </div>

            {activeError ? <p className="text-sm text-destructive">{activeError}</p> : null}

            <div className="flex flex-col gap-2 sm:flex-row">
              {data.can_reschedule !== false ? (
                <Button variant="outline" className="flex-1" disabled={busy} onClick={() => setMode("reschedule")}>
                  Reschedule
                </Button>
              ) : null}
              {data.can_cancel !== false ? (
                <Button
                  variant="destructive"
                  className="flex-1"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm("Cancel your interview booking? You can book again later from this link.")) {
                      cancelM.mutate();
                    }
                  }}
                >
                  {cancelM.isPending ? "Cancelling…" : "Cancel interview"}
                </Button>
              ) : null}
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isReschedule = mode === "reschedule" && data.already_booked;

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/20 p-4 sm:p-8">
      <Card className="w-full max-w-4xl shadow-lg">
        <CardHeader className="space-y-4 border-b border-border pb-6">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-primary/10 p-2.5">
              <CalendarClock className="size-6 text-primary" />
            </div>
            <div>
              <CardTitle className="text-xl">{isReschedule ? "Reschedule your interview" : "Book your interview"}</CardTitle>
              <CardDescription className="mt-1 text-sm">
                Hi {data.candidate_name} — pick a date, then a time for{" "}
                <span className="font-medium text-foreground">{data.role}</span>
                {data.organisation_name ? ` at ${data.organisation_name}` : ""}.
              </CardDescription>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Window opens</p>
              <p className="mt-1.5 text-sm font-medium">{fmtWindow(data.window_start, bookingTz)}</p>
            </div>
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Window closes</p>
              <p className="mt-1.5 text-sm font-medium">{fmtWindow(data.window_end, bookingTz)}</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            All times are shown in {bookingTzLabel}. AI calls are made between{" "}
            {data.calling_hours_label || "the calling hours shown above"}.
          </p>
          <p className="text-xs text-muted-foreground">No login required — this link is unique to you.</p>
        </CardHeader>

        <CardContent className="space-y-6 pt-6">
          {isReschedule && data.booked_start_at ? (
            <div className="rounded-lg border border-border bg-muted/20 px-4 py-3 text-sm">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Current booking</p>
              <p className="mt-1 font-medium">
                {fmtDate(data.booked_start_at, bookingTz)} · {fmtTime(data.booked_start_at, bookingTz)}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="ghost" size="sm" className="px-0" onClick={() => setMode("book")}>
                  Keep this time
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm("Cancel your interview booking? You can book again later from this link.")) {
                      cancelM.mutate();
                    }
                  }}
                >
                  {cancelM.isPending ? "Cancelling…" : "Cancel instead"}
                </Button>
              </div>
            </div>
          ) : null}

          {data.channel_options?.phone_available && data.channel_options?.meeting_available ? (
            <div className="rounded-lg border border-border bg-muted/20 px-4 py-4">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                How would you like to interview?
              </p>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setChannelChoice("phone")}
                  className={`rounded-xl border-2 px-4 py-3 text-left transition ${
                    channelChoice === "phone"
                      ? "border-primary bg-primary/10 ring-2 ring-primary/20"
                      : "border-border hover:border-primary/40"
                  }`}
                >
                  <p className="font-medium">Phone call</p>
                  <p className="mt-1 text-xs text-muted-foreground">We call your mobile at the booked time.</p>
                </button>
                <button
                  type="button"
                  onClick={() => setChannelChoice("meeting")}
                  className={`rounded-xl border-2 px-4 py-3 text-left transition ${
                    channelChoice === "meeting"
                      ? "border-primary bg-primary/10 ring-2 ring-primary/20"
                      : "border-border hover:border-primary/40"
                  }`}
                >
                  <p className="font-medium">Online meeting</p>
                  <p className="mt-1 text-xs text-muted-foreground">Join a browser audio room — no app required.</p>
                </button>
              </div>
            </div>
          ) : data.channel_options?.meeting_available && !data.channel_options?.phone_available ? (
            <p className="rounded-lg border border-border bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
              Your interview will be an online audio meeting in your browser.
            </p>
          ) : null}

          <CalendarSlotPicker
            data={data}
            picked={picked}
            onPick={(slot) => setPicked(slot || null)}
            actionLabel={isReschedule ? "Confirm new time" : "Confirm this time"}
            busy={busy}
            error={activeError}
            onSubmit={() => {
              if (!picked) return;
              if (isReschedule) rescheduleM.mutate(picked);
              else confirmM.mutate(picked);
            }}
          />
        </CardContent>
      </Card>
    </div>
  );
}
