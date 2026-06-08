import { createFileRoute } from "@tanstack/react-router";
import * as React from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertCircle,
  Download,
  MessageSquareText,
  Mic,
  Sparkles,
  TrendingUp,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { downloadAuthenticatedFile } from "@/lib/api";
import { logLaunchFlow } from "@/lib/launch-flow-log";
import { orderToCampaign } from "@/lib/mappers/orders";
import { useServiceOrders, useSurveyResults } from "@/lib/queries";

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
};

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "var(--color-success)",
  neutral: "var(--color-info)",
  negative: "var(--color-destructive)",
};

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
  const [tab, setTab] = React.useState("overview");

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
  const sentimentCounts = (summary.sentiment_counts || {}) as Record<string, number>;

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

  const npsDisplay =
    summary.nps_score != null && summary.nps_score !== ""
      ? String(summary.nps_score)
      : "—";
  const completed = Number(summary.completed_count || 0);
  const totalRecipients = Number(summary.total_recipients || 0);
  const responseRate = Number(summary.response_rate_pct || 0);
  const hasError = resultsQ.isError;
  const isLoading = resultsQ.isLoading;

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow="Surveys · Results"
        title={orderInfo.survey_name || orderInfo.title || selected?.name || "Survey results"}
        description="Response KPIs, question-level sentiment, voice transcripts, and weekly improvement trends for the selected survey."
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
            {completed.toLocaleString()} / {totalRecipients.toLocaleString()} responses ({responseRate}%)
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

      <Tabs value={tab} onValueChange={setTab} className="flex flex-col gap-6">
        <TabsContent value="overview" className="mt-0 flex flex-col gap-6">
          {isLoading ? (
            <div className="grid gap-4 md:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-24" />
              ))}
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-4">
              <Kpi title="NPS score" value={npsDisplay} sub={String(summary.nps_label || "customer score")} icon={<TrendingUp className="size-4" />} />
              <Kpi title="Responses" value={String(completed)} sub={`${responseRate}% response rate`} icon={<Users className="size-4" />} />
              <Kpi
                title="Voice feedback"
                value={String(summary.voice_feedback_count ?? voiceFeedback.length)}
                sub={`${summary.open_feedback_count ?? 0} open-text entries`}
                icon={<Mic className="size-4" />}
              />
              <Kpi
                title="Detractors"
                value={`${summary.nps_detractors_pct ?? 0}%`}
                sub={`${summary.nps_detractors ?? 0} low scores`}
                tone="destructive"
                icon={<Sparkles className="size-4" />}
              />
            </div>
          )}

          <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Weekly improvement trend</CardTitle>
              </CardHeader>
              <CardContent className="h-72">
                {isLoading ? (
                  <Skeleton className="h-full w-full" />
                ) : weeklyTrend.length === 0 ? (
                  <p className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    Trend data appears after more surveys complete in your organisation.
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={weeklyTrend} margin={{ left: -12, right: 8, top: 8 }}>
                      <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="week" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                      <YAxis stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                      <Tooltip
                        contentStyle={{
                          background: "var(--color-popover)",
                          border: "1px solid var(--color-border)",
                          borderRadius: 12,
                          fontSize: 12,
                        }}
                      />
                      <Area
                        dataKey="response_rate_pct"
                        name="Response rate %"
                        stroke="var(--color-primary)"
                        fill="var(--color-primary)"
                        fillOpacity={0.15}
                        strokeWidth={2}
                      />
                      <Area
                        dataKey="nps_score"
                        name="NPS (0–100)"
                        stroke="var(--color-success)"
                        fill="var(--color-success)"
                        fillOpacity={0.08}
                        strokeWidth={2}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Sentiment breakdown</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <SentimentBar label="Positive" value={Number(sentimentCounts.positive || 0)} total={completed} color="bg-success" />
                <SentimentBar label="Neutral" value={Number(sentimentCounts.neutral || 0)} total={completed} color="bg-info" />
                <SentimentBar label="Negative" value={Number(sentimentCounts.negative || 0)} total={completed} color="bg-destructive" />
                <div className="border-t border-border pt-3">
                  <Funnel label="Recipients" value={100} count={String(totalRecipients)} />
                  <Funnel label="Completed" value={responseRate} count={String(completed)} />
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">NPS breakdown</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Segment label="Promoters" nps={`${summary.nps_promoters_pct ?? 0}%`} rate={`${summary.nps_promoters ?? 0} responses`} />
                <Segment label="Passives" nps={`${summary.nps_passives_pct ?? 0}%`} rate={`${summary.nps_passives ?? 0} responses`} />
                <Segment label="Detractors" nps={`${summary.nps_detractors_pct ?? 0}%`} rate={`${summary.nps_detractors ?? 0} responses`} />
              </CardContent>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader className="flex flex-row items-center gap-2">
                <Sparkles className="size-4 text-primary" />
                <CardTitle className="text-base">Recommended actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {recommendations.length === 0 ? (
                  <p className="text-muted-foreground">Recommendations appear after enough responses are analysed.</p>
                ) : (
                  recommendations.slice(0, 4).map((r, i) => (
                    <Action
                      key={i}
                      title={String(r.title || r.text || "Improvement")}
                      text={String(r.text || r.title || "")}
                    />
                  ))
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="questions" className="mt-0">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Question-level results</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-48" />)
              ) : aggregates.length === 0 ? (
                <p className="col-span-full text-sm text-muted-foreground">No question aggregates yet — responses will appear as recipients complete the survey.</p>
              ) : (
                aggregates.map((q) => (
                  <QuestionCard key={q.question} block={q} />
                ))
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="responses" className="mt-0 flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Mic className="size-4" /> Voice & open-text feedback
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2">
              {isLoading ? (
                <Skeleton className="col-span-full h-32" />
              ) : voiceFeedback.length === 0 ? (
                <p className="col-span-full text-sm text-muted-foreground">No voice or open-text feedback captured yet.</p>
              ) : (
                voiceFeedback.map((row, i) => (
                  <VoiceFeedbackCard key={`${row.question}-${i}`} row={row} orderId={activeOrderId} />
                ))
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Respondent summaries</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {isLoading ? (
                Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-36" />)
              ) : respondents.length === 0 ? (
                <p className="col-span-full text-sm text-muted-foreground">No responses to show yet.</p>
              ) : (
                respondents
                  .filter((r) => String(r.status_label || "").toLowerCase() === "completed" || r.quote || r.open_feedback?.length)
                  .slice(0, 12)
                  .map((r, i) => <RespondentCard key={r.id || i} respondent={r} orderId={activeOrderId} />)
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <p className="text-center text-[11px] text-muted-foreground">
        Results reflect one selected survey. Cross-survey trends use your organisation&apos;s recent campaigns.
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
}: {
  title: string;
  value: string;
  sub: string;
  icon: React.ReactNode;
  tone?: "primary" | "destructive";
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className={tone === "destructive" ? "text-destructive" : "text-primary"}>{icon}</div>
        <p className="mt-3 text-xs uppercase tracking-wider text-muted-foreground">{title}</p>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground">{sub}</p>
      </CardContent>
    </Card>
  );
}

function QuestionCard({ block }: { block: AggregateBlock }) {
  if (block.visualization === "sentiment_breakdown" && block.breakdown?.length) {
    const chartData = block.breakdown.map((g) => ({
      name: g.label,
      pct: g.pct,
      count: g.count,
      key: g.key,
    }));
    return (
      <div className="rounded-xl border border-border bg-background p-4">
        <div className="mb-4 flex items-start justify-between gap-2">
          <p className="text-sm font-semibold">{block.question}</p>
          <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">
            {block.step_role || "Rating"}
          </span>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">{block.total} responses</p>
        <div className="mb-4 space-y-2">
          {block.breakdown.map((g) => (
            <SentimentBar
              key={g.key}
              label={g.label}
              value={g.count}
              total={block.total}
              color={g.key === "positive" ? "bg-success" : g.key === "neutral" ? "bg-info" : "bg-destructive"}
            />
          ))}
        </div>
        <div className="h-36">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ left: 4, right: 8, top: 0, bottom: 0 }}>
              <XAxis type="number" domain={[0, 100]} hide />
              <YAxis type="category" dataKey="name" width={72} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip formatter={(v: number) => [`${v}%`, "Share"]} />
              <Bar dataKey="pct" radius={[0, 4, 4, 0]} barSize={14}>
                {chartData.map((entry) => (
                  <Cell key={entry.key} fill={SENTIMENT_COLORS[entry.key] || "var(--color-primary)"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  const rows = block.responses.slice(0, 5).map((r) => {
    const pct = block.total ? Math.round((r.count / block.total) * 100) : 0;
    return [r.answer, pct] as const;
  });

  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="mb-4 flex items-start justify-between gap-2">
        <p className="text-sm font-semibold">{block.question}</p>
        <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">Choice</span>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">{block.total} responses</p>
      <div className="space-y-3">
        {rows.length === 0 ? (
          <p className="text-xs text-muted-foreground">No answers recorded.</p>
        ) : (
          rows.map(([label, value]) => <BarLine key={label} label={label} value={value} tone="info" />)
        )}
      </div>
    </div>
  );
}

function SentimentBar({
  label,
  value,
  total,
  color,
}: {
  label: string;
  value: number;
  total: number;
  color: string;
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">
          {value} ({pct}%)
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-border">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.max(pct, value > 0 ? 4 : 0)}%` }} />
      </div>
    </div>
  );
}

function BarLine({ label, value, tone }: { label: string; value: number; tone: string }) {
  const cls =
    tone === "success" ? "bg-success" : tone === "warning" ? "bg-warning" : tone === "destructive" ? "bg-destructive" : "bg-info";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">{value}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-border">
        <div className={`h-full rounded-full ${cls}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function Funnel({ label, value, count }: { label: string; value: number; count: string }) {
  return (
    <div className="mb-3 last:mb-0">
      <div className="mb-1 flex justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted-foreground">{count}</span>
      </div>
      <Progress value={value} className="h-2" />
    </div>
  );
}

function Segment({ label, nps, rate }: { label: string; nps: string; rate: string }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-background p-3 text-sm">
      <span>{label}</span>
      <span className="text-right">
        <b>{nps}</b>
        <br />
        <span className="text-xs text-muted-foreground">{rate}</span>
      </span>
    </div>
  );
}

function Action({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-lg border border-border bg-background p-3">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-muted-foreground">{text}</p>
    </div>
  );
}

function VoiceFeedbackCard({ row, orderId }: { row: OpenFeedback; orderId?: string }) {
  const source = row.answer_source === "voice" ? "Voice" : "Text";
  const transcript = row.transcript || row.text || "—";
  const downloadAudio = async () => {
    if (!orderId || !row.audio_url) return;
    try {
      await downloadAuthenticatedFile(row.audio_url, `voice-note-${Date.now()}.ogg`);
      toast.success("Audio downloaded");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not download audio");
    }
  };

  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="rounded-full bg-accent px-2 py-0.5 font-medium text-accent-foreground">{source}</span>
        {row.transcription_status ? <span className="text-muted-foreground">{row.transcription_status}</span> : null}
      </div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{row.question || "Feedback"}</p>
      <p className="text-sm leading-relaxed">{transcript}</p>
      {row.answer_source === "voice" && row.audio_url ? (
        <Button variant="outline" size="sm" className="mt-3 gap-1.5" onClick={() => void downloadAudio()}>
          <Mic className="size-3.5" /> Download audio
        </Button>
      ) : null}
    </div>
  );
}

function RespondentCard({ respondent, orderId }: { respondent: Respondent; orderId?: string }) {
  const quote =
    respondent.quote ||
    respondent.short_summary ||
    respondent.final_additional_feedback ||
    respondent.open_feedback?.[0]?.transcript ||
    "—";
  const voice = respondent.voice_responses?.[0];

  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="mb-3 flex justify-between text-xs">
        <span className="rounded-full bg-accent px-2 py-0.5 text-accent-foreground">
          Score {respondent.recommend_score ?? "—"}
        </span>
        <span className="text-muted-foreground">{respondent.sentiment_label || respondent.theme || "General"}</span>
      </div>
      <p className="text-sm leading-relaxed">&ldquo;{quote}&rdquo;</p>
      {voice?.answer_source === "voice" ? (
        <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
          <Mic className="size-3" /> Voice transcript
          {voice.transcription_status ? ` · ${voice.transcription_status}` : ""}
        </p>
      ) : null}
      {respondent.final_feedback_yes_no ? (
        <p className="mt-2 text-xs text-muted-foreground">Closing question: {respondent.final_feedback_yes_no}</p>
      ) : null}
    </div>
  );
}
