import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  Download,
  Filter,
  MessageSquareText,
  Mic,
  Search,
  Sparkles,
  Star,
  TrendingUp,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { downloadAuthenticatedFile } from "@/lib/api";
import { logLaunchFlow } from "@/lib/launch-flow-log";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useServiceOrders, useSurveyResults } from "@/lib/queries";
import { cn } from "@/lib/utils";

type BreakdownGroup = { label: string; key: string; count: number; pct: number };
type AggregateBlock = {
  question: string;
  total: number;
  visualization?: string;
  breakdown?: BreakdownGroup[];
  responses: Array<{ answer: string; count: number }>;
  step_role?: string;
};
type OpenFeedback = {
  question?: string;
  answer_source?: string;
  transcript?: string | null;
  text?: string | null;
  transcription_status?: string | null;
  audio_url?: string | null;
  respondent_initials?: string;
  respondent_id?: string;
};
type Respondent = {
  id?: string;
  quote?: string | null;
  short_summary?: string | null;
  recommend_score?: number | string | null;
  theme?: string | null;
  sentiment_label?: string | null;
  status_label?: string;
  open_feedback?: OpenFeedback[];
  voice_responses?: OpenFeedback[];
  final_additional_feedback?: string | null;
  final_feedback_yes_no?: string | null;
};
type Recommendation = { title?: string; text?: string; impact?: string };
type TrendPoint = {
  week: string;
  response_rate_pct?: number;
  completed_count?: number;
  nps_score?: number | null;
  csat_pct?: number | null;
};

type Bar3 = { label: string; promoters: number; passives: number; detractors: number };
type QuestionView = {
  id: string;
  title: string;
  type: "NPS" | "CSAT" | "Rating" | "Open text" | "Choice";
  responses: number;
  avg?: string;
  delta?: number;
  bars?: Bar3[];
  rating?: { stars: number; pct: number }[];
};

const NPS_PIE_COLORS = {
  detractors: "#ef4444",
  passives: "#f59e0b",
  promoters: "#22c55e",
};

export const Route = createFileRoute("/_app/surveys/results")({
  validateSearch: (search: Record<string, unknown>) => ({
    orderId: typeof search.orderId === "string" ? search.orderId : undefined,
  }),
  head: () => ({ meta: [{ title: "Survey results — VoxBulk" }] }),
  component: SurveyResults,
});

function mapAggregateToQuestion(block: AggregateBlock): QuestionView {
  const total = block.total || 0;
  if (block.visualization === "sentiment_breakdown" && block.breakdown?.length) {
    const positive = block.breakdown.find((g) => g.key === "positive")?.pct ?? 0;
    const neutral = block.breakdown.find((g) => g.key === "neutral")?.pct ?? 0;
    const negative = block.breakdown.find((g) => g.key === "negative")?.pct ?? 0;
    const topScore = block.responses[0]?.answer;
    return {
      id: block.question,
      title: block.question,
      type: "NPS",
      responses: total,
      avg: topScore ? `Top: ${topScore}` : undefined,
      bars: [{ label: block.question, promoters: positive, passives: neutral, detractors: negative }],
    };
  }

  const numeric = block.responses.filter((r) => /^\d+$/.test(String(r.answer || "").trim()));
  if (numeric.length > 0 && numeric.length === block.responses.length) {
    const starBuckets = new Map<number, number>();
    for (const row of numeric) {
      const stars = Math.min(5, Math.max(1, Math.round(Number(row.answer) / 2)));
      starBuckets.set(stars, (starBuckets.get(stars) || 0) + row.count);
    }
    const rating = [5, 4, 3, 2, 1].map((stars) => ({
      stars,
      pct: total ? Math.round(((starBuckets.get(stars) || 0) / total) * 100) : 0,
    }));
    const avgNum = numeric.reduce((sum, r) => sum + Number(r.answer) * r.count, 0) / Math.max(1, total);
    return {
      id: block.question,
      title: block.question,
      type: "Rating",
      responses: total,
      avg: `${(avgNum / 2).toFixed(1)} / 5`,
      rating,
    };
  }

  return {
    id: block.question,
    title: block.question,
    type: block.step_role === "reason" || block.step_role === "final_feedback_text" ? "Open text" : "Choice",
    responses: total,
    avg: block.responses[0]?.answer,
  };
}

function SurveyResults() {
  const { orderId: searchOrderId } = Route.useSearch();
  const ordersQ = useServiceOrders("survey");
  const campaigns = React.useMemo(
    () => (ordersQ.data || []).map((o) => orderToCampaign(o, "survey")),
    [ordersQ.data],
  );
  const [selectedId, setSelectedId] = React.useState<string | undefined>(searchOrderId);
  const [tab, setTab] = React.useState("overview");
  const [themeSearch, setThemeSearch] = React.useState("");

  React.useEffect(() => {
    logLaunchFlow("[results:init]", {
      component: "SurveyResults",
      orderId: searchOrderId || null,
      selectedCampaignId: selectedId || null,
      survey_name: "",
      title: "",
    });
  }, []);

  React.useEffect(() => {
    if (searchOrderId) setSelectedId(searchOrderId);
  }, [searchOrderId]);

  React.useEffect(() => {
    if (searchOrderId) return;
    if (ordersQ.isLoading || ordersQ.isFetching) return;
    if (!selectedId && campaigns[0]) setSelectedId(campaigns[0].id);
  }, [searchOrderId, campaigns, selectedId, ordersQ.isLoading, ordersQ.isFetching]);

  const activeOrderId = searchOrderId || selectedId;
  const selected = campaigns.find((c) => c.id === activeOrderId);
  const resultsQ = useSurveyResults(activeOrderId || null);
  const payload = resultsQ.data || {};
  const summary = (payload.summary || {}) as Record<string, number | string | null | undefined>;
  const orderInfo = (payload.order || {}) as Record<string, string>;
  const aggregates = (payload.aggregates || []) as AggregateBlock[];
  const recommendations = (payload.recommendations || []) as Recommendation[];
  const respondents = (payload.respondents || []) as Respondent[];
  const voiceFeedback = (payload.voice_feedback || []) as OpenFeedback[];
  const weeklyTrend = (payload.weekly_trend || []) as TrendPoint[];
  const topIssues = (summary.top_issues as string[] | undefined) || [];

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

  const completed = Number(summary.completed_count || 0);
  const totalRecipients = Number(summary.total_recipients || 0);
  const responseRate = Number(summary.response_rate_pct || 0);
  const npsDisplay =
    summary.nps_score != null && summary.nps_score !== "" ? String(summary.nps_score) : "—";
  const csatPctValue =
    summary.average_satisfaction_5 != null
      ? Math.round((Number(summary.average_satisfaction_5) / 5) * 100)
      : summary.average_recommend_score != null
        ? Math.round((Number(summary.average_recommend_score) / 10) * 100)
        : null;
  const csatPct = csatPctValue != null ? `${csatPctValue}%` : "—";
  const csatSub =
    summary.average_satisfaction_5 != null
      ? `avg ${summary.average_satisfaction_5} / 5`
      : summary.average_recommend_score != null
        ? `avg score ${summary.average_recommend_score}`
        : "satisfaction";

  const sentimentCounts = (summary.sentiment_counts || {}) as Record<string, number>;
  const sentimentTotal = Object.values(sentimentCounts).reduce((sum, count) => sum + Number(count || 0), 0);

  const chartTrend =
    weeklyTrend.length > 0
      ? weeklyTrend.map((w) => ({
          week: w.week,
          nps: w.nps_score ?? 0,
          csat: w.csat_pct ?? csatPctValue ?? 0,
          responses: w.completed_count ?? 0,
        }))
      : completed > 0
        ? [
            {
              week: "This survey",
              nps: summary.nps_score != null && summary.nps_score !== "" ? Number(summary.nps_score) : 0,
              csat: csatPctValue ?? 0,
              responses: completed,
            },
          ]
        : [];

  const npsDelta =
    chartTrend.length >= 2 ? (chartTrend[chartTrend.length - 1]?.nps ?? 0) - (chartTrend[0]?.nps ?? 0) : undefined;
  const rateDelta =
    chartTrend.length >= 2
      ? (chartTrend[chartTrend.length - 1]?.csat ?? 0) - (chartTrend[0]?.csat ?? 0)
      : undefined;

  const npsDistribution = [
    { name: "Detractors", value: Number(summary.nps_detractors_pct || 0), color: NPS_PIE_COLORS.detractors },
    { name: "Passives", value: Number(summary.nps_passives_pct || 0), color: NPS_PIE_COLORS.passives },
    { name: "Promoters", value: Number(summary.nps_promoters_pct || 0), color: NPS_PIE_COLORS.promoters },
  ];

  const questionViews = aggregates.map(mapAggregateToQuestion);

  const voiceCards = voiceFeedback.map((row, i) => {
    const respondent = respondents.find((r) => r.id === row.respondent_id);
    const score = Number(respondent?.recommend_score ?? 0);
    const tone = score >= 9 ? "success" : score >= 7 ? "warning" : "destructive";
    return {
      id: `voice-${i}`,
      name: row.respondent_initials ? `Anonymous · ${row.respondent_initials}` : "Anonymous",
      score: score || "—",
      tone: tone as "success" | "destructive" | "warning",
      transcript: row.transcript || row.text || "—",
      reason: row.question || "Feedback",
      question: row.question || "Why this score?",
      audioUrl: row.audio_url,
      orderId: activeOrderId,
    };
  });

  const textComments = respondents
    .filter((r) => r.quote || r.final_additional_feedback || r.open_feedback?.some((f) => f.answer_source !== "voice"))
    .map((r) => ({
      quote: String(r.quote || r.final_additional_feedback || r.open_feedback?.[0]?.transcript || "").trim(),
      score: Number(r.recommend_score ?? 0) || 0,
      theme: String(r.theme || r.sentiment_label || "General"),
    }))
    .filter((r) => r.quote)
    .filter((r) => !themeSearch || r.quote.toLowerCase().includes(themeSearch.toLowerCase()) || r.theme.toLowerCase().includes(themeSearch.toLowerCase()));

  const themeItems =
    sentimentTotal > 0
      ? Object.entries(sentimentCounts)
          .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
          .slice(0, 4)
          .map(([label, count]) => ({
            label: label.charAt(0).toUpperCase() + label.slice(1),
            value: Math.round((Number(count) / sentimentTotal) * 100),
            sentiment: label === "negative" ? "negative" : label === "positive" ? "positive" : "mixed",
          }))
      : topIssues.length
        ? topIssues.slice(0, 4).map((label) => ({
            label,
            value: Math.round(100 / Math.min(topIssues.length, 4)),
            sentiment: label.toLowerCase().includes("negative")
              ? "negative"
              : label.toLowerCase().includes("positive")
                ? "positive"
                : "mixed",
          }))
        : recommendations.slice(0, 4).map((r) => ({
            label: String(r.title || r.text || "Theme").slice(0, 48),
            value: 0,
            sentiment: "mixed",
          }));

  const isLoading = resultsQ.isLoading;
  const hasError = resultsQ.isError;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Surveys · Results"
        title={orderInfo.survey_name || orderInfo.title || selected?.name || "Survey results"}
        description="Track week-over-week improvement, dive into each question, and read every voice and text comment."
        actions={
          <>
            <Button variant="outline" className="gap-1.5" onClick={() => void exportResults("pdf")} disabled={!activeOrderId}>
              <Download className="size-4" /> Export PDF
            </Button>
            <Button variant="outline" className="gap-1.5" onClick={() => void exportResults("csv")} disabled={!activeOrderId}>
              <Download className="size-4" /> Export CSV
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3">
        <div className="flex flex-wrap items-center gap-3">
          <Select value={activeOrderId} onValueChange={setSelectedId}>
            <SelectTrigger className="h-9 w-56">
              <SelectValue placeholder="Select survey" />
            </SelectTrigger>
            <SelectContent>
              {campaigns.map((c) => (
                <SelectItem key={c.id} value={c.id}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selected && <StatusBadge tone={selected.status} />}
          <span className="text-sm text-muted-foreground">
            {completed.toLocaleString()} / {totalRecipients.toLocaleString()} responses · {responseRate}% rate
          </span>
        </div>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="questions">Questions</TabsTrigger>
            <TabsTrigger value="responses">Responses</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {hasError ? (
        <Card className="border-destructive/40">
          <CardContent className="flex items-center gap-3 p-6 text-sm text-destructive">
            <AlertCircle className="size-5 shrink-0" />
            Could not load survey results. Try selecting another survey or refresh the page.
          </CardContent>
        </Card>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsContent value="overview" className="space-y-6">
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-28" />
              ))}
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-4">
              <Kpi title="NPS" value={npsDisplay} delta={npsDelta} sub="customer score" icon={<TrendingUp className="size-4" />} />
              <Kpi title="CSAT" value={csatPct} delta={rateDelta} sub={csatSub} icon={<Star className="size-4" />} />
              <Kpi title="Response rate" value={`${responseRate}%`} sub={`${completed} of ${totalRecipients}`} icon={<Users className="size-4" />} />
              <Kpi
                title="Detractor risk"
                value={`${summary.nps_detractors_pct ?? 0}%`}
                sub={`${summary.nps_detractors ?? 0} responses`}
                icon={<MessageSquareText className="size-4" />}
                tone="destructive"
                invertDelta
              />
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-base">Weekly improvement</CardTitle>
                    <p className="text-xs text-muted-foreground">NPS and CSAT over recent weeks</p>
                  </div>
                  {npsDelta != null && npsDelta !== 0 ? (
                    <Badge variant="secondary" className="gap-1">
                      {npsDelta > 0 ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
                      {npsDelta > 0 ? "+" : ""}
                      {npsDelta} NPS
                    </Badge>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="h-[280px]">
                {isLoading ? (
                  <Skeleton className="h-full w-full" />
                ) : chartTrend.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    Trend data appears after more surveys complete in your organisation.
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartTrend} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                      <defs>
                        <linearGradient id="results-nps" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#6366f1" stopOpacity={0.35} />
                          <stop offset="100%" stopColor="#6366f1" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="results-csat" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#14b8a6" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#14b8a6" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="week" stroke="#9ca3af" fontSize={12} />
                      <YAxis stroke="#9ca3af" fontSize={12} />
                      <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Area type="monotone" dataKey="nps" stroke="#6366f1" strokeWidth={2} fill="url(#results-nps)" name="NPS" />
                      <Area type="monotone" dataKey="csat" stroke="#14b8a6" strokeWidth={2} fill="url(#results-csat)" name="CSAT %" />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">NPS distribution</CardTitle>
                <p className="text-xs text-muted-foreground">Promoters · Passives · Detractors</p>
              </CardHeader>
              <CardContent className="h-[280px]">
                {isLoading ? (
                  <Skeleton className="h-full w-full" />
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={npsDistribution} dataKey="value" innerRadius={60} outerRadius={95} paddingAngle={3} stroke="#ffffff">
                        {npsDistribution.map((d) => (
                          <Cell key={d.name} fill={d.color} />
                        ))}
                      </Pie>
                      <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Response volume / week</CardTitle>
              </CardHeader>
              <CardContent className="h-[200px]">
                {isLoading ? (
                  <Skeleton className="h-full w-full" />
                ) : chartTrend.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-muted-foreground">No weekly data yet.</p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartTrend} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                      <XAxis dataKey="week" stroke="#9ca3af" fontSize={11} />
                      <YAxis stroke="#9ca3af" fontSize={11} />
                      <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 12 }} />
                      <Bar dataKey="responses" fill="#6366f1" radius={[6, 6, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">AI themes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {themeItems.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Themes appear after enough responses are analysed.</p>
                ) : (
                  themeItems.map((t) => <Theme key={t.label} label={t.label} value={t.value} sentiment={t.sentiment} />)
                )}
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
                ) : (
                  recommendations.slice(0, 3).map((r, i) => (
                    <Action key={i} text={String(r.text || r.title || "")} impact={String(r.impact || "Medium")} />
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="questions" className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
            Each question shows a positive / neutral / negative breakdown (or star distribution) so you can see exactly where wins or losses come from — not just one bar.
          </div>
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-48 w-full" />)
          ) : questionViews.length === 0 ? (
            <Card>
              <CardContent className="p-6 text-sm text-muted-foreground">No question aggregates yet.</CardContent>
            </Card>
          ) : (
            questionViews.map((q) => <QuestionBlock key={q.id} q={q} />)
          )}
        </TabsContent>

        <TabsContent value="responses" className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base flex items-center gap-2">
                    <Mic className="size-4 text-primary" />
                    Voice comments & transcripts
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Voice replies are transcribed automatically. Download audio when available.
                  </p>
                </div>
                <Badge variant="secondary">{voiceCards.length} voice replies</Badge>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {isLoading ? (
                <Skeleton className="col-span-full h-32" />
              ) : voiceCards.length === 0 ? (
                <p className="col-span-full text-sm text-muted-foreground">No voice comments captured yet.</p>
              ) : (
                voiceCards.map((v) => <VoiceCard key={v.id} v={v} />)
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <CardTitle className="text-base">Anonymous text responses</CardTitle>
                <div className="flex gap-2">
                  <div className="relative">
                    <Search className="absolute left-2 top-2.5 size-4 text-muted-foreground" />
                    <Input
                      placeholder="Search themes"
                      className="h-9 w-48 pl-8"
                      value={themeSearch}
                      onChange={(e) => setThemeSearch(e.target.value)}
                    />
                  </div>
                  <Button variant="outline" size="sm" className="gap-1.5" disabled>
                    <Filter className="size-4" /> Filter
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {isLoading ? (
                Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-32" />)
              ) : textComments.length === 0 ? (
                <p className="col-span-full text-sm text-muted-foreground">No text responses to show yet.</p>
              ) : (
                textComments.slice(0, 12).map((r, i) => <Response key={i} quote={r.quote} score={r.score} theme={r.theme} />)
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <p className="text-center text-[11px] text-muted-foreground">
        Results are for one selected survey. Reports compare many surveys over time.
      </p>
    </div>
  );
}

function Kpi({
  title,
  value,
  sub,
  icon,
  tone = "primary",
  delta,
  invertDelta,
}: {
  title: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  tone?: "primary" | "destructive";
  delta?: number;
  invertDelta?: boolean;
}) {
  const positive = invertDelta ? (delta ?? 0) < 0 : (delta ?? 0) >= 0;
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-4">
        <div className="flex items-center justify-between">
          <div className={cn("rounded-lg p-2", tone === "destructive" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary")}>
            {icon}
          </div>
          {delta !== undefined && delta !== 0 && (
            <span className={cn("flex items-center gap-0.5 text-xs font-medium", positive ? "text-success" : "text-destructive")}>
              {positive ? <ArrowUpRight className="size-3" /> : <ArrowDownRight className="size-3" />}
              {Math.abs(delta)}
              {title === "NPS" ? " pts" : "%"}
            </span>
          )}
        </div>
        <p className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">{title}</p>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function QuestionBlock({ q }: { q: QuestionView }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <CardTitle className="text-base">{q.title}</CardTitle>
              <Badge variant="outline">{q.type}</Badge>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{q.responses.toLocaleString()} responses</p>
          </div>
          {q.avg ? (
            <div className="text-right">
              <p className="text-2xl font-semibold tracking-tight">{q.avg}</p>
            </div>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {q.bars && <StackedBars bars={q.bars} />}
        {q.rating && <RatingDistribution rating={q.rating} />}
        {!q.bars && !q.rating ? (
          <p className="text-sm text-muted-foreground">Open-ended or choice responses — see the Responses tab for quotes.</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function StackedBars({ bars }: { bars: Bar3[] }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <LegendDot color="bg-success" label="Positive" />
        <LegendDot color="bg-warning" label="Neutral" />
        <LegendDot color="bg-destructive" label="Negative" />
      </div>
      {bars.map((b) => (
        <div key={b.label}>
          <div className="mb-1 flex justify-between text-sm">
            <span className="font-medium">{b.label}</span>
            <span className="tabular-nums text-muted-foreground">
              {b.promoters}% / {b.passives}% / {b.detractors}%
            </span>
          </div>
          <div className="flex h-3 overflow-hidden rounded-full bg-border">
            <div className="bg-success transition-all" style={{ width: `${b.promoters}%` }} title={`Positive ${b.promoters}%`} />
            <div className="bg-warning transition-all" style={{ width: `${b.passives}%` }} title={`Neutral ${b.passives}%`} />
            <div className="bg-destructive transition-all" style={{ width: `${b.detractors}%` }} title={`Negative ${b.detractors}%`} />
          </div>
        </div>
      ))}
    </div>
  );
}

function RatingDistribution({ rating }: { rating: { stars: number; pct: number }[] }) {
  return (
    <div className="space-y-2">
      {rating.map((r) => (
        <div key={r.stars} className="flex items-center gap-3">
          <div className="flex w-16 items-center gap-0.5 text-xs">
            {r.stars} <Star className="size-3 fill-warning text-warning" />
          </div>
          <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-border">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                r.stars >= 4 ? "bg-success" : r.stars === 3 ? "bg-warning" : "bg-destructive",
              )}
              style={{ width: `${r.pct}%` }}
            />
          </div>
          <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">{r.pct}%</span>
        </div>
      ))}
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={cn("size-2 rounded-full", color)} />
      {label}
    </span>
  );
}

function VoiceCard({
  v,
}: {
  v: {
    id: string;
    name: string;
    score: number | string;
    tone: "success" | "destructive" | "warning";
    transcript: string;
    reason: string;
    question: string;
    audioUrl?: string | null;
    orderId?: string;
  };
}) {
  const isLow = v.tone === "destructive";
  const downloadAudio = async () => {
    if (!v.orderId || !v.audioUrl) return;
    try {
      await downloadAuthenticatedFile(v.audioUrl, `voice-note-${Date.now()}.ogg`);
      toast.success("Audio downloaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not download audio");
    }
  };

  return (
    <div
      className={cn(
        "group rounded-xl border bg-background p-4 transition-shadow hover:shadow-md",
        isLow ? "border-destructive/30" : "border-success/30",
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-medium",
              isLow ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success",
            )}
          >
            Score {v.score}
          </span>
          <span className="text-[11px] text-muted-foreground">{v.name.split("·")[0]?.trim()}</span>
        </div>
        <Badge variant="outline" className="text-[10px]">
          {v.reason}
        </Badge>
      </div>
      <p className="mb-2 text-[11px] uppercase tracking-wider text-muted-foreground">Transcript · {v.question}</p>
      <p className="text-sm leading-relaxed">&ldquo;{v.transcript}&rdquo;</p>
      {v.audioUrl ? (
        <Button variant="outline" size="sm" className="mt-3 gap-1.5" onClick={() => void downloadAudio()}>
          <Mic className="size-3.5" /> Download audio
        </Button>
      ) : null}
    </div>
  );
}

function Theme({ label, value, sentiment }: { label: string; value: number; sentiment: string }) {
  const tone = sentiment === "positive" ? "bg-success" : sentiment === "negative" ? "bg-destructive" : "bg-warning";
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <div className="flex justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">{value}%</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-border">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${Math.min(100, value * 2)}%` }} />
      </div>
      <p className="mt-1 text-xs capitalize text-muted-foreground">{sentiment} sentiment</p>
    </div>
  );
}

function Action({ text, impact }: { text: string; impact: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <p>{text}</p>
      <p className="mt-1 text-xs text-success">{impact} impact</p>
    </div>
  );
}

function Response({ quote, score, theme }: { quote: string; score: number; theme: string }) {
  const tone = score >= 9 ? "success" : score >= 7 ? "warning" : "destructive";
  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="mb-3 flex justify-between text-xs">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 font-medium",
            tone === "success" && "bg-success/10 text-success",
            tone === "warning" && "bg-warning/10 text-warning",
            tone === "destructive" && "bg-destructive/10 text-destructive",
          )}
        >
          NPS {score || "—"}
        </span>
        <span className="text-muted-foreground">{theme}</span>
      </div>
      <p className="text-sm leading-relaxed">&ldquo;{quote}&rdquo;</p>
    </div>
  );
}
