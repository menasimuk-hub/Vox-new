import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { BarChart3 } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { orderDetailLink } from "@/lib/billing/usage-detail-link";
import { assistantHighlightClass, useAssistantHighlight } from "@/lib/assistant-highlight";
import { cn } from "@/lib/utils";
import { usageServiceIcon } from "@/lib/billing/refund-timing";
import { AllowanceProductPanel } from "@/components/billing/allowance-product-panel";
import { useUsageAllowances } from "@/lib/billing/use-usage-allowances";
import { useBillingUsageBreakdown } from "@/lib/queries";

import { requireBillingAccess } from "@/lib/guards/billing-route";

export const Route = createFileRoute("/_app/account/usage")({
  beforeLoad: () => requireBillingAccess(),
  head: () => ({ meta: [{ title: "Usage — VoxBulk" }] }),
  component: AccountUsagePage,
});

const PAGE_SIZE = 15;

type UsageRow = {
  order_id: string;
  campaign_id?: string | null;
  name?: string;
  service_code?: string;
  type_label?: string;
  channel?: string;
  status?: string;
  usage_display?: string;
  cost_display?: string;
  amount_due_display?: string;
  cost_kind?: string;
  billing_source_label?: string;
  created_at?: string | null;
};

function KpiCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 p-4">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-xl font-semibold tabular-nums">{value}</p>
        {sub ? <p className="text-[11px] text-muted-foreground">{sub}</p> : null}
      </CardContent>
    </Card>
  );
}

function AccountUsagePage() {
  const allowancesState = useUsageAllowances();
  const [serviceCode, setServiceCode] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [billingSource, setBillingSource] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [pollRunning, setPollRunning] = React.useState(false);

  const breakdownQ = useBillingUsageBreakdown(
    {
      service_code: serviceCode || undefined,
      status: status || undefined,
      billing_source: billingSource || undefined,
      search: search.trim() || undefined,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    },
    { refetchInterval: pollRunning ? 45_000 : false },
  );

  const rows = (breakdownQ.data?.rows || []) as UsageRow[];
  const summary = (breakdownQ.data?.summary || {}) as Record<string, unknown>;
  React.useEffect(() => {
    setPollRunning(rows.some((r) => String(r.status || "").toLowerCase() === "running"));
  }, [rows]);
  const table = useTableSort(rows, "created_at", "desc");
  const sortedRows = table.sortKey === "created_at" && table.sortDir === "desc" ? rows : table.sorted;
  const total = Number(breakdownQ.data?.total || rows.length);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const highlight = useAssistantHighlight().highlight;

  React.useEffect(() => {
    setPage(1);
  }, [serviceCode, status, billingSource, search]);

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Account"
        title="Usage"
        description="See what ran on your account, how much was used, and how it was charged."
        actions={
          <Button asChild variant="outline" size="sm" className="gap-1.5">
            <Link to="/account/billing">
              <BarChart3 className="size-4" /> Billing & invoices
            </Link>
          </Button>
        }
      />

      {allowancesState.loading ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      ) : (
        <div className="space-y-4">
          {allowancesState.periodLabel ? (
            <p className="text-xs text-muted-foreground">Billing period: {allowancesState.periodLabel}</p>
          ) : null}
          <div className={cn("grid gap-4", allowancesState.coreRows.length && allowancesState.feedbackRows.length ? "lg:grid-cols-2" : "grid-cols-1")}>
            {allowancesState.coreRows.length > 0 ? (
              <AllowanceProductPanel meta={allowancesState.coreMeta} rows={allowancesState.coreRows} sharedPool={allowancesState.sharedPool} />
            ) : null}
            {allowancesState.feedbackRows.length > 0 ? (
              <AllowanceProductPanel meta={allowancesState.feedbackMeta} rows={allowancesState.feedbackRows} />
            ) : null}
          </div>
          {!breakdownQ.isLoading ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard
                label="AI minutes"
                value={`${summary.calls_used ?? 0} / ${summary.calls_included ?? 0}`}
                sub={`${summary.calls_remaining ?? 0} remaining`}
              />
              <KpiCard
                label="WA surveys"
                value={`${summary.whatsapp_used ?? 0} / ${summary.whatsapp_included ?? 0}`}
                sub={`${summary.whatsapp_remaining ?? 0} remaining`}
              />
              <KpiCard
                label="Extra due at completion"
                value={String(summary.extra_due_at_completion_display || summary.overage_pending_display || "£0.00")}
                sub="Estimated until campaign finishes"
              />
              <KpiCard
                label="Wallet-paid usage"
                value={String(summary.wallet_paid_display || "£0.00")}
                sub="Campaign charges from wallet"
              />
            </div>
          ) : null}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Campaign usage</CardTitle>
          <CardDescription>
            Each row shows campaign value (cost) and amount due. Extras are invoiced once when the campaign completes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Search</Label>
              <Input
                placeholder="Campaign name or ID"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Type</Label>
              <Select value={serviceCode || "all"} onValueChange={(v) => setServiceCode(v === "all" ? "" : v)}>
                <SelectTrigger><SelectValue placeholder="All types" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  <SelectItem value="interview">Interview</SelectItem>
                  <SelectItem value="survey">Survey</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Status</Label>
              <Select value={status || "all"} onValueChange={(v) => setStatus(v === "all" ? "" : v)}>
                <SelectTrigger><SelectValue placeholder="All statuses" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="cancelled">Cancelled</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Billing source</Label>
              <Select value={billingSource || "all"} onValueChange={(v) => setBillingSource(v === "all" ? "" : v)}>
                <SelectTrigger><SelectValue placeholder="All sources" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All sources</SelectItem>
                  <SelectItem value="included_in_package">Included in package</SelectItem>
                  <SelectItem value="wallet">Wallet</SelectItem>
                  <SelectItem value="quote">Quote / service order</SelectItem>
                  <SelectItem value="no_charge">No charge</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {breakdownQ.isLoading ? (
            <Skeleton className="h-48 w-full" />
          ) : sortedRows.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No billable campaign activity in this period. Launches and charges will appear here.
            </p>
          ) : (
            <>
              <div className="table-scroll">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Campaign ID</TableHead>
                      <SortHeader label="Name" sortKey="name" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                      <TableHead>Channel</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Usage</TableHead>
                      <TableHead>Cost</TableHead>
                      <TableHead>Amount due</TableHead>
                      <TableHead>Billing source</TableHead>
                      <SortHeader label="Created" sortKey="created_at" active={table.sortKey} dir={table.sortDir} onToggle={table.toggleSort} />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sortedRows.map((row) => {
                      const link = orderDetailLink(row);
                      const Icon = usageServiceIcon(row.service_code);
                      const name = row.name || "Untitled campaign";
                      return (
                        <TableRow
                          key={row.order_id}
                          data-assistant-highlight={row.order_id}
                          className={cn(assistantHighlightClass(row.order_id, highlight))}
                        >
                          <TableCell className="font-mono text-xs">{row.campaign_id || row.order_id.slice(0, 8)}</TableCell>
                          <TableCell className="max-w-[220px]">
                            {link ? (
                              <Link
                                to={link.to}
                                params={link.params}
                                search={link.search}
                                className="inline-flex items-center gap-1.5 font-medium text-primary underline-offset-4 hover:underline"
                              >
                                {Icon ? <Icon className="size-3.5 shrink-0 opacity-70" aria-hidden /> : null}
                                {name}
                              </Link>
                            ) : (
                              <span className="inline-flex items-center gap-1.5 text-muted-foreground">
                                {Icon ? <Icon className="size-3.5 shrink-0 opacity-70" aria-hidden /> : null}
                                {name}
                              </span>
                            )}
                          </TableCell>
                          <TableCell className="text-xs capitalize">{row.channel || "—"}</TableCell>
                          <TableCell>
                            <StatusBadge tone="draft-script" label={String(row.status || "—")} />
                          </TableCell>
                          <TableCell className="text-xs">{row.usage_display || "—"}</TableCell>
                          <TableCell className="tabular-nums text-xs">
                            {row.cost_display || "—"}
                            {row.cost_kind === "estimated" ? (
                              <span className="ml-1 text-[10px] text-muted-foreground">Est.</span>
                            ) : row.cost_kind === "running" ? (
                              <span className="ml-1 text-[10px] text-muted-foreground">Live</span>
                            ) : null}
                          </TableCell>
                          <TableCell className="tabular-nums text-xs">{row.amount_due_display ?? "—"}</TableCell>
                          <TableCell className="text-xs">{row.billing_source_label || "—"}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">
                            {row.created_at ? new Date(row.created_at).toLocaleDateString() : "—"}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
              {totalPages > 1 ? (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    Page {page} of {totalPages} · {total} campaigns
                  </span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                      Previous
                    </Button>
                    <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                      Next
                    </Button>
                  </div>
                </div>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
