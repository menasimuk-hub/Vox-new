import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import {
  ArrowUpRight, ArrowDownRight, Minus, Plus, Sparkles, Phone, Download,
  PoundSterling, PhoneOutgoing, UserCheck, MessageCircle, ListChecks, Timer, Wallet, Target,
  Radio, PhoneCall, CheckCircle2, Users, BarChart3, MessagesSquare, PauseCircle, type LucideIcon,
  Activity, TrendingUp, Smile, Frown, Meh, Star, QrCode, MessageSquareText, HeartPulse, AlertTriangle, Clock3,
} from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { PendingInviteBanner } from "@/components/pending-invite-banner";
import { NewCampaignPicker } from "@/components/new-campaign-picker";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { useServices, type ServiceKey } from "@/lib/services";
import { showRecoveryModules } from "@/lib/feature-flags";
import { useConnections } from "@/lib/connections";
import { useHomeSummary, useServiceOrders } from "@/lib/queries";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useSession } from "@/lib/session";
import type { HomeSummary } from "@/lib/types/api";
import { cn } from "@/lib/utils";
import { requireBillingOnlyHome } from "@/lib/guards/settings-route";

export const Route = createFileRoute("/_app/")({
  head: () => ({ meta: [{ title: "Dashboard — VoxBulk" }] }),
  beforeLoad: () => requireBillingOnlyHome(),
  component: Dashboard,
});

const COLORS = { green: "#22c55e", amber: "#f59e0b", red: "#ef4444", blue: "#3b82f6" };

function Dashboard() {
  const { visible } = useServices();
  const { openChat } = useConnections();
  const { session } = useSession();
  const [pickOpen, setPickOpen] = React.useState(false);
  const summaryQ = useHomeSummary();
  const interviewOrdersQ = useServiceOrders("interview");
  const summary = summaryQ.data;
  const greetingName = session?.org?.name?.split(/\s+/)[0] || session?.profile?.email?.split("@")[0] || "there";

  const anyResponseService = visible.feedback || visible.surveys;
  const anyService =
    visible.interviews || visible.surveys || visible.feedback || visible.campaigns || visible.recovery || visible.followup;
  const loading = summaryQ.isLoading;
  const summaryReady = summaryQ.isSuccess;
  const summaryError = summaryQ.isError
    ? (summaryQ.error instanceof Error ? summaryQ.error.message : "Could not load dashboard summary")
    : null;

  return (
    <div className="flex w-full flex-col gap-6">
      <PendingInviteBanner />
      <PageHeader
        eyebrow="Dashboard · Live · Overview"
        title={`Good morning, ${greetingName}`}
        description="A live view of your outreach across every enabled service."
        actions={
          <>
            <Button variant="outline" className="gap-1.5" onClick={openChat}><Sparkles className="size-4" /> Ask AI</Button>
            <Button className="gap-1.5" onClick={() => setPickOpen(true)}><Plus className="size-4" /> New campaign</Button>
          </>
        }
      />

      <NewCampaignPicker open={pickOpen} onOpenChange={setPickOpen} />

      {loading && <Skeleton className="h-24 w-full rounded-xl" />}

      {summaryError && !loading && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" />
              <div>
                <p className="text-sm font-medium text-foreground">Could not load dashboard summary</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Metrics below may show zero until the API is reachable. Try refreshing — if this persists after deploy, restart the API on the server.
                </p>
                <p className="mt-2 break-all font-mono text-[11px] text-muted-foreground">{summaryError}</p>
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={() => void summaryQ.refetch()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      )}

      {anyService && summaryReady && <LiveStrip visible={visible} summary={summary} />}
      {anyService && summaryReady && <HeroRow visible={visible} summary={summary} />}

      {(anyResponseService || visible.interviews) && summaryReady && (
        <div className="grid gap-4 lg:grid-cols-3">
          <LiveActivity visible={visible} summary={summary} />
          {anyResponseService && <SentimentCard summary={summary} />}
        </div>
      )}

      {anyResponseService && summaryReady && <UnhappyCustomers summary={summary} />}

      {showRecoveryModules && visible.recovery && summaryReady && <RecoverySection summary={summary} loading={loading} />}
      {visible.interviews && summaryReady && (
        <InterviewsSection
          summary={summary}
          loading={loading || interviewOrdersQ.isLoading}
          liveOrders={(interviewOrdersQ.data || []).filter((o) => o.is_live && o.status === "running").map((o) => orderToCampaign(o, "interview"))}
        />
      )}
      {visible.surveys && summaryReady && <SurveysSection summary={summary} loading={loading} />}
      {!anyService && (
        <Card><CardContent className="p-10 text-center text-sm text-muted-foreground">
          No services are shown on your dashboard right now. Open <span className="font-medium text-foreground">Settings → Services</span> to turn Interviews or Surveys back on.
        </CardContent></Card>
      )}
    </div>
  );
}

type VisibleMap = Record<ServiceKey, boolean>;

function LiveStrip({ visible, summary }: { visible: VisibleMap; summary?: HomeSummary }) {
  const int = summary?.interview;
  const sur = summary?.survey;
  const fb = summary?.feedback;
  const happyTotal = (fb?.sentiment?.excellent ?? 0) + (fb?.sentiment?.good ?? 0);
  const sentimentTotal = happyTotal + (fb?.sentiment?.poor ?? 0);
  const happyPct = sentimentTotal ? `${Math.round((happyTotal / sentimentTotal) * 100)}%` : "—";

  const all = [
    { key: "interviews" as const, icon: PhoneCall, label: "AI interview calls live", value: String(int?.running ?? int?.live ?? 0), tone: "text-blue-500" },
    { key: "surveys" as const, icon: Phone, label: "AI survey calls live", value: String(sur?.running ?? 0), tone: "text-violet-500" },
    { key: "surveys" as const, icon: MessageCircle, label: "WA survey threads active", value: String(sur?.live ?? 0), tone: "text-emerald-500" },
    { key: "feedback" as const, icon: QrCode, label: "QR scans today", value: String(fb?.qr_scans_today ?? 0), tone: "text-amber-500" },
    { key: "feedback" as const, icon: Smile, label: "Happy customers", value: happyPct, tone: "text-emerald-500" },
  ];
  const items = all.filter((i) => visible[i.key]).slice(0, 4);
  if (items.length === 0) return null;

  return (
    <div className={cn("grid gap-2 rounded-2xl border border-border bg-card/60 p-2 sm:grid-cols-2", items.length >= 4 ? "lg:grid-cols-4" : "lg:grid-cols-2")}>
      {items.map((i) => (
        <div key={i.label} className="flex items-center gap-3 rounded-xl bg-background/50 px-3 py-2">
          <span className="relative grid size-9 place-items-center rounded-lg bg-muted">
            <i.icon className={cn("size-4", i.tone)} />
            <span className="absolute -right-0.5 -top-0.5 flex size-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
              <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
            </span>
          </span>
          <div className="min-w-0">
            <p className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">{i.label}</p>
            <p className="text-lg font-semibold tabular-nums leading-tight">{i.value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function HeroRow({ visible, summary }: { visible: VisibleMap; summary?: HomeSummary }) {
  const int = summary?.interview;
  const sur = summary?.survey;
  const fb = summary?.feedback;
  const conversations =
    (int?.calls_completed ?? int?.candidates ?? 0) + (sur?.responses ?? 0) + (fb?.total_scans ?? 0);

  const tiles = [
    { show: visible.interviews, label: "Candidates screened", value: String(int?.candidates ?? 0), tone: "text-blue-500" },
    { show: visible.surveys, label: "Survey responses", value: String(sur?.responses ?? 0), tone: "text-violet-500" },
    { show: visible.feedback, label: "QR feedback", value: String(fb?.total_scans ?? 0), tone: "text-emerald-500" },
  ].filter((t) => t.show);

  const unhappyCount = summary?.feedback?.unhappy?.length ?? 0;
  const liveCampaigns = (int?.live ?? 0) + (sur?.live ?? 0);

  return (
    <div className="grid gap-4 lg:grid-cols-[1.5fr_1fr]">
      <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-card via-card to-accent/40 p-6">
        <div className="absolute -right-24 -top-24 size-72 rounded-full bg-primary/20 blur-3xl" />
        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-primary/80">Activity · this month</p>
        <h2 className="mt-2 text-4xl font-semibold tracking-tight md:text-5xl">
          Your AI ran <span className="text-primary">{conversations.toLocaleString()}</span> conversations
        </h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          Across phone, WhatsApp and QR — every customer touchpoint in one place.
        </p>
        {tiles.length > 0 && (
          <div className={cn("mt-5 grid gap-2", tiles.length <= 2 ? "grid-cols-2" : "grid-cols-3")}>
            {tiles.map((t) => <HeroStat key={t.label} label={t.label} value={t.value} tone={t.tone} />)}
          </div>
        )}
      </div>

      <div className="rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Live campaigns</p>
          <Badge variant="secondary" className="gap-1"><TrendingUp className="size-3" /> active</Badge>
        </div>
        <p className="mt-1 text-2xl font-semibold tabular-nums">{liveCampaigns}</p>
        <Progress value={liveCampaigns ? Math.min(liveCampaigns * 10, 100) : 0} className="mt-3 h-2" />
        <div className="mt-4 grid grid-cols-1 gap-2 text-sm">
          {visible.feedback && unhappyCount > 0 && (
            <HeroAlert tone="warning" icon={AlertTriangle} title={`${unhappyCount} need follow-up`} detail="Review unhappy feedback today" />
          )}
          {liveCampaigns > 0 && (
            <HeroAlert tone="info" icon={Clock3} title={`${liveCampaigns} campaigns live`} detail="Running across your services" />
          )}
        </div>
      </div>
    </div>
  );
}

function HeroStat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-background/50 p-3">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p className={cn("mt-1 text-xl font-semibold tabular-nums", tone)}>{value}</p>
    </div>
  );
}

function HeroAlert({ tone, icon: Icon, title, detail }: { tone: "warning" | "info"; icon: LucideIcon; title: string; detail: string }) {
  const cls = tone === "warning" ? "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" : "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400";
  return (
    <div className={cn("flex items-start gap-2 rounded-lg border p-2", cls)}>
      <Icon className="mt-0.5 size-3.5 shrink-0" />
      <div className="min-w-0">
        <p className="text-xs font-medium leading-tight">{title}</p>
        <p className="text-[10px] opacity-80">{detail}</p>
      </div>
    </div>
  );
}

type ActivityItem = NonNullable<HomeSummary["feedback"]>["recent"] extends (infer R)[] | undefined ? R : never;

function LiveActivity({ visible, summary }: { visible: VisibleMap; summary?: HomeSummary }) {
  const feed: ActivityItem[] = (summary?.feedback?.recent || []).filter((f) => visible[f.svc as ServiceKey] ?? f.svc === "feedback");
  const iconFor = (tone?: string) => {
    if (tone === "bad") return Frown;
    if (tone === "ok") return Star;
    return QrCode;
  };

  return (
    <Card className="lg:col-span-2">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2"><Activity className="size-4 text-emerald-500" /> Live activity</CardTitle>
          <CardDescription>Recent customer interactions across your services</CardDescription>
        </div>
        <Badge variant="outline" className="gap-1.5"><span className="size-1.5 animate-pulse rounded-full bg-emerald-500" /> Live</Badge>
      </CardHeader>
      <CardContent className="space-y-2">
        {feed.length === 0 && (
          <p className="py-6 text-center text-xs text-muted-foreground">No recent activity yet. Launch a campaign or collect feedback to see updates here.</p>
        )}
        {feed.map((f, i) => {
          const Icon = iconFor(f.tone);
          const initials = (f.who || "?").split(/\s+/).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
          return (
            <div key={`${f.when}-${i}`} className="flex items-center gap-3 rounded-lg border border-border/60 bg-background/40 p-2.5 transition hover:border-border hover:bg-background/70">
              <Avatar className="size-8"><AvatarFallback className="text-[10px]">{initials}</AvatarFallback></Avatar>
              <span className={cn(
                "grid size-7 place-items-center rounded-md",
                f.tone === "ok" ? "bg-emerald-500/10 text-emerald-500" :
                f.tone === "bad" ? "bg-red-500/10 text-red-500" :
                "bg-blue-500/10 text-blue-500",
              )}><Icon className="size-3.5" /></span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm"><span className="font-medium">{f.who}</span> <span className="text-muted-foreground">{f.what}</span></p>
                <p className="text-[10px] text-muted-foreground">{formatWhen(f.when)}</p>
              </div>
              {f.chip && (
                <Badge variant={f.tone === "bad" ? "destructive" : f.tone === "ok" ? "default" : "secondary"} className="text-[10px]">{f.chip}</Badge>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

function SentimentCard({ summary }: { summary?: HomeSummary }) {
  const s = summary?.feedback?.sentiment;
  const sentiment = [
    { name: "Excellent", value: s?.excellent ?? 0, color: COLORS.green, icon: Smile },
    { name: "Good", value: s?.good ?? 0, color: COLORS.blue, icon: Meh },
    { name: "Poor", value: s?.poor ?? 0, color: COLORS.red, icon: Frown },
  ];
  const totalSent = sentiment.reduce((a, b) => a + b.value, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customer sentiment</CardTitle>
        <CardDescription>Across surveys, interviews, and feedback responses</CardDescription>
      </CardHeader>
      <CardContent>
        {totalSent === 0 ? (
          <p className="py-10 text-center text-xs text-muted-foreground">No sentiment data yet. Survey and feedback responses will appear here.</p>
        ) : (
          <>
            <div className="relative h-44">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={sentiment} dataKey="value" innerRadius={50} outerRadius={75} paddingAngle={3} stroke="none">
                    {sentiment.map((e, i) => <Cell key={i} fill={e.color} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: "var(--color-popover)", border: "1px solid var(--color-border)", borderRadius: 12, fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
              <div className="pointer-events-none absolute inset-0 grid place-items-center">
                <div className="text-center">
                  <p className="text-3xl font-semibold tabular-nums">{totalSent}</p>
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Responses</p>
                </div>
              </div>
            </div>
            <div className="mt-4 space-y-1.5">
              {sentiment.map((row) => {
                const pct = totalSent ? Math.round((row.value / totalSent) * 100) : 0;
                return (
                  <div key={row.name} className="flex items-center gap-2 text-sm">
                    <row.icon className="size-4" style={{ color: row.color }} />
                    <span className="flex-1">{row.name}</span>
                    <span className="tabular-nums text-muted-foreground">{row.value}</span>
                    <span className="w-10 text-right text-xs font-medium tabular-nums" style={{ color: row.color }}>{pct}%</span>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function UnhappyCustomers({ summary }: { summary?: HomeSummary }) {
  const unhappy = summary?.feedback?.unhappy || [];

  return (
    <Card className="w-full">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="flex items-center gap-2"><Frown className="size-4 text-red-500" /> Needs follow-up</CardTitle>
          <CardDescription>Unhappy customers — reach out today</CardDescription>
        </div>
        {unhappy.length > 0 && <Badge variant="destructive">{unhappy.length}</Badge>}
      </CardHeader>
      <CardContent>
        {unhappy.length === 0 ? (
          <p className="py-6 text-center text-xs text-muted-foreground">No customers need follow-up right now.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {unhappy.map((u) => (
              <div key={u.id || u.reason} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{u.branch || "Customer"}</p>
                    <p className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{u.reason || "Negative feedback"}</p>
                  </div>
                  <span className="shrink-0 text-[10px] text-muted-foreground">{formatWhen(u.when)}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function formatWhen(iso?: string | null) {
  if (!iso) return "Recently";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Recently";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return d.toLocaleDateString();
}

function RecoverySection({ summary, loading }: { summary?: HomeSummary; loading: boolean }) {
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
          <RecoveryStat label="Queue" value={loading ? "…" : String(queuePending)} />
          <RecoveryStat label="Calls" value={loading ? "…" : String(totalCalls)} />
          <RecoveryStat label="WhatsApp" value={loading ? "…" : String(waSent)} />
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
  summary?: HomeSummary;
  loading: boolean;
  liveOrders: ReturnType<typeof orderToCampaign>[];
}) {
  const int = summary?.interview;
  const kpis = [
    { label: "Calls attempted", value: String(int?.calls_attempted ?? 0) },
    { label: "Completed calls", value: String(int?.calls_completed ?? 0) },
    { label: "Recommended advance", value: String(int?.recommended_advance ?? 0) },
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

function SurveysSection({ summary, loading }: { summary?: HomeSummary; loading: boolean }) {
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

function RecoveryStat({ label, value }: { label: string; value: string }) {
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
void Download; void Progress; void Area; void MessageSquareText; void HeartPulse;
