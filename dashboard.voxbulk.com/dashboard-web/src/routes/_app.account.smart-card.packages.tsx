import { createFileRoute, Link, useSearch } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  completeSmartCardSeatCheckout,
  startSmartCardSeatCheckout,
} from "@/lib/billing/smart-card-subscription-payment";
import {
  countryToMarket,
  marketCurrencySymbol,
  orgCountryToCurrencyCode,
  pickPriceMinor,
} from "@/lib/billing/market";
import { apiFetch } from "@/lib/api";
import { useOrganisation } from "@/lib/queries";

type PackageItem = {
  id: string;
  plan_id: string;
  code: string;
  name: string;
  description?: string | null;
  interval?: string;
  prices: Array<{ currency: string; monthly_price_minor?: number | null; yearly_price_minor?: number | null }>;
};

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

function formatMinor(amountMinor: number | null, currency: string) {
  if (amountMinor == null) return "—";
  return `${symbolForCurrency(currency)}${(amountMinor / 100).toFixed(0)}`;
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
  }),
});

function SmartCardPackagesPage() {
  const search = useSearch({ from: "/_app/account/smart-card/packages" });
  const qc = useQueryClient();
  const orgQ = useOrganisation();
  const [seatsByPlan, setSeatsByPlan] = React.useState<Record<string, number>>({});
  const completingRef = React.useRef(false);

  const orgCountry = orgQ.data?.country;
  const currencyCode = orgCountryToCurrencyCode(orgCountry);
  const currencySym = marketCurrencySymbol(countryToMarket(orgCountry));

  const packagesQ = useQuery({
    queryKey: ["smart-card", "packages"],
    queryFn: () => apiFetch<{ ok: boolean; items: PackageItem[] }>("/smart-card/packages"),
  });
  const entQ = useQuery({
    queryKey: ["smart-card", "entitlement"],
    queryFn: () =>
      apiFetch<{
        mode: string;
        seat_quantity: number;
        period_end?: string | null;
      }>("/smart-card/entitlement"),
  });

  React.useEffect(() => {
    const pi =
      search.payment_intent ||
      (typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("payment_intent")
        : null);
    if (!pi || completingRef.current) return;
    if (search.billing && search.billing !== "card_success") return;
    completingRef.current = true;
    void (async () => {
      try {
        await completeSmartCardSeatCheckout(pi);
        toast.success("Seats activated");
        await qc.invalidateQueries({ queryKey: ["smart-card"] });
      } catch (e: any) {
        toast.error(e?.message || "Could not activate seats");
      }
    })();
  }, [search.billing, search.payment_intent, qc]);

  const checkoutMut = useMutation({
    mutationFn: ({ planId, seats }: { planId: string; seats: number }) =>
      startSmartCardSeatCheckout(planId, seats),
    onError: (e: Error) => toast.error(e.message || "Checkout failed"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Packages & pricing"
        description={`Per-seat pricing in ${currencyCode}, based on your organisation country. Billed annually — choose how many seats, then pay by card.`}
        actions={
          <Button asChild variant="outline">
            <Link to="/smart-card">Back to hub</Link>
          </Button>
        }
      />

      {entQ.data ? (
        <Card>
          <CardContent className="space-y-1 p-4 text-sm">
            <p>
              Status: <span className="font-medium capitalize">{entQ.data.mode.replace(/_/g, " ")}</span>
            </p>
            <p>Seats purchased: {entQ.data.seat_quantity}</p>
            <p>
              Expires:{" "}
              <span className="font-medium">
                {entQ.data.period_end ? new Date(entQ.data.period_end).toLocaleDateString() : "—"}
              </span>
            </p>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Pricing table</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-xl border">
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="px-3 py-2 font-medium">Plan</th>
                  <th className="px-3 py-2 font-medium">{currencyCode} / seat / year</th>
                  <th className="px-3 py-2 font-medium">{currencyCode} / seat / month</th>
                </tr>
              </thead>
              <tbody>
                {(packagesQ.data?.items || []).map((pkg) => {
                  const yearly = pickPriceMinor(pkg.prices, currencyCode, { yearly: true });
                  const monthly = pickPriceMinor(pkg.prices, currencyCode, { yearly: false });
                  return (
                    <tr key={pkg.id} className="border-b last:border-0">
                      <td className="px-3 py-2">{pkg.name}</td>
                      <td className="px-3 py-2">{formatMinor(yearly.amountMinor, yearly.currency)}</td>
                      <td className="px-3 py-2">{formatMinor(monthly.amountMinor, monthly.currency)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Currency follows your organisation country
            {orgCountry ? ` (${orgCountry})` : ""}. Change it in{" "}
            <Link to="/settings/profile" className="text-primary underline-offset-4 hover:underline">
              Settings → Profile
            </Link>
            .
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-3 md:grid-cols-2">
        {(packagesQ.data?.items || []).map((pkg) => {
          const yearly = pickPriceMinor(pkg.prices, currencyCode, { yearly: true });
          const seats = seatsByPlan[pkg.plan_id] ?? 1;
          const unit = yearly.amountMinor;
          const total = unit != null ? (unit * seats) / 100 : null;
          const sym = unit != null ? symbolForCurrency(yearly.currency) : currencySym;
          return (
            <Card key={pkg.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{pkg.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm text-muted-foreground">
                <p>{pkg.description}</p>
                <p className="font-medium text-foreground">
                  {unit != null ? `${sym}${(unit / 100).toFixed(0)} / seat / year` : "See Admin pricing"}
                </p>
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
                  disabled={checkoutMut.isPending || !pkg.plan_id}
                  onClick={() => checkoutMut.mutate({ planId: pkg.plan_id, seats })}
                >
                  {checkoutMut.isPending ? "Starting…" : "Buy seats"}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
