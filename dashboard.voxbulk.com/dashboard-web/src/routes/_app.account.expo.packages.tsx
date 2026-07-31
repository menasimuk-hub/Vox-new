import { createFileRoute, Link } from "@tanstack/react-router";
import { Check, Ticket } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ActiveSubscriptionHeader } from "@/components/billing/active-subscription-header";
import { SERVICE_TINTS, ServicePackageShell } from "@/components/billing/service-package-shell";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { requireBillingAccess } from "@/lib/guards/billing-route";
import { apiFetch } from "@/lib/api";
import { countryToMarket } from "@/lib/billing/market";
import { useOrganisation } from "@/lib/queries";
import { cn } from "@/lib/utils";

type ExpoPackage = {
  id: string;
  name: string;
  tier: string;
  duration_days?: number;
  price_minor: number;
  currency: string;
  features: string[];
  is_featured?: boolean;
  lead_scoring_enabled?: boolean;
};

const BEST_FOR: Record<string, string> = {
  day1: "Single-day pop-ups and short stands",
  day3: "Typical multi-day trade shows",
  day7: "Long fairs and week-long exhibitions",
};

const MARKET_TO_ZONE: Record<string, string> = {
  gbp: "gb",
  eur: "eu",
  usd: "us",
  cad: "ca",
  aud: "au",
};

export const Route = createFileRoute("/_app/account/expo/packages")({
  head: () => ({ meta: [{ title: "Expo packages — VoxBulk" }] }),
  beforeLoad: () => {
    requireBillingAccess();
  },
  component: ExpoPackagesPage,
});

function ExpoPackagesPage() {
  const orgQ = useOrganisation();
  const market = countryToMarket(orgQ.data?.country);
  const zone = MARKET_TO_ZONE[market] || "us";
  const tint = SERVICE_TINTS.expo;

  const packagesQ = useQuery({
    queryKey: ["expo", "packages", zone],
    queryFn: () => apiFetch<{ items: ExpoPackage[] }>(`/expo/packages?zone=${zone}`),
    enabled: !orgQ.isLoading,
  });
  const items = (packagesQ.data?.items || []).slice().sort((a, b) => (a.duration_days || 0) - (b.duration_days || 0));

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 pb-16">
      <PageHeader
        eyebrow="Account"
        title="Expo packages & pricing"
        description="One-off per exhibition — choose how many days your booth QR stays active. Prices use your organisation country market."
        actions={
          <Button asChild variant="outline">
            <Link to="/expo/new">Create booth</Link>
          </Button>
        }
      />

      <ServicePackageShell
        tint={tint}
        icon={Ticket}
        title="Exhibition packages"
        blurb="Pay once per booth — not a recurring subscription. Pick a duration, then create your booth."
        badge="One-time"
      >
        <ActiveSubscriptionHeader
          title="Exhibition packages"
          finance={null}
          loading={false}
          emptyMessage="One-time per exhibition — no recurring subscription. Choose a package below, then create your booth."
          tintClass={tint.soft}
        />

        {packagesQ.isLoading || orgQ.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-80 rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <Card className="border-cyan-200/50 bg-background/80">
            <CardContent className="p-8 text-center text-sm text-muted-foreground">
              No Expo packages available yet.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((pkg) => {
              const days = pkg.duration_days || 1;
              const featured = Boolean(pkg.is_featured);
              return (
                <Card
                  key={pkg.id}
                  className={cn(
                    "relative flex flex-col border-cyan-200/50 bg-background/80",
                    featured && "border-cyan-400/60 ring-1 ring-cyan-300/40",
                  )}
                >
                  {featured ? (
                    <span className="absolute -top-2.5 left-4 rounded-full bg-cyan-600 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                      Most popular
                    </span>
                  ) : null}
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{pkg.name}</CardTitle>
                    <p className="text-xs text-muted-foreground">
                      {BEST_FOR[pkg.tier] || `Booth active for ${days} day${days === 1 ? "" : "s"}`}
                    </p>
                    <p className="pt-2 text-3xl font-semibold tabular-nums">
                      {(pkg.price_minor / 100).toLocaleString("en-GB", {
                        style: "currency",
                        currency: pkg.currency || "GBP",
                        maximumFractionDigits: 0,
                      })}
                      <span className="ml-1 text-sm font-normal text-muted-foreground">/ exhibition</span>
                    </p>
                    <p className="text-xs font-medium text-cyan-700 dark:text-cyan-300">
                      Active for {days} day{days === 1 ? "" : "s"}
                    </p>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col">
                    <ul className="space-y-2 text-sm text-muted-foreground">
                      {(pkg.features || []).map((f) => (
                        <li key={f} className="flex items-start gap-2">
                          <Check className="mt-0.5 size-3.5 shrink-0 text-cyan-600" />
                          <span>{f}</span>
                        </li>
                      ))}
                    </ul>
                    <Button asChild className="mt-6 w-full" variant={featured ? "default" : "outline"}>
                      <Link to="/expo/new">Choose {pkg.name}</Link>
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </ServicePackageShell>
    </div>
  );
}
