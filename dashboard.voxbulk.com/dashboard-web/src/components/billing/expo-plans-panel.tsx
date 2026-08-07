import { useNavigate } from "@tanstack/react-router";
import { Check } from "lucide-react";
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { CheckoutConfirmDialog, type CheckoutConfirmDetails } from "@/components/billing/checkout-confirm-dialog";
import { SERVICE_TINTS } from "@/components/billing/service-package-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
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

function money(minor: number, currency: string) {
  return (minor / 100).toLocaleString("en-GB", {
    style: "currency",
    currency: currency || "GBP",
    maximumFractionDigits: 0,
  });
}

export function ExpoPlansPanel() {
  const navigate = useNavigate();
  const orgQ = useOrganisation();
  const market = countryToMarket(orgQ.data?.country);
  const zone = MARKET_TO_ZONE[market] || "us";

  const packagesQ = useQuery({
    queryKey: ["expo", "packages", zone],
    queryFn: () => apiFetch<{ items: ExpoPackage[] }>(`/expo/packages?zone=${zone}`),
    enabled: !orgQ.isLoading,
  });
  const items = (packagesQ.data?.items || [])
    .slice()
    .sort((a, b) => (a.duration_days || 0) - (b.duration_days || 0));

  const [checkoutOpen, setCheckoutOpen] = React.useState(false);
  const [checkoutDetails, setCheckoutDetails] = React.useState<CheckoutConfirmDetails | null>(null);
  const [pendingPkg, setPendingPkg] = React.useState<ExpoPackage | null>(null);

  const openCheckout = (pkg: ExpoPackage) => {
    const days = pkg.duration_days || 1;
    setPendingPkg(pkg);
    setCheckoutDetails({
      planName: pkg.name,
      intervalLabel: `One exhibition · active ${days} day${days === 1 ? "" : "s"}`,
      amountDisplay: money(pkg.price_minor, pkg.currency),
      amountNote: "Ex-VAT. VAT may be added at checkout when applicable.",
      amountMinor: pkg.price_minor,
      serviceKind: "expo",
      providerHint: "After confirming, complete booth details — then pay by card to go live.",
    });
    setCheckoutOpen(true);
  };

  if (packagesQ.isLoading || orgQ.isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-72 rounded-xl" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="p-8 text-center text-sm text-muted-foreground">
          No Expo packages available yet.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        One-off per exhibition — review price and promo here, then create your booth and pay by card to go live.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((pkg) => {
          const days = pkg.duration_days || 1;
          const featured = Boolean(pkg.is_featured);
          return (
            <Card
              key={pkg.id}
              className={cn(
                "relative flex flex-col",
                featured && "border-sky-400/60 shadow-md ring-1 ring-sky-300/40",
              )}
            >
              {featured ? (
                <span className="absolute -top-2.5 left-4 rounded-full bg-sky-600 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                  Most popular
                </span>
              ) : null}
              <CardHeader className="pb-2">
                <CardTitle className="text-base">{pkg.name}</CardTitle>
                <p className="text-xs text-muted-foreground">
                  {BEST_FOR[pkg.tier] || `Booth active for ${days} day${days === 1 ? "" : "s"}`}
                </p>
                <p className="pt-2 text-3xl font-semibold tabular-nums">
                  {money(pkg.price_minor, pkg.currency)}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">/ exhibition</span>
                </p>
                <p className="text-xs font-medium text-sky-700 dark:text-sky-300">
                  Active for {days} day{days === 1 ? "" : "s"}
                </p>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col">
                <ul className="space-y-2 text-sm text-muted-foreground">
                  {(pkg.features || []).map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <Check className="mt-0.5 size-3.5 shrink-0 text-sky-600" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  type="button"
                  className="mt-6 w-full"
                  variant={featured ? "default" : "outline"}
                  onClick={() => openCheckout(pkg)}
                >
                  Choose {pkg.name}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <CheckoutConfirmDialog
        open={checkoutOpen}
        onOpenChange={(open) => {
          setCheckoutOpen(open);
          if (!open) {
            setPendingPkg(null);
            setCheckoutDetails(null);
          }
        }}
        title="Confirm Expo package"
        details={checkoutDetails}
        serviceHint="Expo"
        tintClass={SERVICE_TINTS.expo.soft}
        confirmLabel="Continue to booth & pay"
        onConfirm={async () => {
          if (!pendingPkg) return;
          setCheckoutOpen(false);
          toast.message("Complete booth details, then pay to go live");
          await navigate({
            to: "/expo/new",
            search: { packageId: pendingPkg.id, fromBilling: true },
          });
        }}
      />
    </div>
  );
}
