import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowUpRight,
  Flame,
  Minus,
  QrCode,
  Thermometer,
  User,
  Users,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

type Lead = {
  id: string;
  name?: string | null;
  company?: string | null;
  representative_name?: string | null;
  lead_score?: string | null;
  interest?: string | null;
  ai_summary?: string | null;
  suggested_follow_up?: string | null;
  follow_up_status?: string;
  created_at?: string | null;
};

type Summary = {
  scans: number;
  scans_today?: number;
  leads: number;
  leads_today?: number;
  hot: number;
  warm: number;
  cold: number;
  need_follow_up?: number;
  leads_this_week?: number;
  leads_this_month?: number;
  daily?: Array<{ day: string; scans: number; leads: number; hot: number }>;
  by_representative?: Array<{ id: string; name: string; scan_count: number; lead_count: number }>;
  active_reps?: number;
  seat_quantity?: number;
};

type RepRow = {
  id: string;
  name: string;
  scan_count?: number;
  status?: string;
  email?: string | null;
};

export const Route = createFileRoute("/_app/smart-card/leads")({
  head: () => ({ meta: [{ title: "Lead results — Smart Card QR" }] }),
  component: SmartCardLeadsPage,
});

function SmartCardLeadsPage() {
  const qc = useQueryClient();

  const summaryQ = useQuery({
    queryKey: ["smart-card", "summary"],
    queryFn: () => apiFetch<{ ok: boolean } & Summary>("/smart-card/results/summary"),
  });

  const repsQ = useQuery({
    queryKey: ["smart-card", "reps", "leads-page"],
    queryFn: () => apiFetch<{ ok: boolean; items: RepRow[] }>("/smart-card/representatives"),
  });

  const leadsQ = useQuery({
    queryKey: ["smart-card", "leads"],
    queryFn: () => apiFetch<{ ok: boolean; items: Lead[] }>("/smart-card/results/leads"),
  });

  const markMut = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      apiFetch(`/smart-card/results/leads/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ follow_up_status: status }),
      }),
    onSuccess: async () => {
      toast.success("Lead updated");
      await qc.invalidateQueries({ queryKey: ["smart-card", "leads"] });
      await qc.invalidateQueries({ queryKey: ["smart-card", "summary"] });
    },
  });

  const summary = summaryQ.data;
  const daily = summary?.daily || [];
  const byRep =
    summary?.by_representative ||
    (repsQ.data?.items || [])
      .filter((r) => r.status !== "archived")
      .map((r) => ({
        id: r.id,
        name: r.name,
        scan_count: r.scan_count || 0,
        lead_count: 0,
      }));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Lead results"
        description="Owner/manager see all; representatives see only their own."
      />

      {summaryQ.isLoading ? (
        <Skeleton className="h-32 rounded-2xl" />
      ) : summary ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <RichKpi
              label="Scans total"
              value={summary.scans}
              sub={`${summary.active_reps ?? 0} representatives`}
              trend={(summary.scans_today || 0) > 0 ? "up" : "flat"}
              labelDelta={`${summary.scans_today || 0} today`}
              todayLabel={`${summary.scans_today || 0} today`}
              icon={<QrCode className="size-4" />}
              spark={daily.map((d) => d.scans)}
              accent="sky"
            />
            <RichKpi
              label="Leads total"
              value={summary.leads}
              sub={`${summary.leads_this_week || 0} this week`}
              trend={(summary.leads_today || 0) > 0 ? "up" : "flat"}
              labelDelta={`${summary.leads_today || 0} today`}
              todayLabel={`${summary.leads_today || 0} today`}
              icon={<User className="size-4" />}
              spark={daily.map((d) => d.leads)}
              accent="emerald"
            />
            <RichKpi
              label="Hot leads"
              value={summary.hot}
              sub={`${summary.warm} warm · ${summary.cold} cold`}
              trend="up"
              labelDelta={`${summary.need_follow_up || 0} need follow-up`}
              todayLabel="Priority follow-up"
              icon={<Flame className="size-4" />}
              spark={daily.map((d) => d.hot)}
              accent="orange"
            />
            <RichKpi
              label="This month"
              value={summary.leads_this_month || 0}
              sub="Completed leads"
              trend="flat"
              labelDelta="Calendar month"
              todayLabel={`${summary.leads_this_week || 0} this week`}
              icon={<Thermometer className="size-4" />}
              spark={daily.map((d) => d.leads)}
              accent="violet"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Last 7 days</CardTitle>
                <p className="text-xs text-muted-foreground">Scans and leads (UK calendar days)</p>
              </CardHeader>
              <CardContent className="h-[220px]">
                {daily.length === 0 ? (
                  <p className="grid h-full place-items-center text-sm text-muted-foreground">No activity yet</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={daily} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                      <defs>
                        <linearGradient id="scScans" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#0ea5e9" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#0ea5e9" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="scLeads" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#10b981" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                      <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip
                        contentStyle={{
                          background: "hsl(var(--card))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: 8,
                          fontSize: 12,
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="scans"
                        name="Scans"
                        stroke="#0ea5e9"
                        strokeWidth={2}
                        fill="url(#scScans)"
                      />
                      <Area
                        type="monotone"
                        dataKey="leads"
                        name="Leads"
                        stroke="#10b981"
                        strokeWidth={2}
                        fill="url(#scLeads)"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users className="size-4" /> Representatives
                </CardTitle>
                <p className="text-xs text-muted-foreground">Scans and leads per QR</p>
              </CardHeader>
              <CardContent className="max-h-[220px] overflow-auto p-0">
                {byRep.length === 0 ? (
                  <p className="grid h-[180px] place-items-center text-sm text-muted-foreground">No representatives</p>
                ) : (
                  <table className="w-full text-left text-sm">
                    <thead className="sticky top-0 border-b bg-muted/40 text-xs text-muted-foreground">
                      <tr>
                        <th className="px-4 py-2 font-medium">Name</th>
                        <th className="px-3 py-2 font-medium tabular-nums">Scans</th>
                        <th className="px-4 py-2 font-medium tabular-nums">Leads</th>
                      </tr>
                    </thead>
                    <tbody>
                      {byRep.map((r) => (
                        <tr key={r.id} className="border-b last:border-0">
                          <td className="truncate px-4 py-2 font-medium">{r.name}</td>
                          <td className="px-3 py-2 tabular-nums">{r.scan_count}</td>
                          <td className="px-4 py-2 tabular-nums">{r.lead_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold tracking-tight">Recent leads</h2>
        {(leadsQ.data?.items || []).map((lead) => (
          <Card key={lead.id}>
            <CardContent className="space-y-2 p-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">
                    {lead.name || "Unknown"} · {lead.company || "—"}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {lead.representative_name} · {lead.lead_score || "unscored"} · {lead.follow_up_status}
                  </p>
                </div>
                {lead.follow_up_status === "open" ? (
                  <Button size="sm" variant="secondary" onClick={() => markMut.mutate({ id: lead.id, status: "done" })}>
                    Mark done
                  </Button>
                ) : null}
              </div>
              {lead.ai_summary ? <p className="text-sm text-muted-foreground">{lead.ai_summary}</p> : null}
              {lead.suggested_follow_up ? (
                <p className="rounded-md border bg-muted/40 p-2 text-sm">{lead.suggested_follow_up}</p>
              ) : null}
            </CardContent>
          </Card>
        ))}
        {!leadsQ.isLoading && !(leadsQ.data?.items || []).length ? (
          <p className="text-sm text-muted-foreground">No leads yet.</p>
        ) : null}
      </div>
    </div>
  );
}

function RichKpi({
  label,
  value,
  sub,
  todayLabel,
  trend,
  labelDelta,
  icon,
  spark,
  accent,
}: {
  label: string;
  value: number;
  sub?: string;
  todayLabel: string;
  trend: "up" | "down" | "flat";
  labelDelta?: string;
  icon: React.ReactNode;
  spark: number[];
  accent: "sky" | "emerald" | "orange" | "violet";
}) {
  const meta =
    trend === "up"
      ? { Arrow: ArrowUpRight, cls: "text-emerald-700 bg-emerald-500/10 border-emerald-500/20", stroke: "#10b981" }
      : trend === "down"
        ? { Arrow: ArrowDownRight, cls: "text-rose-700 bg-rose-500/10 border-rose-500/20", stroke: "#f43f5e" }
        : { Arrow: Minus, cls: "text-muted-foreground bg-muted border-border", stroke: "#94a3b8" };
  const { Arrow } = meta;
  const iconBg =
    accent === "sky"
      ? "bg-sky-500/10 text-sky-700"
      : accent === "emerald"
        ? "bg-emerald-500/10 text-emerald-700"
        : accent === "orange"
          ? "bg-orange-500/10 text-orange-700"
          : "bg-violet-500/10 text-violet-700";
  const deltaText = labelDelta || todayLabel;

  return (
    <Card className="overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
      <CardContent className="flex flex-col gap-3 p-3">
        <div className="flex items-start justify-between gap-2">
          <span className={cn("grid size-7 place-items-center rounded-lg", iconBg)}>{icon}</span>
          <span
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium tabular-nums",
              meta.cls,
            )}
          >
            <Arrow className="size-3" /> {deltaText}
          </span>
        </div>
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="mt-0.5 text-lg font-semibold tracking-tight tabular-nums">{value.toLocaleString()}</p>
          {sub ? <p className="mt-0.5 text-[11px] text-muted-foreground">{sub}</p> : null}
          <p className="mt-1 text-xs font-medium text-foreground/80">{todayLabel}</p>
        </div>
        <div className="-mx-1 -mb-1 h-8">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={(spark.length ? spark : [0, 0, 0]).map((v, i) => ({ i, v }))}
              margin={{ top: 4, right: 0, left: 0, bottom: 0 }}
            >
              <Area
                type="monotone"
                dataKey="v"
                stroke={meta.stroke}
                strokeWidth={1.75}
                fill={meta.stroke}
                fillOpacity={0.12}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
