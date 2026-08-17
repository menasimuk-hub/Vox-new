import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
  const m = String(raw).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) {
    const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  }
  const d = new Date(raw);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Prefill seat count when opening from Billing packages. */
  initialSeats?: number | null;
};

export function SmartCardChangeSeatsDialog({ open, onOpenChange, initialSeats = null }: Props) {
  const qc = useQueryClient();
  const seatsQ = useQuery({
    queryKey: ["smart-card", "billing", "seats"],
    queryFn: () => apiFetch<SeatsPayload>("/smart-card/billing/seats"),
    enabled: open,
  });
  const [seats, setSeats] = React.useState<number>(1);
  const [step, setStep] = React.useState<"edit" | "confirm">("edit");
  const [acknowledged, setAcknowledged] = React.useState(false);

  React.useEffect(() => {
    if (!open) {
      setStep("edit");
      setAcknowledged(false);
      return;
    }
    if (initialSeats != null && Number.isFinite(initialSeats)) {
      setSeats(Math.max(1, Math.floor(Number(initialSeats))));
    } else if (seatsQ.data?.seat_quantity) {
      setSeats(Number(seatsQ.data.seat_quantity));
    }
  }, [open, initialSeats, seatsQ.data?.seat_quantity]);

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
  const laterBillable = data?.is_trial ? seats : seats;
  const laterAmount = unit * laterBillable;
  const freeUntilEstimate =
    added > 0 && !data?.is_trial
      ? formatDate(
          data?.added_seats_free_until ||
            new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
        )
      : formatDate(data?.added_seats_free_until);
  const billingDate = formatDate(data?.next_billing_date);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{step === "edit" ? "Change seats" : "Confirm seat change"}</DialogTitle>
          <DialogDescription>
            {step === "edit" ? (
              <>
                You currently have <strong>{currentSeats || "—"}</strong> seat
                {currentSeats === 1 ? "" : "s"}. New seats are free for 30 days; existing billable seats keep
                charging. No mid-cycle charge.
              </>
            ) : (
              <>Review the next payment amount and date, then confirm.</>
            )}
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
        ) : step === "edit" ? (
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
                <strong className="text-foreground">
                  {money(Number(data?.estimated_next_amount_minor || 0), currency)}
                </strong>
                {" · "}
                {billingDate}
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
        ) : (
          <div className="space-y-4 py-2">
            <div className="space-y-2 rounded-md border bg-muted/40 px-3 py-3 text-sm">
              <p>
                Seats: <strong>{currentSeats}</strong> → <strong>{seats}</strong>
              </p>
              {added > 0 && !data?.is_trial ? (
                <p>
                  {added} new seat{added === 1 ? "" : "s"} free until <strong>{freeUntilEstimate}</strong>. Next
                  payment stays <strong>{money(nextAmount, currency)}</strong> on <strong>{billingDate}</strong> (
                  {nextBillable} billable).
                </p>
              ) : data?.is_trial ? (
                <p>
                  During trial you are not charged. After trial, payment will be{" "}
                  <strong>{money(laterAmount, currency)}</strong> ({seats} × {money(unit, currency)}) from{" "}
                  <strong>{formatDate(data?.trial_ends_at) || billingDate}</strong>.
                </p>
              ) : (
                <p>
                  Next payment: <strong>{money(nextAmount, currency)}</strong> on <strong>{billingDate}</strong>.
                </p>
              )}
              {added > 0 && !data?.is_trial ? (
                <p className="text-xs text-muted-foreground">
                  After the free window, billing becomes{" "}
                  <strong className="text-foreground">{money(laterAmount, currency)}</strong> ({laterBillable} ×{" "}
                  {money(unit, currency)}).
                </p>
              ) : null}
            </div>
            <label className="flex items-start gap-2 text-sm leading-snug">
              <Checkbox
                checked={acknowledged}
                onCheckedChange={(v) => setAcknowledged(v === true)}
                className="mt-0.5"
              />
              <span>
                I understand the next payment will be <strong>{money(nextAmount, currency)}</strong> on{" "}
                <strong>{data?.is_trial ? formatDate(data?.trial_ends_at) || billingDate : billingDate}</strong>
                {added > 0 && !data?.is_trial
                  ? `, and later ${money(laterAmount, currency)} after free seats end`
                  : null}
                .
              </span>
            </label>
          </div>
        )}
        <DialogFooter>
          {step === "confirm" ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setStep("edit");
                setAcknowledged(false);
              }}
              disabled={saveMut.isPending}
            >
              Back
            </Button>
          ) : (
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saveMut.isPending}>
              Never mind
            </Button>
          )}
          {step === "edit" ? (
            <Button
              type="button"
              disabled={
                seatsQ.isLoading ||
                seatsQ.isError ||
                seats < minSeats ||
                seats > maxSeats ||
                sameAsCurrent
              }
              onClick={() => {
                setAcknowledged(false);
                setStep("confirm");
              }}
            >
              {sameAsCurrent ? "Already on these seats" : "Continue"}
            </Button>
          ) : (
            <Button
              type="button"
              disabled={!acknowledged || saveMut.isPending}
              onClick={() => saveMut.mutate(seats)}
            >
              {saveMut.isPending ? (
                <>
                  <Loader2 className="mr-2 size-4 animate-spin" /> Saving…
                </>
              ) : (
                "Confirm seat change"
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
