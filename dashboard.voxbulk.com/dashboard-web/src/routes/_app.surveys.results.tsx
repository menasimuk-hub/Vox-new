import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import { Download, Filter, MessageSquareText, Search, Sparkles, TrendingUp, Users } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { downloadAuthenticatedFile } from "@/lib/api";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useServiceOrders, useSurveyResults } from "@/lib/queries";

export const Route = createFileRoute("/_app/surveys/results")({
  validateSearch: (search: Record<string, unknown>) => ({
    orderId: typeof search.orderId === "string" ? search.orderId : undefined,
  }),
  head: () => ({ meta: [{ title: "Survey results — VoxBulk" }] }),
  component: SurveyResults,
});

function SurveyResults() {
  const { orderId: searchOrderId } = Route.useSearch();
  const ordersQ = useServiceOrders("survey");
  const campaigns = React.useMemo(
    () => (ordersQ.data || []).map((o) => orderToCampaign(o, "survey")),
    [ordersQ.data],
  );
  const [selectedId, setSelectedId] = React.useState<string | undefined>(searchOrderId);
  React.useEffect(() => {
    if (searchOrderId) {
      setSelectedId(searchOrderId);
      return;
    }
    if (!selectedId && campaigns[0]) setSelectedId(campaigns[0].id);
  }, [searchOrderId, campaigns, selectedId]);

  const activeOrderId = searchOrderId || selectedId;
  const selected = campaigns.find((c) => c.id === activeOrderId);
  const resultsQ = useSurveyResults(activeOrderId || null);
  const payload = resultsQ.data || {};
  const summary = (payload.summary || {}) as Record<string, number | string | null | undefined>;
  const orderInfo = (payload.order || {}) as Record<string, string>;
  const aggregates = (payload.aggregates || []) as Array<{ question: string; total: number; responses: Array<{ answer: string; count: number }> }>;
  const recommendations = (payload.recommendations || []) as Array<{ text?: string; impact?: string }>;
  const respondents = (payload.respondents || []) as Array<{ quote?: string; recommend_score?: number; theme?: string }>;

  const exportResults = async (kind: "pdf" | "csv") => {
    const exportId = searchOrderId || selectedId;
    if (!exportId) return;
    try {
      const ext = kind === "pdf" ? "pdf" : "csv";
      await downloadAuthenticatedFile(
        `/service-orders/${encodeURIComponent(exportId)}/survey-results/export.${ext}`,
        `survey-results-${exportId.slice(0, 8)}.${ext}`,
      );
      toast.success(`${kind.toUpperCase()} downloaded`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    }
  };

  const npsDisplay = summary.nps_score != null ? `+${summary.nps_score}` : "—";

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Surveys · Results"
        title={orderInfo.title || selected?.name || (searchOrderId ? "Survey results" : "Survey results")}
        description="One-survey results: live responses, question analysis, segments, themes, and anonymous response browser."
        actions={
          <>
            <Button variant="outline" className="gap-1.5" onClick={() => void exportResults("pdf")} disabled={!activeOrderId}><Download className="size-4" /> Export PDF</Button>
            <Button variant="outline" className="gap-1.5" onClick={() => void exportResults("csv")} disabled={!activeOrderId}><Download className="size-4" /> Export CSV</Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={activeOrderId} onValueChange={setSelectedId}>
            <SelectTrigger className="h-9 w-56"><SelectValue placeholder="Select survey" /></SelectTrigger>
            <SelectContent>
              {campaigns.map((c) => (
                <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selected && <StatusBadge tone={selected.status} />}
          <span className="text-sm text-muted-foreground">
            {Number(summary.completed_count || selected?.responses || 0).toLocaleString()} / {Number(summary.total_recipients || selected?.target || 0).toLocaleString()} responses
          </span>
        </div>
        <Tabs defaultValue="overview"><TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="questions">Questions</TabsTrigger>
          <TabsTrigger value="responses">Responses</TabsTrigger>
        </TabsList></Tabs>
      </div>

      {resultsQ.isLoading ? (
        <div className="grid gap-4 md:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-4">
          <Kpi title="NPS" value={npsDisplay} sub={String(summary.nps_label || "customer score")} icon={<TrendingUp className="size-4" />} />
          <Kpi title="Response rate" value={`${summary.response_rate_pct ?? 0}%`} sub={`${summary.completed_count ?? 0} of ${summary.total_recipients ?? 0}`} icon={<Users className="size-4" />} />
          <Kpi title="Completion" value={`${summary.response_rate_pct ?? 0}%`} sub={String(summary.average_call_duration_label || "avg. duration")} icon={<MessageSquareText className="size-4" />} />
          <Kpi title="Detractor risk" value={`${summary.nps_detractors_pct ?? 0}%`} sub={`${summary.nps_detractors ?? 0} responses`} tone="destructive" icon={<Sparkles className="size-4" />} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <Card>
          <CardHeader><CardTitle className="text-base">Question-level results</CardTitle></CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-3">
            {aggregates.length === 0 ? (
              <p className="col-span-full text-sm text-muted-foreground">No question aggregates yet.</p>
            ) : aggregates.slice(0, 3).map((q) => (
              <QuestionCard
                key={q.question}
                title={q.question}
                type="Survey"
                rows={q.responses.slice(0, 4).map((r) => {
                  const pct = q.total ? Math.round((r.count / q.total) * 100) : 0;
                  return [r.answer, pct, "info"] as const;
                })}
              />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Response progress</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Funnel label="Recipients" value={100} count={String(summary.total_recipients || 0)} />
            <Funnel label="Completed" value={Number(summary.response_rate_pct || 0)} count={String(summary.completed_count || 0)} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-base">Top issues</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {((summary.top_issues as string[]) || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No themes yet.</p>
            ) : ((summary.top_issues as string[]) || []).slice(0, 4).map((label) => (
              <Theme key={label} label={label} value={0} sentiment="mixed" />
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">NPS breakdown</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <Segment label="Promoters" nps={`${summary.nps_promoters_pct ?? 0}%`} rate={`${summary.nps_promoters ?? 0} responses`} />
            <Segment label="Passives" nps={`${summary.nps_passives_pct ?? 0}%`} rate={`${summary.nps_passives ?? 0} responses`} />
            <Segment label="Detractors" nps={`${summary.nps_detractors_pct ?? 0}%`} rate={`${summary.nps_detractors ?? 0} responses`} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <Sparkles className="size-4 text-primary" />
            <CardTitle className="text-base">AI recommended actions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {recommendations.length === 0 ? (
              <p className="text-muted-foreground">Recommendations appear after enough responses are analysed.</p>
            ) : recommendations.slice(0, 3).map((r, i) => (
              <Action key={i} text={String(r.text || "")} impact={String(r.impact || "Medium")} />
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CardTitle className="text-base">Anonymous response browser</CardTitle>
            <div className="flex gap-2">
              <div className="relative"><Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" /><Input placeholder="Search themes" className="h-9 w-48 pl-8" /></div>
              <Button variant="outline" size="sm" className="gap-1.5"><Filter className="size-4" /> Filter</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          {respondents.length === 0 ? (
            <p className="col-span-full text-sm text-muted-foreground">No anonymous responses to show yet.</p>
          ) : respondents.slice(0, 6).map((r, i) => (
            <Response key={i} quote={String(r.quote || "—")} score={String(r.recommend_score ?? "—")} theme={String(r.theme || "General")} />
          ))}
        </CardContent>
      </Card>

      <p className="text-center text-[11px] text-muted-foreground">Results are for one selected survey. Reports compare many surveys over time.</p>
    </div>
  );
}

function Kpi({ title, value, sub, icon, tone = "primary" }: { title: string; value: string; sub: string; icon: React.ReactNode; tone?: "primary" | "destructive" }) {
  return <Card><CardContent className="p-4"><div className={tone === "destructive" ? "text-destructive" : "text-primary"}>{icon}</div><p className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">{title}</p><p className="text-3xl font-semibold tracking-tight">{value}</p><p className="text-xs text-muted-foreground">{sub}</p></CardContent></Card>;
}

function QuestionCard({ title, type, rows }: { title: string; type: string; rows: readonly (readonly [string, number, string])[] }) {
  return <div className="rounded-xl border border-border bg-background p-4"><div className="mb-4 flex items-start justify-between gap-2"><p className="text-sm font-semibold">{title}</p><span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">{type}</span></div><div className="space-y-3">{rows.map(([label, value, tone]) => <BarLine key={label} label={label} value={value} tone={tone} />)}</div></div>;
}

function BarLine({ label, value, tone }: { label: string; value: number; tone: string }) {
  const cls = tone === "success" ? "bg-success" : tone === "warning" ? "bg-warning" : tone === "destructive" ? "bg-destructive" : "bg-info";
  return <div className="space-y-1"><div className="flex justify-between text-xs"><span className="text-muted-foreground">{label}</span><span className="tabular-nums">{value}%</span></div><div className="h-2 overflow-hidden rounded-full bg-border"><div className={`h-full rounded-full ${cls}`} style={{ width: `${value}%` }} /></div></div>;
}

function Funnel({ label, value, count }: { label: string; value: number; count: string }) {
  return <div><div className="mb-1 flex justify-between text-sm"><span>{label}</span><span className="text-muted-foreground">{count}</span></div><Progress value={value} className="h-2" /></div>;
}

function Theme({ label, value, sentiment }: { label: string; value: number; sentiment: string }) {
  return <div className="rounded-lg border border-border bg-background p-3"><div className="flex justify-between text-sm"><span className="font-medium">{label}</span><span className="tabular-nums text-muted-foreground">{value}%</span></div><p className="mt-1 text-xs capitalize text-muted-foreground">{sentiment} sentiment cluster</p></div>;
}

function Segment({ label, nps, rate }: { label: string; nps: string; rate: string }) {
  return <div className="flex items-center justify-between rounded-lg border border-border bg-background p-3 text-sm"><span>{label}</span><span className="text-right"><b>{nps}</b><br /><span className="text-xs text-muted-foreground">{rate}</span></span></div>;
}

function Action({ text, impact }: { text: string; impact: string }) {
  return <div className="rounded-lg border border-border bg-background p-3"><p>{text}</p><p className="mt-1 text-xs text-success">{impact} impact</p></div>;
}

function Response({ quote, score, theme }: { quote: string; score: string; theme: string }) {
  return <div className="rounded-xl border border-border bg-background p-4"><div className="mb-3 flex justify-between text-xs"><span className="rounded-full bg-accent px-2 py-0.5 text-accent-foreground">NPS {score}</span><span className="text-muted-foreground">{theme}</span></div><p className="text-sm leading-relaxed">"{quote}"</p></div>;
}
