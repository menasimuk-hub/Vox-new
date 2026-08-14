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
    onSuccess: async () => {
      toast.success("Seat count updated — next invoice recalculated");
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
  const minSeats = Math.max(1, Number(data?.min_seats || 1));
  const maxSeats = Math.max(minSeats, Number(data?.max_seats || 500));
  const unit = Number(data?.unit_price_minor || 0);
  const currency = String(data?.currency || "GBP");
  const nextAmount = unit * Math.max(1, seats);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Change seats</DialogTitle>
          <DialogDescription>
            Adjust how many Smart Card seats you need. Your next invoice updates immediately; you are not
            charged mid-cycle.
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
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span>
                Status:{" "}
                <strong className="text-foreground">
                  {data?.is_trial ? "Free trial" : "Active subscription"}
                </strong>
              </span>
              <span>·</span>
              <span>
                Next billing: <strong className="text-foreground">{formatDate(data?.next_billing_date)}</strong>
              </span>
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
              </p>
            </div>
            <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
              Estimated next payment:{" "}
              <strong>
                {money(nextAmount, currency)}
              </strong>{" "}
              ({seats} × {money(unit, currency)})
            </p>
          </div>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saveMut.isPending}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={seatsQ.isLoading || seatsQ.isError || saveMut.isPending || seats < minSeats || seats > maxSeats}
            onClick={() => saveMut.mutate(seats)}
          >
            {saveMut.isPending ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" /> Saving…
              </>
            ) : (
              "Save seats"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
