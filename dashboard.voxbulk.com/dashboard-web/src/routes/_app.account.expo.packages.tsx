import { createFileRoute, Link } from "@tanstack/react-router";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { requireBillingAccess } from "@/lib/guards/billing-route";
import { apiFetch } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

type ExpoPackage = {
  id: string;
  name: string;
  tier: string;
  price_minor: number;
  currency: string;
  features: string[];
  is_featured?: boolean;
  lead_scoring_enabled?: boolean;
  post_show_followup_enabled?: boolean;
  post_event_survey_enabled?: boolean;
  ai_summary_report_enabled?: boolean;
};

export const Route = createFileRoute("/_app/account/expo/packages")({
  head: () => ({ meta: [{ title: "Expo packages — VoxBulk" }] }),
  beforeLoad: () => {
    requireBillingAccess();
  },
  component: ExpoPackagesPage,
});

function ExpoPackagesPage() {
  const packagesQ = useQuery({
    queryKey: ["expo", "packages", "gb"],
    queryFn: () => apiFetch<{ items: ExpoPackage[] }>("/expo/packages?zone=gb"),
  });
  const items = packagesQ.data?.items || [];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Account"
        title="Expo packages & pricing"
        description="Per-exhibition packages for VoxBulk Expo lead capture. Checkout wiring follows in a later release — packages are available to assign now."
        actions={
          <Button asChild variant="outline">
            <Link to="/expo/new">Create booth</Link>
          </Button>
        }
      />

      {packagesQ.isLoading ? (
        <div className="grid gap-4 md:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-72 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {items.map((pkg) => (
            <Card key={pkg.id} className={cn(pkg.is_featured && "ring-1 ring-primary/40")}>
              <CardHeader>
                <CardTitle className="text-base">{pkg.name}</CardTitle>
                <p className="text-3xl font-semibold tabular-nums">
                  {(pkg.price_minor / 100).toLocaleString("en-GB", {
                    style: "currency",
                    currency: pkg.currency || "GBP",
                    maximumFractionDigits: 0,
                  })}
                  <span className="ml-1 text-sm font-normal text-muted-foreground">/ exhibition</span>
                </p>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm text-muted-foreground">
                  {(pkg.features || []).map((f) => (
                    <li key={f}>• {f}</li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
