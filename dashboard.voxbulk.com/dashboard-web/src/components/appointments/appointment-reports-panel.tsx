import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiFetch } from "@/lib/api";

/* ============================================================================
   MOCK FALLBACKS (design source)
============================================================================ */

const MOCK_CONFIRM_MIX = [
  { name: "WA confirmed", value: 248, color: "#22c55e" },
  { name: "Call confirmed", value: 106, color: "#3b82f6" },
  { name: "Not confirmed", value: 58, color: "#ef4444" },
];

const MOCK_DAILY = Array.from({ length: 30 }, (_, i) => {
  const total = 8 + Math.round(Math.random() * 18);
  const rate = 65 + Math.round(Math.random() * 30);
  return { d: `${i + 1}`, total, rate };
});

const MOCK_BY_CRM = [
  { crm: "HubSpot", rate: 88 },
  { crm: "Pipedrive", rate: 81 },
  { crm: "Zoho", rate: 76 },
  { crm: "Manual", rate: 69 },
];

const MOCK_BY_BRANCH = [
  { branch: "London — Marylebone", total: 142, rate: 91, spark: [60, 70, 78, 82, 88, 91] },
  { branch: "Manchester — Deansgate", total: 88, rate: 84, spark: [62, 70, 74, 78, 80, 84] },
  { branch: "Berlin — Mitte", total: 72, rate: 79, spark: [58, 64, 70, 72, 76, 79] },
  { branch: "Milan — Brera", total: 54, rate: 73, spark: [48, 55, 62, 66, 70, 73] },
  { branch: "Copenhagen — Central", total: 56, rate: 86, spark: [60, 68, 74, 80, 84, 86] },
];

const MOCK_METRICS = {
  avg_hours_to_confirm: 3.4,
  wa_sent: 1184,
  calls_made: 318,
  call_answer_rate: 74,
  rescheduled_kept_rate: 82,
};

type ConfirmItem = { name: string; value: number; color: string };
type DailyItem = { d: string; total: number; rate: number };
type CrmItem = { crm: string; rate: number };
type BranchItem = { branch: string; total: number; rate: number; spark: number[] };
type Metrics = {
  avg_hours_to_confirm: number | null;
  wa_sent: number;
  calls_made: number;
  call_answer_rate: number | null;
  rescheduled_kept_rate: number | null;
};

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-[120px] flex-1 items-center justify-between gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
      <p className="truncate text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="shrink-0 text-sm font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = max - min || 1;
  const w = 80;
  const h = 24;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg width={w} height={h} className="text-emerald-500">
      <polyline fill="none" stroke="currentColor" strokeWidth={1.5} points={pts} />
    </svg>
  );
}

function formatMetrics(m: Metrics) {
  return {
    avgTime: m.avg_hours_to_confirm != null ? `${m.avg_hours_to_confirm}h` : "—",
    waSent: m.wa_sent.toLocaleString(),
    callsMade: m.calls_made.toLocaleString(),
    callRate: m.call_answer_rate != null ? `${m.call_answer_rate}%` : "—",
    rescheduledKept: m.rescheduled_kept_rate != null ? `${m.rescheduled_kept_rate}%` : "—",
  };
}

export function AppointmentReportsPanel() {
  const summaryQ = useQuery({
    queryKey: ["appointments", "reports", "summary"],
    queryFn: () =>
      apiFetch<{
        total: number;
        scheduled: number;
        confirmed: number;
        rescheduled: number;
        cancelled: number;
        no_show: number;
        wa_sent: number;
        calls_triggered: number;
      }>("/appointments/reports/summary"),
  });

  const pipelineQ = useQuery({
    queryKey: ["appointments", "reports", "pipeline"],
    queryFn: () =>
      apiFetch<{
        items: Array<{ label: string; value: number; color: string }>;
        outreach_window_start: string;
        outreach_window_end: string;
      }>("/appointments/reports/pipeline"),
  });

  const confirmQ = useQuery({
    queryKey: ["appointments", "reports", "confirmation-methods"],
    queryFn: () => apiFetch<{ items: ConfirmItem[] }>("/appointments/reports/confirmation-methods"),
  });

  const dailyQ = useQuery({
    queryKey: ["appointments", "reports", "daily"],
    queryFn: () =>
      apiFetch<{ items: Array<{ date: string; total: number; confirmed: number }> }>(
        "/appointments/reports/daily?days=30",
      ),
  });

  const byBranchQ = useQuery({
    queryKey: ["appointments", "reports", "by-branch"],
    queryFn: () =>
      apiFetch<{ items: Array<{ branch: string; total: number; rate: number; spark?: number[] }> }>(
        "/appointments/reports/by-branch",
      ),
  });

  const metricsQ = useQuery({
    queryKey: ["appointments", "reports", "metrics"],
    queryFn: () => apiFetch<Metrics>("/appointments/reports/metrics"),
  });

  const confirmMix =
    confirmQ.data?.items?.length && confirmQ.data.items.some((x) => x.value > 0)
      ? confirmQ.data.items
      : MOCK_CONFIRM_MIX;

  const daily: DailyItem[] =
    dailyQ.data?.items?.length && dailyQ.data.items.some((x) => x.total > 0)
      ? dailyQ.data.items.map((row, i) => ({
          d: row.date.slice(5) || String(i + 1),
          total: row.total,
          rate: row.total > 0 ? Math.round((100 * row.confirmed) / row.total) : 0,
        }))
      : MOCK_DAILY;

  const summary = summaryQ.data;
  const confirmationRate =
    summary && summary.total > 0 ? Math.round((100 * summary.confirmed) / summary.total) : 0;

  const pipeline =
    pipelineQ.data?.items?.length && pipelineQ.data.items.some((x) => x.value > 0)
      ? pipelineQ.data.items
      : [
          { label: "Scheduled", value: summary?.scheduled ?? 0, color: "#3b82f6" },
          { label: "Confirmed", value: summary?.confirmed ?? 0, color: "#22c55e" },
          { label: "At risk", value: summary?.scheduled ?? 0, color: "#f59e0b" },
        ];

  const outreachStart = pipelineQ.data?.outreach_window_start ?? "09:00";
  const outreachEnd = pipelineQ.data?.outreach_window_end ?? "16:00";

  const byBranch: BranchItem[] =
    byBranchQ.data?.items?.length && byBranchQ.data.items.some((x) => x.total > 0)
      ? byBranchQ.data.items.map((x) => ({
          branch: x.branch,
          total: x.total,
          rate: x.rate,
          spark: x.spark?.length ? x.spark : [x.rate, x.rate, x.rate, x.rate, x.rate, x.rate],
        }))
      : MOCK_BY_BRANCH;

  const metrics = metricsQ.data ?? MOCK_METRICS;
  const formatted = formatMetrics(metrics);

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
          <CardDescription>
            WA &amp; AI calls only send between {outreachStart} and {outreachEnd} (your outreach window)
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-nowrap gap-2 overflow-x-auto pb-0.5">
          <Mini label="Total appointments" value={String(summary?.total ?? "—")} />
          <Mini label="Confirmation rate" value={summary ? `${confirmationRate}%` : "—"} />
          <Mini label="WA messages sent" value={formatted.waSent} />
          <Mini label="AI calls made" value={formatted.callsMade} />
          <Mini label="Avg time to confirm" value={formatted.avgTime} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 p-3 text-sm text-muted-foreground">
          <span>
            <strong className="text-foreground">Outreach hours:</strong> {outreachStart} – {outreachEnd}
          </span>
          <span className="ml-auto text-[11px]">WhatsApp and AI calls are queued inside this window</span>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 p-3">
          <Button variant="outline" size="sm">Period: Last 30 days</Button>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Pipeline health</CardTitle>
            <CardDescription>What needs attention right now (not by CRM — you use one CRM)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {pipeline.map((r) => (
              <div key={r.label} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span>{r.label}</span>
                  <span className="tabular-nums text-muted-foreground">{r.value}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, r.value * 8)}%`, background: r.color }} />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Confirmation method</CardTitle>
            <CardDescription>How appointments got confirmed</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={confirmMix}
                  dataKey="value"
                  innerRadius={50}
                  outerRadius={85}
                  paddingAngle={3}
                  stroke="none"
                >
                  {confirmMix.map((e, i) => (
                    <Cell key={i} fill={e.color} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    background: "var(--color-popover)",
                    border: "1px solid var(--color-border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Daily volume + confirmation rate</CardTitle>
            <CardDescription>Bars: total · Line: confirmation %</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={daily}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="d" stroke="var(--color-muted-foreground)" fontSize={10} />
                <YAxis yAxisId="left" stroke="var(--color-muted-foreground)" fontSize={10} />
                <YAxis yAxisId="right" orientation="right" stroke="var(--color-muted-foreground)" fontSize={10} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-popover)",
                    border: "1px solid var(--color-border)",
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                />
                <Bar yAxisId="left" dataKey="total" fill="#3b82f6" radius={[3, 3, 0, 0]} />
                <Line yAxisId="right" dataKey="rate" stroke="#22c55e" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>By branch / location</CardTitle>
        </CardHeader>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">Branch</TableHead>
                <TableHead>Total</TableHead>
                <TableHead>Rate</TableHead>
                <TableHead className="pr-6">Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {byBranch.map((b) => (
                <TableRow key={b.branch}>
                  <TableCell className="pl-6 text-sm">{b.branch}</TableCell>
                  <TableCell className="tabular-nums">{b.total}</TableCell>
                  <TableCell className="tabular-nums">{b.rate}%</TableCell>
                  <TableCell className="pr-6">
                    <Sparkline values={b.spark} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Detail metrics</CardTitle></CardHeader>
        <CardContent className="flex flex-nowrap gap-2 overflow-x-auto pb-0.5">
          <Mini label="Call answer rate" value={formatted.callRate} />
          <Mini label="Rescheduled → kept" value={formatted.rescheduledKept} />
          <Mini label="Cancelled" value={String(summary?.cancelled ?? "—")} />
        </CardContent>
      </Card>
    </>
  );
}
