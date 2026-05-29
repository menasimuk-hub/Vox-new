import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowUpRight, ArrowDownRight, Minus, Plus, Sparkles, Phone, Download,
  PoundSterling, PhoneOutgoing, UserCheck, MessageCircle, ListChecks, Timer, Wallet, Target,
  Radio, PhoneCall, CheckCircle2, Users, BarChart3, MessagesSquare, PauseCircle, type LucideIcon,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useServices } from "@/lib/services";
import { showRecoveryModules } from "@/lib/feature-flags";
import { useConnections } from "@/lib/connections";
import { useHomeSummary, useServiceOrders } from "@/lib/queries";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useSession } from "@/lib/session";

export const Route = createFileRoute("/_app/")({
  head: () => ({ meta: [{ title: "Dashboard — VoxBulk" }] }),
  component: Dashboard,
});

function Dashboard() {
  const { visible } = useServices();
  const { openChat } = useConnections();
  const { session } = useSession();
  const summaryQ = useHomeSummary();
  const interviewOrdersQ = useServiceOrders("interview");
  const summary = summaryQ.data;
  const greetingName = session?.org?.name?.split(/\s+/)[0] || session?.profile?.email?.split("@")[0] || "there";

  return (
    <div className="flex w-full flex-col gap-8">
      <PageHeader
        eyebrow="Dashboard · Live · Overview"
        title={`Good morning, ${greetingName}`}
        description="A live view of your outreach across every enabled service."
        actions={
          <>
            <Button variant="outline" className="gap-1.5" onClick={openChat}><Sparkles className="size-4" /> Ask AI</Button>
            {visible.interviews && (
              <Button asChild className="gap-1.5"><Link to="/interviews/new"><Plus className="size-4" /> New campaign</Link></Button>
            )}
            {!visible.interviews && visible.surveys && (
              <Button asChild className="gap-1.5"><Link to="/surveys/new"><Plus className="size-4" /> New survey</Link></Button>
            )}
          </>
        }
      />

      {summaryQ.isLoading && <Skeleton className="h-24 w-full rounded-xl" />}

      {showRecoveryModules && visible.recovery && <RecoverySection summary={summary} loading={summaryQ.isLoading} />}
      {visible.interviews && (
        <InterviewsSection
          summary={summary}
          loading={summaryQ.isLoading || interviewOrdersQ.isLoading}
          liveOrders={(interviewOrdersQ.data || []).filter((o) => o.is_live && o.status === "running").map((o) => orderToCampaign(o, "interview"))}
        />
      )}
      {visible.surveys && <SurveysSection summary={summary} loading={summaryQ.isLoading} />}
      {!visible.recovery && !visible.interviews && !visible.surveys && (
        <Card><CardContent className="p-10 text-center text-sm text-muted-foreground">
          No services are shown on your dashboard right now. Open <span className="font-medium text-foreground">Settings → Services</span> to turn Interviews or Surveys back on.
        </CardContent></Card>
      )}
    </div>
  );
}

function RecoverySection({ summary, loading }: { summary?: ReturnType<typeof useHomeSummary>["data"]; loading: boolean }) {
  const rec = summary?.recovery;
  const queuePending = rec?.queue_pending ?? 0;
  const totalCalls = rec?.total_calls ?? 0;
  const waSent = rec?.whatsapp_sent ?? 0;

  const kpis = [
    { label: "Calls made", value: String(totalCalls), delta: "—", trend: "flat" as const },
    { label: "Queue pending", value: String(queuePending), delta: "—", trend: "flat" as const },
    { label: "WhatsApp sent", value: String(waSent), delta: "—", trend: "flat" as const },
    { label: "Patients on file", value: String(summary?.total_patients ?? 0), delta: "—", trend: "flat" as const },
  ];

  return (
    <section className="flex flex-col gap-4">
      <div className="grid gap-5 rounded-2xl border border-border bg-gradient-to-br from-card via-card to-accent/40 p-6 md:grid-cols-[1.4fr_1fr]">
        <div className="flex flex-col justify-between gap-5">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-primary/80">Recovery · Live</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">Patient recovery outreach</h2>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              {loading ? "Loading recovery metrics…" : `${queuePending} patients in queue · ${totalCalls} calls logged.`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild className="gap-1.5"><Link to="/recovery"><Phone className="size-4" /> Recovery queue</Link></Button>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <RoiStat label="Queue" value={loading ? "…" : String(queuePending)} />
          <RoiStat label="Calls" value={loading ? "…" : String(totalCalls)} />
          <RoiStat label="WhatsApp" value={loading ? "…" : String(waSent)} />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => (
          <RichKpi
            key={k.label}
            label={k.label}
            value={loading ? "…" : k.value}
            delta={k.delta}
            trend={k.trend}
            icon={recoveryIcon(k.label)}
            spark={sparkFor(k.label)}
          />
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Calls overview</CardTitle>
          <CardDescription>Recovery call activity from your account</CardDescription>
        </CardHeader>
        <CardContent className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={[{ day: "Total", calls: totalCalls }]} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="day" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 12, fontSize: 12 }} />
              <Bar dataKey="calls" fill="var(--color-primary)" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </section>
  );
}

function InterviewsSection({
  summary,
  loading,
  liveOrders,
}: {
  summary?: ReturnType<typeof useHomeSummary>["data"];
  loading: boolean;
  liveOrders: ReturnType<typeof orderToCampaign>[];
}) {
  const int = summary?.interview;
  const kpis = [
    { label: "Live campaigns", value: String(int?.live ?? 0) },
    { label: "Running calls", value: String(int?.running ?? 0) },
    { label: "Finished this month", value: String(int?.finished ?? 0) },
    { label: "Candidates screened", value: String(int?.candidates ?? 0) },
  ];

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader title="Interviews" subtitle="AI phone screening at scale" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => (
          <SmallKpi key={k.label} label={k.label} value={loading ? "…" : k.value} icon={interviewsIcon(k.label)} tone="primary" />
        ))}
      </div>
      {liveOrders.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-base">Live interview campaigns</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {liveOrders.map((c) => (
              <div key={c.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 p-3">
                <div>
                  <p className="text-sm font-medium">{c.name}</p>
                  <p className="text-[11px] text-muted-foreground">{c.responses}/{c.target} calls · {c.updatedAt}</p>
                </div>
                <StatusBadge tone={c.status} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </section>
  );
}

function SurveysSection({ summary, loading }: { summary?: ReturnType<typeof useHomeSummary>["data"]; loading: boolean }) {
  const sur = summary?.survey;
  const kpis = [
    { label: "Live surveys", value: String(sur?.live ?? 0) },
    { label: "Responses", value: String(sur?.responses ?? 0) },
    { label: "Completion rate", value: `${sur?.completion_rate ?? 0}%` },
    { label: "Paused", value: String(sur?.paused ?? 0) },
  ];

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader title="Surveys" subtitle="Voice and WhatsApp questionnaires" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map((k) => (
          <SmallKpi key={k.label} label={k.label} value={loading ? "…" : k.value} icon={surveysIcon(k.label)} tone="info" />
        ))}
      </div>
    </section>
  );
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="flex items-end justify-between border-b border-border pb-2">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
    </div>
  );
}

function SmallKpi({ label, value, icon: Icon, tone = "primary" }: { label: string; value: string; icon?: LucideIcon; tone?: "primary" | "info" }) {
  const toneCls = tone === "info" ? "bg-info/10 text-info" : "bg-primary/10 text-primary";
  return (
    <Card className="group relative overflow-hidden transition hover:shadow-md">
      <div className={`pointer-events-none absolute -right-8 -top-8 size-24 rounded-full blur-2xl opacity-50 ${tone === "info" ? "bg-info/20" : "bg-primary/15"}`} />
      <CardContent className="relative flex items-start justify-between gap-3 p-4">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
        </div>
        {Icon && (
          <span className={`grid size-9 place-items-center rounded-lg ${toneCls}`}>
            <Icon className="size-4" />
          </span>
        )}
      </CardContent>
    </Card>
  );
}

function RichKpi({
  label, value, delta, trend, icon: Icon, spark,
}: {
  label: string; value: string; delta: string; trend: "up" | "down" | "flat";
  icon: LucideIcon; spark: number[];
}) {
  const trendCfg =
    trend === "up"
      ? { cls: "text-success bg-success/10 border-success/20", Arrow: ArrowUpRight, stroke: "var(--color-success)" }
      : trend === "down"
        ? { cls: "text-destructive bg-destructive/10 border-destructive/20", Arrow: ArrowDownRight, stroke: "var(--color-destructive)" }
        : { cls: "text-muted-foreground bg-muted border-border", Arrow: Minus, stroke: "var(--color-muted-foreground)" };
  const { Arrow } = trendCfg;
  return (
    <Card className="group relative overflow-hidden transition hover:-translate-y-0.5 hover:shadow-md">
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <span className="grid size-9 place-items-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" />
          </span>
          <span className={`inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] font-medium tabular-nums ${trendCfg.cls}`}>
            <Arrow className="size-3" /> {delta}
          </span>
        </div>
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</p>
          <p className="mt-0.5 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
        </div>
        <div className="-mx-1 -mb-1 h-10">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={spark.map((v, i) => ({ i, v }))} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <Area type="monotone" dataKey="v" stroke={trendCfg.stroke} strokeWidth={1.75} fill={`url(#g-${label})`} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function RoiStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/40 p-3">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function recoveryIcon(label: string): LucideIcon {
  const m: Record<string, LucideIcon> = {
    "Calls made": PhoneOutgoing,
    "Queue pending": ListChecks,
    "WhatsApp sent": MessageCircle,
    "Patients on file": UserCheck,
    "Recovered today": PoundSterling,
    "No-shows contacted": UserCheck,
    "WhatsApp open rate": MessageCircle,
    "Avg. call length": Timer,
    "Monthly cost": Wallet,
    "Monthly target": Target,
  };
  return m[label] ?? Sparkles;
}
function interviewsIcon(label: string): LucideIcon {
  const m: Record<string, LucideIcon> = {
    "Live campaigns": Radio,
    "Running calls": PhoneCall,
    "Finished this month": CheckCircle2,
    "Candidates screened": Users,
  };
  return m[label] ?? Users;
}
function surveysIcon(label: string): LucideIcon {
  const m: Record<string, LucideIcon> = {
    "Live surveys": Radio,
    "Responses": MessagesSquare,
    "Completion rate": BarChart3,
    "Paused": PauseCircle,
  };
  return m[label] ?? MessagesSquare;
}
function sparkFor(label: string): number[] {
  const seed = label.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  return Array.from({ length: 12 }, (_, i) => {
    const x = Math.sin((seed + i * 13) * 0.7) * 0.5 + Math.cos((seed + i * 7) * 0.4) * 0.4;
    return 50 + x * 35 + i * 1.4;
  });
}
void Download; void Progress; void Area;
