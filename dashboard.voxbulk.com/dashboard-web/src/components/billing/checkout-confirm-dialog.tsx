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
import { apiFetch } from "@/lib/api";
import type { PaymentMethodChoice } from "@/lib/billing/subscription-payment";
import { cn } from "@/lib/utils";

export type CheckoutConfirmDetails = {
  planName: string;
  intervalLabel?: string | null;
  amountDisplay: string;
  amountNote?: string | null;
  seats?: number | null;
  unitDisplay?: string | null;
  providerHint?: string | null;
  /** Catalog amount in minor units before promo/VAT (enables live re-quote). */
  amountMinor?: number | null;
  serviceKind?: string | null;
  /** When set, quote/format uses this currency instead of org default. */
  currency?: string | null;
};

type QuoteOut = {
  total_display?: string;
  amount_note?: string;
  discount_applied?: boolean;
  discount_display?: string | null;
  vat_display?: string | null;
  net_display?: string;
  catalog_display?: string;
  trial_days?: number;
  promo_code?: string | null;
  promo_label?: string | null;
  after_trial_display?: string | null;
  total_minor?: number;
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
  onConfirm: (paymentMethod?: PaymentMethodChoice) => void | Promise<void>;
  /** When both GoCardless and Stripe are available, show a picker. */
  paymentMethods?: PaymentMethodChoice[];
  defaultPaymentMethod?: PaymentMethodChoice | null;
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
  paymentMethods,
  defaultPaymentMethod,
}: Props) {
  const [quote, setQuote] = React.useState<QuoteOut | null>(null);
  const [quoting, setQuoting] = React.useState(false);
  const methods = paymentMethods?.length ? paymentMethods : [];
  // Prefer Card when available; never persist — always show full picker each open.
  const preferredDefault: PaymentMethodChoice =
    (methods.includes("stripe") ? "stripe" : null) ||
    defaultPaymentMethod ||
    methods[0] ||
    "gocardless";
  const [paymentMethod, setPaymentMethod] = React.useState<PaymentMethodChoice>(preferredDefault);

  React.useEffect(() => {
    if (!open) return;
    const next: PaymentMethodChoice =
      (methods.includes("stripe") ? "stripe" : null) ||
      defaultPaymentMethod ||
      methods[0] ||
      "gocardless";
    setPaymentMethod(next);
  }, [open, defaultPaymentMethod, methods.join("|")]);

  const refreshQuote = React.useCallback(async () => {
    if (!details?.amountMinor || details.amountMinor <= 0 || !details.serviceKind) {
      setQuote(null);
      return;
    }
    setQuoting(true);
    try {
      const res = await apiFetch<QuoteOut>("/billing/checkout/quote", {
        method: "POST",
        body: JSON.stringify({
          amount_minor: details.amountMinor,
          service_kind: details.serviceKind,
          ...(details.currency ? { currency: details.currency } : {}),
        }),
      });
      setQuote(res);
    } catch {
      setQuote(null);
    } finally {
      setQuoting(false);
    }
  }, [details?.amountMinor, details?.serviceKind, details?.currency]);

  React.useEffect(() => {
    if (!open) {
      setQuote(null);
      return;
    }
    void refreshQuote();
  }, [open, refreshQuote]);

  if (!details) return null;

  const catalogDisplay = quote?.catalog_display || details.amountDisplay;
  const dueToday = quote?.total_display || details.amountDisplay;
  const amountNote = quote?.amount_note || details.amountNote;
  const trialDays = Number(quote?.trial_days || 0);
  const dueZero = trialDays > 0 || Number(quote?.total_minor || 0) === 0;

  let payLabel = confirmLabel;
  if (methods.length) {
    if (dueZero && paymentMethod === "stripe") {
      payLabel = trialDays > 0 ? "Start free trial" : "Activate with promo";
    } else if (paymentMethod === "gocardless") {
      payLabel = trialDays > 0 ? "Continue to Direct Debit (trial)" : "Continue to Direct Debit";
    } else {
      payLabel = "Pay with card";
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            Review package price, promo, and total due, then choose how to pay.
          </DialogDescription>
        </DialogHeader>

        <div className={cn("space-y-3 rounded-xl border p-4 text-sm", tintClass)}>
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Plan</p>
            <p className="text-base font-semibold text-foreground">{details.planName}</p>
            {details.intervalLabel ? (
              <p className="text-xs text-muted-foreground">{details.intervalLabel}</p>
            ) : null}
          </div>

          <div className="space-y-1.5 border-t border-black/5 pt-3 dark:border-white/10">
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">Package price</span>
              <span className="tabular-nums font-medium">{quoting ? "…" : catalogDisplay}</span>
            </div>
            <div className="flex items-start justify-between gap-3">
              <span className="text-muted-foreground">Promo</span>
              <span className="max-w-[60%] text-right text-emerald-700 dark:text-emerald-400">
                {quoting
                  ? "…"
                  : quote?.discount_applied
                    ? [
                        quote.promo_code ? `Promo ${quote.promo_code}` : "Promo",
                        quote.promo_label ||
                          (quote.discount_display ? `−${quote.discount_display}` : null),
                      ]
                        .filter(Boolean)
                        .join(" · ")
                    : "No promo applied"}
              </span>
            </div>
            {details.seats != null && details.seats > 0 ? (
              <p className="text-xs text-muted-foreground">
                {details.seats} seat{details.seats === 1 ? "" : "s"}
                {details.unitDisplay ? ` · ${details.unitDisplay} each` : ""}
              </p>
            ) : null}
            {quote?.vat_display ? (
              <p className="text-xs text-muted-foreground">
                Net {quote.net_display}
                {quote.vat_display ? ` · VAT ${quote.vat_display}` : ""}
              </p>
            ) : null}
          </div>

          <div className="flex items-end justify-between gap-3 border-t border-black/5 pt-3 dark:border-white/10">
            <div>
              <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Total due today</p>
              {trialDays > 0 && quote?.after_trial_display ? (
                <p className="text-xs text-muted-foreground">Then {quote.after_trial_display} after {trialDays} days</p>
              ) : null}
            </div>
            <p className="text-2xl font-semibold tabular-nums text-foreground">{quoting ? "…" : dueToday}</p>
          </div>
          {amountNote ? <p className="text-xs text-muted-foreground">{amountNote}</p> : null}
        </div>

        <PromoCodeRedeem
          serviceHint={serviceHint}
          onRedeemed={() => {
            void refreshQuote();
          }}
        />

        {methods.length > 0 ? (
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Pay with</p>
            <div className="grid gap-2">
              {methods.includes("stripe") ? (
                <label
                  className={cn(
                    "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-sm",
                    paymentMethod === "stripe" ? "border-sky-500 bg-sky-50/80 dark:bg-sky-950/30" : "",
                  )}
                >
                  <input
                    type="radio"
                    name="checkout-pay-method"
                    checked={paymentMethod === "stripe"}
                    onChange={() => setPaymentMethod("stripe")}
                  />
                  <span>
                    <span className="font-medium">Card</span>
                    <span className="block text-xs text-muted-foreground">Stripe — pay by card</span>
                  </span>
                </label>
              ) : null}
              {methods.includes("gocardless") ? (
                <label
                  className={cn(
                    "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-sm",
                    paymentMethod === "gocardless" ? "border-sky-500 bg-sky-50/80 dark:bg-sky-950/30" : "",
                  )}
                >
                  <input
                    type="radio"
                    name="checkout-pay-method"
                    checked={paymentMethod === "gocardless"}
                    onChange={() => setPaymentMethod("gocardless")}
                  />
                  <span>
                    <span className="font-medium">Direct Debit</span>
                    <span className="block text-xs text-muted-foreground">GoCardless — bank mandate</span>
                  </span>
                </label>
              ) : null}
            </div>
          </div>
        ) : details.providerHint ? (
          <p className="text-xs text-muted-foreground">{details.providerHint}</p>
        ) : null}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" disabled={loading} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={loading}
            onClick={() => {
              void onConfirm(methods.length ? paymentMethod : undefined);
            }}
          >
            {loading ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" /> Starting…
              </>
            ) : (
              payLabel
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
