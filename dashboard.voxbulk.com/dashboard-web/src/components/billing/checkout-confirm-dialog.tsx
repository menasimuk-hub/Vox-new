import * as React from "react";
import { Loader2 } from "lucide-react";

import { PromoCodeRedeem } from "@/components/billing/promo-code-redeem";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

export type CheckoutConfirmDetails = {
  planName: string;
  intervalLabel?: string | null;
  amountDisplay: string;
  amountNote?: string | null;
  seats?: number | null;
  unitDisplay?: string | null;
  providerHint?: string | null;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  details: CheckoutConfirmDetails | null;
  serviceHint?: string;
  tintClass?: string;
  confirmLabel?: string;
  loading?: boolean;
  onConfirm: () => void | Promise<void>;
};

export function CheckoutConfirmDialog({
  open,
  onOpenChange,
  title = "Confirm payment",
  details,
  serviceHint,
  tintClass = "border-sky-200/80 bg-sky-50/50",
  confirmLabel = "Pay now",
  loading,
  onConfirm,
}: Props) {
  if (!details) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Review what you will pay, apply a promo if you have one, then continue to payment.
          </DialogDescription>
        </DialogHeader>

        <div className={cn("space-y-3 rounded-xl border p-4 text-sm", tintClass)}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Plan</p>
              <p className="text-base font-semibold text-foreground">{details.planName}</p>
              {details.intervalLabel ? (
                <p className="text-xs text-muted-foreground">{details.intervalLabel}</p>
              ) : null}
            </div>
            <div className="text-right">
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Due today</p>
              <p className="text-xl font-semibold tabular-nums text-foreground">{details.amountDisplay}</p>
            </div>
          </div>
          {details.seats != null && details.seats > 0 ? (
            <p className="text-xs text-muted-foreground">
              {details.seats} seat{details.seats === 1 ? "" : "s"}
              {details.unitDisplay ? ` · ${details.unitDisplay} each` : ""}
            </p>
          ) : null}
          {details.amountNote ? <p className="text-xs text-muted-foreground">{details.amountNote}</p> : null}
          {details.providerHint ? <p className="text-xs text-muted-foreground">{details.providerHint}</p> : null}
        </div>

        <PromoCodeRedeem serviceHint={serviceHint} />

        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" disabled={loading} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={loading}
            onClick={() => {
              void onConfirm();
            }}
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" /> Starting…
              </>
            ) : (
              confirmLabel
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
