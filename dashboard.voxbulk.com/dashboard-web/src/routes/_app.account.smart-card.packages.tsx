import { createFileRoute, Link, useSearch } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QrCode } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ActiveSubscriptionHeader } from "@/components/billing/active-subscription-header";
import { CheckoutConfirmDialog, type CheckoutConfirmDetails } from "@/components/billing/checkout-confirm-dialog";
import { SERVICE_TINTS, ServicePackageShell } from "@/components/billing/service-package-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  clearBillingQuery,
  gocardlessAvailable,
  readBillingReturnParams,
} from "@/lib/billing/gocardless";
import {
  completeSmartCardGoCardless,
  completeSmartCardSeatCheckout,
  GC_SMART_CARD_FLOW_KEY,
  startSmartCardGoCardless,
  startSmartCardSeatCheckout,
} from "@/lib/billing/smart-card-subscription-payment";
import {
  countryToMarket,
  marketCurrencySymbol,
  orgCountryToCurrencyCode,
  pickPriceMinor,
} from "@/lib/billing/market";
import { apiFetch } from "@/lib/api";
import { useBillingSubscriptionsSummary, useOrganisation } from "@/lib/queries";
import { useSession } from "@/lib/session";
import { primarySubscriptionProvider } from "@/lib/billing/subscription-payment";

type PackageItem = {
  id: string;
  plan_id: string;
  code: string;
  name: string;
  description?: string | null;
  interval?: string;
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

export const Route = createFileRoute("/_app/account/smart-card/packages")({
  component: SmartCardPackagesPage,
  validateSearch: (search: Record<string, unknown>) => ({
    billing: typeof search.billing === "string" ? search.billing : undefined,
    payment_intent: typeof search.payment_intent === "string" ? search.payment_intent : undefined,
    payment_intent_client_secret:
      typeof search.payment_intent_client_secret === "string"
        ? search.payment_intent_client_secret
        : undefined,
    redirect_flow_id: typeof search.redirect_flow_id === "string" ? search.redirect_flow_id : undefined,
  }),
});

function SmartCardPackagesPage() {
  const search = useSearch({ from: "/_app/account/smart-card/packages" });
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
  const completingRef = React.useRef(false);

  const orgCountry = orgQ.data?.country;
  const currencyCode = orgCountryToCurrencyCode(orgCountry);
  const currencySym = marketCurrencySymbol(countryToMarket(orgCountry));
  const gcReady = gocardlessAvailable(session as Record<string, unknown> | null);
  const primaryProvider = primarySubscriptionProvider(session as Record<string, unknown> | null);
  const useGcMonthly = billingInterval === "monthly" && (gcReady || primaryProvider === "gocardless");

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
        } catch (e: any) {
          toast.error(e?.message || "Could not complete Direct Debit signup");
        }
      })();
      return;
    }

    const pi =
      search.payment_intent ||
      (typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("payment_intent")
        : null);
    if (!pi) return;
    if (search.billing && search.billing !== "card_success") return;
    completingRef.current = true;
    void (async () => {
      try {
        await completeSmartCardSeatCheckout(pi);
        toast.success("Seats activated");
        await qc.invalidateQueries({ queryKey: ["smart-card"] });
        await qc.invalidateQueries({ queryKey: ["billing"] });
      } catch (e: any) {
        toast.error(e?.message || "Could not activate seats");
      }
    })();
  }, [search.billing, search.payment_intent, search.redirect_flow_id, qc]);

  const checkoutMut = useMutation({
    mutationFn: async ({ planId, seats }: { planId: string; seats: number }) => {
      if (useGcMonthly) {
        await startSmartCardGoCardless(planId, seats, "monthly");
        return { provider: "gocardless" };
      }
      const result = await startSmartCardSeatCheckout(planId, seats, billingInterval);
      if (result.provider === "promo_discount" && result.paid) {
        toast.success("Seats activated with promo");
        await qc.invalidateQueries({ queryKey: ["smart-card"] });
        await qc.invalidateQueries({ queryKey: ["billing"] });
      }
      return result;
    },
    onError: (e: Error) => {
      const msg = e.message || "Checkout failed";
      if (/GoCardless|Direct Debit/i.test(msg) && billingInterval === "monthly") {
        toast.message("Trying card checkout…");
        return;
      }
      toast.error(msg);
    },
  });

  const finance = (subsSummaryQ.data as { smart_card?: Record<string, unknown> } | undefined)?.smart_card || null;
  const tint = SERVICE_TINTS.smartCard;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 pb-16">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Packages & pricing"
        description={`Flat ${currencySym}5/seat/month (local equivalent). Monthly via Direct Debit when available; yearly by card with 20% off.`}
        actions={
          <Button asChild variant="outline">
            <Link to="/smart-card">Back to hub</Link>
          </Button>
        }
      />

      <ServicePackageShell
        tint={tint}
        icon={QrCode}
        title="Smart Card QR"
        blurb="Personal QR for representatives — pay per seat. Monthly Direct Debit or yearly card (20% off)."
        badge="Subscription"
      >
        <ActiveSubscriptionHeader
          title="Smart Card subscription"
          finance={finance as any}
          loading={subsSummaryQ.isLoading}
          emptyMessage="No active Smart Card subscription."
          tintClass={tint.soft}
        />

        <div className="mb-2 flex flex-col items-center gap-2">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">Billing period</p>
          <div className="flex rounded-full border border-violet-300/60 bg-background p-1 text-xs shadow-sm">
            <button
              type="button"
              className={`rounded-full px-4 py-2 transition-colors ${billingInterval === "monthly" ? "bg-violet-600 text-white shadow" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setBillingInterval("monthly")}
            >
              Monthly
            </button>
            <button
              type="button"
              className={`inline-flex items-center gap-2 rounded-full px-4 py-2 transition-colors ${billingInterval === "yearly" ? "bg-violet-600 text-white shadow" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setBillingInterval("yearly")}
            >
              Yearly
              <span className="rounded-full bg-emerald-500 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                20% off
              </span>
            </button>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {(packagesQ.data?.items || []).map((pkg) => {
            const price = pickPriceMinor(pkg.prices, currencyCode, { yearly: billingInterval === "yearly" });
            const seats = seatsByPlan[pkg.plan_id] ?? 1;
            const unit = price.amountMinor;
            const total = unit != null ? (unit * seats) / 100 : null;
            const sym = unit != null ? symbolForCurrency(price.currency) : currencySym;
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
                  <p>{pkg.description}</p>
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
                      Total due today: {sym}
                      {total.toFixed(0)}
                    </p>
                  ) : null}
                  <Button
                    className="mt-auto w-full"
                    disabled={checkoutMut.isPending || !pkg.plan_id}
                    onClick={() => {
                      if (unit == null || total == null) {
                        toast.error("Price not available for your currency");
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
                        providerHint: useGcMonthly
                          ? "You will continue to GoCardless Direct Debit."
                          : "You will continue to secure card payment.",
                      });
                      setCheckoutOpen(true);
                    }}
                  >
                    {checkoutMut.isPending ? "Starting…" : "Subscribe"}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </ServicePackageShell>

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
        confirmLabel={useGcMonthly ? "Continue to Direct Debit" : "Pay with card"}
        loading={checkoutMut.isPending}
        onConfirm={async () => {
          if (!pendingCheckout) return;
          setCheckoutOpen(false);
          await checkoutMut.mutateAsync({ planId: pendingCheckout.planId, seats: pendingCheckout.seats });
        }}
      />
    </div>
  );
}
