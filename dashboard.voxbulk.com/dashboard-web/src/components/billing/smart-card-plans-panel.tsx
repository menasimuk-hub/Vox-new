import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearch } from "@tanstack/react-router";
import { toast } from "sonner";

import { CheckoutConfirmDialog, type CheckoutConfirmDetails } from "@/components/billing/checkout-confirm-dialog";
import { SmartCardChangeSeatsDialog } from "@/components/billing/smart-card-change-seats-dialog";
import { StripeCardCheckoutDialog } from "@/components/billing/stripe-card-checkout-dialog";
import { SERVICE_TINTS } from "@/components/billing/service-package-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import {
  clearBillingQuery,
  readBillingReturnParams,
} from "@/lib/billing/gocardless";
import {
  countryToMarket,
  marketCurrencySymbol,
  orgCountryToCurrencyCode,
  pickPriceMinor,
} from "@/lib/billing/market";
import {
  clearSmartCardCardCheckoutState,
  completeSmartCardGoCardless,
  completeSmartCardSeatCheckout,
  GC_SMART_CARD_FLOW_KEY,
  startSmartCardGoCardless,
  startSmartCardSeatCheckout,
} from "@/lib/billing/smart-card-subscription-payment";
import {
  availablePaymentMethods,
  isStripeElementsCheckout,
  primarySubscriptionProvider,
  type PaymentMethodChoice,
  type StripeElementsCheckout,
} from "@/lib/billing/subscription-payment";
import { useBillingSubscriptionsSummary, useOrganisation } from "@/lib/queries";
import { useSession } from "@/lib/session";
import { ActiveSubscriptionHeader } from "@/components/billing/active-subscription-header";

type PackageItem = {
  id: string;
  plan_id: string;
  code: string;
  name: string;
  description?: string | null;
  prices: Array<{ currency: string; monthly_price_minor?: number | null; yearly_price_minor?: number | null }>;
};

type BillingInterval = "monthly" | "yearly";

const CURRENCY_TO_MARKET: Record<string, string> = {
  GBP: "gbp",
  EUR: "eur",
  USD: "usd",
  CAD: "cad",
  AUD: "aud",
};

function symbolForCurrency(code: string) {
  return marketCurrencySymbol(CURRENCY_TO_MARKET[String(code || "").toUpperCase()] || "usd");
}

function BillingIntervalToggle({
  value,
  onChange,
}: {
  value: BillingInterval;
  onChange: (v: BillingInterval) => void;
}) {
  return (
    <div className="mb-3 flex flex-col items-center gap-2">
      <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Billing period</p>
      <div className="flex rounded-full border border-border bg-background p-1 text-xs shadow-sm">
        <button
          type="button"
          className={`rounded-full px-4 py-2 transition-colors ${value === "monthly" ? "bg-primary text-primary-foreground shadow" : "text-muted-foreground hover:text-foreground"}`}
          onClick={() => onChange("monthly")}
        >
          Monthly
        </button>
        <button
          type="button"
          className={`inline-flex items-center gap-2 rounded-full px-4 py-2 transition-colors ${value === "yearly" ? "bg-primary text-primary-foreground shadow" : "text-muted-foreground hover:text-foreground"}`}
          onClick={() => onChange("yearly")}
        >
          Yearly
          <span className="rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            20% off
          </span>
        </button>
      </div>
    </div>
  );
}

export function SmartCardPlansPanel() {
  const search = useSearch({ strict: false }) as {
    billing?: string;
    payment_intent?: string;
    setup_intent?: string;
    redirect_flow_id?: string;
  };
  const qc = useQueryClient();
  const orgQ = useOrganisation();
  const { session } = useSession();
  const subsSummaryQ = useBillingSubscriptionsSummary();
  const [seatsByPlan, setSeatsByPlan] = React.useState<Record<string, number>>({});
  const [billingInterval, setBillingInterval] = React.useState<BillingInterval>("monthly");
  const [checkoutOpen, setCheckoutOpen] = React.useState(false);
  const [checkoutDetails, setCheckoutDetails] = React.useState<CheckoutConfirmDetails | null>(null);
  const [pendingCheckout, setPendingCheckout] = React.useState<{ planId: string; seats: number; name: string } | null>(
    null,
  );
  const [stripeCheckout, setStripeCheckout] = React.useState<StripeElementsCheckout | null>(null);
  const [seatsDialogOpen, setSeatsDialogOpen] = React.useState(false);
  const [pendingSeatCount, setPendingSeatCount] = React.useState<number | null>(null);
  const completingRef = React.useRef(false);

  const orgCountry = orgQ.data?.country;
  const currencyCode = orgCountryToCurrencyCode(orgCountry);
  const currencySym = marketCurrencySymbol(countryToMarket(orgCountry));
  const subscription = session?.subscription as Record<string, unknown> | null | undefined;
  const paymentMethods = availablePaymentMethods(subscription);
  const primaryProvider = primarySubscriptionProvider(subscription);
  const defaultPayMethod: PaymentMethodChoice =
    (paymentMethods.includes(primaryProvider as PaymentMethodChoice)
      ? (primaryProvider as PaymentMethodChoice)
      : paymentMethods[0]) || "gocardless";

  const packagesQ = useQuery({
    queryKey: ["smart-card", "packages"],
    queryFn: () => apiFetch<{ ok: boolean; items: PackageItem[] }>("/smart-card/packages"),
  });

  React.useEffect(() => {
    if (completingRef.current) return;
    const params = readBillingReturnParams();
    let gcFlow = "";
    try {
      gcFlow = (sessionStorage.getItem(GC_SMART_CARD_FLOW_KEY) || "").trim();
    } catch {
      /* ignore */
    }
    const redirectId = (search.redirect_flow_id || params.redirectFlowId || gcFlow || "").trim();
    if (redirectId && (params.billing === "success" || search.billing === "success" || gcFlow)) {
      completingRef.current = true;
      void (async () => {
        try {
          await completeSmartCardGoCardless(redirectId);
          toast.success("Smart Card seats activated");
          try {
            sessionStorage.removeItem(GC_SMART_CARD_FLOW_KEY);
          } catch {
            /* ignore */
          }
          clearBillingQuery();
          await qc.invalidateQueries({ queryKey: ["smart-card"] });
          await qc.invalidateQueries({ queryKey: ["billing"] });
        } catch (e: unknown) {
          toast.error(e instanceof Error ? e.message : "Could not complete Direct Debit signup");
        }
      })();
      return;
    }

    const pi =
      search.setup_intent ||
      search.payment_intent ||
      (typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("setup_intent") ||
          new URLSearchParams(window.location.search).get("payment_intent")
        : null);
    if (!pi) return;
    if (search.billing && search.billing !== "card_success") return;
    completingRef.current = true;
    void (async () => {
      try {
        await completeSmartCardSeatCheckout(pi);
        toast.success("Seats activated");
        clearSmartCardCardCheckoutState();
        await qc.invalidateQueries({ queryKey: ["smart-card"] });
        await qc.invalidateQueries({ queryKey: ["billing"] });
      } catch (e: unknown) {
        toast.error(e instanceof Error ? e.message : "Could not activate seats");
      }
    })();
  }, [search.billing, search.payment_intent, search.setup_intent, search.redirect_flow_id, qc]);

  const checkoutMut = useMutation({
    mutationFn: async ({
      planId,
      seats,
      paymentMethod,
    }: {
      planId: string;
      seats: number;
      paymentMethod?: PaymentMethodChoice;
    }) => {
      const method = paymentMethod || defaultPayMethod;
      if (method === "gocardless") {
        await startSmartCardGoCardless(planId, seats, billingInterval);
        return { provider: "gocardless" };
      }
      const result = await startSmartCardSeatCheckout(planId, seats, billingInterval, "stripe");
      if (result.provider === "promo_discount" && result.paid) {
        toast.success("Seats activated with promo");
        await qc.invalidateQueries({ queryKey: ["smart-card"] });
        await qc.invalidateQueries({ queryKey: ["billing"] });
      } else if (isStripeElementsCheckout(result)) {
        setStripeCheckout(result);
      }
      return result;
    },
    onError: (e: Error) => {
      toast.error(e.message || "Checkout failed");
    },
  });

  const finance =
    (subsSummaryQ.data as { smart_card?: Record<string, unknown> } | undefined)?.smart_card || null;
  const tint = SERVICE_TINTS.smartCard;
  const items = packagesQ.data?.items || [];
  const currentSeats = Number(finance?.seat_quantity || 0);
  const hasActiveSub = Boolean(finance?.plan_name || finance?.plan_code || currentSeats > 0);
  const isTrial = Boolean(finance?.is_trial) || String(finance?.status || "").toLowerCase() === "trial";

  React.useEffect(() => {
    if (!hasActiveSub || currentSeats < 1 || items.length === 0) return;
    setSeatsByPlan((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const pkg of items) {
        if (next[pkg.plan_id] == null) {
          next[pkg.plan_id] = currentSeats;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [hasActiveSub, currentSeats, items]);

  return (
    <div className="space-y-4">
      <ActiveSubscriptionHeader
        title="Smart Card subscription"
        finance={finance as Parameters<typeof ActiveSubscriptionHeader>[0]["finance"]}
        loading={subsSummaryQ.isLoading}
        emptyMessage="No active Smart Card subscription."
        tintClass={tint.soft}
      />

      <Card className="border-violet-200/60 bg-violet-50/40">
        <CardContent className="space-y-1 p-4 text-sm">
          <p className="font-medium text-foreground">Offer: 1 month free, then pay per seat</p>
          <p className="text-muted-foreground">
            {hasActiveSub
              ? `You already have ${currentSeats} seat${currentSeats === 1 ? "" : "s"}. Adding seats gives new seats 30 days free; existing billable seats keep charging.`
              : "Choose seats and add a payment method at signup — you are not charged today. After the trial, billing is seats × price each cycle."}
          </p>
          {hasActiveSub ? (
            <p className="text-xs text-muted-foreground">
              {isTrial
                ? `Free trial ${String(finance?.trial_started_at || "").slice(0, 10) || "—"} → ${String(finance?.trial_ends_at || finance?.current_period_end || "").slice(0, 10) || "—"}`
                : `Next payment ${String(finance?.amount_next_payment_display || "—")} · ${String(finance?.next_billing_date || "").slice(0, 10) || "—"}`}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Flat {currencySym}5/seat/month (local equivalent). First month free on signup. New seats added later also get
        30 days free. Yearly includes 20% off after the trial.
      </p>

      {!hasActiveSub ? <BillingIntervalToggle value={billingInterval} onChange={setBillingInterval} /> : null}

      {packagesQ.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-64 rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-muted-foreground">
            No Smart Card packages available yet.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((pkg) => {
            const price = pickPriceMinor(pkg.prices, currencyCode, { yearly: billingInterval === "yearly" });
            const seats = seatsByPlan[pkg.plan_id] ?? (hasActiveSub ? currentSeats : 1);
            const unit = price.amountMinor;
            const total = unit != null ? (unit * seats) / 100 : null;
            const sym = unit != null ? symbolForCurrency(price.currency) : currencySym;
            const sameSeats = hasActiveSub && seats === currentSeats;
            return (
              <Card key={pkg.id} className="flex flex-col border-violet-200/50 bg-background/80">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">{pkg.name}</CardTitle>
                  <p className="font-medium text-foreground">
                    {unit != null
                      ? `${sym}${(unit / 100).toFixed(0)} / seat / ${billingInterval === "yearly" ? "year" : "month"}`
                      : "See Admin pricing"}
                  </p>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col space-y-3 text-sm text-muted-foreground">
                  {pkg.description ? <p>{pkg.description}</p> : null}
                  {hasActiveSub ? (
                    <p className="text-xs">
                      You already have {currentSeats} seat{currentSeats === 1 ? "" : "s"}.
                    </p>
                  ) : null}
                  <div className="space-y-1.5">
                    <Label>Seats</Label>
                    <Input
                      type="number"
                      min={1}
                      max={500}
                      value={seats}
                      onChange={(e) =>
                        setSeatsByPlan((prev) => ({
                          ...prev,
                          [pkg.plan_id]: Math.max(1, Math.min(500, Number(e.target.value) || 1)),
                        }))
                      }
                    />
                  </div>
                  {total != null ? (
                    <p className="text-foreground">
                      {hasActiveSub ? (
                        sameSeats ? (
                          <>
                            Already on {currentSeats} seat{currentSeats === 1 ? "" : "s"}
                          </>
                        ) : seats > currentSeats ? (
                          <>
                            Add {seats - currentSeats} seat(s) — free for 30 days; next bill stays based on current
                            billable seats
                          </>
                        ) : (
                          <>
                            Reduce to {seats} seat{seats === 1 ? "" : "s"} — next invoice updates
                          </>
                        )
                      ) : (
                        <>
                          Due today: {sym}0{" "}
                          <span className="text-muted-foreground">
                            (then {sym}
                            {total.toFixed(0)} / {billingInterval === "yearly" ? "year" : "month"} after trial)
                          </span>
                        </>
                      )}
                    </p>
                  ) : null}
                  <Button
                    className="mt-auto w-full"
                    disabled={
                      hasActiveSub
                        ? sameSeats || !pkg.plan_id
                        : checkoutMut.isPending || !pkg.plan_id || paymentMethods.length === 0
                    }
                    onClick={() => {
                      if (hasActiveSub) {
                        if (sameSeats) {
                          toast.message(`Already on ${currentSeats} seat${currentSeats === 1 ? "" : "s"}`);
                          return;
                        }
                        setPendingSeatCount(seats);
                        setSeatsDialogOpen(true);
                        return;
                      }
                      if (unit == null || total == null) {
                        toast.error("Price not available for your currency");
                        return;
                      }
                      if (paymentMethods.length === 0) {
                        toast.error("No subscription payment method is configured for your region.");
                        return;
                      }
                      setPendingCheckout({ planId: pkg.plan_id, seats, name: pkg.name });
                      setCheckoutDetails({
                        planName: pkg.name,
                        intervalLabel:
                          billingInterval === "yearly" ? "Yearly billing (20% off)" : "Monthly billing",
                        amountDisplay: `${sym}${total.toFixed(0)}`,
                        seats,
                        unitDisplay: `${sym}${(unit / 100).toFixed(0)}`,
                        amountNote: "Ex-VAT. VAT may be added at checkout when applicable.",
                        amountMinor: Math.round(total * 100),
                        serviceKind: "smart_card",
                        trial_days: 30,
                        after_trial_display: `${sym}${total.toFixed(0)} / ${billingInterval === "yearly" ? "year" : "month"}`,
                      });
                      setCheckoutOpen(true);
                    }}
                  >
                    {hasActiveSub
                      ? sameSeats
                        ? "Already on these seats"
                        : "Update seats"
                      : checkoutMut.isPending
                        ? "Starting…"
                        : "Subscribe"}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      <CheckoutConfirmDialog
        open={checkoutOpen}
        onOpenChange={(open) => {
          setCheckoutOpen(open);
          if (!open) {
            setPendingCheckout(null);
            setCheckoutDetails(null);
          }
        }}
        details={checkoutDetails}
        serviceHint="Smart Card"
        tintClass={tint.soft}
        confirmLabel="Continue to payment"
        paymentMethods={paymentMethods}
        defaultPaymentMethod={defaultPayMethod}
        loading={checkoutMut.isPending}
        onConfirm={async (paymentMethod) => {
          if (!pendingCheckout) return;
          setCheckoutOpen(false);
          await checkoutMut.mutateAsync({
            planId: pendingCheckout.planId,
            seats: pendingCheckout.seats,
            paymentMethod,
          });
        }}
      />

      <StripeCardCheckoutDialog
        open={Boolean(stripeCheckout)}
        onOpenChange={(open) => {
          if (!open) setStripeCheckout(null);
        }}
        session={stripeCheckout}
        title="Pay for Smart Card seats"
        onPaid={async (paymentIntentId) => {
          try {
            await completeSmartCardSeatCheckout(paymentIntentId);
            clearSmartCardCardCheckoutState();
            toast.success("Seats activated");
            await qc.invalidateQueries({ queryKey: ["smart-card"] });
            await qc.invalidateQueries({ queryKey: ["billing"] });
          } catch (e) {
            toast.error(e instanceof Error ? e.message : "Could not activate seats");
            throw e;
          }
        }}
      />

      <SmartCardChangeSeatsDialog
        open={seatsDialogOpen}
        initialSeats={pendingSeatCount}
        onOpenChange={(open) => {
          setSeatsDialogOpen(open);
          if (!open) setPendingSeatCount(null);
        }}
      />
    </div>
  );
}
