import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import { queryKeys } from "@/lib/queries";

type SeatsPayload = {
  ok?: boolean;
  seat_quantity: number;
  billable_seat_quantity?: number;
  free_seat_quantity?: number;
  added_seats_free_until?: string | null;
  trial_started_at?: string | null;
  trial_ends_at?: string | null;
  active_representatives: number;
  min_seats: number;
  max_seats: number;
  unit_price_minor: number;
  currency: string;
  estimated_next_amount_minor: number;
  next_billing_date?: string | null;
  status?: string;
  is_trial?: boolean;
};

function money(minor: number, currency: string) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: (currency || "GBP").toUpperCase(),
    }).format((minor || 0) / 100);
  } catch {
    return `${((minor || 0) / 100).toFixed(2)} ${currency || ""}`.trim();
  }
}

function formatDate(raw?: string | null) {
  if (!raw) return "—";
  const d = new Date(raw);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function SmartCardChangeSeatsDialog({ open, onOpenChange }: Props) {
  const qc = useQueryClient();
  const seatsQ = useQuery({
    queryKey: ["smart-card", "billing", "seats"],
    queryFn: () => apiFetch<SeatsPayload>("/smart-card/billing/seats"),
    enabled: open,
  });
  const [seats, setSeats] = React.useState<number>(1);

  React.useEffect(() => {
    if (seatsQ.data?.seat_quantity) setSeats(Number(seatsQ.data.seat_quantity));
  }, [seatsQ.data?.seat_quantity]);

  const saveMut = useMutation({
    mutationFn: (seat_quantity: number) =>
      apiFetch<SeatsPayload>("/smart-card/billing/seats", {
        method: "PATCH",
        body: JSON.stringify({ seat_quantity }),
      }),
    onSuccess: async (data) => {
      const same = Number(data?.seat_quantity) === Number(seatsQ.data?.seat_quantity);
      toast.success(same ? "Already on that seat count" : "Seat count updated — next invoice recalculated");
      await Promise.all([
        qc.invalidateQueries({ queryKey: ["smart-card"] }),
        qc.invalidateQueries({ queryKey: ["billing"] }),
        qc.invalidateQueries({ queryKey: queryKeys.billingSubscriptionsSummary }),
      ]);
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message || "Could not update seats"),
  });

  const data = seatsQ.data;
  const currentSeats = Number(data?.seat_quantity || 0);
  const minSeats = Math.max(1, Number(data?.min_seats || 1));
  const maxSeats = Math.max(minSeats, Number(data?.max_seats || 500));
  const unit = Number(data?.unit_price_minor || 0);
  const currency = String(data?.currency || "GBP");
  const billable = Number(data?.billable_seat_quantity ?? currentSeats);
  const sameAsCurrent = seats === currentSeats;
  const added = Math.max(0, seats - currentSeats);
  const nextBillable = data?.is_trial
    ? 0
    : seats > currentSeats
      ? billable
      : Math.min(billable, seats);
  const nextAmount = data?.is_trial ? unit * seats : unit * nextBillable;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Change seats</DialogTitle>
          <DialogDescription>
            You currently have <strong>{currentSeats || "—"}</strong> seat
            {currentSeats === 1 ? "" : "s"}. New seats are free for 30 days; existing billable seats keep
            charging. No mid-cycle charge.
          </DialogDescription>
        </DialogHeader>
        {seatsQ.isLoading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : seatsQ.isError ? (
          <p className="text-sm text-destructive">
            {(seatsQ.error as Error)?.message || "Could not load seats"}
          </p>
        ) : (
          <div className="space-y-4 py-2">
            <div className="space-y-1 rounded-md border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              <p>
                Status:{" "}
                <strong className="text-foreground">
                  {data?.is_trial ? "Free trial" : "Active subscription"}
                </strong>
              </p>
              {data?.is_trial ? (
                <p>
                  Free trial: {formatDate(data.trial_started_at)} → {formatDate(data.trial_ends_at)}
                </p>
              ) : null}
              <p>
                Next payment:{" "}
                <strong className="text-foreground">{money(Number(data?.estimated_next_amount_minor || 0), currency)}</strong>
                {" · "}
                {formatDate(data?.next_billing_date)}
              </p>
              {!data?.is_trial && Number(data?.free_seat_quantity || 0) > 0 ? (
                <p>
                  {data?.free_seat_quantity} new seat(s) free until {formatDate(data?.added_seats_free_until)} (
                  {billable} billable now)
                </p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="sc-seats">Seats</Label>
              <Input
                id="sc-seats"
                type="number"
                min={minSeats}
                max={maxSeats}
                value={seats}
                onChange={(e) => setSeats(Number(e.target.value) || minSeats)}
              />
              <p className="text-xs text-muted-foreground">
                Minimum {minSeats} (active representatives). Maximum {maxSeats}.
                {sameAsCurrent ? " Already on this seat count." : null}
              </p>
            </div>
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
              {added > 0 && !data?.is_trial ? (
                <>
                  Adding {added} seat{added === 1 ? "" : "s"} — free for 30 days. Estimated next payment stays{" "}
                  <strong>{money(nextAmount, currency)}</strong> ({nextBillable} × {money(unit, currency)}) until
                  then.
                </>
              ) : (
                <>
                  Estimated next payment: <strong>{money(nextAmount, currency)}</strong>
                  {data?.is_trial ? " after trial" : null} ({seats} × {money(unit, currency)}
                  {!data?.is_trial && nextBillable !== seats ? `, ${nextBillable} billable now` : null})
                </>
              )}
            </p>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saveMut.isPending}>
            Never mind
          </Button>
          <Button
            type="button"
            disabled={
              seatsQ.isLoading ||
              seatsQ.isError ||
              saveMut.isPending ||
              seats < minSeats ||
              seats > maxSeats ||
              sameAsCurrent
            }
            onClick={() => saveMut.mutate(seats)}
          >
            {saveMut.isPending ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" /> Saving…
              </>
            ) : sameAsCurrent ? (
              "Already on these seats"
            ) : (
              "Save seats"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
