import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import { CircleDollarSign, Clock3, Wallet } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { apiFetch } from "@/lib/api";
import { requirePartnerChannel } from "@/lib/guards/settings-route";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/partner-channel/wallet")({
  head: () => ({ meta: [{ title: "Wallet & commission — VoxBulk" }] }),
  beforeLoad: () => requirePartnerChannel(),
  component: PartnerChannelWallet,
});

type CommissionRow = {
  id: string;
  org_id?: string | null;
  org_name?: string | null;
  amount_minor: number;
  currency?: string;
  status: string;
  note?: string | null;
  created_at?: string | null;
};

type Stats = {
  wallet: {
    commission_minor: number;
    commission_paid_minor: number;
    commission_pending_minor: number;
    revenue_minor: number;
  };
  commissions?: CommissionRow[];
};

function money(minor?: number) {
  const n = Number(minor || 0) / 100;
  return `£${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function PartnerChannelWallet() {
  const [stats, setStats] = React.useState<Stats | null>(null);
  const [loading, setLoading] = React.useState(true);

  React.useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const dash = await apiFetch<{ stats: Stats }>("/sales/dashboard");
        setStats(dash.stats);
      } catch {
        setStats(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const commissions = stats?.commissions || [];

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Partner Channel Sales"
        title="Wallet & commission"
        description="Your partner earnings wallet. Pending amounts are paid out by VoxBulk admin; paid totals are settled."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Card className="border-primary/20 bg-gradient-to-b from-primary/[0.06] to-card">
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <CircleDollarSign className="size-3.5" />
              Available in wallet
            </CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(stats?.wallet.commission_pending_minor)}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-muted-foreground">Pending commission ready for payout</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Paid out</CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(stats?.wallet.commission_paid_minor)}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-muted-foreground">Already settled by admin</CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription className="flex items-center gap-1.5">
              <Wallet className="size-3.5" />
              Lifetime earned
            </CardDescription>
            <CardTitle className="text-3xl tabular-nums">
              {loading ? "…" : money(stats?.wallet.commission_minor)}
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-xs text-muted-foreground">
            From {loading ? "…" : money(stats?.wallet.revenue_minor)} attributed revenue
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Commission ledger</CardTitle>
          <CardDescription>Every paid subscription from your promo code creates a commission row here.</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading wallet…</p>
          ) : commissions.length === 0 ? (
            <div className="rounded-xl border border-dashed px-4 py-12 text-center">
              <Clock3 className="mx-auto mb-2 size-8 text-muted-foreground/70" />
              <p className="text-sm font-medium">No commission yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                When a customer signs up with your promo code and pays a subscription invoice, it appears here.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Company</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Date</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {commissions.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="font-medium">{c.org_name || c.org_id || "—"}</TableCell>
                      <TableCell className="tabular-nums">{money(c.amount_minor)}</TableCell>
                      <TableCell>
                        <Badge
                          variant="secondary"
                          className={cn(
                            c.status === "paid"
                              ? "bg-success-soft text-success hover:bg-success-soft"
                              : "bg-warning-soft text-warning hover:bg-warning-soft",
                          )}
                        >
                          {c.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {c.created_at ? String(c.created_at).slice(0, 10) : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
