import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Download, FileSpreadsheet, TrendingUp } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { SortHeader, useTableSort } from "@/components/sortable-table";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useServiceOrders } from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/reports")({
  head: () => ({ meta: [{ title: "Survey reports — VoxBulk" }] }),
  component: SurveyReports,
});

function SurveyReports() {
  const ordersQ = useServiceOrders("survey");
  const rows = React.useMemo(
    () => (ordersQ.data || []).map((o) => orderToCampaign(o, "survey")),
    [ordersQ.data],
  );
  const rowsSort = useTableSort(rows);
  const totalResponses = rows.reduce((sum, r) => sum + r.responses, 0);
  const avgCompletion = rows.length ? Math.round(rows.reduce((sum, r) => sum + r.completion, 0) / rows.length) : 0;

  const trend = rows.slice(0, 6).map((r, i) => ({
    month: r.name.slice(0, 8) || `S${i + 1}`,
    nps: r.completion,
    rate: r.completion,
  }));

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Surveys · Reports"
        title="Survey analytics reports"
        description="Cross-survey reporting: trends, clinic comparisons, benchmarks, and exports across many campaigns."
        actions={
          <>
            <Button variant="outline" className="gap-1.5" disabled><Download className="size-4" /> Export PDF</Button>
            <Button className="gap-1.5" disabled><FileSpreadsheet className="size-4" /> Export CSV</Button>
          </>
        }
      />

      <Tabs defaultValue="quarter"><TabsList>
        <TabsTrigger value="month">Month</TabsTrigger>
        <TabsTrigger value="quarter">Quarter</TabsTrigger>
        <TabsTrigger value="year">Year</TabsTrigger>
      </TabsList></Tabs>

      <div className="grid gap-4 md:grid-cols-4">
        <ReportKpi label="Live surveys" value={ordersQ.isLoading ? "…" : String(rows.filter((r) => r.status === "live").length)} delta="from API" />
        <ReportKpi label="Avg completion" value={ordersQ.isLoading ? "…" : `${avgCompletion}%`} delta="across campaigns" />
        <ReportKpi label="Response rate" value={ordersQ.isLoading ? "…" : `${avgCompletion}%`} delta="avg. completion" />
        <ReportKpi label="Total responses" value={ordersQ.isLoading ? "…" : totalResponses.toLocaleString()} delta="all surveys" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Completion across surveys</CardTitle></CardHeader>
          <CardContent className="h-72">
            {ordersQ.isLoading ? (
              <Skeleton className="h-full w-full" />
            ) : trend.length === 0 ? (
              <p className="flex h-full items-center justify-center text-sm text-muted-foreground">No survey data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ left: -18, right: 8, top: 8 }}>
                  <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 12, fontSize: 12 }} />
                  <Area dataKey="nps" stroke="var(--color-primary)" fill="var(--color-primary)" fillOpacity={0.18} strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Response progress</CardTitle></CardHeader>
          <CardContent className="h-72">
            {ordersQ.isLoading ? (
              <Skeleton className="h-full w-full" />
            ) : trend.length === 0 ? (
              <p className="flex h-full items-center justify-center text-sm text-muted-foreground">No survey data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={trend} margin={{ left: -18, right: 8, top: 8 }}>
                  <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="month" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <YAxis stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                  <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 12, fontSize: 12 }} />
                  <Bar dataKey="rate" fill="var(--color-success)" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card><CardContent className="px-0">
        {ordersQ.isLoading ? (
          <div className="space-y-2 p-6"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></div>
        ) : rows.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted-foreground">No survey campaigns yet.</p>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <SortHeader label="Survey campaign" sortKey="name" active={rowsSort.sortKey} dir={rowsSort.sortDir} onToggle={rowsSort.toggleSort} className="pl-6" />
              <SortHeader label="Status" sortKey="status" active={rowsSort.sortKey} dir={rowsSort.sortDir} onToggle={rowsSort.toggleSort} />
              <SortHeader label="Responses" sortKey="responses" active={rowsSort.sortKey} dir={rowsSort.sortDir} onToggle={rowsSort.toggleSort} />
              <SortHeader label="Completion" sortKey="completion" active={rowsSort.sortKey} dir={rowsSort.sortDir} onToggle={rowsSort.toggleSort} />
              <TableHead className="pr-6 text-right">Open</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {rowsSort.sorted.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="pl-6 font-medium">{c.name}</TableCell>
                  <TableCell><StatusBadge tone={c.status} /></TableCell>
                  <TableCell>{c.responses.toLocaleString()}</TableCell>
                  <TableCell>{c.completion}%</TableCell>
                  <TableCell className="pr-6 text-right">
                    <Button size="sm" variant="outline" asChild>
                      <Link to="/surveys/results" search={{ orderId: c.id }}>View results</Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent></Card>
    </div>
  );
}

function ReportKpi({ label, value, delta }: { label: string; value: string; delta: string }) {
  return <Card><CardContent className="p-4"><p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p><p className="mt-1 text-3xl font-semibold tracking-tight">{value}</p><p className="mt-2 inline-flex items-center gap-1 text-xs text-success"><TrendingUp className="size-3.5" /> {delta}</p></CardContent></Card>;
}
