import { createFileRoute, Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Flame, QrCode, TrendingUp, User } from "lucide-react";
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

type Summary = {
  scans: number;
  scans_today: number;
  leads: number;
  leads_today: number;
  leads_this_week: number;
  leads_this_month: number;
  hot: number;
  warm: number;
  cold: number;
  need_follow_up: number;
  daily: Array<{ day: string; scans: number; leads: number; hot: number }>;
  seat_quantity: number;
  active_reps: number;
  mode: string;
};

export const Route = createFileRoute("/_app/smart-card/")({
  component: SmartCardHubPage,
});

function SmartCardHubPage() {
  const summaryQ = useQuery({
    queryKey: ["smart-card", "summary"],
    queryFn: () => apiFetch<{ ok: boolean } & Summary>("/smart-card/results/summary"),
  });
  const s = summaryQ.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Dashboard"
        description="Scans, leads, and follow-ups for your Smart Card QR team."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/smart-card/leads">Leads</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/account/smart-card/packages">Packages</Link>
            </Button>
          </div>
        }
      />

      {summaryQ.isLoading ? (
        <Skeleton className="h-32 rounded-2xl" />
      ) : s ? (
        <>
          {s.mode === "expired" ? (
            <Card className="border-rose-500/30 bg-rose-500/5">
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                <p className="text-sm">We&apos;re sorry — your package expired. Renew to accept new scans.</p>
                <Button asChild>
                  <Link to="/account/smart-card/packages">Renew</Link>
                </Button>
              </CardContent>
            </Card>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <RichKpi
              label="Scans"
              value={s.scans}
              todayLabel={`${s.scans_today} today`}
              sub={`${s.leads_this_week} leads this week · ${s.leads_this_month} this month`}
              icon={<QrCode className="size-4" />}
              spark={s.daily.map((d) => d.scans)}
              accent="sky"
            />
            <RichKpi
              label="Leads"
              value={s.leads}
              todayLabel={`${s.leads_today} today`}
              sub={s.scans ? `${Math.round((s.leads / Math.max(1, s.scans)) * 100)}% conversion` : "No scans yet"}
              icon={<User className="size-4" />}
              spark={s.daily.map((d) => d.leads)}
              accent="emerald"
            />
            <RichKpi
              label="Hot leads"
              value={s.hot}
              todayLabel="Priority follow-up"
              sub={`${s.warm} warm · ${s.cold} cold`}
              icon={<Flame className="size-4" />}
              spark={s.daily.map((d) => d.hot)}
              accent="orange"
              ping={s.need_follow_up > 0}
            />
            <RichKpi
              label="Team seats"
              value={s.active_reps}
              todayLabel={`${s.seat_quantity} purchased`}
              sub={`Mode: ${s.mode.replace(/_/g, " ")}`}
              icon={<TrendingUp className="size-4" />}
              spark={s.daily.map((d) => d.leads)}
              accent="violet"
            />
          </div>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Last 7 days</CardTitle>
            </CardHeader>
            <CardContent className="h-[220px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={s.daily} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="day" tick={{ fontSize: 11 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Area type="monotone" dataKey="scans" name="Scans" stroke="#0ea5e9" fill="#0ea5e933" />
                  <Area type="monotone" dataKey="leads" name="Leads" stroke="#10b981" fill="#10b98133" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function RichKpi({
  label,
  value,
  sub,
  todayLabel,
  icon,
  spark,
  accent,
  ping,
}: {
  label: string;
  value: number;
  sub?: string;
  todayLabel: string;
  icon: React.ReactNode;
  spark: number[];
  accent: "sky" | "emerald" | "orange" | "violet";
  ping?: boolean;
}) {
  const iconBg =
    accent === "sky"
      ? "bg-sky-500/10 text-sky-700"
      : accent === "emerald"
        ? "bg-emerald-500/10 text-emerald-700"
        : accent === "orange"
          ? "bg-orange-500/10 text-orange-700"
          : "bg-violet-500/10 text-violet-700";
  return (
    <Card className="overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
      <CardContent className="flex flex-col gap-3 p-3">
        <div className="flex items-start justify-between gap-2">
          <span className={cn("relative grid size-7 place-items-center rounded-lg", iconBg)}>
            {icon}
            {ping ? (
              <span className="absolute -right-0.5 -top-0.5 flex size-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
            ) : null}
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
            <AreaChart data={(spark.length ? spark : [0, 0, 0]).map((v, i) => ({ i, v }))} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <Area type="monotone" dataKey="v" stroke="#94a3b8" strokeWidth={1.75} fill="#94a3b820" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
