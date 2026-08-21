import * as React from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Minus, Plus } from "lucide-react";
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
  billing_interval?: string | null;
  remaining_fraction?: number;
  charge_now_minor?: number;
  change_kind?: string;
};

type PreviewPayload = {
  ok?: boolean;
  seat_quantity: number;
  current_seat_quantity: number;
  seats_added: number;
  active_representatives: number;
  min_seats: number;
  blocked: boolean;
  block_reason?: string | null;
  is_trial?: boolean;
  charge_now_minor: number;
  estimated_next_amount_minor: number;
  unit_price_minor: number;
  currency: string;
  billing_interval?: string | null;
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

  const previewQ = useQuery({
    queryKey: ["smart-card", "billing", "seats", "preview", seats],
    queryFn: () =>
      apiFetch<PreviewPayload>(`/smart-card/billing/seats/preview?seat_quantity=${encodeURIComponent(String(seats))}`),
    enabled: open && step === "edit" && Number.isFinite(seats) && seats >= 1,
  });

  const saveMut = useMutation({
    mutationFn: (seat_quantity: number) =>
      apiFetch<SeatsPayload>("/smart-card/billing/seats", {
        method: "PATCH",
        body: JSON.stringify({ seat_quantity }),
      }),
    onSuccess: async (data) => {
      const charged = Number(data?.charge_now_minor || 0);
      const same = Number(data?.seat_quantity) === Number(seatsQ.data?.seat_quantity);
      if (same) {
        toast.success("Already on that seat count");
      } else if (charged > 0) {
        toast.success(`Seats updated — charged ${money(charged, data.currency || "GBP")} for new seats`);
      } else {
        toast.success("Seat count updated — next invoice recalculated");
      }
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
  const preview = previewQ.data;
  const currentSeats = Number(data?.seat_quantity || 0);
  const minSeats = Math.max(1, Number(preview?.min_seats ?? data?.min_seats ?? 1));
  const maxSeats = Math.max(minSeats, Number(data?.max_seats || 500));
  const unit = Number(preview?.unit_price_minor ?? data?.unit_price_minor ?? 0);
  const currency = String(preview?.currency || data?.currency || "GBP");
  const sameAsCurrent = seats === currentSeats;
  const added = Math.max(0, seats - currentSeats);
  const belowMin = seats < minSeats;
  const blocked = Boolean(preview?.blocked) || belowMin;
  const chargeNow = Number(preview?.charge_now_minor || 0);
  const nextAmount = Number(preview?.estimated_next_amount_minor ?? data?.estimated_next_amount_minor ?? 0);
  const billingDate = formatDate(data?.next_billing_date);
  const interval = String(preview?.billing_interval || data?.billing_interval || "monthly");
  const canContinue = !seatsQ.isLoading && !seatsQ.isError && !sameAsCurrent && !blocked && seats <= maxSeats;

  const clampSeats = (n: number) => Math.max(1, Math.min(maxSeats, Math.floor(n) || 1));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{step === "edit" ? "Change seats" : "Confirm seat change"}</DialogTitle>
          <DialogDescription>
            {step === "edit" ? (
              <>
                You currently have <strong>{currentSeats || "—"}</strong> seat
                {currentSeats === 1 ? "" : "s"} ({interval}). Add seats to pay a prorated amount now; reduce seats
                to lower the next invoice.
              </>
            ) : (
              <>Review the charge and next payment, then confirm.</>
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
                {" · "}
                <strong className="text-foreground capitalize">{interval}</strong>
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
              <p>
                Active representatives:{" "}
                <strong className="text-foreground">{Number(data?.active_representatives || 0)}</strong>
                {" — "}minimum seats is {minSeats}.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="sc-seats">Seats</Label>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="shrink-0"
                  disabled={seats <= 1}
                  onClick={() => setSeats((s) => clampSeats(s - 1))}
                  aria-label="Fewer seats"
                >
                  <Minus className="size-4" />
                </Button>
                <Input
                  id="sc-seats"
                  type="number"
                  min={1}
                  max={maxSeats}
                  value={seats}
                  onChange={(e) => setSeats(clampSeats(Number(e.target.value) || 1))}
                  className="text-center"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="shrink-0"
                  disabled={seats >= maxSeats}
                  onClick={() => setSeats((s) => clampSeats(s + 1))}
                  aria-label="More seats"
                >
                  <Plus className="size-4" />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Minimum {minSeats} (active representatives). Maximum {maxSeats}.
                {sameAsCurrent ? " Already on this seat count." : null}
              </p>
            </div>
            {blocked && !sameAsCurrent ? (
              <div className="rounded-md border border-amber-300/80 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
                <p>
                  {preview?.block_reason ||
                    `You have ${minSeats} active representative(s). Archive extras before downgrading.`}
                </p>
                <Link
                  to="/smart-card"
                  className="mt-1 inline-block text-sm font-medium underline underline-offset-2"
                  onClick={() => onOpenChange(false)}
                >
                  Open Smart Card to archive representatives
                </Link>
              </div>
            ) : null}
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
              {previewQ.isFetching ? (
                <span className="inline-flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="size-3.5 animate-spin" /> Calculating…
                </span>
              ) : added > 0 && !data?.is_trial ? (
                <>
                  Adding {added} seat{added === 1 ? "" : "s"} — due now{" "}
                  <strong>{money(chargeNow, currency)}</strong> (prorated for the rest of this {interval} period).
                  Next renewal: <strong>{money(nextAmount, currency)}</strong> ({seats} × {money(unit, currency)}).
                </>
              ) : seats < currentSeats && !blocked ? (
                <>
                  Reduce to {seats} seat{seats === 1 ? "" : "s"} — no charge now. Next invoice becomes{" "}
                  <strong>{money(nextAmount, currency)}</strong>.
                </>
              ) : data?.is_trial && !sameAsCurrent ? (
                <>
                  During trial there is no charge. After trial:{" "}
                  <strong>{money(nextAmount, currency)}</strong> ({seats} × {money(unit, currency)}).
                </>
              ) : (
                <>Already on this seat count.</>
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
                  Due now: <strong>{money(chargeNow, currency)}</strong> for {added} new seat
                  {added === 1 ? "" : "s"} (prorated).
                </p>
              ) : null}
              <p>
                Next payment: <strong>{money(nextAmount, currency)}</strong>
                {data?.is_trial ? " after trial" : null} on{" "}
                <strong>{data?.is_trial ? formatDate(data?.trial_ends_at) || billingDate : billingDate}</strong>.
              </p>
            </div>
            <label className="flex items-start gap-2 text-sm leading-snug">
              <Checkbox
                checked={acknowledged}
                onCheckedChange={(v) => setAcknowledged(v === true)}
                className="mt-0.5"
              />
              <span>
                I understand
                {added > 0 && !data?.is_trial ? (
                  <>
                    {" "}
                    I will be charged <strong>{money(chargeNow, currency)}</strong> now, and
                  </>
                ) : null}{" "}
                the next payment will be <strong>{money(nextAmount, currency)}</strong> on{" "}
                <strong>{data?.is_trial ? formatDate(data?.trial_ends_at) || billingDate : billingDate}</strong>.
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
              disabled={!canContinue}
              onClick={() => {
                setAcknowledged(false);
                setStep("confirm");
              }}
            >
              {sameAsCurrent ? "Already on these seats" : blocked ? "Fix representatives first" : "Continue"}
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
              ) : added > 0 && !data?.is_trial && chargeNow > 0 ? (
                `Pay ${money(chargeNow, currency)} & confirm`
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
