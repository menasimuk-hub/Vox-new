import { createFileRoute, Link } from "@tanstack/react-router";
import { IdCard, Package, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";

type Entitlement = {
  ok: boolean;
  mode: string;
  seat_quantity: number;
  active_reps: number;
  preview_tests_used: number;
  preview_tests_limit: number;
  period_end?: string | null;
};

export const Route = createFileRoute("/_app/smart-card/")({
  component: SmartCardHubPage,
});

function SmartCardHubPage() {
  const entQ = useQuery({
    queryKey: ["smart-card", "entitlement"],
    queryFn: () => apiFetch<Entitlement>("/smart-card/entitlement"),
  });

  const ent = entQ.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Dashboard"
        description="Company profile, representatives, QR codes, and lead capture — WhatsApp or web."
        actions={
          <Button asChild variant="outline" className="gap-1.5">
            <Link to="/account/smart-card/packages">
              <Package className="size-4" /> Packages
            </Link>
          </Button>
        }
      />

      {entQ.isLoading ? (
        <Skeleton className="h-28 rounded-2xl" />
      ) : ent ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi label="Access" value={ent.mode.replace(/_/g, " ")} sub="live · preview · expired" />
          <Kpi label="Seats" value={`${ent.active_reps} / ${ent.seat_quantity}`} sub="Active reps / purchased" />
          <Kpi
            label="Preview tests"
            value={`${ent.preview_tests_used} / ${ent.preview_tests_limit}`}
            sub="Free tests before go-live"
          />
          <Kpi
            label="Period end"
            value={ent.period_end ? new Date(ent.period_end).toLocaleDateString() : "—"}
            sub="Renew before expiry"
          />
        </div>
      ) : null}

      {ent?.mode === "expired" ? (
        <Card className="border-rose-500/30 bg-rose-500/5">
          <CardHeader>
            <CardTitle className="text-base">Package expired</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>We&apos;re sorry — your Smart Card QR package has expired. Renew to accept new scans and leads.</p>
            <Button asChild>
              <Link to="/account/smart-card/packages">Renew now</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <Card className="transition hover:-translate-y-0.5 hover:shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="size-4" /> Representatives
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Button asChild variant="secondary" size="sm">
              <Link to="/smart-card/representatives">Manage reps & QR</Link>
            </Button>
          </CardContent>
        </Card>
        <Card className="transition hover:-translate-y-0.5 hover:shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <IdCard className="size-4" /> Company
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Button asChild variant="secondary" size="sm">
              <Link to="/smart-card/company">Edit company profile</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
      <CardContent className="p-3">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-0.5 text-lg font-semibold tracking-tight capitalize tabular-nums">{value}</p>
        {sub ? <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p> : null}
      </CardContent>
    </Card>
  );
}
