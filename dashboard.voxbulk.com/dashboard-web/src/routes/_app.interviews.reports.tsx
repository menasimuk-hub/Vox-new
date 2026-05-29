import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Download, TrendingUp } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { downloadAuthenticatedFile } from "@/lib/api";
import type { CampaignTone } from "@/lib/types/campaign";
import { useInterviewReports } from "@/lib/queries";

export const Route = createFileRoute("/_app/interviews/reports")({
  head: () => ({ meta: [{ title: "Interview reports — VoxBulk" }] }),
  component: ReportsPage,
});

function batchStatusTone(status: string): CampaignTone {
  const l = String(status || "").toLowerCase();
  if (l === "running") return "live";
  if (l === "completed") return "finished";
  if (l === "cancelled" || l === "archived") return "archived";
  return "finished";
}

type BatchRow = {
  id: string;
  campaignId: string;
  name: string;
  status: CampaignTone;
  responses: number;
  target: number;
  qualified: number;
  avgAts: number | string;
};

function ReportsPage() {
  const [period, setPeriod] = React.useState("month");
  const reportsQ = useInterviewReports(period);

  const payload = reportsQ.data || {};
  const overview = (payload.overview || {}) as Record<string, number | string>;
  const batches = (payload.batches || []) as Record<string, unknown>[];

  const rows: BatchRow[] = React.useMemo(
    () =>
      batches.map((b) => ({
        id: String(b.order_id || ""),
        campaignId: String(b.campaign_id || b.reference_id || "—"),
        name: String(b.title || b.reference_id || "Interview"),
        status: batchStatusTone(String(b.status_label || b.status || "")),
        responses: Number(b.reached || 0),
        target: Number(b.candidate_count || 0),
        qualified: Number(b.advance_count || 0),
        avgAts: b.avg_score != null ? Number(b.avg_score) : "—",
      })),
    [batches],
  );

  const s = useTableSort(rows);
  const funnel = [
    { stage: "Candidates", value: Number(overview.candidate_count || 0) },
    { stage: "Reached", value: Number(overview.reached || 0) },
    { stage: "Qualified", value: Number(overview.advance_count || 0) },
    { stage: "Batches", value: Number(overview.batch_count || 0) },
  ];

  const onExportCsv = async () => {
    try {
      await downloadAuthenticatedFile(
        `/service-orders/interview-reports/export.csv?period=${encodeURIComponent(period)}`,
        `interview-batches-${period}.csv`,
      );
      toast.success("CSV downloaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  };

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Interviews · Reports"
        title="Hiring analytics reports"
        description="Cross-campaign reporting: funnel, score distribution, source quality, costs, and hiring efficiency."
        actions={
          <Button className="gap-1.5" onClick={() => void onExportCsv()}>
            <Download className="size-4" /> Export CSV
          </Button>
        }
      />

      <Tabs value={period} onValueChange={setPeriod}>
        <TabsList>
          <TabsTrigger value="month">This month</TabsTrigger>
          <TabsTrigger value="last_month">Last month</TabsTrigger>
          <TabsTrigger value="week">This week</TabsTrigger>
          <TabsTrigger value="all">All time</TabsTrigger>
        </TabsList>
      </Tabs>

      {reportsQ.isLoading ? (
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-4">
          <ReportKpi label="Batches" value={String(overview.batch_count ?? 0)} delta={String(payload.period_label || period)} />
          <ReportKpi label="Candidates" value={String(overview.candidate_count ?? 0)} delta={`${overview.reach_rate_pct ?? 0}% reached`} />
          <ReportKpi label="Qualified" value={String(overview.advance_count ?? 0)} delta="advance recommendations" />
          <ReportKpi label="Total cost" value={String(overview.total_cost_gbp ?? "—")} delta="quoted spend" />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader><CardTitle className="text-base">Hiring funnel across campaigns</CardTitle></CardHeader>
          <CardContent className="h-72">
            {reportsQ.isLoading ? (
              <Skeleton className="h-full w-full" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={funnel} margin={{ left: -18, right: 8, top: 8 }}>
                  <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="stage" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 12, fontSize: 12 }} />
                  <Bar dataKey="value" fill="var(--color-primary)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Period summary</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Source label="Reach rate" score={`${overview.reach_rate_pct ?? 0}%`} cost={`${overview.reached ?? 0} reached`} />
            <Source label="Advance count" score={String(overview.advance_count ?? 0)} cost="qualified candidates" />
            <Source label="Total spend" score={String(overview.total_cost_gbp ?? "—")} cost="across batches" />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="px-0">
          {reportsQ.isLoading ? (
            <div className="space-y-2 p-6"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
          ) : rows.length === 0 ? (
            <p className="p-8 text-center text-sm text-muted-foreground">No finished interview batches in this period.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHeader label="Campaign ID" sortKey="campaignId" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} className="pl-6" />
                  <SortHeader label="Campaign" sortKey="name" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Status" sortKey="status" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Candidates" sortKey="responses" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Qualified" sortKey="qualified" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <SortHeader label="Avg ATS" sortKey="avgAts" active={s.sortKey} dir={s.sortDir} onToggle={s.toggleSort} />
                  <TableHead className="pr-6 text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {s.sorted.map((c) => (
                  <TableRow key={c.id || c.campaignId}>
                    <TableCell className="pl-6 font-mono text-xs">
                      {c.id ? (
                        <Link to="/interviews/results/$orderId" params={{ orderId: c.id }} className="text-primary hover:underline">
                          {c.campaignId}
                        </Link>
                      ) : (
                        c.campaignId
                      )}
                    </TableCell>
                    <TableCell className="font-medium">
                      {c.id ? (
                        <Link to="/interviews/results/$orderId" params={{ orderId: c.id }} className="hover:underline">
                          {c.name}
                        </Link>
                      ) : (
                        c.name
                      )}
                    </TableCell>
                    <TableCell><StatusBadge tone={c.status} /></TableCell>
                    <TableCell>{c.responses}/{c.target}</TableCell>
                    <TableCell>{c.qualified}</TableCell>
                    <TableCell className="font-medium">{c.avgAts || "—"}</TableCell>
                    <TableCell className="pr-6 text-right">
                      {c.id ? (
                        <Button size="sm" variant="outline" asChild>
                          <Link to="/interviews/results/$orderId" params={{ orderId: c.id }}>View results</Link>
                        </Button>
                      ) : (
                        <Button size="sm" variant="outline" disabled title="Missing campaign order id">
                          View results
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ReportKpi({ label, value, delta }: { label: string; value: string; delta: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="mt-1 text-3xl font-semibold tracking-tight">{value}</p>
        <p className="mt-2 inline-flex items-center gap-1 text-xs text-success"><TrendingUp className="size-3.5" /> {delta}</p>
      </CardContent>
    </Card>
  );
}

function Source({ label, score, cost }: { label: string; score: string; cost: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex items-center justify-between text-sm"><span className="font-medium">{label}</span><span>{score}</span></div>
      <p className="mt-1 text-xs text-muted-foreground">{cost}</p>
    </div>
  );
}
