import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { CalendarClock, CheckCircle2, Clock, Loader2, XCircle } from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { publicApiFetch } from "@/lib/api";

export const Route = createFileRoute("/book/$token")({
  head: () => ({ meta: [{ title: "Book your interview — VoxBulk" }] }),
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
  can_reschedule?: boolean;
  can_cancel?: boolean;
};

function fmtDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtWindow(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function groupSlotsByDay(slots: string[]) {
  const groups = new Map<string, string[]>();
  for (const slot of slots) {
    const dayKey = new Date(slot).toDateString();
    const list = groups.get(dayKey) || [];
    list.push(slot);
    groups.set(dayKey, list);
  }
  return Array.from(groups.entries()).map(([dayKey, daySlots]) => ({
    dayKey,
    label: fmtDate(daySlots[0]),
    slots: daySlots.sort((a, b) => new Date(a).getTime() - new Date(b).getTime()),
  }));
}

function SlotPicker({
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
  const slotGroups = React.useMemo(
    () => (data.available_slots ? groupSlotsByDay(data.available_slots) : []),
    [data.available_slots],
  );

  return (
    <>
      {data.available_slots.length === 0 ? (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
          No slots left in this window. Please contact the hiring team.
        </p>
      ) : (
        <div className="max-h-[min(28rem,60vh)] space-y-8 overflow-y-auto pr-1">
          {slotGroups.map((group) => (
            <section key={group.dayKey} className="space-y-4">
              <h2 className="text-sm font-semibold text-foreground">{group.label}</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {group.slots.map((slot) => {
                  const selected = picked === slot;
                  return (
                    <button
                      key={slot}
                      type="button"
                      onClick={() => onPick(slot)}
                      className={`flex min-h-[4.5rem] flex-col items-start justify-center rounded-xl border-2 px-4 py-3 text-left transition-all ${
                        selected
                          ? "border-primary bg-primary/10 shadow-sm ring-2 ring-primary/20"
                          : "border-border bg-background hover:border-primary/40 hover:bg-muted/40"
                      }`}
                    >
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Clock className="size-3.5" />
                        {data.slot_minutes} min
                      </span>
                      <span className="mt-1 text-lg font-semibold tabular-nums tracking-tight">{fmtTime(slot)}</span>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </div>
      )}

      {picked && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm">
          <p className="text-xs uppercase tracking-wider text-muted-foreground">Selected</p>
          <p className="mt-1 font-medium">{fmtDate(picked)}</p>
          <p className="text-base font-semibold tabular-nums">{fmtTime(picked)}</p>
        </div>
      )}

      {error ? <p className="text-sm text-destructive">{error}</p> : null}

      <Button className="h-12 w-full text-base" disabled={!picked || busy} onClick={onSubmit}>
        {busy ? "Saving…" : actionLabel}
      </Button>
    </>
  );
}

function PublicBookingPage() {
  const { token } = Route.useParams();
  const qc = useQueryClient();
  const [picked, setPicked] = React.useState<string | null>(null);
  const [mode, setMode] = React.useState<"book" | "reschedule">("book");

  const pageQ = useQuery({
    queryKey: ["public-booking", token],
    queryFn: () => publicApiFetch<BookingPage>(`/public/interview-booking/${encodeURIComponent(token)}`),
  });

  const confirmM = useMutation({
    mutationFn: (slot: string) =>
      publicApiFetch(`/public/interview-booking/${encodeURIComponent(token)}/confirm`, {
        method: "POST",
        body: JSON.stringify({ slot_start_at: slot }),
      }),
    onSuccess: () => {
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
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>Link unavailable</CardTitle>
            <CardDescription>
              {pageQ.error instanceof Error ? pageQ.error.message : "This booking link is invalid or has expired."}
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  if (data.cancelled_at && !data.already_booked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-lg">
          <CardHeader>
            <div className="flex items-center gap-2 text-muted-foreground">
              <XCircle className="size-5" />
              <CardTitle>Interview cancelled</CardTitle>
            </div>
            <CardDescription>
              Hi {data.candidate_name}, your {data.role} interview booking was cancelled. You can pick a new time below if
              you still want to take part.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SlotPicker
              data={data}
              picked={picked}
              onPick={setPicked}
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
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <Card className="w-full max-w-lg">
          <CardHeader>
            <div className="flex items-center gap-2 text-success">
              <CheckCircle2 className="size-5" />
              <CardTitle>You're booked</CardTitle>
            </div>
            <CardDescription>
              Hi {data.candidate_name}, your {data.role} slot is confirmed.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-4 text-sm">
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Date</p>
                <p className="mt-1 text-base font-medium">{fmtDate(data.booked_start_at)}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground">Time</p>
                <p className="mt-1 text-base font-medium">{fmtTime(data.booked_start_at)}</p>
              </div>
              {data.organisation_name ? <p className="text-muted-foreground">{data.organisation_name}</p> : null}
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
      <Card className="w-full max-w-2xl shadow-lg">
        <CardHeader className="space-y-4 border-b border-border pb-6">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-primary/10 p-2.5">
              <CalendarClock className="size-6 text-primary" />
            </div>
            <div>
              <CardTitle className="text-xl">{isReschedule ? "Reschedule your interview" : "Book your interview"}</CardTitle>
              <CardDescription className="mt-1 text-sm">
                Hi {data.candidate_name} — pick a {data.slot_minutes}-minute slot for{" "}
                <span className="font-medium text-foreground">{data.role}</span>
                {data.organisation_name ? ` at ${data.organisation_name}` : ""}.
              </CardDescription>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Window opens</p>
              <p className="mt-1.5 text-sm font-medium">{fmtWindow(data.window_start)}</p>
            </div>
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Window closes</p>
              <p className="mt-1.5 text-sm font-medium">{fmtWindow(data.window_end)}</p>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">No login required — this link is unique to you.</p>
        </CardHeader>

        <CardContent className="space-y-6 pt-6">
          {isReschedule && data.booked_start_at ? (
            <div className="rounded-lg border border-border bg-muted/20 px-4 py-3 text-sm">
              <p className="text-xs uppercase tracking-wider text-muted-foreground">Current booking</p>
              <p className="mt-1 font-medium">
                {fmtDate(data.booked_start_at)} · {fmtTime(data.booked_start_at)}
              </p>
              <Button variant="ghost" size="sm" className="mt-2 px-0" onClick={() => setMode("book")}>
                Keep this time
              </Button>
            </div>
          ) : null}

          <SlotPicker
            data={data}
            picked={picked}
            onPick={setPicked}
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
