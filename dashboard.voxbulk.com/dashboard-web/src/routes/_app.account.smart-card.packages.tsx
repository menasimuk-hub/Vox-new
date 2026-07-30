import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type PackageItem = {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  interval?: string;
  prices: Array<{ currency: string; monthly_price_minor?: number | null; yearly_price_minor?: number | null }>;
};

export const Route = createFileRoute("/_app/account/smart-card/packages")({
  component: SmartCardPackagesPage,
});

function SmartCardPackagesPage() {
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

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Packages & pricing"
        description="$5 per seat per month, billed annually. Admin can change prices in the backend. Renew here when your package expires."
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
            <p>Period end: {entQ.data.period_end ? new Date(entQ.data.period_end).toLocaleDateString() : "—"}</p>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        {(packagesQ.data?.items || []).map((pkg) => {
          const usd = pkg.prices.find((p) => p.currency === "USD");
          const gbp = pkg.prices.find((p) => p.currency === "GBP");
          return (
            <Card key={pkg.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{pkg.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{pkg.description}</p>
                <p className="font-medium text-foreground">
                  {usd?.yearly_price_minor != null
                    ? `$${(usd.yearly_price_minor / 100).toFixed(0)} / seat / year`
                    : gbp?.yearly_price_minor != null
                      ? `£${(gbp.yearly_price_minor / 100).toFixed(0)} / seat / year`
                      : "See Admin pricing"}
                  {usd?.monthly_price_minor != null
                    ? ` (≈ $${(usd.monthly_price_minor / 100).toFixed(2)}/mo)`
                    : null}
                </p>
                <p className="text-xs">Checkout with seat quantity coming next — contact support to activate seats meanwhile, or use Admin private packages.</p>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
